"""Ingest: transcription, not evidence.

Every test here is about a way the converter could quietly manufacture or
corrupt a number. The source files written into ``tmp_path`` are parser inputs
-- the same category as a CSV with a missing month in ``tests/conftest.py`` --
and no value in this file supports any claim about how many people visited a
shrine (brief 4).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
import yaml

from yatra import ingest
from yatra.errors import ConfigError

SOURCE = {
    "id": "probe_source",
    "publisher": "Probe Publisher",
    "title": "Parser fixture, not a real source",
    "url": "https://example.invalid/probe",
    "accessed": "2026-08-18",
}


def write_source(tmp_path: Path, rows: list[tuple[str, object]], name="src.csv") -> Path:
    """Write a monthly source file, plus a companion annual file beside it.

    An `annual` section is required in the ingest config, because the data
    contract will not load without `data/raw/annual.csv`. Its contents do not
    matter to most tests here -- reconciling the two is the contract's job, not
    the converter's -- so a minimal one is written alongside, letting each test
    below isolate a single failure mode.
    """
    path = tmp_path / name
    lines = ["month,pilgrims"] + [f"{m},{v}" for m, v in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    (tmp_path / "annual_companion.csv").write_text(
        "year,pilgrims\n2019,1000\n", encoding="utf-8"
    )
    return path


def config_for(path: Path, unit="absolute", month_format="%Y-%m", annual=None, source=None):
    raw = {
        "monthly": {
            "path": str(path),
            "columns": {"month": "month", "pilgrims": "pilgrims"},
            "month_format": month_format,
            "unit": unit,
        },
        "source": source or dict(SOURCE),
    }
    raw["annual"] = annual or {
        "path": str(Path(path).parent / "annual_companion.csv"),
        "columns": {"year": "year", "pilgrims": "pilgrims"},
        "unit": "absolute",
    }
    return raw


def load(tmp_path: Path, raw: dict) -> ingest.IngestConfig:
    path = tmp_path / "ingest.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    return ingest.load_config(path)


# --- units -----------------------------------------------------------------


def test_lakh_is_expanded_to_whole_people(tmp_path):
    """The trap the schema doc calls out: a column silently left in lakh."""
    source = write_source(tmp_path, [("2019-01", "8.5"), ("2019-02", "9.25")])
    config = load(tmp_path, config_for(source, unit="lakh"))
    monthly, _, _ = ingest.build(config)
    assert list(monthly["pilgrims"]) == [850_000, 925_000]
    assert monthly["pilgrims"].dtype == "int64"


def test_absolute_is_left_alone(tmp_path):
    source = write_source(tmp_path, [("2019-01", "850000")])
    config = load(tmp_path, config_for(source, unit="absolute"))
    monthly, _, _ = ingest.build(config)
    assert list(monthly["pilgrims"]) == [850_000]


def test_an_unknown_unit_is_refused(tmp_path):
    source = write_source(tmp_path, [("2019-01", "8.5")])
    with pytest.raises(ConfigError, match="unit"):
        load(tmp_path, config_for(source, unit="lakhs"))


def test_a_unit_that_leaves_fractional_people_is_refused(tmp_path):
    """8.523456 lakh is 852345.6 people, which means the unit or source is wrong."""
    source = write_source(tmp_path, [("2019-01", "8.523456")])
    config = load(tmp_path, config_for(source, unit="lakh"))
    with pytest.raises(ConfigError, match="fractional people"):
        ingest.build(config)


def test_the_conversion_is_recorded_in_the_source_note(tmp_path):
    """A converted series must carry its conversion, or it cannot be audited."""
    source = write_source(tmp_path, [("2019-01", "8.5")])
    config = load(tmp_path, config_for(source, unit="lakh"))
    _, _, sources = ingest.build(config)
    note = sources["probe_source"]["note"]
    assert "lakh" in note and "100,000" in note


# --- parsing ---------------------------------------------------------------


def test_thousands_separators_are_handled(tmp_path):
    source = write_source(tmp_path, [("2019-01", '"1,234,567"')])
    path = tmp_path / "src.csv"
    path.write_text('month,pilgrims\n2019-01,"1,234,567"\n', encoding="utf-8")
    config = load(tmp_path, config_for(path))
    monthly, _, _ = ingest.build(config)
    assert list(monthly["pilgrims"]) == [1_234_567]


def test_a_blank_cell_is_refused_not_filled(tmp_path):
    """The whole point. A hole stays a hole."""
    source = write_source(tmp_path, [("2019-01", "100"), ("2019-02", ""), ("2019-03", "120")])
    config = load(tmp_path, config_for(source))
    with pytest.raises(ConfigError, match="not.*numbers"):
        ingest.build(config)


def test_negative_counts_are_refused(tmp_path):
    source = write_source(tmp_path, [("2019-01", "-5")])
    config = load(tmp_path, config_for(source))
    with pytest.raises(ConfigError, match="[Nn]egative"):
        ingest.build(config)


def test_month_format_must_be_declared(tmp_path):
    source = write_source(tmp_path, [("2019-01", "100")])
    raw = config_for(source)
    del raw["monthly"]["month_format"]
    with pytest.raises(ConfigError, match="month_format"):
        load(tmp_path, raw)


def test_a_month_that_does_not_match_the_format_is_refused(tmp_path):
    """No silent dayfirst/monthfirst guessing."""
    source = write_source(tmp_path, [("Jan-2019", "100")])
    config = load(tmp_path, config_for(source, month_format="%Y-%m"))
    with pytest.raises(ConfigError, match="month_format"):
        ingest.build(config)


def test_an_alternative_declared_format_works(tmp_path):
    source = write_source(tmp_path, [("Jan-19", "100"), ("Feb-19", "110")])
    config = load(tmp_path, config_for(source, month_format="%b-%y"))
    monthly, _, _ = ingest.build(config)
    assert list(monthly["month"]) == ["2019-01", "2019-02"]


def test_duplicate_months_are_refused(tmp_path):
    source = write_source(tmp_path, [("2019-01", "100"), ("2019-01", "110")])
    config = load(tmp_path, config_for(source))
    with pytest.raises(ConfigError, match="Duplicate months"):
        ingest.build(config)


def test_a_missing_column_names_what_is_available(tmp_path):
    source = write_source(tmp_path, [("2019-01", "100")])
    raw = config_for(source)
    raw["monthly"]["columns"]["pilgrims"] = "yatris"
    config = load(tmp_path, raw)
    with pytest.raises(ConfigError, match="yatris"):
        ingest.build(config)


# --- gaps are preserved ----------------------------------------------------


def test_gaps_are_not_filled(tmp_path):
    """A month absent from the source stays absent from the output."""
    source = write_source(tmp_path, [("2019-01", "100"), ("2019-04", "130")])
    config = load(tmp_path, config_for(source))
    monthly, _, _ = ingest.build(config)
    assert list(monthly["month"]) == ["2019-01", "2019-04"]
    assert len(monthly) == 2


def test_the_summary_names_the_gap(tmp_path):
    source = write_source(tmp_path, [("2019-01", "100"), ("2019-04", "130")])
    config = load(tmp_path, config_for(source))
    monthly, annual, _ = ingest.build(config)
    text = ingest.summarise(monthly, annual)
    assert "GAPS" in text
    assert "2019-02" in text


def test_ingest_module_has_no_generative_vocabulary():
    """Mirrors the guard on contract.py. No fill path can appear here either."""
    path = Path(ingest.__file__)
    text = path.read_text(encoding="utf-8")
    for forbidden in ("fillna(", "interpolate(", "ffill(", "bfill(", "resample("):
        assert forbidden not in text, (
            f"ingest.py contains '{forbidden}'. Ingest transcribes; it must not "
            "be able to manufacture an observation."
        )


# --- citations -------------------------------------------------------------


def test_template_placeholders_are_refused(tmp_path):
    source = write_source(tmp_path, [("2019-01", "100")])
    bad = dict(SOURCE, publisher="CHANGE ME")
    with pytest.raises(ConfigError, match="placeholders"):
        load(tmp_path, config_for(source, source=bad))


def test_a_missing_citation_field_is_refused(tmp_path):
    source = write_source(tmp_path, [("2019-01", "100")])
    bad = {k: v for k, v in SOURCE.items() if k != "publisher"}
    with pytest.raises(ConfigError, match="missing"):
        load(tmp_path, config_for(source, source=bad))


def test_missing_config_points_at_inspect(tmp_path):
    with pytest.raises(ConfigError, match="--inspect"):
        ingest.load_config(tmp_path / "nope.yaml")


# --- end to end ------------------------------------------------------------


def test_written_files_satisfy_the_contract(tmp_path):
    """The real test: ingest output must load through contract.load unchanged."""
    from yatra import contract

    months = [f"2019-{m:02d}" for m in range(1, 13)] + [f"2020-{m:02d}" for m in range(1, 13)]
    values = [100 + i for i in range(24)]
    path = tmp_path / "src.csv"
    path.write_text(
        "month,pilgrims\n" + "\n".join(f"{m},{v}" for m, v in zip(months, values)) + "\n",
        encoding="utf-8",
    )

    annual_path = tmp_path / "annual.csv"
    annual_path.write_text(
        "year,pilgrims\n"
        f"2019,{sum(values[:12])}\n"
        f"2020,{sum(values[12:])}\n",
        encoding="utf-8",
    )

    raw = config_for(path)
    raw["annual"] = {
        "path": str(annual_path),
        "columns": {"year": "year", "pilgrims": "pilgrims"},
        "unit": "absolute",
    }
    config = load(tmp_path, raw)
    monthly, annual, sources = ingest.build(config)

    out = tmp_path / "raw"
    ingest.write(monthly, annual, sources, out)
    loaded = contract.load(out)
    assert len(loaded.monthly) == 24


def test_inspect_describes_a_file_and_prints_a_template(tmp_path):
    source = write_source(tmp_path, [("2019-01", "100")])
    text = ingest.inspect(source)
    assert "Columns:" in text
    assert "month" in text
    assert "unit:" in text
    assert "CHANGE ME" in text, (
        "The template must contain placeholders the user has to replace, and "
        "load_config must reject them if they do not."
    )


def test_a_missing_annual_section_is_refused_with_the_reason(tmp_path):
    """Found by an end-to-end run: ingest used to treat annual as optional.

    The contract requires data/raw/annual.csv, so a config without an annual
    section produced files that validate rejected immediately -- the happy path
    handed the user a broken result. Now it fails here, where the fix is.
    """
    source = write_source(tmp_path, [("2019-01", "100")])
    raw = config_for(source)
    del raw["annual"]
    with pytest.raises(ConfigError, match="contract requires"):
        load(tmp_path, raw)

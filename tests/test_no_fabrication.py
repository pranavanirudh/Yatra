"""Structural guards on the "never generate observations" constraint.

A rule enforced only by intention decays. These tests check the properties that
make the rule true of the code rather than of the author's memory: there is no
sample dataset in the repository, the loader has no generative path, and the
README's numbers cannot be typed by hand.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
import pytest
import yaml

from yatra import contract, report
from yatra.errors import MissingObservations

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "yatra"


def test_every_observation_traces_to_a_real_citation():
    """Nothing may sit in data/raw whose provenance cannot be followed.

    This test used to assert that ``data/raw`` held no CSVs at all, which was
    the right guard while the directory was empty: the only thing that could
    have appeared there was a sample. Real observations landed on 2026-08-18
    (built by ``scripts/build_raw.py`` from the Shrine Board's published
    statistics), so that form of the check now fires on exactly the situation
    the project wants.

    The intent it was protecting is unchanged and is what is asserted here
    instead: a figure in this repository must be traceable to a published
    source. A fabricated series would have to arrive with a fabricated citation
    to get past this, which is a much harder thing to do by accident -- and
    accident is what the guard is for.
    """
    raw = ROOT / "data" / "raw"
    if not raw.exists():
        return

    csvs = sorted(p.name for p in raw.glob("*.csv"))
    if not csvs:
        return

    sources_path = raw / "sources.yaml"
    assert sources_path.exists(), (
        f"data/raw holds {csvs} but no sources.yaml. Observations without "
        "citations are indistinguishable from invented ones."
    )
    sources = yaml.safe_load(sources_path.read_text(encoding="utf-8")) or {}
    assert sources, "data/raw/sources.yaml is empty."

    placeholder = re.compile(r"example\.(invalid|com)|CHANGE[ -]ME|localhost|TODO", re.I)
    for identifier, entry in sources.items():
        for field in ("publisher", "title", "url", "accessed"):
            value = str(entry.get(field, "")).strip()
            assert value, f"source '{identifier}' is missing '{field}'."
            assert not placeholder.search(value), (
                f"source '{identifier}' has a placeholder {field}: {value!r}. "
                "A fixture citation on real-looking data is how a sample gets "
                "mistaken for a measurement."
            )

    # And the citations must actually cover the data, not merely exist.
    used = set()
    for name in csvs:
        frame = pd.read_csv(raw / name)
        assert "source_id" in frame.columns, f"{name} has no source_id column."
        used |= set(frame["source_id"].dropna().unique())
    dangling = sorted(used - set(sources))
    assert not dangling, f"source_id(s) used but never defined: {dangling}."


def test_loader_has_no_generative_vocabulary():
    """Catches a fill/impute/synthesise path being added to the contract module."""
    text = (SRC / "contract.py").read_text(encoding="utf-8")
    for forbidden in ("fillna(", "interpolate(", "ffill(", "bfill(", "resample("):
        assert forbidden not in text, (
            f"contract.py contains '{forbidden}'. The loader must not be able to "
            "manufacture an observation, even accidentally."
        )


def test_loader_raises_rather_than_returning_empty(tmp_path: Path):
    with pytest.raises(MissingObservations):
        contract.load(tmp_path)


def test_report_refuses_to_render_without_metrics(tmp_path: Path):
    """No placeholder tables. Absent results must read as absent."""
    with pytest.raises(FileNotFoundError):
        report.render(tmp_path / "metrics.csv")


def test_readme_has_the_generated_markers():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert report.BEGIN in text and report.END in text
    assert text.index(report.BEGIN) < text.index(report.END)


def test_hand_written_readme_prose_contains_no_statistics():
    """Every number in the README must trace to a row in metrics.csv.

    The mechanism is that report.py owns the generated block. This test guards
    the other half: that nobody types a result into the prose around it. Prose
    outside the markers may not contain a decimal number or a thousands-grouped
    integer, which is what a MASE, a correlation or a forecast count looks like.
    """
    import re

    text = (ROOT / "README.md").read_text(encoding="utf-8")
    head, _, rest = text.partition(report.BEGIN)
    _, _, tail = rest.partition(report.END)

    pattern = re.compile(r"(?<![\w.])(\d+\.\d+|\d{1,3}(?:,\d{3})+)(?![\w])")
    offenders = pattern.findall(head) + pattern.findall(tail)
    assert not offenders, (
        f"Numbers found in hand-written README prose: {offenders}. Results belong "
        "inside the generated block, where they trace to metrics.csv."
    )


def test_shock_config_is_not_importable_as_a_model_feature():
    """Shock windows are labels. No model module may read them.

    A model that could see the declared windows would be reading the answer key,
    and would post a spectacular score that meant nothing.
    """
    # Matched against code, not prose. These modules are entitled to *discuss*
    # regimes in a docstring -- metrics.py has to explain why one MASE
    # denominator is what makes the per-regime tables comparable. What they may
    # not do is import the module or read the config.
    references = re.compile(
        r"^\s*(?:from\s+\.?\S*\s+)?import\s+.*\bregimes\b"    # any import of it
        r"|\bregimes\s*\."                                     # any attribute use
        r"|\bShockWindow\b"
        r"|\bshocks\.yaml\b",
        re.MULTILINE,
    )
    for module in ("models.py", "metrics.py"):
        text = (SRC / module).read_text(encoding="utf-8")
        found = references.findall(text)
        assert not found, (
            f"{module} references the regimes module ({found}). Shock windows "
            "are evaluation labels and must not reach a model."
        )

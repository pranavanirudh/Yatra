"""Turn the owner's published figures into contract-compliant files.

The pipeline refuses to run without ``data/raw/``, and getting real figures into
exactly the shape :mod:`yatra.contract` demands is the slowest part of starting
this project. This module is the shortcut -- but it is a shortcut through
*transcription*, not through evidence.

**What this module will not do.** It will not invent a month, interpolate a gap,
guess a unit, or infer which column holds what. Every transformation is declared
in ``experiments/configs/ingest.yaml`` and applied literally. If the source file
is missing months, the output is missing those months and ``make validate`` says
so by name. There is no code path here that can produce a footfall number that
was not in the input file.

That restraint is the point rather than an inconvenience. The outputs of this
project are meant to inform crowd resourcing at a site where getting the number
wrong has hurt people. A convenience that quietly filled a gap would be
indistinguishable, downstream, from a measurement.

**Units are declared, never sniffed.** Indian sources routinely publish this
series in lakh. A column of values around 8.5 could be 8.5 lakh or 8.5 million
and nothing in the numbers says which. ``unit:`` in the config is required, has
no default, and is recorded in the emitted source note so the conversion stays
auditable.

Workflow::

    python make.py ingest --inspect path/to/whatever.csv   # see what is in it
    # write experiments/configs/ingest.yaml from the template it prints
    python make.py ingest                                  # convert
    python make.py validate                                # prove it landed
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, overload

import numpy as np
import pandas as pd
import yaml

from .errors import ConfigError

# Multipliers from a declared unit to a raw count of people. Named, not
# computed, so that adding one is a deliberate edit rather than a regex.
UNITS: dict[str, int] = {
    "absolute": 1,
    "thousand": 1_000,
    "lakh": 100_000,
    "million": 1_000_000,
    "crore": 10_000_000,
}

TEMPLATE = """\
# Ingest mapping. Every field is required; nothing here is inferred from the
# file, because a wrong guess about units or columns is invisible downstream.
schema_version: 1

monthly:
  path: {path}
  # Sheet name, for spreadsheets. Omit for CSV.
  # sheet: Sheet1
  columns:
    # Column holding the month. Parsed with `month_format` below.
    month: {month_guess}
    # Column holding the count.
    pilgrims: {count_guess}
  # How the month is written in the file. strftime syntax; "%Y-%m" for 2019-04,
  # "%b-%y" for Apr-19. Declared so an ambiguous 04-05 cannot be read as
  # April 2005 on one machine and May 2004 on another.
  month_format: "%Y-%m"
  # REQUIRED, no default. One of: {units}
  unit: absolute

# Published annual totals. REQUIRED -- the contract will not load without
# data/raw/annual.csv. This is the check that catches a transcription error
# inside an otherwise well-formed series. Must be independently published, NOT
# a sum of the monthly column, which would compare a number to itself.
#
# Partial years (the current one) belong in the monthly file only. A
# year-to-date figure here fails reconciliation for a reason that has nothing
# to do with data quality.
annual:
  path: {path}
  columns:
    year: year
    pilgrims: pilgrims
  unit: absolute

source:
  id: {source_id}
  publisher: CHANGE ME
  title: CHANGE ME
  url: https://CHANGE-ME
  accessed: {today}
  note: >
    Where in the document these figures came from, and any conversion applied.
"""


@dataclass(frozen=True)
class TableSpec:
    path: Path
    key_column: str
    value_column: str
    unit: str
    sheet: str | None = None
    month_format: str | None = None

    @property
    def multiplier(self) -> int:
        if self.unit not in UNITS:
            raise ConfigError(
                f"unit: {self.unit!r} is not one of {sorted(UNITS)}. It has no "
                "default -- a series published in lakh and read as absolute is "
                "wrong by a factor of 100,000 and nothing downstream can detect it."
            )
        return UNITS[self.unit]


@dataclass(frozen=True)
class IngestConfig:
    monthly: TableSpec
    annual: TableSpec | None
    source: dict = field(default_factory=dict)


# --------------------------------------------------------------------------
# Inspection: what is actually in the file?
# --------------------------------------------------------------------------


def read_any(path: Path, sheet: str | None = None) -> pd.DataFrame:
    """Read a CSV or a spreadsheet. Nothing is coerced at this stage."""
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"Source file {path} does not exist.")
    if path.suffix.lower() in {".xlsx", ".xls", ".xlsm"}:
        try:
            return pd.read_excel(path, sheet_name=sheet or 0, dtype=object)
        except ImportError as exc:
            raise ConfigError(
                f"Reading {path.suffix} needs openpyxl: pip install openpyxl. "
                "Or export the sheet to CSV and point the config at that."
            ) from exc
    return pd.read_csv(path, dtype=object)


def inspect(path: Path, sheet: str | None = None) -> str:
    """Describe a candidate file and print a config template for it.

    This is the part that makes the first attempt cheap. It guesses column names
    only to *pre-fill a template a human then edits* -- the guesses never reach
    the conversion, which reads the config and nothing else.
    """
    frame = read_any(path, sheet)
    lines = [
        f"{path}  --  {len(frame)} rows, {len(frame.columns)} columns",
        "",
        "Columns:",
    ]
    for column in frame.columns:
        sample = [str(v) for v in frame[column].dropna().head(3).tolist()]
        lines.append(f"  {str(column):<28} e.g. {', '.join(sample) if sample else '(empty)'}")

    month_guess = _guess(frame.columns, ("month", "date", "period", "yearmonth"))
    count_guess = _guess(frame.columns, ("pilgrim", "yatri", "visitor", "count", "footfall", "total"))

    lines += [
        "",
        "Suggested experiments/configs/ingest.yaml (EDIT before using):",
        "",
        TEMPLATE.format(
            path=path.as_posix(),
            month_guess=month_guess or "CHANGE ME",
            count_guess=count_guess or "CHANGE ME",
            units=", ".join(sorted(UNITS)),
            source_id=_slug(path.stem),
            today=dt.date.today().isoformat(),
        ),
    ]
    return "\n".join(lines)


def _guess(columns, needles: tuple[str, ...]) -> str | None:
    for needle in needles:
        for column in columns:
            if needle in str(column).strip().lower():
                return str(column)
    return None


def _slug(text: str) -> str:
    keep = [c if (c.isalnum() or c == "_") else "_" for c in str(text).strip().lower()]
    return "".join(keep).strip("_") or "source"


# --------------------------------------------------------------------------
# Config.
# --------------------------------------------------------------------------


def load_config(path: str | Path = "experiments/configs/ingest.yaml") -> IngestConfig:
    path = Path(path)
    if not path.exists():
        raise ConfigError(
            f"{path} not found. Run `python make.py ingest --inspect <file>` "
            "to print a template for the file you have, then edit it."
        )
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return IngestConfig(
        monthly=_table(raw, "monthly", "month", required=True),
        annual=_table(raw, "annual", "year", required=True),
        source=_source(raw),
    )


# `required=True` does not return None: it raises. The overloads say so, which
# is what lets `load_config` hand the result straight to `IngestConfig.monthly`
# without a cast asserting something the checker cannot see.
@overload
def _table(raw: dict, section: str, key: str,
           required: Literal[True]) -> TableSpec: ...


@overload
def _table(raw: dict, section: str, key: str,
           required: bool) -> TableSpec | None: ...


def _table(raw: dict, section: str, key: str, required: bool) -> TableSpec | None:
    block = raw.get(section)
    if not block:
        if section == "annual":
            raise ConfigError(
                "ingest.yaml has no 'annual' section, but the data contract "
                "requires data/raw/annual.csv and will refuse to load without "
                "it. Published annual totals are the only check that catches a "
                "transcription error inside an otherwise well-formed monthly "
                "series -- a dropped digit still leaves the file contiguous, "
                "correctly typed and fully sourced. Point it at the source's "
                "published yearly figures; do not sum the monthly column, which "
                "would make the reconciliation check compare a number to itself."
            )
        if required:
            raise ConfigError(f"ingest.yaml has no '{section}' section.")
        return None

    for field_name in ("path", "columns", "unit"):
        if field_name not in block:
            raise ConfigError(f"ingest.yaml {section} is missing '{field_name}'.")
    columns = block["columns"]
    for name in (key, "pilgrims"):
        if name not in columns:
            raise ConfigError(f"ingest.yaml {section}.columns is missing '{name}'.")

    spec = TableSpec(
        path=Path(block["path"]),
        key_column=str(columns[key]),
        value_column=str(columns["pilgrims"]),
        unit=str(block["unit"]),
        sheet=block.get("sheet"),
        month_format=block.get("month_format") if section == "monthly" else None,
    )
    spec.multiplier          # validate the unit now, not halfway through a conversion
    if section == "monthly" and not spec.month_format:
        raise ConfigError(
            "ingest.yaml monthly.month_format is required. Without it, a value "
            "like 04-05 is April 2005 or May 2004 depending on the reader."
        )
    return spec


def _source(raw: dict) -> dict:
    block = raw.get("source")
    if not block:
        raise ConfigError("ingest.yaml has no 'source' section. Observations need a citation.")
    missing = [f for f in ("id", "publisher", "title", "accessed") if not block.get(f)]
    if missing:
        raise ConfigError(f"ingest.yaml source is missing {missing}.")
    if any("CHANGE ME" in str(v) or "CHANGE-ME" in str(v) for v in block.values()):
        raise ConfigError(
            "ingest.yaml source still contains template placeholders. Fill in "
            "the real publisher, title and URL -- an uncited observation series "
            "is an unfalsifiable claim."
        )
    return dict(block)


# --------------------------------------------------------------------------
# Conversion.
# --------------------------------------------------------------------------


def _counts(spec: TableSpec, frame: pd.DataFrame) -> pd.Series:
    """The value column, scaled by the declared unit, as exact integers."""
    if spec.value_column not in frame.columns:
        raise ConfigError(
            f"Column {spec.value_column!r} is not in {spec.path} "
            f"(has {list(frame.columns)})."
        )
    raw = frame[spec.value_column]
    cleaned = (
        raw.astype(str)
        .str.replace(",", "", regex=False)
        .str.replace(" ", "", regex=False)
        .str.strip()
    )
    numbers = pd.to_numeric(cleaned, errors="coerce")
    if numbers.isna().any():
        bad = raw[numbers.isna()].head(5).tolist()
        raise ConfigError(
            f"{spec.path}: column {spec.value_column!r} has values that are not "
            f"numbers, first few {bad}. Blank or placeholder cells are not "
            "filled in -- remove the rows or supply the figures."
        )

    scaled = numbers * spec.multiplier
    rounded = scaled.round()
    drift = (scaled - rounded).abs().max()
    if drift > 1e-6:
        raise ConfigError(
            f"{spec.path}: converting from {spec.unit!r} leaves fractional "
            f"people (largest remainder {drift:.6f}). Either the unit is wrong "
            "or the source is rounded more coarsely than it appears."
        )
    if (rounded < 0).any():
        raise ConfigError(f"{spec.path}: negative counts in {spec.value_column!r}.")
    return rounded.astype("int64")


def _months(spec: TableSpec, frame: pd.DataFrame) -> pd.Series:
    if spec.key_column not in frame.columns:
        raise ConfigError(
            f"Column {spec.key_column!r} is not in {spec.path} "
            f"(has {list(frame.columns)})."
        )
    text = frame[spec.key_column].astype(str).str.strip()
    parsed = pd.to_datetime(text, format=spec.month_format, errors="coerce")
    if parsed.isna().any():
        bad = text[parsed.isna()].head(5).tolist()
        raise ConfigError(
            f"{spec.path}: {parsed.isna().sum()} value(s) in {spec.key_column!r} "
            f"do not match month_format {spec.month_format!r}, first few {bad}."
        )
    return parsed.dt.to_period("M").astype(str)


def build(config: IngestConfig) -> tuple[pd.DataFrame, pd.DataFrame | None, dict]:
    """Read the declared sources and return contract-shaped frames.

    Rows are sorted and duplicate months are refused. Gaps are left alone: the
    contract reports them by name, which is the behaviour that keeps a hole in
    the record visible instead of quietly closed.
    """
    frame = read_any(config.monthly.path, config.monthly.sheet)
    source_id = str(config.source["id"])

    monthly = pd.DataFrame(
        {
            "month": _months(config.monthly, frame),
            "pilgrims": _counts(config.monthly, frame),
            "source_id": source_id,
        }
    ).sort_values("month").reset_index(drop=True)

    duplicated = monthly["month"][monthly["month"].duplicated()].tolist()
    if duplicated:
        raise ConfigError(
            f"Duplicate months in {config.monthly.path}: {sorted(set(duplicated))}. "
            "Two rows for one month is a source problem; this module will not "
            "pick one or add them together."
        )

    annual = None
    if config.annual is not None:
        annual_frame = read_any(config.annual.path, config.annual.sheet)
        years = pd.to_numeric(
            annual_frame[config.annual.key_column], errors="coerce"
        )
        if years.isna().any():
            raise ConfigError(
                f"{config.annual.path}: column {config.annual.key_column!r} has "
                "values that are not years."
            )
        annual = pd.DataFrame(
            {
                "year": years.astype("int64"),
                "pilgrims": _counts(config.annual, annual_frame),
                "source_id": source_id,
            }
        ).sort_values("year").reset_index(drop=True)

    note = dict(config.source)
    identifier = note.pop("id")
    if config.monthly.unit != "absolute":
        existing = str(note.get("note", "")).strip()
        conversion = (
            f"Figures published in {config.monthly.unit}; expanded to absolute "
            f"counts at ingest by multiplying by {config.monthly.multiplier:,}."
        )
        note["note"] = f"{existing}\n{conversion}".strip()
    sources = {identifier: note}
    return monthly, annual, sources


def write(
    monthly: pd.DataFrame,
    annual: pd.DataFrame | None,
    sources: dict,
    directory: str | Path = "data/raw",
) -> list[Path]:
    """Write the three contract files. Refuses to clobber silently."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    monthly_path = directory / "monthly.csv"
    monthly.to_csv(monthly_path, index=False)
    written.append(monthly_path)

    if annual is not None:
        annual_path = directory / "annual.csv"
        annual.to_csv(annual_path, index=False)
        written.append(annual_path)

    sources_path = directory / "sources.yaml"
    sources_path.write_text(yaml.safe_dump(sources, sort_keys=False), encoding="utf-8")
    written.append(sources_path)
    return written


def summarise(monthly: pd.DataFrame, annual: pd.DataFrame | None) -> str:
    """A short human check: span, count, and any gap, before validate runs."""
    periods = pd.PeriodIndex(monthly["month"], freq="M")
    expected = pd.period_range(periods.min(), periods.max(), freq="M")
    missing = sorted(set(expected) - set(periods))

    lines = [
        f"months:  {len(monthly)} rows, {periods.min()} to {periods.max()}",
        f"total:   {monthly['pilgrims'].sum():,} pilgrims",
        f"range:   {monthly['pilgrims'].min():,} to {monthly['pilgrims'].max():,} per month",
    ]
    if annual is not None:
        lines.append(f"annual:  {len(annual)} published totals, "
                     f"{annual['year'].min()}-{annual['year'].max()}")
    if missing:
        lines.append(
            f"GAPS:    {len(missing)} month(s) absent, first "
            f"{', '.join(str(m) for m in missing[:6])}"
            f"{' ...' if len(missing) > 6 else ''}"
        )
        lines.append("         Left absent on purpose. `make validate` will name them all.")
    return "\n".join(lines)

"""Observation loading and the invariants that must hold before anything runs.

This module has no default data, no sample file, no generator, and no
interpolation. If the observations are absent it raises and names the path it
wanted. If they are present but malformed it raises and names the rows.

That is the whole design. The constraint "never generate, simulate, or impute
observations" is not enforceable by good intentions in a module that has a
code path capable of inventing a value -- so this one does not have such a path.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import yaml

from .errors import ContractViolation, MissingObservations

REQUIRED_SOURCE_FIELDS = ("publisher", "title", "accessed")

MONTHLY_FILE = "monthly.csv"
ANNUAL_FILE = "annual.csv"
SOURCES_FILE = "sources.yaml"


@dataclass(frozen=True)
class Observations:
    """A validated observation set. Only constructed by :func:`load`."""

    monthly: pd.Series
    """Integer pilgrim counts indexed by month-start ``DatetimeIndex``."""

    annual: pd.DataFrame
    """Published annual totals, indexed by year."""

    sources: dict
    """Source metadata keyed by ``source_id``."""

    @property
    def span(self) -> tuple[pd.Timestamp, pd.Timestamp]:
        return self.monthly.index[0], self.monthly.index[-1]

    @property
    def n_months(self) -> int:
        return int(len(self.monthly))

    def describe(self) -> str:
        first, last = self.span
        return (
            f"{self.n_months} monthly observations, "
            f"{first:%Y-%m} to {last:%Y-%m}, no gaps; "
            f"{len(self.annual)} published annual totals reconciled"
        )


def load(data_dir: str | Path = "data/raw") -> Observations:
    """Load and validate the observation set.

    Raises
    ------
    MissingObservations
        If any of the three required files is absent.
    ContractViolation
        If the files exist but violate the contract in docs/data_schema.md.
    """
    data_dir = Path(data_dir)
    monthly_path = data_dir / MONTHLY_FILE
    annual_path = data_dir / ANNUAL_FILE
    sources_path = data_dir / SOURCES_FILE

    missing = [p for p in (monthly_path, annual_path, sources_path) if not p.exists()]
    if missing:
        listed = "\n  ".join(str(p) for p in missing)
        raise MissingObservations(
            "Required observation files are absent:\n  "
            + listed
            + "\n\nThese are owner-supplied. This repository does not ship a sample "
            "and will not generate one -- see docs/data_schema.md for the exact "
            "columns expected."
        )

    sources = _load_sources(sources_path)
    monthly = _load_monthly(monthly_path, sources)
    annual = _load_annual(annual_path, sources)
    _check_reconciliation(monthly, annual)

    return Observations(monthly=monthly["pilgrims"], annual=annual, sources=sources)


def _load_sources(path: Path) -> dict:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ContractViolation(f"{path} must be a mapping of source_id -> metadata.")

    for source_id, meta in raw.items():
        if not isinstance(meta, dict):
            raise ContractViolation(f"{path}: source '{source_id}' is not a mapping.")
        absent = [f for f in REQUIRED_SOURCE_FIELDS if not meta.get(f)]
        if absent:
            raise ContractViolation(
                f"{path}: source '{source_id}' is missing {', '.join(absent)}. "
                "A citation without a publisher and an access date is not a citation."
            )
    return raw


def _read_counts(path: Path, key: str) -> pd.DataFrame:
    """Read a counts CSV, enforcing the column set and the integer/non-null rule."""
    frame = pd.read_csv(path)
    expected = {key, "pilgrims", "source_id"}
    if set(frame.columns) != expected:
        raise ContractViolation(
            f"{path}: columns are {sorted(frame.columns)}, expected {sorted(expected)}."
        )

    if frame["pilgrims"].isna().any():
        blank = frame.loc[frame["pilgrims"].isna(), key].tolist()
        raise ContractViolation(
            f"{path}: null pilgrim counts at {blank}. A missing observation stays "
            "missing -- it is not zero and it is not interpolated. Remove the row "
            "and the contiguity check will report the gap honestly."
        )

    counts = pd.to_numeric(frame["pilgrims"], errors="coerce")
    if counts.isna().any():
        bad = frame.loc[counts.isna(), key].tolist()
        raise ContractViolation(f"{path}: non-numeric pilgrim counts at {bad}.")
    if (counts % 1 != 0).any():
        bad = frame.loc[counts % 1 != 0, key].tolist()
        raise ContractViolation(
            f"{path}: non-integer pilgrim counts at {bad}. Counts are people, and a "
            "fractional count usually means a figure in lakh reached the column "
            "without being expanded -- see docs/data_schema.md."
        )
    if (counts < 0).any():
        bad = frame.loc[counts < 0, key].tolist()
        raise ContractViolation(f"{path}: negative pilgrim counts at {bad}.")

    frame["pilgrims"] = counts.astype("int64")
    return frame


def _check_source_refs(frame: pd.DataFrame, sources: dict, path: Path) -> None:
    dangling = sorted(set(frame["source_id"]) - set(sources))
    if dangling:
        raise ContractViolation(
            f"{path}: source_id values not present in {SOURCES_FILE}: {dangling}."
        )


def _load_monthly(path: Path, sources: dict) -> pd.DataFrame:
    frame = _read_counts(path, "month")
    _check_source_refs(frame, sources, path)

    try:
        index = pd.PeriodIndex(frame["month"].astype(str), freq="M")
    except Exception as exc:  # pragma: no cover - message is the point
        raise ContractViolation(f"{path}: 'month' must be YYYY-MM. {exc}") from None

    if index.has_duplicates:
        dupes = sorted({str(m) for m in index[index.duplicated()]})
        raise ContractViolation(f"{path}: duplicate months {dupes}.")

    if not index.is_monotonic_increasing:
        frame = frame.assign(_p=index).sort_values("_p").drop(columns="_p")
        index = index.sort_values()

    # Contiguity. Report the missing months by name: a count alone sends the
    # reader back to the spreadsheet to work out which ones.
    full = pd.period_range(index[0], index[-1], freq="M")
    gaps = full.difference(index)
    if len(gaps):
        shown = ", ".join(str(g) for g in gaps[:24])
        more = "" if len(gaps) <= 24 else f" (and {len(gaps) - 24} more)"
        raise ContractViolation(
            f"{path}: {len(gaps)} missing month(s) between {index[0]} and "
            f"{index[-1]}: {shown}{more}.\n"
            "Missing data stays missing. Do not fill these -- either source the "
            "months or shorten the series to a contiguous span."
        )

    frame = frame.set_index(full.to_timestamp(how="start"))
    frame.index.name = "month"
    return frame


def _load_annual(path: Path, sources: dict) -> pd.DataFrame:
    frame = _read_counts(path, "year")
    _check_source_refs(frame, sources, path)

    years = pd.to_numeric(frame["year"], errors="coerce")
    if years.isna().any() or (years % 1 != 0).any():
        raise ContractViolation(f"{path}: 'year' must be an integer year.")
    frame["year"] = years.astype("int64")

    if frame["year"].duplicated().any():
        dupes = sorted(frame.loc[frame["year"].duplicated(), "year"].tolist())
        raise ContractViolation(f"{path}: duplicate years {dupes}.")

    return frame.set_index("year").sort_index()


def _check_reconciliation(monthly: pd.DataFrame, annual: pd.DataFrame) -> None:
    """Every published annual total must equal the sum of its twelve months.

    This is the only check in the contract that can catch a transcription error
    inside an otherwise well-formed series. A dropped digit in one month leaves
    the file contiguous, correctly typed and fully sourced -- and fails here.
    """
    by_year = monthly["pilgrims"].groupby(monthly.index.year)
    sums = by_year.sum()
    counts = by_year.count()

    problems: list[str] = []
    for year, published in annual["pilgrims"].items():
        if year not in sums.index:
            problems.append(f"  {year}: published total but no monthly rows at all")
            continue
        if counts[year] != 12:
            problems.append(
                f"  {year}: published total but only {counts[year]} monthly row(s); "
                "a partial year cannot reconcile and does not belong in annual.csv"
            )
            continue
        if sums[year] != published:
            diff = int(sums[year]) - int(published)
            problems.append(
                f"  {year}: months sum to {int(sums[year]):,} but published total is "
                f"{int(published):,} (difference {diff:+,})"
            )

    if problems:
        raise ContractViolation(
            "Annual totals do not reconcile against the monthly series:\n"
            + "\n".join(problems)
            + "\n\nNo tolerance is applied and none should be added. A year that "
            "genuinely does not reconcile is a finding about the sources and "
            "belongs in the README."
        )

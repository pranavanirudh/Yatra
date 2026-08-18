"""Festival dates -> a monthly feature frame.

This is the only place calendar information becomes something a model can be fit
on, and it is deliberately thin: every column here is a function of the
astronomical calendar and nothing else. None of them reads the footfall series,
so none of them can carry a future observation back to a forecast origin. That
is the whole argument for letting ``sarimax_cal`` see future rows of this frame
while no model ever sees a future observation -- the calendar is knowable at the
origin in a way the data is not.

Which columns get built is declared in ``calendar.yaml`` under ``features``.
The names are looked up in :data:`BUILDERS`, an explicit registry. An unknown
name raises; it does not get silently dropped, because a quietly missing
regressor turns the calendar arm into a duplicate of its control and reports a
null result. That is the failure in brief 5, one layer up.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pandas as pd

from .ephemeris import jd_to_datetime
from .errors import ConfigError
from .panchanga import Occurrence, Panchanga

FeatureBuilder = Callable[[Panchanga, pd.DatetimeIndex], pd.Series]

BUILDERS: dict[str, FeatureBuilder] = {}


def feature(name: str) -> Callable[[FeatureBuilder], FeatureBuilder]:
    def decorate(fn: FeatureBuilder) -> FeatureBuilder:
        if name in BUILDERS:
            raise ConfigError(f"Calendar feature {name!r} is already registered.")
        BUILDERS[name] = fn
        return fn

    return decorate


def _month_starts(start: dt.date, end: dt.date) -> pd.DatetimeIndex:
    return pd.date_range(
        pd.Timestamp(start).to_period("M").to_timestamp(),
        pd.Timestamp(end).to_period("M").to_timestamp(),
        freq="MS",
    )


def _day_counts(occurrences: list[Occurrence], index: pd.DatetimeIndex) -> pd.Series:
    """Festival days per month.

    Counted day by day rather than by assigning a whole festival to the month
    holding its first day, so a Navratri straddling a month boundary is split
    across the two months in the proportion actually observed. That split is the
    entire reason this is a day count and not an indicator.
    """
    counts = pd.Series(0, index=index, dtype="int64")
    for occurrence in occurrences:
        for date in occurrence.dates:
            key = pd.Timestamp(date.year, date.month, 1)
            if key in counts.index:
                counts.loc[key] += 1
    return counts


@feature("festival_days")
def festival_days(panchanga: Panchanga, index: pd.DatetimeIndex) -> pd.Series:
    """Total declared festival days falling in the month."""
    return _day_counts(panchanga.occurrences, index)


@feature("sharad_navratri_days")
def sharad_navratri_days(panchanga: Panchanga, index: pd.DatetimeIndex) -> pd.Series:
    """Sharad Navratri days alone.

    The dominant driver at this shrine gets its own column rather than being
    averaged into the generic count, where nine days of the busiest festival of
    the year would be indistinguishable from nine scattered single-day ones.
    """
    subset = [o for o in panchanga.occurrences if o.festival_id == "sharad_navratri"]
    if not subset:
        raise ConfigError(
            "Feature 'sharad_navratri_days' is requested but no festival with id "
            "'sharad_navratri' is declared in calendar.yaml. A column of zeros "
            "here would read as 'Navratri does not matter' rather than as a "
            "missing rule."
        )
    return _day_counts(subset, index)


@feature("is_navratri_month")
def is_navratri_month(panchanga: Panchanga, index: pd.DatetimeIndex) -> pd.Series:
    """1 if any Navratri day falls in the month, else 0."""
    subset = [o for o in panchanga.occurrences if o.festival_id.endswith("navratri")]
    return (_day_counts(subset, index) > 0).astype("int64")


@feature("lunar_drift_days")
def lunar_drift_days(panchanga: Panchanga, index: pd.DatetimeIndex) -> pd.Series:
    """How far the lunar reckoning has slid against the solar one, in days.

    For each civil month, the drift of the lunar month covering most of it:
    days from that lunar month's new moon to the sankranti that names it. Month
    of the year is already carried by the seasonal terms inside the models, so
    what this column adds is the part month-of-year cannot express -- the same
    calendar month arrives at a different point of the lunar cycle each year,
    and an adhika year displaces the whole festival season by weeks.

    Values run 0 to about 29.5 for ordinary months and past 29.5 for the
    intercalary ones, so the extreme-drift case is exactly where the column goes
    out of its usual range instead of wrapping quietly back to zero.
    """
    tz = panchanga.tz
    spans = [
        (
            jd_to_datetime(month.start_jd, tz).date(),
            jd_to_datetime(month.end_jd, tz).date(),
            month.drift_days,
        )
        for month in panchanga.months
    ]

    values = np.full(len(index), np.nan)
    for position, month_start in enumerate(index):
        first = month_start.date()
        last = (month_start + pd.offsets.MonthEnd(1)).date()
        best_overlap, best_drift = 0, np.nan
        for span_start, span_end, drift in spans:
            overlap = (min(last, span_end) - max(first, span_start)).days + 1
            if overlap > best_overlap:
                best_overlap, best_drift = overlap, drift
        values[position] = best_drift

    series = pd.Series(values, index=index, dtype="float64")
    if series.isna().any():
        missing = series.index[series.isna()]
        raise ConfigError(
            f"No lunar month covers {len(missing)} civil month(s), first "
            f"{missing[0]:%Y-%m}. The computed range does not span the requested "
            "months; widen 'range' in calendar.yaml."
        )
    return series


def build(panchanga: Panchanga, config: dict, start: dt.date, end: dt.date) -> pd.DataFrame:
    """The monthly feature frame the backtest reads, one column per declared feature."""
    names = config.get("features")
    if not names:
        raise ConfigError(
            "calendar.yaml declares no 'features'. An empty calendar frame would "
            "make sarimax_cal refuse to fit rather than quietly matching sarima, "
            "but there is no reason to run the stage at all in that state."
        )

    unknown = [name for name in names if name not in BUILDERS]
    if unknown:
        raise ConfigError(
            f"calendar.yaml requests unknown calendar feature(s) {unknown}. "
            f"Registered: {sorted(BUILDERS)}. A typo here would drop a regressor "
            "and leave the calendar arm looking like a null result."
        )

    index = _month_starts(start, end)
    frame = pd.DataFrame({name: BUILDERS[name](panchanga, index) for name in names})
    frame.index.name = "month"

    if frame.isna().any().any():
        bad = frame.columns[frame.isna().any()].tolist()
        raise ConfigError(f"Calendar features contain NaN in columns {bad}.")
    return frame


def occurrence_frame(panchanga: Panchanga) -> pd.DataFrame:
    """Every festival DAY as its own dated row.

    The monthly feature frame is what models are fit on; this is what an
    operations briefing needs. A month total of nine Navratri days does not tell
    a duty officer which nine dates to roster for, and those dates are the only
    thing in this project that speaks to *when within a month* crowds
    concentrate.
    """
    rows = [
        {
            "date": date,
            "festival_id": occurrence.festival_id,
            "label": occurrence.label,
            "day_index": position + 1,
            "duration_days": occurrence.duration_days,
            "lunar_month": occurrence.lunar_month,
        }
        for occurrence in panchanga.occurrences
        for position, date in enumerate(occurrence.dates)
    ]
    if not rows:
        raise ConfigError("No festival occurrences to write; the range resolved nothing.")
    return pd.DataFrame(rows).sort_values(["date", "festival_id"]).reset_index(drop=True)


def write(frame: pd.DataFrame, path: Path | str) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(destination, date_format="%Y-%m-%d")
    return destination

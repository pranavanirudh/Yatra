"""Shock windows: the labels that split the backtest into two leaderboards.

These are **evaluation labels**. Nothing here is ever handed to a model. The
module deliberately exposes no function that returns a shock flag for a date
range in a form convenient to a feature builder, and ``backtest.py`` imports
only :func:`label_months`, which it applies to results after fitting is done.

A model that could see these windows would post a spectacular score and mean
nothing at all -- it would be reading the answer key.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import yaml

from .errors import ConfigError, MissingCitation

REQUIRED_SOURCE_FIELDS = ("publisher", "title", "url", "accessed")

CLEAN = "clean"
SHOCK = "shock"


@dataclass(frozen=True)
class Source:
    publisher: str
    title: str
    url: str
    accessed: str

    def cite(self) -> str:
        return f"{self.publisher}, “{self.title}”, accessed {self.accessed}. {self.url}"


@dataclass(frozen=True)
class ShockWindow:
    id: str
    label: str
    start: pd.Period
    end: pd.Period
    source: Source
    rationale: str
    verified: bool
    corroborating_source: Source | None = None

    def contains(self, period: pd.Period) -> bool:
        return self.start <= period <= self.end

    @property
    def n_months(self) -> int:
        return int((self.end - self.start).n) + 1


def _parse_source(raw: object, window_id: str, field: str) -> Source:
    if raw is None:
        raise MissingCitation(
            f"Shock window '{window_id}' has no {field}. Every window needs one: "
            "an undocumented shock window is an unfalsifiable claim about which "
            "months were disrupted, and the finding this project reports is a "
            "comparison across exactly that line."
        )
    if not isinstance(raw, dict):
        raise MissingCitation(f"Shock window '{window_id}': {field} must be a mapping.")

    absent = [f for f in REQUIRED_SOURCE_FIELDS if not str(raw.get(f, "")).strip()]
    if absent:
        raise MissingCitation(
            f"Shock window '{window_id}': {field} is missing {', '.join(absent)}. "
            "A citation without a publisher, a title, a URL and an access date "
            "cannot be checked by anyone reading the README."
        )
    return Source(
        publisher=str(raw["publisher"]),
        title=str(raw["title"]),
        url=str(raw["url"]),
        accessed=str(raw["accessed"]),
    )


def _parse_month(value: object, window_id: str, field: str) -> pd.Period:
    try:
        return pd.Period(str(value), freq="M")
    except Exception:
        raise ConfigError(
            f"Shock window '{window_id}': {field} = {value!r} is not a YYYY-MM month."
        ) from None


def load_windows(config_path: str | Path = "experiments/configs/shocks.yaml") -> list[ShockWindow]:
    """Load and validate the declared shock windows.

    Raises
    ------
    MissingCitation
        If any window lacks a source, or a source lacks a required field.
    ConfigError
        If the file is malformed, a window is reversed, or two windows overlap.
    """
    path = Path(config_path)
    if not path.exists():
        raise ConfigError(f"Shock config not found: {path}")

    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    entries = raw.get("windows")
    if not entries:
        raise ConfigError(
            f"{path} declares no windows. An empty shock list would make every "
            "month clean and the regime split vacuous, so this is an error "
            "rather than a degenerate run."
        )

    windows: list[ShockWindow] = []
    for entry in entries:
        if not isinstance(entry, dict) or "id" not in entry:
            raise ConfigError(f"{path}: every window needs an 'id'. Got: {entry!r}")
        wid = str(entry["id"])

        start = _parse_month(entry.get("start"), wid, "start")
        end = _parse_month(entry.get("end"), wid, "end")
        if end < start:
            raise ConfigError(f"Shock window '{wid}': end {end} precedes start {start}.")

        rationale = str(entry.get("rationale", "")).strip()
        if not rationale:
            raise ConfigError(
                f"Shock window '{wid}' has no rationale. The dates are a judgement "
                "call and the judgement has to be written down."
            )

        corroborating = entry.get("corroborating_source")
        windows.append(
            ShockWindow(
                id=wid,
                label=str(entry.get("label", wid)),
                start=start,
                end=end,
                source=_parse_source(entry.get("source"), wid, "source"),
                rationale=rationale,
                verified=bool(entry.get("verified", False)),
                corroborating_source=(
                    _parse_source(corroborating, wid, "corroborating_source")
                    if corroborating is not None
                    else None
                ),
            )
        )

    _check_disjoint(windows, path)
    return windows


def _check_disjoint(windows: list[ShockWindow], path: Path) -> None:
    """Overlapping windows would double-count months in the per-window breakdown.

    The clean/shock split itself would survive an overlap, but the per-window
    counts reported in the README would not sum to the shock total, and a reader
    reconciling them would be right to distrust everything else on the page.
    """
    ordered = sorted(windows, key=lambda w: w.start)
    for earlier, later in zip(ordered, ordered[1:]):
        if later.start <= earlier.end:
            raise ConfigError(
                f"{path}: windows '{earlier.id}' ({earlier.start}..{earlier.end}) and "
                f"'{later.id}' ({later.start}..{later.end}) overlap. Merge them or "
                "move a boundary -- overlapping windows double-count months."
            )


def label_months(months: pd.PeriodIndex, windows: list[ShockWindow]) -> pd.DataFrame:
    """Label each month ``clean`` or ``shock``, naming the window that applies.

    Applied to the TARGET month of a forecast, not the origin. A forecast made
    from a clean origin that lands inside COVID is a shock-month forecast --
    that is the month the model got wrong, and the regime of the target is what
    the finding is about.
    """
    # freqstr, not freq: comparing an Offset to the string "M" is deprecated in
    # pandas 2 and will stop being an equality check rather than start being
    # False loudly -- which would leave this guard passing everything.
    if not isinstance(months, pd.PeriodIndex) or months.freqstr != "M":
        raise ConfigError("label_months expects a monthly PeriodIndex.")

    regime = pd.Series(CLEAN, index=months, dtype="object")
    window_id = pd.Series(pd.NA, index=months, dtype="object")

    for window in windows:
        mask = (months >= window.start) & (months <= window.end)
        regime[mask] = SHOCK
        window_id[mask] = window.id

    return pd.DataFrame({"regime": regime, "shock_window": window_id})


def unverified(windows: list[ShockWindow]) -> list[ShockWindow]:
    """Windows whose citation the owner has not yet checked.

    Loading does not fail on these -- an unread citation is still a citation,
    and blocking the pipeline on a human review step would just invite someone
    to flip the flags without reading. Instead ``report.py`` stamps the README
    with a warning for as long as any remain, so the caveat travels with the
    numbers rather than sitting in a config file nobody opens.
    """
    return [w for w in windows if not w.verified]

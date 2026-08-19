"""Forward forecasts turned into a crowd-management briefing.

Everything above this module answers "which model is right". This one answers
"what should be staffed next month", which is a different question with a
different failure cost: a wrong MASE in a table is an academic embarrassment,
and a wrong resourcing number at a shrine that has had fatal crushes is not.

Three rules follow from that, and they are the whole design.

**1. Monthly volume is not peak load.** This project forecasts pilgrims per
month. A stampede is a minute-long event. A monthly total tells an operator how
much capacity the season needs; it cannot tell them which hour the crush comes.
What bridges the gap is the calendar layer, which knows exactly which dates
concentrate arrivals -- so the briefing reports the forecast volume *and* the
specific dates within that month, and refuses to collapse them into a single
"peak day" number that the data cannot support. Estimating a peak-day multiplier
needs daily observations, which this project does not have.

**2. Intervals come from measured error, not from a model's own optimism.** The
band on each forecast is the empirical spread of that model's backtest errors at
that horizon -- actual rows in ``results/metrics.csv``. A model's analytic
prediction interval assumes its own specification is correct, which is exactly
the assumption that fails during a disruption. Clean-month and shock-month
spreads are reported separately, because planning to the clean band and then
meeting a shock is how a site ends up under-resourced.

**3. Planning ratios are policy, not output.** How many marshals per thousand
pilgrims a day is a decision for the people who run the site, informed by
geometry, regulation and experience this model knows nothing about. They are
declared in ``experiments/configs/operations.yaml``. If none are declared, the
briefing reports volumes and says plainly that no resourcing was computed. It
never ships a plausible-looking default, because a default ratio would be
indistinguishable, in the output, from an evidence-based one.
"""

from __future__ import annotations

import calendar as _calendar
import datetime as dt
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from . import models, regimes
from .errors import ConfigError

# Basis a planning ratio is applied to. Named so a config cannot silently mean
# something other than what it says.
BASES = ("monthly_total", "daily_mean", "festival_day_total")


@dataclass(frozen=True)
class PlanningRatio:
    id: str
    label: str
    per_pilgrims: float
    basis: str
    minimum: int = 0

    def requirement(self, row: pd.Series) -> float:
        if self.basis == "monthly_total":
            volume = row["forecast"]
        elif self.basis == "daily_mean":
            volume = row["daily_mean"]
        elif self.basis == "festival_day_total":
            volume = row["festival_day_load"]
        else:  # pragma: no cover - guarded at load time
            raise ConfigError(f"Unknown basis {self.basis!r}.")
        return max(float(self.minimum), float(np.ceil(volume / self.per_pilgrims)))


@dataclass(frozen=True)
class OperationsConfig:
    model: str
    horizons: list[int]
    ratios: list[PlanningRatio]
    confidence: float


def load_config(path: str | Path = "experiments/configs/operations.yaml") -> OperationsConfig:
    path = Path(path)
    if not path.exists():
        raise ConfigError(
            f"{path} not found. It declares which model to forecast with and the "
            "planning ratios to apply. See docs/operations.md."
        )
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    model = str(raw.get("model", "best_clean"))
    if model != "best_clean" and model not in models.REGISTRY:
        raise ConfigError(
            f"operations.yaml names model {model!r}, which is not registered. "
            f"Known: {sorted(models.REGISTRY)}, or 'best_clean' to use whichever "
            "model scored best on clean months in the last backtest."
        )

    horizons = [int(h) for h in raw.get("horizons", [1, 2, 3, 4, 5, 6])]
    if not horizons or min(horizons) < 1:
        raise ConfigError(f"operations.yaml horizons must be positive, got {horizons}.")

    ratios = []
    for entry in raw.get("planning", {}).get("ratios", []) or []:
        for required in ("id", "per_pilgrims", "basis"):
            if required not in entry:
                raise ConfigError(f"operations.yaml ratio {entry!r} is missing {required!r}.")
        if entry["basis"] not in BASES:
            raise ConfigError(
                f"Ratio {entry['id']!r} declares basis {entry['basis']!r}; "
                f"known bases are {list(BASES)}."
            )
        if float(entry["per_pilgrims"]) <= 0:
            raise ConfigError(f"Ratio {entry['id']!r} has a non-positive per_pilgrims.")
        ratios.append(
            PlanningRatio(
                id=str(entry["id"]),
                label=str(entry.get("label", entry["id"])),
                per_pilgrims=float(entry["per_pilgrims"]),
                basis=str(entry["basis"]),
                minimum=int(entry.get("minimum", 0)),
            )
        )

    return OperationsConfig(
        model=model,
        horizons=sorted(set(horizons)),
        ratios=ratios,
        confidence=float(raw.get("confidence", 0.9)),
    )


# --------------------------------------------------------------------------
# Choosing the model, and measuring how wrong it usually is.
# --------------------------------------------------------------------------


def choose_model(metrics_frame: pd.DataFrame, declared: str) -> str:
    """Resolve ``best_clean`` against the backtest, or check the declared name."""
    if declared != "best_clean":
        if declared not in set(metrics_frame["model"]):
            raise ConfigError(
                f"operations.yaml asks to forecast with {declared!r}, but that "
                "model has no rows in results/metrics.csv. Re-run the backtest "
                "with it in the model list, or the interval below would be "
                "borrowed from a different model."
            )
        return declared

    clean = metrics_frame[metrics_frame["regime"] == regimes.CLEAN]
    if clean.empty:
        raise ConfigError("metrics.csv has no clean-regime rows to pick a model from.")
    return str(clean.groupby("model")["mase"].mean().idxmin())


def error_spread(
    metrics_frame: pd.DataFrame, model: str, confidence: float
) -> pd.DataFrame:
    """Empirical forecast-error quantiles per horizon and regime.

    Errors are expressed in **units of the MASE denominator** -- the same
    seasonal-naive scale the whole project normalises by -- and converted back
    to people at the current level by :func:`planning_table`.

    The obvious alternative, a ratio ``actual / predicted``, is unusable here
    and was tried first. During a closure the model predicts near zero, the
    ratio explodes, and a 90th percentile computed from a handful of shock
    months turns a 1,500-pilgrim forecast into an upper bound of half a
    million. That is not a wide interval, it is a broken one, and it would
    appear in a planning document looking like analysis. The MASE scale cannot
    collapse toward zero -- ``metrics.seasonal_naive_scale`` raises rather than
    return zero -- so the same failure cannot happen through this route.

    Regimes are kept apart on purpose. The clean band is what to plan to; the
    shock band is what a contingency has to absorb. Averaging them would give
    one number too wide for ordinary months and too narrow for bad ones.
    """
    lower_q = (1.0 - confidence) / 2.0
    mine = metrics_frame[metrics_frame["model"] == model]
    if mine.empty:
        raise ConfigError(
            f"results/metrics.csv holds no rows for model {model!r}, so its error "
            "spread cannot be measured. Borrowing another model's band would "
            "report an uncertainty that belongs to a different forecast."
        )
    if "mase_scale" not in mine.columns:
        raise ConfigError("metrics.csv has no 'mase_scale' column; re-run the backtest.")

    rows = []
    for (horizon, regime), group in mine.groupby(["horizon", "regime"]):
        predicted = group["predicted"].to_numpy(dtype="float64")
        actual = group["actual"].to_numpy(dtype="float64")
        scale = group["mase_scale"].to_numpy(dtype="float64")
        usable = (
            np.isfinite(predicted) & np.isfinite(actual)
            & np.isfinite(scale) & (scale > 0)
        )
        # Five is a floor, not a sufficiency claim: a quantile from four points
        # is just the extremes. Thin cells are dropped, and the count is carried
        # through to the briefing so a reader can see how thin the basis was.
        if usable.sum() < 5:
            continue
        scaled_error = (actual[usable] - predicted[usable]) / scale[usable]
        rows.append(
            {
                "horizon": int(horizon),
                "regime": regime,
                "n": int(usable.sum()),
                "lo_error": float(np.quantile(scaled_error, lower_q)),
                "median_error": float(np.median(scaled_error)),
                "hi_error": float(np.quantile(scaled_error, 1.0 - lower_q)),
            }
        )
    if not rows:
        raise ConfigError(
            f"Not enough scored forecasts for {model!r} to measure an error "
            "spread. An operational forecast without a measured band would be a "
            "point estimate presented as a plan."
        )
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# The forward forecast.
# --------------------------------------------------------------------------


def forward(
    observations: pd.Series,
    model: str,
    horizons: list[int],
    calendar_features: pd.DataFrame | None = None,
) -> pd.Series:
    """Forecast forward from the end of the observed series.

    This is the only place in the project that forecasts past the last
    observation. The backtest deliberately never does -- it scores against known
    outcomes. Here there is nothing to score against, which is exactly why the
    band from :func:`error_spread` is not optional.
    """
    predicted = models.predict(model, observations, horizons, calendar=calendar_features)
    index = pd.PeriodIndex(
        [observations.index[-1].to_period("M") + h for h in horizons], freq="M"
    )
    return pd.Series(predicted, index=index, name="forecast")


def _festival_dates(festivals: pd.DataFrame | None, period: pd.Period) -> list[tuple[dt.date, str]]:
    if festivals is None or festivals.empty:
        return []
    subset = festivals[
        (festivals["date"] >= period.start_time.date())
        & (festivals["date"] <= period.end_time.date())
    ]
    return [(row.date, row.label) for row in subset.itertuples()]


def planning_table(
    forecast: pd.Series,
    spread: pd.DataFrame,
    horizons: list[int],
    config: OperationsConfig,
    current_scale: float,
    festivals: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """One row per forecast month, with bands, calendar load and resourcing.

    ``current_scale`` is the MASE denominator computed on the observed series as
    it stands now -- the same seasonal-naive quantity the backtest normalised
    by. It converts the scale-free error quantiles back into people at today's
    level, so a band measured partly on the 1990s is not applied verbatim to a
    volume an order of magnitude larger.
    """
    if not np.isfinite(current_scale) or current_scale <= 0:
        raise ConfigError(f"current_scale must be positive and finite, got {current_scale!r}.")

    clean = spread[spread["regime"] == regimes.CLEAN].set_index("horizon")
    shock = spread[spread["regime"] == regimes.SHOCK].set_index("horizon")

    def bounds(band) -> tuple[float, float]:
        if band is None:
            return np.nan, np.nan
        # Clamped at zero: a negative attendance is not a plan. This clamp is on
        # a planning band, not on a model's point forecast -- clamping the
        # latter would flatter one estimator in a comparison, which is why
        # models.py deliberately does not do it.
        lo = max(0.0, float(point + band["lo_error"] * current_scale))
        hi = max(0.0, float(point + band["hi_error"] * current_scale))
        return lo, hi

    rows = []
    for horizon, (period, point) in zip(horizons, forecast.items()):
        days = _calendar.monthrange(period.year, period.month)[1]
        dates = _festival_dates(festivals, period)

        lo, hi = bounds(clean.loc[horizon] if horizon in clean.index else None)
        shock_lo, shock_hi = bounds(shock.loc[horizon] if horizon in shock.index else None)

        daily_mean = float(point) / days
        row = {
            "month": str(period),
            "horizon": horizon,
            "forecast": float(point),
            "lo": lo,
            "hi": hi,
            "shock_lo": shock_lo,
            "shock_hi": shock_hi,
            "days_in_month": days,
            "daily_mean": daily_mean,
            "festival_days": len(dates),
            "festival_dates": "; ".join(d.isoformat() for d, _ in dates),
            "festival_labels": "; ".join(sorted({label for _, label in dates})),
            # Load attributable to festival days if they carried an average day's
            # share. This is a FLOOR, not a peak: festival days plainly draw more
            # than an average day, and by how much is a daily-data question.
            "festival_day_load": daily_mean * len(dates),
        }
        for ratio in config.ratios:
            row[f"need_{ratio.id}"] = ratio.requirement(pd.Series(row))
        rows.append(row)

    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# The briefing.
# --------------------------------------------------------------------------


def _people(value: float) -> str:
    if not np.isfinite(value):
        return "—"
    if value >= 1e5:
        return f"{value/1e5:,.2f} lakh"
    return f"{value:,.0f}"


def briefing(
    table: pd.DataFrame,
    config: OperationsConfig,
    model: str,
    observations: pd.Series,
    spread: pd.DataFrame,
    shocks_hash: str | None = None,
) -> str:
    """A plain-language operational briefing. Written for a duty officer.

    ``shocks_hash`` fingerprints the shock windows the bands were split by. It
    is recorded because this document is read on its own, away from the run
    that produced it: without it, a briefing built before the windows were
    edited is indistinguishable from one built after, and the difference is the
    contingency range.
    """
    confidence = int(round(config.confidence * 100))
    last = observations.index[-1].to_period("M")

    lines = [
        "# Crowd planning briefing",
        "",
        f"_Generated from `results/metrics.csv` and the observation series. "
        f"Forecasting model: **{model}**. Last observed month: **{last}**._",
        "",
        "> **Read this first.** These are forecasts of pilgrims **per month**. "
        "They size the resourcing a month needs. They do **not** predict the "
        "load at any given hour, and a monthly total cannot identify a crush "
        "risk on a particular afternoon. The dated festival days in each row are "
        "where arrivals concentrate; treat those as the days requiring surge "
        "cover, and see the limitations section for what would be needed to put "
        "numbers on a single day.",
        "",
        "## Forecast",
        "",
        f"| Month | Expected | Likely range ({confidence}%) | Per day (avg) | Festival days |",
        "|---|---:|---:|---:|---|",
    ]

    for row in table.itertuples():
        band = f"{_people(row.lo)} – {_people(row.hi)}"
        dates = row.festival_dates.replace("; ", ", ") if row.festival_dates else "—"
        lines.append(
            f"| {row.month} | {_people(row.forecast)} | {band} | "
            f"{_people(row.daily_mean)} | {dates} |"
        )

    lines += [
        "",
        "## If a disruption occurs",
        "",
        "The range above is measured on **ordinary** months. Months inside a "
        "declared shock window behave differently, and the same model's error "
        "there is far wider. Plan the contingency to this, not to the range above.",
        "",
        "| Month | Shock-regime range |",
        "|---|---:|",
    ]
    unmeasured = []
    floored = []
    for row in table.itertuples():
        if not np.isfinite(row.shock_hi):
            unmeasured.append(row.month)
            lines.append(f"| {row.month} | not measurable |")
        else:
            if np.isfinite(row.shock_lo) and row.shock_lo <= 0:
                floored.append(row.month)
            lines.append(f"| {row.month} | {_people(row.shock_lo)} – {_people(row.shock_hi)} |")

    if floored:
        # A zero in a planning table looks like a rendering fault, and a reader
        # who dismisses it as one has dismissed the only entry in this document
        # that has actually happened.
        lines += [
            "",
            "**A lower bound of zero is a measurement here, not a placeholder.** "
            f"For {', '.join(floored)} the shock-regime range reaches zero "
            "because the observed record contains months when this shrine was "
            "closed and the count was zero. The band is clamped at zero rather "
            "than going negative, but the floor itself is something that has "
            "happened, not a missing value.",
        ]

    if unmeasured:
        # A blank cell in a contingency table is dangerous if it reads as "no
        # risk" rather than "not measured". Say which it is.
        lines += [
            "",
            f"**\"Not measurable\" is not \"no risk.\"** For {', '.join(unmeasured)} "
            "there were too few scored forecasts inside a declared shock window "
            "at that horizon to form a range — fewer than five. That is a "
            "statement about how rarely shocks have been observed and labelled, "
            "not about how safe those months are. Treat them as at least as "
            "uncertain as the months that do have a range.",
        ]

    if config.ratios:
        lines += ["", "## Resourcing", "",
                  "Computed by applying the ratios declared in "
                  "`experiments/configs/operations.yaml` to the expected volume. "
                  "**The ratios are your policy, not a model output** — the "
                  "forecast supplies the volume, you supply what a safe volume "
                  "per unit is.", ""]
        header = "| Month | " + " | ".join(r.label for r in config.ratios) + " |"
        lines.append(header)
        lines.append("|---|" + "---:|" * len(config.ratios))
        for row in table.itertuples():
            cells = [f"{int(getattr(row, f'need_{r.id}')):,}" for r in config.ratios]
            lines.append(f"| {row.month} | " + " | ".join(cells) + " |")
    else:
        lines += [
            "",
            "## Resourcing",
            "",
            "**No planning ratios are declared, so no resourcing was computed.** "
            "Add them under `planning.ratios` in "
            "`experiments/configs/operations.yaml` — for example, one marshal per "
            "N pilgrims per day. No defaults are supplied here on purpose: a "
            "ratio invented by this tool would appear in the table looking "
            "exactly like one grounded in site experience.",
        ]

    lines += [
        "",
        "## What this cannot tell you",
        "",
        "- **Peak-hour or peak-day load.** The series is monthly. Sizing a "
        "single day's barricading, queue geometry or medical cover needs daily "
        "(ideally hourly) arrival counts. Those are not in this project.",
        "- **Where crowding happens.** Footfall is a count of people entering, "
        "not a density anywhere on the track. Chokepoints are a site-geometry "
        "question.",
        "- **Anything about an undeclared shock.** The detector reacts to a "
        "break only after it appears in the observed data. A disruption "
        "beginning after the last observed month is not in any number here.",
        "",
        "## Provenance",
        "",
        "| | |",
        "|---|---|",
        f"| Model | `{model}` |",
        f"| Last observed month | {last} |",
        f"| Band | empirical, {confidence}% of backtest errors |",
        f"| Clean-month errors used | {int(spread[spread['regime'] == regimes.CLEAN]['n'].sum())} |",
        f"| Shock-month errors used | {int(spread[spread['regime'] == regimes.SHOCK]['n'].sum())} |",
    ]
    if shocks_hash:
        lines.append(f"| Shock windows | `{shocks_hash}` |")
    lines += [
        "",
    ]
    return "\n".join(lines)


def write_table(table: pd.DataFrame, path: str | Path = "results/operations.csv") -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(path, index=False)
    return path


def write_briefing(text: str, path: str | Path = "results/briefing.md") -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path

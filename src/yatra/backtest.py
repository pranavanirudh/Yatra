"""Rolling-origin backtest.

The origin set is built **once**, before any model runs, and every model is
scored on all of it. After the run, :func:`_assert_rectangular` checks that the
resulting panel is complete and raises if it is not. Those two facts together
are what make the per-regime leaderboards comparable: without them the clean and
shock tables could be summarising different subsets of history and the
"rankings invert" finding would be an artefact of which origins each model
happened to survive.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from . import metrics, models, regimes
from .errors import ConfigError, RaggedPanel


@dataclass(frozen=True)
class BacktestConfig:
    min_train_months: int
    step_months: int
    horizons: list[int]
    window: str
    mase_seasonality: int
    model_names: list[str]
    rectangular: bool
    on_model_failure: str
    config_hash: str

    @property
    def max_horizon(self) -> int:
        return max(self.horizons)


def load_config(path: str | Path = "experiments/configs/backtest.yaml") -> BacktestConfig:
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"Backtest config not found: {path}")

    text = path.read_text(encoding="utf-8")
    raw = yaml.safe_load(text) or {}

    origins = raw.get("origins", {})
    horizons = list(raw.get("horizons", []))
    if not horizons:
        raise ConfigError(f"{path}: no horizons declared.")

    window = str(raw.get("window", "expanding"))
    if window != "expanding":
        # Rolling windows are a legitimate design, but they change what the MASE
        # denominator means, so they are not silently accepted.
        raise ConfigError(
            f"{path}: window='{window}' is not implemented. Only 'expanding' is, "
            "and switching would change the MASE scale definition with it."
        )

    on_failure = str(raw.get("on_model_failure", "fail"))
    if on_failure != "fail":
        raise ConfigError(
            f"{path}: on_model_failure='{on_failure}' is not supported. A model "
            "that errors on an origin must abort the run -- dropping it from that "
            "origin and averaging over the rest is how a ragged panel gets "
            "reported as a comparison."
        )

    return BacktestConfig(
        min_train_months=int(origins.get("min_train_months", 120)),
        step_months=int(origins.get("step_months", 1)),
        horizons=[int(h) for h in horizons],
        window=window,
        mase_seasonality=int(raw.get("metrics", {}).get("mase_seasonality", 12)),
        model_names=[str(m) for m in raw.get("models", [])],
        rectangular=bool(raw.get("rectangular", True)),
        on_model_failure=on_failure,
        config_hash=hashlib.sha256(text.encode("utf-8")).hexdigest()[:12],
    )


def build_origins(series: pd.Series, config: BacktestConfig) -> list[int]:
    """Positional indices of the usable forecast origins.

    An origin is usable only if it has enough history *and* can be scored at
    every horizon. An origin scorable at h=1 but not h=6 is dropped entirely
    rather than contributing a partial row -- otherwise short horizons would be
    evaluated on a longer span of history than long ones, and the per-horizon
    columns would not be comparable with each other.
    """
    n = len(series)
    first = config.min_train_months - 1
    last = n - config.max_horizon - 1
    if last < first:
        raise ConfigError(
            f"Series of {n} months cannot support min_train_months="
            f"{config.min_train_months} with max horizon {config.max_horizon}."
        )
    return list(range(first, last + 1, config.step_months))


def run(
    series: pd.Series,
    config: BacktestConfig,
    calendar: pd.DataFrame | None = None,
    windows: list[regimes.ShockWindow] | None = None,
    shocks_path: str | Path | None = None,
) -> pd.DataFrame:
    """Score every model on every (origin, horizon) cell.

    ``windows`` is applied *after* every forecast has been produced. It is never
    passed into a model call -- shock labels are the answer key.
    """
    if series.index.freq is None:
        series = series.asfreq("MS")

    origins = build_origins(series, config)
    horizons = config.horizons
    unknown = sorted(set(config.model_names) - set(models.REGISTRY))
    if unknown:
        raise ConfigError(f"Config names unregistered models: {unknown}.")

    rows: list[dict] = []
    for pos in origins:
        train = series.iloc[: pos + 1]
        origin_month = series.index[pos]

        # One scale per origin, shared by every model. See CLAUDE.md 3.2.
        scale = metrics.seasonal_naive_scale(train, config.mase_seasonality)

        target_positions = [pos + h for h in horizons]
        target_months = series.index[target_positions]
        actual = series.iloc[target_positions].to_numpy(dtype="float64")

        for name in config.model_names:
            spec = models.get(name)
            model_calendar = calendar if spec.needs_calendar else None
            try:
                predicted = models.predict(name, train, horizons, model_calendar)
            except Exception as exc:
                # on_model_failure=fail. Naming both the model and the origin is
                # the point: "holt_winters_mul failed" is not actionable,
                # "holt_winters_mul failed at 2020-04" is a finding.
                raise RuntimeError(
                    f"Model '{name}' failed at origin {origin_month:%Y-%m}: "
                    f"{type(exc).__name__}: {exc}"
                ) from exc

            for i, h in enumerate(horizons):
                rows.append(
                    {
                        "origin": origin_month,
                        "target": target_months[i],
                        "horizon": h,
                        "model": name,
                        "actual": actual[i],
                        "predicted": predicted[i],
                        "mase_scale": scale,
                    }
                )

    frame = pd.DataFrame(rows)
    # Months are periods, not instants. The series carries a DatetimeIndex, so
    # the rows above arrive as month-start Timestamps; normalise once here so
    # that the in-memory frame and the one `read` hands back from metrics.csv
    # are the same object type. They were not, and a round trip through the CSV
    # silently changed the dtype of the two columns everything else joins on.
    frame["origin"] = pd.PeriodIndex(frame["origin"], freq="M")
    frame["target"] = pd.PeriodIndex(frame["target"], freq="M")
    frame = _score(frame)
    frame = _attach_regimes(frame, windows)
    _assert_rectangular(frame, origins, horizons, config)
    frame["config_hash"] = config.config_hash
    if shocks_path is not None:
        frame["shocks_hash"] = shocks_fingerprint(shocks_path)
    return frame.sort_values(["model", "origin", "horizon"]).reset_index(drop=True)


def _score(frame: pd.DataFrame) -> pd.DataFrame:
    actual = frame["actual"].to_numpy()
    predicted = frame["predicted"].to_numpy()
    frame["ae"] = metrics.absolute_error(actual, predicted)
    frame["se"] = metrics.squared_error(actual, predicted)
    frame["smape"] = metrics.smape(actual, predicted)
    frame["mase"] = frame["ae"] / frame["mase_scale"]
    return frame


def shocks_fingerprint(path: str | Path) -> str:
    """Hash of a shocks file. Identifies which declaration produced the labels."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:12]


def assert_labels_current(frame: pd.DataFrame, shocks_path: str | Path) -> None:
    """Refuse to report on labels that no longer match the declared windows.

    The regime column is written into ``metrics.csv`` when the backtest runs.
    Editing ``shocks.yaml`` afterwards does not change that file, so every
    downstream table would keep reporting the old split while the config on disk
    said something else -- numbers that look fine and are stale, which is the
    failure this project is built against.

    Cheap to fix, because regimes are labels and not model inputs: run
    ``python make.py relabel``. No refitting is involved.
    """
    if "shocks_hash" not in frame.columns:
        raise ConfigError(
            "metrics.csv predates regime-label tracking, so it cannot be checked "
            "against the current shocks.yaml. Run `python make.py relabel` to "
            "stamp it (no refitting -- regimes are labels)."
        )
    stored = sorted(frame["shocks_hash"].dropna().unique())
    current = shocks_fingerprint(shocks_path)
    if stored != [current]:
        raise ConfigError(
            f"metrics.csv was labelled from a different {shocks_path}: it "
            f"carries {stored}, the file on disk hashes to {current}. "
            "The shock windows have been edited since the backtest ran, so every "
            "regime table below would be reporting the old split. "
            "Run `python make.py relabel` -- it re-applies the current windows "
            "in seconds and does not refit anything."
        )


def relabel(frame: pd.DataFrame, windows: list[regimes.ShockWindow]) -> pd.DataFrame:
    """Re-apply regime labels to an existing metrics frame. Returns a copy.

    This is the concrete payoff of CLAUDE.md 3.4. Because no model ever receives
    a shock label, the forecasts in ``results/metrics.csv`` do not depend on the
    window definitions at all -- so asking "does the finding survive a different
    boundary?" is a re-join, not a re-fit. A sensitivity analysis that would
    otherwise cost another full backtest costs milliseconds.

    If windows were inputs rather than labels, this function could not exist,
    and the boundary choice would be untestable without refitting everything.
    """
    return _attach_regimes(frame.copy(), windows)


def relabel_from(frame: pd.DataFrame, shocks_path: str | Path) -> pd.DataFrame:
    """Re-apply the windows in ``shocks_path`` and re-stamp the fingerprint."""
    out = relabel(frame, regimes.load_windows(shocks_path))
    out["shocks_hash"] = shocks_fingerprint(shocks_path)
    return out


def _attach_regimes(frame: pd.DataFrame, windows: list[regimes.ShockWindow] | None) -> pd.DataFrame:
    if not windows:
        raise ConfigError(
            "No shock windows supplied. The entire point of this backtest is the "
            "regime split; running without labels would produce a single "
            "leaderboard and quietly answer a different question."
        )
    targets = pd.PeriodIndex(frame["target"], freq="M")
    labels = regimes.label_months(pd.PeriodIndex(targets.unique()).sort_values(), windows)
    joined = labels.reindex(targets)
    frame["regime"] = joined["regime"].to_numpy()
    frame["shock_window"] = joined["shock_window"].to_numpy()
    return frame


def _assert_rectangular(
    frame: pd.DataFrame,
    origins: list[int],
    horizons: list[int],
    config: BacktestConfig,
) -> None:
    """Every model must occupy every (origin, horizon) cell. No exceptions.

    Checked after the fact rather than trusted from construction, because the
    cost of being wrong here is a published comparison between different origin
    sets, and the check is cheap.
    """
    if not config.rectangular:
        return

    expected = len(origins) * len(horizons)
    counts = frame.groupby("model").size()
    wrong = counts[counts != expected]
    if len(wrong):
        detail = ", ".join(f"{m}={int(c)}" for m, c in wrong.items())
        raise RaggedPanel(
            f"Expected {expected} forecasts per model "
            f"({len(origins)} origins x {len(horizons)} horizons); got {detail}."
        )

    reference = None
    for name, group in frame.groupby("model"):
        cells = set(zip(group["origin"], group["horizon"]))
        if reference is None:
            reference = cells
            continue
        if cells != reference:
            missing = len(reference - cells)
            extra = len(cells - reference)
            raise RaggedPanel(
                f"Model '{name}' was scored on a different origin set: "
                f"{missing} cell(s) missing, {extra} extra. All models must share "
                "one origin set -- different origins is not a comparison."
            )


# Twelve significant digits, not full repr.
#
# The backtest is reproducible to about one ulp but not bit-identical: BLAS
# reduction order inside the estimators moves the last bit of a fitted value,
# so a no-op re-run rewrote most rows of this file with numerically identical
# numbers. This file is committed and is the artefact every README number
# traces to, and a diff touching 60% of its rows after a re-run that changed
# nothing makes `git diff` useless for spotting a change that did.
#
# Twelve digits is nine finer than the third decimal the README quotes and
# four finer than any aggregate here is meaningful to, so nothing reported can
# move. It does not make the file bit-stable in principle -- a value sitting
# within an ulp of a rounding boundary can still flip its twelfth digit -- but
# it takes the churn from most of the file to a handful of rows, which is the
# difference between a diff nobody reads and one that means something.
METRICS_FLOAT_FORMAT = "%.12g"


def write(frame: pd.DataFrame, path: str | Path = "results/metrics.csv") -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    out = frame.copy()
    out["origin"] = pd.PeriodIndex(out["origin"], freq="M").astype(str)
    out["target"] = pd.PeriodIndex(out["target"], freq="M").astype(str)
    out.to_csv(path, index=False, float_format=METRICS_FLOAT_FORMAT)
    return path


def read(path: str | Path = "results/metrics.csv") -> pd.DataFrame:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run `python make.py backtest` first -- the README "
            "generator refuses to invent numbers when the metrics file is absent."
        )
    frame = pd.read_csv(path)
    frame["origin"] = pd.PeriodIndex(frame["origin"], freq="M")
    frame["target"] = pd.PeriodIndex(frame["target"], freq="M")
    return frame


def per_regime_table(frame: pd.DataFrame, metric: str = "mase") -> pd.DataFrame:
    """Mean metric per model per regime, with ranks. The headline table."""
    table = frame.pivot_table(index="model", columns="regime", values=metric, aggfunc="mean")
    for regime in table.columns:
        table[f"{regime}_rank"] = table[regime].rank(method="min").astype(int)
    counts = frame.groupby(["model", "regime"]).size().unstack(fill_value=0)
    for regime in counts.columns:
        table[f"{regime}_n"] = counts[regime]
    return table.sort_values(regimes.CLEAN if regimes.CLEAN in table.columns else table.columns[0])

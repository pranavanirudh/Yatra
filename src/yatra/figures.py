"""Figures, regenerated from the artefacts on every run.

Every figure here is drawn from ``results/metrics.csv``, ``results/bootstrap.csv``
or the observation series -- never from a number typed into this file. Same rule
as the README: if a figure shows a value, a row produced it.

Matplotlib only, no seaborn, no styling package. The Agg backend is selected
explicitly because this runs from ``make`` with no display attached.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from . import regimes
from .errors import ConfigError

# One shared palette so the regimes read the same way in every figure. Shock is
# warm and clean is neutral deliberately: the eye should land on the disrupted
# months, because those are the ones the finding is about.
CLEAN_COLOUR = "#3f6d9e"
SHOCK_COLOUR = "#c1483a"
SHOCK_BAND = "#c1483a"
GRID = "#d9d9d9"

DPI = 150


def _style(ax) -> None:
    ax.grid(True, color=GRID, linewidth=0.6, alpha=0.7)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)


def _shade_shocks(ax, windows: list[regimes.ShockWindow]) -> None:
    """Shade every declared shock window, labelled once each.

    Labels are staggered down the axis rather than all sitting at the top.
    Adjacent windows -- Article 370 in late 2019 running almost straight into
    COVID in early 2020 -- otherwise print on top of each other and neither is
    readable, which matters because these bands are the whole point of the plot.
    """
    ordered = sorted(windows, key=lambda w: w.start)
    for position, window in enumerate(ordered):
        start = window.start.to_timestamp(how="start")
        end = window.end.to_timestamp(how="end")
        ax.axvspan(start, end, color=SHOCK_BAND, alpha=0.13, linewidth=0)
        ax.annotate(
            window.id.replace("_", " "),
            xy=(start, 1.0),
            xycoords=("data", "axes fraction"),
            xytext=(3, -10 - 11 * (position % 3)),
            textcoords="offset points",
            fontsize=7,
            color=SHOCK_COLOUR,
        )


def series_with_shocks(
    observations: pd.Series, windows: list[regimes.ShockWindow], path: Path
) -> Path:
    """The observed series, with the declared shock windows shaded.

    This is the figure that shows what the whole project is reacting to. It is
    also the one that makes a mis-declared window obvious: a shaded band that
    does not sit over a visible disruption is a claim that needs revisiting.
    """
    fig, ax = plt.subplots(figsize=(11, 4.2))
    _shade_shocks(ax, windows)
    ax.plot(observations.index, observations.to_numpy(), color=CLEAN_COLOUR, linewidth=1.2)
    ax.set_title("Monthly pilgrim footfall, with declared shock windows shaded")
    ax.set_ylabel("pilgrims per month")
    ax.set_xlabel("")
    ax.yaxis.set_major_formatter(lambda v, _: f"{v/1e5:.1f}L" if v >= 1e5 else f"{v:,.0f}")
    _style(ax)
    return _save(fig, path)


def forecast_vs_actual(
    frame: pd.DataFrame, windows: list[regimes.ShockWindow], path: Path, horizon: int = 1
) -> Path:
    """Actuals against each model's forecast at one horizon.

    One horizon at a time: overlaying six would make the plot unreadable and
    would also imply the horizons are comparable draws, which they are not.
    """
    subset = frame[frame["horizon"] == horizon]
    if subset.empty:
        raise ConfigError(f"No rows at horizon {horizon}; available: "
                          f"{sorted(frame['horizon'].unique())}.")

    fig, ax = plt.subplots(figsize=(11, 4.6))
    _shade_shocks(ax, windows)

    actuals = subset.groupby("target")["actual"].first()
    index = [p.to_timestamp(how="start") for p in actuals.index]
    ax.plot(index, actuals.to_numpy(), color="black", linewidth=1.6, label="actual", zorder=5)

    palette = plt.get_cmap("tab10")
    for i, (name, group) in enumerate(subset.groupby("model")):
        predicted = group.groupby("target")["predicted"].first()
        ax.plot(
            [p.to_timestamp(how="start") for p in predicted.index],
            predicted.to_numpy(),
            linewidth=0.9,
            alpha=0.8,
            color=palette(i % 10),
            label=name,
        )

    ax.set_title(f"Forecast vs actual, horizon h={horizon}")
    ax.set_ylabel("pilgrims per month")
    ax.yaxis.set_major_formatter(lambda v, _: f"{v/1e5:.1f}L" if v >= 1e5 else f"{v:,.0f}")
    ax.legend(fontsize=7, ncol=5, loc="upper left", framealpha=0.9)
    _style(ax)
    return _save(fig, path)


def regime_ranking(table: pd.DataFrame, path: Path, metric: str = "mase") -> Path:
    """Per-model score in each regime, side by side. The inversion, if there is one.

    Models are ordered by their clean score, so an inversion shows up as the
    shock bars running against the sorted order rather than with it.
    """
    if regimes.CLEAN not in table.columns or regimes.SHOCK not in table.columns:
        raise ConfigError(
            f"Per-regime table lacks both regimes; has {list(table.columns)}. "
            "With only one regime present there is no comparison to draw."
        )

    ordered = table.sort_values(regimes.CLEAN)
    y = np.arange(len(ordered))
    height = 0.38

    fig, ax = plt.subplots(figsize=(8.5, 0.52 * len(ordered) + 2.0))
    ax.barh(y + height / 2, ordered[regimes.CLEAN], height, label="clean", color=CLEAN_COLOUR)
    ax.barh(y - height / 2, ordered[regimes.SHOCK], height, label="shock", color=SHOCK_COLOUR)
    ax.set_yticks(y, ordered.index)
    ax.invert_yaxis()
    ax.set_xlabel(f"mean {metric.upper()} (lower is better)")
    ax.set_title(f"{metric.upper()} by regime, models ordered by clean-month score")
    ax.legend(fontsize=8)
    _style(ax)
    return _save(fig, path)


def rank_shift(table: pd.DataFrame, path: Path) -> Path:
    """A slope chart of each model's rank in one regime against the other.

    Crossing lines are the finding, stated as directly as it can be stated: a
    model that sits near the top on clean months and near the bottom on shock
    months draws a line straight through the middle of the plot.
    """
    left, right = f"{regimes.CLEAN}_rank", f"{regimes.SHOCK}_rank"
    if left not in table.columns or right not in table.columns:
        raise ConfigError(f"Per-regime table lacks rank columns; has {list(table.columns)}.")

    fig, ax = plt.subplots(figsize=(6.4, 0.52 * len(table) + 2.0))
    palette = plt.get_cmap("tab10")
    for i, (name, row) in enumerate(table.iterrows()):
        inverted = row[right] > row[left]
        ax.plot(
            [0, 1],
            [row[left], row[right]],
            marker="o",
            linewidth=2.0 if inverted else 1.0,
            alpha=0.95 if inverted else 0.55,
            color=palette(i % 10),
        )
        ax.annotate(name, xy=(-0.02, row[left]), ha="right", va="center", fontsize=8)
        ax.annotate(f"{int(row[right])}", xy=(1.02, row[right]), ha="left", va="center", fontsize=8)

    ax.set_xlim(-0.55, 1.35)
    ax.set_xticks([0, 1], ["clean", "shock"])
    ax.invert_yaxis()
    ax.set_ylabel("rank (1 = best)")
    ax.set_title("Does the ranking invert?")
    ax.grid(True, axis="y", color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    return _save(fig, path)


def horizon_profile(frame: pd.DataFrame, path: Path, metric: str = "mase") -> Path:
    """Each model's score against forecast lead time, one panel per regime.

    The leaderboard pools h=1..6. If the inversion lived only at the long
    horizons, the pooled table would look identical and a planner forecasting
    one month out would be reading a claim that did not apply to them. Two
    panels, so the crossing is visible at every lead time or not at all.

    The panels do **not** share a y-axis. Shock-month errors are several times
    larger, and forcing one scale would flatten the clean panel into a line.
    The axis labels carry the scales; the comparison being made here is within
    a panel, not across them.
    """
    if "horizon" not in frame.columns:
        raise ConfigError("Scored frame has no 'horizon' column to profile.")
    present = [r for r in (regimes.CLEAN, regimes.SHOCK) if (frame["regime"] == r).any()]
    if len(present) < 2:
        raise ConfigError(
            f"Only regime(s) {present} present, so there is no per-horizon "
            "comparison to draw."
        )

    pooled = frame.pivot_table(index="model", columns="regime", values=metric, aggfunc="mean")
    ordered = list(pooled.sort_values(regimes.CLEAN).index)
    palette = plt.get_cmap("tab10")
    colours = {model: palette(i % 10) for i, model in enumerate(ordered)}

    fig, axes = plt.subplots(1, 2, figsize=(11.0, 4.6))
    for ax, regime in zip(axes, (regimes.CLEAN, regimes.SHOCK)):
        subset = frame[frame["regime"] == regime]
        grid = subset.pivot_table(index="horizon", columns="model", values=metric, aggfunc="mean")
        for model in ordered:
            if model not in grid.columns:
                continue
            ax.plot(grid.index, grid[model], marker="o", markersize=3.5,
                    linewidth=1.6, color=colours[model], label=model)
        ax.set_xlabel("forecast horizon (months ahead)")
        ax.set_ylabel(f"mean {metric.upper()} (lower is better)")
        ax.set_xticks(sorted(int(h) for h in grid.index))
        ax.set_title(f"{regime} months")
        _style(ax)

    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=min(len(labels), 5), fontsize=8,
               frameon=False, bbox_to_anchor=(0.5, -0.02))
    fig.suptitle("Does the ranking invert at every lead time?", fontsize=11)
    fig.tight_layout(rect=(0, 0.09, 1, 1))
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=DPI)
    plt.close(fig)
    return path


def bootstrap_intervals(frame: pd.DataFrame, path: Path) -> Path:
    """Per-regime means with their bootstrap intervals, and the rho interval.

    Overlapping intervals are the honest answer when they overlap. This figure
    exists so that a difference of a few percent between two models cannot be
    read as a ranking without the reader also seeing how wide the bands are.
    """
    means = frame[frame["statistic"].str.startswith("mean_")]
    if means.empty:
        raise ConfigError("bootstrap.csv contains no mean_* rows.")

    order = (
        means[means["regime"] == regimes.CLEAN]
        .sort_values("point")["model"]
        .tolist()
    )
    fig, ax = plt.subplots(figsize=(8.5, 0.55 * len(order) + 2.2))
    offsets = {regimes.CLEAN: 0.16, regimes.SHOCK: -0.16}
    colours = {regimes.CLEAN: CLEAN_COLOUR, regimes.SHOCK: SHOCK_COLOUR}

    for regime, offset in offsets.items():
        subset = means[means["regime"] == regime].set_index("model").reindex(order)
        y = np.arange(len(order)) + offset
        ax.errorbar(
            subset["point"],
            y,
            xerr=[
                (subset["point"] - subset["lo"]).clip(lower=0),
                (subset["hi"] - subset["point"]).clip(lower=0),
            ],
            fmt="o",
            markersize=4,
            capsize=3,
            linewidth=1.2,
            color=colours[regime],
            label=regime,
        )

    ax.set_yticks(np.arange(len(order)), order)
    ax.invert_yaxis()
    ax.set_xlabel("mean MASE with bootstrap interval")

    rho = frame[frame["statistic"] == "rank_correlation"]
    subtitle = ""
    if not rho.empty:
        row = rho.iloc[0]
        confidence = int(round(100 * float(row["confidence"])))
        subtitle = (
            f"\nclean-vs-shock rank correlation {row['point']:.2f} "
            f"[{row['lo']:.2f}, {row['hi']:.2f}] at {confidence}%"
        )
    ax.set_title("Per-regime accuracy, with resampling uncertainty" + subtitle, fontsize=10)
    ax.legend(fontsize=8)
    _style(ax)
    return _save(fig, path)


def _save(fig, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(path, dpi=DPI)
    plt.close(fig)
    return path


def build_all(
    observations: pd.Series,
    frame: pd.DataFrame,
    table: pd.DataFrame,
    windows: list[regimes.ShockWindow],
    directory: Path,
    bootstrap_frame: pd.DataFrame | None = None,
) -> list[Path]:
    """Every figure, in one call. Returns the paths written."""
    directory = Path(directory)
    written = [
        series_with_shocks(observations, windows, directory / "series_shocks.png"),
        forecast_vs_actual(frame, windows, directory / "forecast_vs_actual_h1.png", horizon=1),
        regime_ranking(table, directory / "regime_ranking.png"),
        rank_shift(table, directory / "rank_shift.png"),
        horizon_profile(frame, directory / "horizon_profile.png"),
    ]
    if bootstrap_frame is not None and not bootstrap_frame.empty:
        written.append(
            bootstrap_intervals(bootstrap_frame, directory / "bootstrap_intervals.png")
        )
    return written

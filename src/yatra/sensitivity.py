"""Does the finding survive a different definition of "shock"?

The headline claim is a comparison across a line, and the line is drawn by hand
in ``shocks.yaml``. A result that flips when the boundary moves by a month is
not a result about forecasting; it is a result about where somebody put the
boundary. This module scores the same forecasts under several window
definitions and reports whether the ranking, and the inversion, hold.

**Why this is cheap.** No model ever receives a shock label (CLAUDE.md 3.4), so
the forecasts in ``results/metrics.csv`` do not depend on the window definitions
at all. Re-labelling is a join, not a refit: an arm costs milliseconds where a
full backtest costs half an hour. Had windows been model inputs, this analysis
would be unaffordable and the boundary choice would go untested -- which is
precisely how a boundary artefact gets published as a finding.

Arms are declared in ``experiments/configs/backtest.yaml`` under
``sensitivity.arms``, each naming a shocks file. Every arm is loaded through the
same :func:`yatra.regimes.load_windows`, so an arm with an uncited window raises
exactly as the primary one would.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import yaml

from . import backtest, metrics, regimes
from .errors import ConfigError


@dataclass(frozen=True)
class Arm:
    name: str
    path: Path
    description: str = ""


def load_arms(path: str | Path = "experiments/configs/backtest.yaml") -> list[Arm]:
    """Read the declared sensitivity arms. The primary windows are always first."""
    path = Path(path)
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    block = raw.get("sensitivity") or {}
    entries = block.get("arms") or []

    arms = [
        Arm("declared", Path("experiments/configs/shocks.yaml"),
            "the owner's declared windows, as shipped")
    ]
    for entry in entries:
        if "name" not in entry or "shocks" not in entry:
            raise ConfigError(
                f"sensitivity arm {entry!r} needs both 'name' and 'shocks'."
            )
        arms.append(
            Arm(str(entry["name"]), Path(str(entry["shocks"])),
                str(entry.get("description", "")))
        )

    seen = [a.name for a in arms]
    if len(set(seen)) != len(seen):
        raise ConfigError(f"Duplicate sensitivity arm names: {seen}.")
    return arms


def run(frame: pd.DataFrame, arms: list[Arm]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Score ``frame`` under every arm.

    Returns ``(per_model, summary)``: the first has one row per arm per model
    with its per-regime scores and ranks, the second one row per arm with the
    inversion statistic.
    """
    if len(arms) < 2:
        raise ConfigError(
            "A sensitivity analysis needs at least two arms. With one, there is "
            "nothing to be sensitive to."
        )

    per_model_rows = []
    summary_rows = []

    for arm in arms:
        if not arm.path.exists():
            raise ConfigError(f"Sensitivity arm '{arm.name}' names a missing file: {arm.path}")
        windows = regimes.load_windows(arm.path)
        labelled = backtest.relabel(frame, windows)
        table = backtest.per_regime_table(labelled)

        if regimes.SHOCK not in table.columns:
            raise ConfigError(
                f"Arm '{arm.name}' labels no month as a shock, so it produces no "
                "comparison. Check the window dates against the observation span."
            )

        shock_per_model = int(
            (labelled["regime"] == regimes.SHOCK).sum() / labelled["model"].nunique()
        )
        rho, p_value = metrics.rank_correlation(table[regimes.CLEAN], table[regimes.SHOCK])

        for model, row in table.iterrows():
            per_model_rows.append(
                {
                    "arm": arm.name,
                    "model": model,
                    "clean": row[regimes.CLEAN],
                    "shock": row[regimes.SHOCK],
                    "clean_rank": int(row[f"{regimes.CLEAN}_rank"]),
                    "shock_rank": int(row[f"{regimes.SHOCK}_rank"]),
                }
            )

        summary_rows.append(
            {
                "arm": arm.name,
                "windows": str(arm.path),
                "description": arm.description,
                "n_windows": len(windows),
                "shock_forecasts_per_model": shock_per_model,
                "rank_correlation": rho,
                "p_value": p_value,
                "inverts": bool(rho < 0),
            }
        )

    return pd.DataFrame(per_model_rows), pd.DataFrame(summary_rows)


def agreement(per_model: pd.DataFrame) -> dict:
    """How far the arms agree. The actual question this module exists to answer."""
    arms = list(dict.fromkeys(per_model["arm"]))
    baseline = per_model[per_model["arm"] == arms[0]].set_index("model")

    changed_clean, changed_shock = set(), set()
    for arm in arms[1:]:
        other = per_model[per_model["arm"] == arm].set_index("model")
        shared = baseline.index.intersection(other.index)
        for model in shared:
            if baseline.loc[model, "clean_rank"] != other.loc[model, "clean_rank"]:
                changed_clean.add(model)
            if baseline.loc[model, "shock_rank"] != other.loc[model, "shock_rank"]:
                changed_shock.add(model)

    return {
        "arms": arms,
        "clean_rank_changes": sorted(changed_clean),
        "shock_rank_changes": sorted(changed_shock),
        "rankings_identical": not changed_clean and not changed_shock,
    }


def write(per_model: pd.DataFrame, summary: pd.DataFrame, directory: str | Path = "results") -> list[Path]:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, frame in (("sensitivity.csv", per_model), ("sensitivity_summary.csv", summary)):
        destination = directory / name
        frame.to_csv(destination, index=False)
        paths.append(destination)
    return paths

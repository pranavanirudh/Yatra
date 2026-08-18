"""Error measures, and the single definition of the MASE denominator.

The denominator is the load-bearing part. MASE is only comparable across models
if they share a scale, and only comparable across regimes if that scale does not
itself depend on the regime. Both properties come from computing it once per
forecast origin, from the training window alone, and handing the same number to
every model -- see :func:`seasonal_naive_scale` and CLAUDE.md 3.2.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

SEASONAL_PERIOD = 12


def seasonal_naive_scale(train: pd.Series, m: int = SEASONAL_PERIOD) -> float:
    """In-sample seasonal-naive MAE over the training window: the MASE denominator.

    ``mean(|y_t - y_{t-m}|)`` for every ``t`` where ``y_{t-m}`` exists.

    Computed from the training window that ends at the forecast origin, so it
    uses no information the models did not also have. Computed once per origin
    and shared, so a model cannot be flattered by a scale of its own.

    Raises
    ------
    ValueError
        If the window is too short to form a single seasonal difference, or if
        the series is exactly seasonally constant. A zero scale would make every
        MASE infinite, which is worth crashing over rather than propagating as
        ``inf`` into a mean.
    """
    values = np.asarray(train, dtype="float64")
    if len(values) <= m:
        raise ValueError(
            f"Need more than {m} observations to form a seasonal-naive scale; "
            f"got {len(values)}."
        )

    diffs = np.abs(values[m:] - values[:-m])
    scale = float(np.mean(diffs))
    if not np.isfinite(scale) or scale == 0.0:
        raise ValueError(
            "Seasonal-naive scale is zero or non-finite: the training window is "
            "seasonally constant, so MASE is undefined here. This is a property "
            "of the window, not of any model."
        )
    return scale


def mase(actual: np.ndarray, predicted: np.ndarray, scale: float) -> np.ndarray:
    """Per-forecast MASE. ``scale`` comes from :func:`seasonal_naive_scale`."""
    if scale <= 0 or not np.isfinite(scale):
        raise ValueError(f"MASE scale must be positive and finite, got {scale!r}.")
    return np.abs(np.asarray(actual, dtype="float64") - np.asarray(predicted, dtype="float64")) / scale


def absolute_error(actual: np.ndarray, predicted: np.ndarray) -> np.ndarray:
    return np.abs(np.asarray(actual, dtype="float64") - np.asarray(predicted, dtype="float64"))


def squared_error(actual: np.ndarray, predicted: np.ndarray) -> np.ndarray:
    diff = np.asarray(actual, dtype="float64") - np.asarray(predicted, dtype="float64")
    return diff**2


def smape(actual: np.ndarray, predicted: np.ndarray) -> np.ndarray:
    """Symmetric MAPE in percent, ``200|F-A| / (|A|+|F|)``.

    Reported alongside MASE rather than instead of it. sMAPE is unstable exactly
    where this project's interesting months are -- when actuals collapse toward
    zero during a closure, the denominator collapses with them. The COVID window
    contains months of that kind, so treat sMAPE there as descriptive only.
    """
    a = np.asarray(actual, dtype="float64")
    f = np.asarray(predicted, dtype="float64")
    denom = np.abs(a) + np.abs(f)
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.where(denom == 0, 0.0, 200.0 * np.abs(f - a) / denom)
    return out


def rank_correlation(left: pd.Series, right: pd.Series) -> tuple[float, float]:
    """Spearman correlation between two model rankings, keyed by model name.

    Both series are indexed by model and hold a score where lower is better. The
    returned correlation is between the RANKS, so a negative value means the
    ordering inverts: models that win on one side lose on the other.

    Returns ``(rho, p_value)``. With a registry this small the p-value is weak
    evidence at best -- nine points cannot carry much -- which is why Step 2
    puts a bootstrap interval around the rho instead of leaning on it.
    """
    shared = left.index.intersection(right.index)
    if len(shared) < 3:
        raise ValueError(
            f"Need at least 3 models in common to rank-correlate, got {len(shared)}."
        )
    result = stats.spearmanr(left.loc[shared].to_numpy(), right.loc[shared].to_numpy())
    return float(result.statistic), float(result.pvalue)

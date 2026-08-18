"""Block bootstrap over forecast origins. Writes ``results/bootstrap.csv``.

The headline claim of this project is a comparison: model rankings on clean
months versus on shock months. A single Spearman rho between those two rankings
is one number computed from a handful of models over one particular history, and
on its own it cannot say whether an inversion is real or is the shape this
particular run happened to take. That is what this stage is for.

**The resampling unit is the origin, not the row.** Every forecast made from one
origin shares a training window and shares the MASE denominator computed at that
origin, so the rows within an origin are not independent draws. Resampling rows
would treat six correlated horizons as six independent observations and would
report an interval far tighter than the evidence supports -- narrow intervals
around a wrong number being precisely the failure this project is built against.

**Blocks, not single origins.** Origins step monthly over expanding training
windows, so neighbouring origins share almost all of their data and their errors
run in streaks. Resampling origins independently would break that serial
dependence and again understate the interval. Contiguous blocks preserve it.

Percentile intervals rather than BCa: the statistics here are a mean and a rank
correlation over a modest number of origins, the bias correction would be
estimated from the same thin sample it was meant to correct, and a percentile
interval is the one whose assumptions are easiest to state honestly.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from . import metrics, regimes
from .errors import ConfigError

DEFAULT_RESAMPLES = 2000
DEFAULT_BLOCK = 12
DEFAULT_CONFIDENCE = 0.95


@dataclass(frozen=True)
class BootstrapConfig:
    n_resamples: int
    block_origins: int
    confidence: float
    seed: int
    metric: str

    @property
    def alpha(self) -> float:
        return 1.0 - self.confidence


def load_config(path: str | Path = "experiments/configs/backtest.yaml") -> BootstrapConfig:
    """Read the ``bootstrap:`` block. Nothing numeric is defaulted silently."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"{path} not found.")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    block = raw.get("bootstrap") or {}

    config = BootstrapConfig(
        n_resamples=int(block.get("n_resamples", DEFAULT_RESAMPLES)),
        block_origins=int(block.get("block_origins", DEFAULT_BLOCK)),
        confidence=float(block.get("confidence", DEFAULT_CONFIDENCE)),
        seed=int(block.get("seed", raw.get("seed", 0))),
        metric=str(block.get("metric", "mase")),
    )
    if config.n_resamples < 100:
        raise ConfigError(
            f"bootstrap.n_resamples is {config.n_resamples}. A percentile "
            "interval from fewer than a few hundred resamples has its endpoints "
            "set by a handful of draws."
        )
    if config.block_origins < 1:
        raise ConfigError(f"bootstrap.block_origins must be >= 1, got {config.block_origins}.")
    if not 0.5 < config.confidence < 1.0:
        raise ConfigError(f"bootstrap.confidence must be in (0.5, 1), got {config.confidence}.")
    return config


# --------------------------------------------------------------------------
# Resampling.
# --------------------------------------------------------------------------


def _blocks(n_origins: int, block: int, rng: np.random.Generator) -> np.ndarray:
    """Moving-block resample of origin positions, length ``n_origins``."""
    if block >= n_origins:
        # One block cannot be shorter than the series it is drawn from; fall
        # back to resampling the whole ordered set, which is the honest
        # degenerate case rather than an error.
        return np.arange(n_origins)
    n_blocks = int(np.ceil(n_origins / block))
    starts = rng.integers(0, n_origins - block + 1, size=n_blocks)
    return np.concatenate([np.arange(s, s + block) for s in starts])[:n_origins]


def _group_means(
    values: np.ndarray, model_index: np.ndarray, regime_index: np.ndarray, n_models: int
) -> np.ndarray:
    """Mean of ``values`` per (model, regime). Returns shape ``(n_models, 2)``.

    Cells with no rows come back as NaN rather than zero: a resample that drew
    no shock months has no shock mean, and calling that zero would be inventing
    a perfect score.
    """
    key = model_index * 2 + regime_index
    totals = np.bincount(key, weights=values, minlength=n_models * 2)
    counts = np.bincount(key, minlength=n_models * 2)
    with np.errstate(invalid="ignore", divide="ignore"):
        means = np.where(counts > 0, totals / np.maximum(counts, 1), np.nan)
    return means.reshape(n_models, 2)


def run(frame: pd.DataFrame, config: BootstrapConfig) -> pd.DataFrame:
    """Bootstrap the per-regime means and the inversion statistic.

    Returns a long frame: one row per statistic, with a point estimate from the
    observed data and a percentile interval from the resamples.
    """
    required = {"origin", "model", "regime", config.metric}
    missing = required - set(frame.columns)
    if missing:
        raise ConfigError(f"metrics frame is missing columns {sorted(missing)}.")

    models = sorted(frame["model"].unique())
    origins = sorted(frame["origin"].unique())
    if len(origins) < 2:
        raise ConfigError(
            f"Bootstrapping needs at least 2 origins, got {len(origins)}. "
            "An interval over a single origin describes nothing."
        )

    model_index = frame["model"].map({m: i for i, m in enumerate(models)}).to_numpy()
    regime_index = (frame["regime"].to_numpy() == regimes.SHOCK).astype(int)
    values = frame[config.metric].to_numpy(dtype="float64")

    positions = {origin: i for i, origin in enumerate(origins)}
    rows_by_origin = [
        np.flatnonzero(frame["origin"].map(positions).to_numpy() == i)
        for i in range(len(origins))
    ]

    observed = _group_means(values, model_index, regime_index, len(models))
    observed_rho = _rho(observed, models)

    rng = np.random.default_rng(config.seed)
    draws = np.full((config.n_resamples, len(models), 2), np.nan)
    rhos = np.full(config.n_resamples, np.nan)

    for b in range(config.n_resamples):
        picked = _blocks(len(origins), config.block_origins, rng)
        rows = np.concatenate([rows_by_origin[i] for i in picked])
        draws[b] = _group_means(
            values[rows], model_index[rows], regime_index[rows], len(models)
        )
        rhos[b] = _rho(draws[b], models)

    return _assemble(models, observed, observed_rho, draws, rhos, config)


def _rho(means: np.ndarray, models: list[str]) -> float:
    """Spearman rho between the clean and shock rankings implied by ``means``.

    NaN when either side is missing for too many models -- a resample that drew
    almost no shock months cannot speak to whether rankings invert, and saying
    so is better than ranking around the holes.
    """
    clean, shock = means[:, 0], means[:, 1]
    usable = np.isfinite(clean) & np.isfinite(shock)
    if usable.sum() < 3:
        return float("nan")
    left = pd.Series(clean[usable], index=[m for m, ok in zip(models, usable) if ok])
    right = pd.Series(shock[usable], index=left.index)
    try:
        rho, _ = metrics.rank_correlation(left, right)
    except ValueError:
        return float("nan")
    return rho


def _pairwise(
    draws: np.ndarray, models: list[str]
) -> list[dict]:
    """P(model A scores better than model B) in each regime, over the resamples.

    This is the statistic that carries the claims anyone actually makes from
    this project -- "use the naive forecast during a closure" is a statement
    about two models, not about the ordering of eight.

    It is also far tighter than the rank correlation, and for a structural
    reason rather than a lucky one. Spearman's rho over eight models has to
    estimate a whole permutation from a sample that contains only a handful of
    disrupted months, and one model swapping places with its neighbour moves it.
    A pairwise proportion asks one binary question per resample, so the same
    evidence buys a far more precise answer to a far narrower question. Both are
    reported because they answer different things: rho asks whether the *whole*
    ordering reverses, the pairs ask whether a *specific* substitution pays.

    Lower MASE is better, so A beats B when A's mean is the smaller of the two.
    """
    rows = []
    for regime_index, regime in enumerate((regimes.CLEAN, regimes.SHOCK)):
        for i, left in enumerate(models):
            for j, right in enumerate(models):
                if i == j:
                    continue
                a = draws[:, i, regime_index]
                b = draws[:, j, regime_index]
                usable = np.isfinite(a) & np.isfinite(b)
                if usable.sum() == 0:
                    continue
                rows.append(
                    {
                        "statistic": "p_beats",
                        "model": left,
                        "opponent": right,
                        "regime": regime,
                        "point": float(np.mean(a[usable] < b[usable])),
                        "lo": float("nan"),
                        "hi": float("nan"),
                        "n_usable": int(usable.sum()),
                    }
                )
    return rows


def _interval(samples: np.ndarray, config: BootstrapConfig) -> tuple[float, float, int]:
    finite = samples[np.isfinite(samples)]
    if len(finite) < 2:
        return float("nan"), float("nan"), len(finite)
    lo = float(np.percentile(finite, 100 * config.alpha / 2))
    hi = float(np.percentile(finite, 100 * (1 - config.alpha / 2)))
    return lo, hi, len(finite)


def _assemble(
    models: list[str],
    observed: np.ndarray,
    observed_rho: float,
    draws: np.ndarray,
    rhos: np.ndarray,
    config: BootstrapConfig,
) -> pd.DataFrame:
    rows: list[dict] = []
    for i, model in enumerate(models):
        for j, regime in enumerate((regimes.CLEAN, regimes.SHOCK)):
            lo, hi, n = _interval(draws[:, i, j], config)
            rows.append(
                {
                    "statistic": f"mean_{config.metric}",
                    "model": model,
                    "opponent": pd.NA,
                    "regime": regime,
                    "point": observed[i, j],
                    "lo": lo,
                    "hi": hi,
                    "n_usable": n,
                }
            )

    lo, hi, n = _interval(rhos, config)
    rows.append(
        {
            "statistic": "rank_correlation",
            "model": pd.NA,
            "opponent": pd.NA,
            "regime": "clean_vs_shock",
            "point": observed_rho,
            "lo": lo,
            "hi": hi,
            "n_usable": n,
        }
    )

    # The share of resamples in which the ranking actually inverted. This is the
    # question in plain terms -- "how often does the ordering flip" -- and it
    # does not depend on rho's sampling distribution being symmetric.
    finite = rhos[np.isfinite(rhos)]
    rows.append(
        {
            "statistic": "p_inversion",
            "model": pd.NA,
            "opponent": pd.NA,
            "regime": "clean_vs_shock",
            "point": float(np.mean(finite < 0)) if len(finite) else float("nan"),
            "lo": float("nan"),
            "hi": float("nan"),
            "n_usable": len(finite),
        }
    )

    rows.extend(_pairwise(draws, models))

    out = pd.DataFrame(rows)
    out["n_resamples"] = config.n_resamples
    out["block_origins"] = config.block_origins
    out["confidence"] = config.confidence
    out["seed"] = config.seed
    return out


def write(frame: pd.DataFrame, path: str | Path = "results/bootstrap.csv") -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    return path


def read(path: str | Path = "results/bootstrap.csv") -> pd.DataFrame:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run `python make.py bootstrap` first."
        )
    return pd.read_csv(path)

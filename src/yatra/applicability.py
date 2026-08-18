"""Which models can be fit at all, and where they cannot.

A model that cannot produce a forecast has no row in ``results/metrics.csv``, so
it silently vanishes from every table. That absence is itself a result and this
module measures it rather than leaving it to a comment in a config file.

The case that prompted it: Holt-Winters with multiplicative seasonality needs
every value in its training window to be above zero, because it divides by the
seasonal index. The shrine was shut for part of 2020 and those months are
published as zero. From the first origin whose history includes a closed month,
the model cannot be fit at all -- not badly, not approximately, at all.

**No fallback.** The obvious "fix" is to quietly fit additive seasonality
instead. That would put a number in the table under the multiplicative model's
name, and nothing downstream could tell the difference. It is the same failure
this project was built against, so :mod:`yatra.models` raises instead, and
``tests/test_applicability.py`` asserts no fallback has been added.

What is written here is a per-model count of origins where the fit is possible
and where it is not, with the reason. "Inapplicable to a series containing a
total closure" is a finding about forecasting through shocks, and it belongs
next to the accuracy tables rather than in a footnote.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from . import backtest, models
from .errors import ConfigError


@dataclass(frozen=True)
class Outcome:
    model: str
    origins_total: int
    origins_fittable: int
    first_failure: str | None
    reason: str | None

    @property
    def origins_failed(self) -> int:
        return self.origins_total - self.origins_fittable

    @property
    def applicable(self) -> bool:
        return self.origins_failed == 0


def probe(
    series: pd.Series,
    config: backtest.BacktestConfig,
    model_names: list[str],
    calendar: pd.DataFrame | None = None,
) -> list[Outcome]:
    """Try to fit each named model at every origin. Record where it cannot be.

    Only the *fit* is attempted, at the shortest horizon, because the question
    is whether the model is defined on the window -- not how accurate it is.
    Accuracy is the backtest's job and is only meaningful for models that get
    that far.
    """
    origins = backtest.build_origins(series, config)
    if not origins:
        raise ConfigError("No usable origins; cannot probe applicability.")

    outcomes = []
    for name in model_names:
        if name not in models.REGISTRY:
            raise ConfigError(f"Unknown model {name!r}.")

        fittable = 0
        first_failure: str | None = None
        reason: str | None = None

        for position in origins:
            train = series.iloc[: position + 1]
            window = None
            if name in models.NEEDS_CALENDAR and calendar is not None:
                window = calendar
            try:
                models.predict(name, train, [config.horizons[0]], calendar=window)
                fittable += 1
            except Exception as exc:  # noqa: BLE001 - the failure is the measurement
                if first_failure is None:
                    first_failure = f"{series.index[position]:%Y-%m}"
                    reason = f"{type(exc).__name__}: {str(exc).splitlines()[0]}"

        outcomes.append(
            Outcome(
                model=name,
                origins_total=len(origins),
                origins_fittable=fittable,
                first_failure=first_failure,
                reason=reason,
            )
        )
    return outcomes


def to_frame(outcomes: list[Outcome]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "model": o.model,
                "applicable": o.applicable,
                "origins_total": o.origins_total,
                "origins_fittable": o.origins_fittable,
                "origins_failed": o.origins_failed,
                "first_failure_origin": o.first_failure,
                "reason": o.reason,
            }
            for o in outcomes
        ]
    )


def write(frame: pd.DataFrame, path: str | Path = "results/applicability.csv") -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    return path


def read(path: str | Path = "results/applicability.csv") -> pd.DataFrame | None:
    path = Path(path)
    if not path.exists():
        return None
    return pd.read_csv(path)


def excluded_models(config: backtest.BacktestConfig) -> list[str]:
    """Registered models that the backtest config leaves out.

    These are exactly the ones worth probing: anything the backtest scored is
    provably fittable at every origin, because the run asserts a rectangular
    panel and would have aborted otherwise.
    """
    return sorted(set(models.REGISTRY) - set(config.model_names))

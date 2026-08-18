"""Model behaviour.

The benchmark models are checked against exact arithmetic on literal sequences.
The estimator wrappers are checked for shape and finiteness on a deterministic
numeric probe -- see the note in ``_probe``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from yatra import models
from yatra.errors import CalendarRoutingError, ConfigError

HORIZONS = [1, 2, 3, 4, 5, 6]


def series(values, start="1990-01") -> pd.Series:
    index = pd.period_range(start, periods=len(values), freq="M").to_timestamp(how="start")
    return pd.Series(np.asarray(values, dtype="float64"), index=index).asfreq("MS")


def _probe(n: int = 96) -> pd.Series:
    """A deterministic ramp with a seasonal wave.

    This is a numeric probe for the estimator wrappers, not data. It never
    leaves the test process, never reaches results/, and supports no claim about
    footfall -- it exists so that a statsmodels API change fails here loudly
    rather than surfacing as a moved decimal in a published table.
    """
    t = np.arange(n, dtype="float64")
    return series(1000.0 + 5.0 * t + 200.0 * np.sin(2 * np.pi * t / 12.0))


# --- benchmarks, exact -----------------------------------------------------


def test_naive_repeats_the_last_value():
    out = models.predict("naive", series([10.0, 20.0, 30.0]), [1, 2, 3])
    assert out == pytest.approx([30.0, 30.0, 30.0])


def test_seasonal_naive_reaches_back_twelve_months():
    values = list(range(100, 124))  # 24 months, last is 123
    out = models.predict("seasonal_naive", series(values), [1, 6])
    # h=1 -> the month 12 before the target -> index -12 -> 112
    # h=6 -> index -7 -> 117
    assert out == pytest.approx([112.0, 117.0])


def test_seasonal_naive_needs_a_full_season():
    with pytest.raises(ValueError, match="at least 12"):
        models.predict("seasonal_naive", series(list(range(6))), [1])


def test_drift_extends_the_average_slope():
    # 0..10 over 11 points -> slope 1.0 per step, last value 10.
    out = models.predict("drift", series([float(v) for v in range(11)]), [1, 4])
    assert out == pytest.approx([11.0, 14.0])


def test_drift_needs_two_points():
    with pytest.raises(ValueError, match="at least 2"):
        models.predict("drift", series([1.0]), [1])


@pytest.mark.parametrize("name", ["naive", "seasonal_naive", "drift"])
def test_benchmarks_ignore_horizon_order_consistently(name):
    train = series([float(v) for v in range(100, 130)])
    forward = models.predict(name, train, [1, 2, 3])
    reversed_ = models.predict(name, train, [3, 2, 1])
    assert forward == pytest.approx(reversed_[::-1])


# --- estimator wrappers ----------------------------------------------------


@pytest.mark.parametrize(
    "name", ["theta", "holt_winters_add", "holt_winters_mul", "sarima"]
)
def test_estimators_return_one_finite_value_per_horizon(name):
    out = models.predict(name, _probe(), HORIZONS)
    assert out.shape == (len(HORIZONS),)
    assert np.isfinite(out).all()


def test_holt_winters_mul_refuses_a_window_containing_zero():
    """A closure month makes multiplicative seasonality undefined. Report it."""
    values = _probe().to_numpy()
    values[40] = 0.0
    with pytest.raises(ValueError, match="strictly positive"):
        models.predict("holt_winters_mul", series(values), HORIZONS)


# --- calendar routing ------------------------------------------------------


def test_calendar_model_refuses_to_fit_without_features():
    """The named failure mode: an arm that trains featureless reads as a null."""
    with pytest.raises(CalendarRoutingError, match="Refusing"):
        models.predict("sarimax_cal", _probe(), HORIZONS, calendar=None)


def test_calendar_model_refuses_an_empty_frame():
    with pytest.raises(CalendarRoutingError):
        models.predict("sarimax_cal", _probe(), HORIZONS, calendar=pd.DataFrame())


def test_calendar_model_refuses_features_that_do_not_cover_training():
    train = _probe()
    short = pd.DataFrame(
        {"festival_days": np.ones(len(train) - 10)}, index=train.index[:-10]
    )
    with pytest.raises(CalendarRoutingError, match="do not cover the training window"):
        models.predict("sarimax_cal", train, HORIZONS, calendar=short)


def test_calendar_model_refuses_features_that_stop_at_the_origin():
    """Features must extend past the origin, or the forecast has no exog."""
    train = _probe()
    exact = pd.DataFrame({"festival_days": np.ones(len(train))}, index=train.index)
    with pytest.raises(CalendarRoutingError, match="do not extend past"):
        models.predict("sarimax_cal", train, HORIZONS, calendar=exact)


def test_calendar_model_runs_when_features_cover_the_forecast_span():
    train = _probe()
    index = pd.date_range(train.index[0], periods=len(train) + max(HORIZONS), freq="MS")
    t = np.arange(len(index), dtype="float64")
    features = pd.DataFrame({"festival_days": (t % 12 < 2).astype("float64")}, index=index)
    out = models.predict("sarimax_cal", train, HORIZONS, calendar=features)
    assert out.shape == (len(HORIZONS),)
    assert np.isfinite(out).all()


def test_non_calendar_models_are_not_handed_features():
    """Passing exog to a model that ignores it is how an ablation stops being one."""
    train = _probe()
    features = pd.DataFrame({"festival_days": np.ones(len(train))}, index=train.index)
    with_features = models.predict("sarima", train, HORIZONS, calendar=features)
    without = models.predict("sarima", train, HORIZONS, calendar=None)
    assert with_features == pytest.approx(without)


# --- dispatch --------------------------------------------------------------


def test_unknown_model_raises_and_lists_the_registry():
    with pytest.raises(ConfigError, match="Unknown model"):
        models.predict("holt_winters_multiplicative", _probe(), [1])

"""Models that cannot be fit, and the fallback that must never be added.

The temptation with `holt_winters_mul` is to catch the error and fit the
additive variant instead. That would place a number in the results table under
the multiplicative model's name, produced by a different model, with nothing
downstream able to tell. These tests exist so that change fails loudly.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from yatra import applicability, models

SRC = Path(models.__file__).parent


def series(values, start="1990-01") -> pd.Series:
    index = pd.period_range(start, periods=len(values), freq="M").to_timestamp(how="start")
    return pd.Series(np.asarray(values, dtype="float64"), index=index).asfreq("MS")


def clean(n: int = 144) -> np.ndarray:
    t = np.arange(n, dtype="float64")
    return 1000.0 + 2.0 * t + 300.0 * np.sin(2 * np.pi * t / 12.0)


def test_multiplicative_refuses_a_window_containing_a_zero():
    values = clean()
    values[100] = 0.0
    with pytest.raises(ValueError, match="strictly positive"):
        models.predict("holt_winters_mul", series(values), [1])


def test_multiplicative_still_works_when_every_month_is_positive():
    """The refusal must be about the zero, not about the model being broken."""
    out = models.predict("holt_winters_mul", series(clean()), [1, 2, 3])
    assert np.isfinite(out).all()


def test_no_silent_fallback_to_additive():
    """The specific bad fix, blocked structurally.

    If the multiplicative branch ever learns to catch its own error and call the
    additive one, the two models stop being distinguishable in the results.
    """
    text = (SRC / "models.py").read_text(encoding="utf-8")
    body = text[text.index("def holt_winters_mul"):]
    body = body[: body.index("def _sarimax")]
    assert "except" not in body, (
        "holt_winters_mul contains an exception handler. It must raise on a "
        "non-positive window, never substitute another model's forecast."
    )
    assert '"add"' not in body, (
        "holt_winters_mul references additive seasonality. A fallback here would "
        "report one model's numbers under another model's name."
    )


def test_probe_counts_the_origins_that_fail(tmp_path):
    """A model broken partway through the series is reported, not dropped."""
    from yatra import backtest

    values = clean(200)
    values[150] = 0.0
    data = series(values)

    config = backtest.BacktestConfig(
        min_train_months=120, step_months=10, horizons=[1], window="expanding",
        mase_seasonality=12, model_names=[], rectangular=True,
        on_model_failure="fail", config_hash="probe",
    )
    outcomes = applicability.probe(data, config, ["holt_winters_mul"])
    outcome = outcomes[0]

    assert not outcome.applicable
    assert outcome.origins_failed > 0
    assert outcome.origins_fittable > 0, "origins before the zero should still fit"
    assert outcome.first_failure is not None
    assert "strictly positive" in outcome.reason


def test_a_healthy_model_is_reported_as_applicable():
    from yatra import backtest

    config = backtest.BacktestConfig(
        min_train_months=120, step_months=10, horizons=[1], window="expanding",
        mase_seasonality=12, model_names=[], rectangular=True,
        on_model_failure="fail", config_hash="probe",
    )
    outcomes = applicability.probe(series(clean(200)), config, ["seasonal_naive"])
    assert outcomes[0].applicable
    assert outcomes[0].origins_failed == 0


def test_excluded_models_are_exactly_those_absent_from_the_config():
    from yatra import backtest

    config = backtest.load_config("experiments/configs/backtest.yaml")
    excluded = applicability.excluded_models(config)
    assert "holt_winters_mul" in excluded
    for name in config.model_names:
        assert name not in excluded

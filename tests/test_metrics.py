"""Error measures. Arithmetic on literals -- no observations involved."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from yatra import metrics


def test_seasonal_naive_scale_is_mean_absolute_seasonal_difference():
    # 1..24: every value is 12 greater than the one twelve steps back.
    train = pd.Series(range(1, 25), dtype="float64")
    assert metrics.seasonal_naive_scale(train, m=12) == pytest.approx(12.0)


def test_scale_needs_more_than_one_season():
    with pytest.raises(ValueError, match="Need more than 12"):
        metrics.seasonal_naive_scale(pd.Series(range(12), dtype="float64"), m=12)


def test_seasonally_constant_window_raises_rather_than_returning_zero():
    """A zero scale would send inf into a mean and quietly poison every table."""
    train = pd.Series([5.0] * 30)
    with pytest.raises(ValueError, match="seasonally constant"):
        metrics.seasonal_naive_scale(train, m=12)


def test_mase_divides_absolute_error_by_the_shared_scale():
    actual = np.array([100.0, 200.0])
    predicted = np.array([90.0, 260.0])
    assert metrics.mase(actual, predicted, scale=10.0) == pytest.approx([1.0, 6.0])


def test_mase_rejects_a_non_positive_scale():
    with pytest.raises(ValueError):
        metrics.mase(np.array([1.0]), np.array([2.0]), scale=0.0)


def test_absolute_and_squared_error():
    actual, predicted = np.array([10.0, -4.0]), np.array([7.0, 0.0])
    assert metrics.absolute_error(actual, predicted) == pytest.approx([3.0, 4.0])
    assert metrics.squared_error(actual, predicted) == pytest.approx([9.0, 16.0])


def test_smape_endpoints():
    assert metrics.smape(np.array([100.0]), np.array([100.0])) == pytest.approx([0.0])
    assert metrics.smape(np.array([100.0]), np.array([0.0])) == pytest.approx([200.0])


def test_smape_defines_zero_over_zero_as_zero():
    """Guarded rather than nan: a closure month with a zero forecast is exact."""
    assert metrics.smape(np.array([0.0]), np.array([0.0])) == pytest.approx([0.0])


def test_rank_correlation_detects_a_perfect_inversion():
    clean = pd.Series([1.0, 2.0, 3.0, 4.0], index=list("abcd"))
    shock = pd.Series([4.0, 3.0, 2.0, 1.0], index=list("abcd"))
    rho, _ = metrics.rank_correlation(clean, shock)
    assert rho == pytest.approx(-1.0)


def test_rank_correlation_detects_agreement():
    clean = pd.Series([1.0, 2.0, 3.0, 4.0], index=list("abcd"))
    rho, _ = metrics.rank_correlation(clean, clean * 10)
    assert rho == pytest.approx(1.0)


def test_rank_correlation_uses_only_shared_models():
    clean = pd.Series([1.0, 2.0, 3.0, 4.0], index=list("abcd"))
    shock = pd.Series([4.0, 3.0, 2.0], index=list("abc"))
    rho, _ = metrics.rank_correlation(clean, shock)
    assert rho == pytest.approx(-1.0)


def test_rank_correlation_refuses_too_few_models():
    left = pd.Series([1.0, 2.0], index=list("ab"))
    with pytest.raises(ValueError, match="at least 3"):
        metrics.rank_correlation(left, left)

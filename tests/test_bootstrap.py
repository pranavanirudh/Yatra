"""The block bootstrap.

The property that matters most here is the resampling unit. Forecasts made from
one origin share a training window and a MASE denominator, so they are not
independent draws; resampling rows instead of origins would report an interval
far tighter than the evidence supports, and a narrow interval around a wrong
number is worse than an honest wide one.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
import yaml

from yatra import bootstrap, regimes
from yatra.errors import ConfigError


def metrics_frame(n_origins: int = 40, shock_every: int = 5) -> pd.DataFrame:
    """A probe metrics table. Model 'winner' is better on clean, worse on shock."""
    rng = np.random.default_rng(3)
    rows = []
    for origin in range(n_origins):
        shock = origin % shock_every == 0
        regime = regimes.SHOCK if shock else regimes.CLEAN
        for horizon in (1, 2, 3):
            for name, clean_err, shock_err in (
                ("winner", 0.5, 4.0),
                ("loser", 2.0, 1.0),
                ("middle", 1.2, 2.0),
            ):
                base = shock_err if shock else clean_err
                rows.append(
                    {
                        "origin": pd.Period("2000-01", freq="M") + origin,
                        "target": pd.Period("2000-01", freq="M") + origin + horizon,
                        "horizon": horizon,
                        "model": name,
                        "regime": regime,
                        "mase": abs(base + rng.normal(0, 0.05)),
                    }
                )
    return pd.DataFrame(rows)


def config(**overrides) -> bootstrap.BootstrapConfig:
    base = dict(n_resamples=200, block_origins=4, confidence=0.9, seed=5, metric="mase")
    base.update(overrides)
    return bootstrap.BootstrapConfig(**base)


# --- config ----------------------------------------------------------------


def test_too_few_resamples_is_refused(tmp_path):
    path = tmp_path / "backtest.yaml"
    path.write_text(yaml.safe_dump({"bootstrap": {"n_resamples": 20}}), encoding="utf-8")
    with pytest.raises(ConfigError, match="n_resamples"):
        bootstrap.load_config(path)


def test_confidence_outside_the_unit_interval_is_refused(tmp_path):
    path = tmp_path / "backtest.yaml"
    path.write_text(yaml.safe_dump({"bootstrap": {"confidence": 1.5}}), encoding="utf-8")
    with pytest.raises(ConfigError, match="confidence"):
        bootstrap.load_config(path)


def test_the_shipped_config_loads():
    from pathlib import Path

    path = Path(__file__).resolve().parent.parent / "experiments/configs/backtest.yaml"
    loaded = bootstrap.load_config(path)
    assert loaded.n_resamples >= 100
    assert loaded.block_origins >= 1


# --- resampling ------------------------------------------------------------


def test_blocks_are_contiguous_and_the_right_length():
    rng = np.random.default_rng(0)
    picked = bootstrap._blocks(40, 5, rng)
    assert len(picked) == 40
    assert picked.min() >= 0 and picked.max() < 40
    # Each block of 5 must be a run of consecutive positions.
    for start in range(0, 40, 5):
        block = picked[start : start + 5]
        assert list(block) == list(range(block[0], block[0] + len(block)))


def test_a_block_longer_than_the_series_degrades_to_the_whole_set():
    rng = np.random.default_rng(0)
    picked = bootstrap._blocks(6, 99, rng)
    assert list(picked) == list(range(6))


def test_resampling_is_deterministic_under_a_seed():
    frame = metrics_frame()
    first = bootstrap.run(frame, config())
    second = bootstrap.run(frame, config())
    pd.testing.assert_frame_equal(first, second)


def test_a_different_seed_moves_the_interval():
    frame = metrics_frame()
    first = bootstrap.run(frame, config(seed=1))
    second = bootstrap.run(frame, config(seed=2))
    assert not np.allclose(first["lo"].to_numpy(), second["lo"].to_numpy(), equal_nan=True)


# --- statistics ------------------------------------------------------------


def test_point_estimates_match_the_observed_means():
    frame = metrics_frame()
    result = bootstrap.run(frame, config())
    means = result[result["statistic"] == "mean_mase"]
    for row in means.itertuples():
        expected = frame[
            (frame["model"] == row.model) & (frame["regime"] == row.regime)
        ]["mase"].mean()
        assert row.point == pytest.approx(expected)


def test_intervals_bracket_the_point_estimate():
    result = bootstrap.run(metrics_frame(), config())
    means = result[result["statistic"] == "mean_mase"]
    assert (means["lo"] <= means["point"] + 1e-9).all()
    assert (means["hi"] >= means["point"] - 1e-9).all()


def test_inversion_is_detected_when_it_is_there():
    """The probe frame is built so the ranking genuinely inverts."""
    result = bootstrap.run(metrics_frame(), config())
    rho = result[result["statistic"] == "rank_correlation"].iloc[0]
    assert rho["point"] < 0, "A frame constructed to invert must report rho < 0."
    inversion = result[result["statistic"] == "p_inversion"].iloc[0]
    assert 0.0 <= inversion["point"] <= 1.0
    assert inversion["point"] > 0.5


def test_no_inversion_reported_when_rankings_agree():
    """Same ordering in both regimes must not read as an inversion."""
    frame = metrics_frame()
    # Make every model's shock error proportional to its clean error.
    order = {"winner": 0.5, "middle": 1.2, "loser": 2.0}
    frame["mase"] = frame["model"].map(order) * np.where(
        frame["regime"] == regimes.SHOCK, 3.0, 1.0
    )
    result = bootstrap.run(frame, config())
    rho = result[result["statistic"] == "rank_correlation"].iloc[0]
    assert rho["point"] > 0


def test_a_single_origin_is_refused():
    frame = metrics_frame(n_origins=1)
    with pytest.raises(ConfigError, match="at least 2 origins"):
        bootstrap.run(frame, config())


def test_missing_columns_are_named():
    frame = metrics_frame().drop(columns=["regime"])
    with pytest.raises(ConfigError, match="missing columns"):
        bootstrap.run(frame, config())


def test_group_means_leave_empty_cells_as_nan():
    """A resample that drew no shock months has no shock mean.

    Reporting zero there would be inventing a perfect score for every model in
    the regime the whole project is about.
    """
    values = np.array([1.0, 2.0])
    model_index = np.array([0, 0])
    regime_index = np.array([0, 0])          # clean only
    means = bootstrap._group_means(values, model_index, regime_index, 1)
    assert means[0, 0] == pytest.approx(1.5)
    assert np.isnan(means[0, 1])


def test_round_trip_through_csv(tmp_path):
    result = bootstrap.run(metrics_frame(), config())
    path = bootstrap.write(result, tmp_path / "bootstrap.csv")
    restored = bootstrap.read(path)
    assert list(restored["statistic"]) == list(result["statistic"])
    assert restored["point"].to_numpy() == pytest.approx(result["point"].to_numpy(), nan_ok=True)

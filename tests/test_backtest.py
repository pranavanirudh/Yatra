"""Origin construction and the rectangularity guarantee.

These use a deterministic numeric probe rather than observations. What is being
tested is the harness -- which origins it builds, and whether it notices when a
model has not been scored on all of them.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from yatra import backtest, regimes
from yatra.errors import ConfigError, RaggedPanel

CONFIG_PATH = "experiments/configs/backtest.yaml"


def probe(n: int) -> pd.Series:
    index = pd.period_range("1986-01", periods=n, freq="M").to_timestamp(how="start")
    t = np.arange(n, dtype="float64")
    return pd.Series(1000.0 + 5.0 * t + 200.0 * np.sin(2 * np.pi * t / 12.0),
                     index=index).asfreq("MS")


def small_config(tmp_path: Path, **overrides) -> backtest.BacktestConfig:
    raw = {
        "origins": {"min_train_months": 24, "step_months": 1},
        "horizons": [1, 2, 3],
        "window": "expanding",
        "metrics": {"mase_seasonality": 12},
        "models": ["naive", "seasonal_naive", "drift"],
        "rectangular": True,
        "on_model_failure": "fail",
    }
    raw.update(overrides)
    path = tmp_path / "backtest.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    return backtest.load_config(path)


def windows(tmp_path: Path) -> list[regimes.ShockWindow]:
    path = tmp_path / "shocks.yaml"
    path.write_text(yaml.safe_dump({
        "schema_version": 1,
        "windows": [{
            "id": "fixture_shock",
            "label": "Fixture",
            "start": "1988-01",
            "end": "1988-06",
            "rationale": "Fixture window for harness tests.",
            "source": {
                "publisher": "Fixture", "title": "Fixture",
                "url": "https://example.invalid/x", "accessed": "2026-08-18",
            },
        }],
    }), encoding="utf-8")
    return regimes.load_windows(path)


# --- origins ---------------------------------------------------------------


def test_origins_respect_min_train_and_leave_room_for_the_longest_horizon(tmp_path):
    config = small_config(tmp_path)
    series = probe(60)
    origins = backtest.build_origins(series, config)
    assert origins[0] == 23                      # 24 months of history
    assert origins[-1] == 60 - 3 - 1             # room for h=3
    assert origins == list(range(23, 57))


def test_every_origin_is_scorable_at_every_horizon(tmp_path):
    """An origin usable at h=1 but not h=6 is dropped, not partially scored."""
    config = small_config(tmp_path, horizons=[1, 6])
    series = probe(60)
    origins = backtest.build_origins(series, config)
    assert max(origins) + 6 <= len(series) - 1


def test_too_short_a_series_raises(tmp_path):
    config = small_config(tmp_path)
    with pytest.raises(ConfigError, match="cannot support"):
        backtest.build_origins(probe(20), config)


# --- config guardrails -----------------------------------------------------


def test_rolling_window_is_refused(tmp_path):
    with pytest.raises(ConfigError, match="not implemented"):
        small_config(tmp_path, window="rolling")


def test_skipping_failed_models_is_refused(tmp_path):
    with pytest.raises(ConfigError, match="ragged panel"):
        small_config(tmp_path, on_model_failure="skip")


def test_committed_config_is_loadable_and_rectangular():
    config = backtest.load_config(CONFIG_PATH)
    assert config.rectangular is True
    assert config.on_model_failure == "fail"
    assert config.horizons == [1, 2, 3, 4, 5, 6]
    assert len(config.config_hash) == 12


# --- the run ---------------------------------------------------------------


def test_run_produces_a_rectangular_panel(tmp_path):
    config = small_config(tmp_path)
    series = probe(60)
    frame = backtest.run(series, config, None, windows(tmp_path))

    expected = len(backtest.build_origins(series, config)) * len(config.horizons)
    assert set(frame["model"]) == set(config.model_names)
    for _, group in frame.groupby("model"):
        assert len(group) == expected

    assert {"mase", "ae", "se", "smape", "regime", "shock_window"} <= set(frame.columns)
    assert frame["mase"].notna().all()


def test_all_models_share_one_mase_scale_per_origin(tmp_path):
    """If the scale varied by model the regime tables would not be comparable."""
    config = small_config(tmp_path)
    frame = backtest.run(probe(60), config, None, windows(tmp_path))
    per_origin = frame.groupby("origin")["mase_scale"].nunique()
    assert (per_origin == 1).all()


def test_regime_is_labelled_on_the_target_not_the_origin(tmp_path):
    config = small_config(tmp_path)
    frame = backtest.run(probe(60), config, None, windows(tmp_path))
    shock_rows = frame[frame["regime"] == regimes.SHOCK]
    assert len(shock_rows) > 0
    targets = pd.PeriodIndex(shock_rows["target"], freq="M")
    assert targets.min() >= pd.Period("1988-01", "M")
    assert targets.max() <= pd.Period("1988-06", "M")


def test_missing_shock_windows_raise(tmp_path):
    config = small_config(tmp_path)
    with pytest.raises(ConfigError, match="regime split"):
        backtest.run(probe(60), config, None, [])


def test_a_ragged_panel_is_caught(tmp_path):
    config = small_config(tmp_path)
    frame = backtest.run(probe(60), config, None, windows(tmp_path))
    mutilated = frame.drop(frame.index[frame["model"] == "drift"][:1])
    origins = backtest.build_origins(probe(60), config)
    with pytest.raises(RaggedPanel, match="Expected"):
        backtest._assert_rectangular(mutilated, origins, config.horizons, config)


def test_round_trip_through_csv_preserves_periods(tmp_path):
    config = small_config(tmp_path)
    frame = backtest.run(probe(60), config, None, windows(tmp_path))
    path = backtest.write(frame, tmp_path / "metrics.csv")
    restored = backtest.read(path)
    assert list(restored["origin"]) == list(frame["origin"])
    assert restored["mase"].to_numpy() == pytest.approx(frame["mase"].to_numpy())


def test_per_regime_table_has_ranks_and_counts(tmp_path):
    config = small_config(tmp_path)
    frame = backtest.run(probe(60), config, None, windows(tmp_path))
    table = backtest.per_regime_table(frame, "mase")
    assert regimes.CLEAN in table.columns
    assert f"{regimes.CLEAN}_rank" in table.columns
    assert f"{regimes.CLEAN}_n" in table.columns
    assert sorted(table[f"{regimes.CLEAN}_rank"]) == [1, 2, 3]


def test_writing_metrics_is_idempotent(tmp_path):
    """A read-write round trip must not change a byte.

    The backtest is reproducible to about one ulp but not bit-identical, and
    metrics.csv is committed. Before the write format was pinned, a re-run that
    changed nothing rewrote most rows with numerically equal values, which
    hides a change that matters inside a diff of changes that do not.
    """
    frame = pd.DataFrame(
        {
            "origin": ["2000-01", "2000-01"],
            "target": ["2000-02", "2000-03"],
            "horizon": [1, 2],
            "model": ["probe", "probe"],
            "actual": [1234.0, 5678.0],
            # Values chosen to need more digits than the format keeps.
            "predicted": [1234.5678901234567, 68175664362.090004],
            "mase": [3.3222948549659956, 1.0 / 3.0],
        }
    )
    first = backtest.write(frame, tmp_path / "metrics.csv")
    text_one = first.read_bytes()

    second = backtest.write(backtest.read(first), tmp_path / "metrics.csv")
    assert second.read_bytes() == text_one, (
        "metrics.csv changes on a round trip, so a re-run that computed the "
        "same numbers still produces a diff."
    )


def test_the_written_precision_is_far_finer_than_anything_reported():
    """Guard the trade: the format must not be tightened into the reported range."""
    digits = int(backtest.METRICS_FLOAT_FORMAT.strip("%.g"))
    assert digits >= 9, (
        f"metrics.csv is written to {digits} significant digits, which is "
        "approaching the precision the README quotes. Rounding must stay well "
        "clear of anything reported."
    )

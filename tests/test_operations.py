"""The operational briefing.

This is the output a duty officer would act on, so the tests here are less about
numerical accuracy than about the properties that keep a wrong number from
looking like a right one: that no resourcing figure appears without a declared
ratio behind it, that the uncertainty band cannot blow up or go negative, and
that the limitations stay in the document.

Frames are built from literals. Nothing here is an observation.
"""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from yatra import operations, regimes
from yatra.errors import ConfigError


def metrics_frame(
    n_origins: int = 40, models: tuple[str, ...] = ("alpha", "beta"), shock_every: int = 6
) -> pd.DataFrame:
    """A probe metrics table shaped exactly like results/metrics.csv."""
    rows = []
    rng = np.random.default_rng(11)
    for origin in range(n_origins):
        scale = 100.0
        for horizon in (1, 2, 3):
            regime = regimes.SHOCK if origin % shock_every == 0 else regimes.CLEAN
            for name in models:
                actual = 1000.0 + 10.0 * origin
                bias = 0.0 if name == "alpha" else 40.0
                predicted = actual - bias - rng.normal(0, 20)
                if regime == regimes.SHOCK:
                    # A collapse: the model keeps predicting a normal month.
                    actual *= 0.05
                rows.append(
                    {
                        "origin": pd.Period(f"2000-01", freq="M") + origin,
                        "target": pd.Period(f"2000-01", freq="M") + origin + horizon,
                        "horizon": horizon,
                        "model": name,
                        "actual": actual,
                        "predicted": predicted,
                        "mase_scale": scale,
                        "mase": abs(actual - predicted) / scale,
                        "regime": regime,
                    }
                )
    return pd.DataFrame(rows)


def observations(n: int = 130) -> pd.Series:
    t = np.arange(n, dtype="float64")
    index = pd.period_range("1995-01", periods=n, freq="M").to_timestamp(how="start")
    return pd.Series(1000.0 + 5.0 * t + 200.0 * np.sin(2 * np.pi * t / 12), index=index).asfreq("MS")


def config(ratios=None, confidence: float = 0.9) -> operations.OperationsConfig:
    return operations.OperationsConfig(
        model="alpha", horizons=[1, 2, 3], ratios=ratios or [], confidence=confidence
    )


# --- error spread ----------------------------------------------------------


def test_spread_is_measured_in_mase_units_not_ratios():
    """Regression: a ratio band explodes when the model predicts near zero.

    During a closure the forecast is a normal month and the actual is almost
    nothing, so ``actual / predicted`` is fine but ``predicted / actual`` -- or
    any band built by multiplying a forecast by a ratio quantile -- runs away.
    An early version of this module produced a shock upper bound of half a
    million pilgrims from a fifteen-hundred forecast. Scaling by the MASE
    denominator cannot do that, because that denominator is never near zero.
    """
    spread = operations.error_spread(metrics_frame(), "alpha", 0.9)
    assert {"lo_error", "median_error", "hi_error"} <= set(spread.columns)
    assert "lo_ratio" not in spread.columns
    assert np.isfinite(spread[["lo_error", "median_error", "hi_error"]].to_numpy()).all()


def test_spread_separates_the_regimes():
    spread = operations.error_spread(metrics_frame(), "alpha", 0.9)
    assert set(spread["regime"]) == {regimes.CLEAN, regimes.SHOCK}
    clean = spread[spread["regime"] == regimes.CLEAN]
    shock = spread[spread["regime"] == regimes.SHOCK]
    clean_width = (clean["hi_error"] - clean["lo_error"]).mean()
    shock_width = (shock["hi_error"] - shock["lo_error"]).mean()
    assert shock_width > clean_width, (
        "Shock months must not report a tighter band than clean ones; planning "
        "to the narrower of the two is how a site ends up under-resourced."
    )


def test_spread_raises_for_a_model_with_no_rows():
    with pytest.raises(ConfigError, match="no rows for model"):
        operations.error_spread(metrics_frame(), "gamma", 0.9)


def test_spread_requires_the_mase_scale_column():
    frame = metrics_frame().drop(columns=["mase_scale"])
    with pytest.raises(ConfigError, match="mase_scale"):
        operations.error_spread(frame, "alpha", 0.9)


# --- planning table --------------------------------------------------------


def _table(cfg=None, festivals=None):
    frame = metrics_frame()
    cfg = cfg or config()
    spread = operations.error_spread(frame, "alpha", cfg.confidence)
    forecast = pd.Series(
        [50_000.0, 52_000.0, 48_000.0],
        index=pd.PeriodIndex(["2026-09", "2026-10", "2026-11"], freq="M"),
    )
    return operations.planning_table(forecast, spread, cfg.horizons, cfg, 5_000.0, festivals)


def test_bands_never_go_negative():
    """A negative attendance is not a plan."""
    table = _table()
    assert (table["lo"] >= 0).all()
    assert (table["shock_lo"] >= 0).all()


def test_band_brackets_the_point_forecast():
    table = _table()
    assert (table["lo"] <= table["forecast"]).all()
    assert (table["hi"] >= table["forecast"]).all()


def test_daily_mean_uses_the_real_month_length():
    table = _table()
    assert table.set_index("month").loc["2026-09", "days_in_month"] == 30
    assert table.set_index("month").loc["2026-10", "days_in_month"] == 31
    row = table.iloc[0]
    assert row["daily_mean"] == pytest.approx(row["forecast"] / row["days_in_month"])


def test_festival_dates_are_attributed_to_the_right_month():
    festivals = pd.DataFrame(
        {
            "date": [dt.date(2026, 10, 11), dt.date(2026, 10, 12), dt.date(2026, 11, 8)],
            "label": ["Sharad Navratri (day 1)", "Sharad Navratri (day 1)", "Diwali"],
        }
    )
    table = _table(festivals=festivals).set_index("month")
    assert table.loc["2026-09", "festival_days"] == 0
    assert table.loc["2026-10", "festival_days"] == 2
    assert table.loc["2026-11", "festival_days"] == 1
    assert "2026-11-08" in table.loc["2026-11", "festival_dates"]


def test_planning_table_rejects_a_non_positive_scale():
    with pytest.raises(ConfigError, match="current_scale"):
        _table_with_scale(0.0)


def _table_with_scale(scale: float):
    frame = metrics_frame()
    cfg = config()
    spread = operations.error_spread(frame, "alpha", cfg.confidence)
    forecast = pd.Series([1.0, 1.0, 1.0], index=pd.PeriodIndex(
        ["2026-09", "2026-10", "2026-11"], freq="M"))
    return operations.planning_table(forecast, spread, cfg.horizons, cfg, scale, None)


# --- resourcing ------------------------------------------------------------


def test_no_ratios_means_no_resourcing_numbers():
    """The load-bearing safety property of this module.

    With nothing declared, the briefing must say so rather than fall back on a
    plausible-looking default. A ratio invented here would be indistinguishable,
    in the rendered table, from one signed off by an operations lead.
    """
    cfg = config(ratios=[])
    table = _table(cfg)
    assert not [c for c in table.columns if c.startswith("need_")]

    text = operations.briefing(table, cfg, "alpha", observations(),
                               operations.error_spread(metrics_frame(), "alpha", 0.9))
    assert "No planning ratios are declared" in text
    assert "no resourcing was computed" in text


def test_declared_ratios_are_applied_on_the_declared_basis():
    ratio = operations.PlanningRatio(
        id="marshals", label="Marshals", per_pilgrims=500.0, basis="daily_mean", minimum=20
    )
    table = _table(config(ratios=[ratio]))
    row = table.iloc[0]
    assert row["need_marshals"] == max(20, np.ceil(row["daily_mean"] / 500.0))


def test_ratio_minimum_is_a_floor():
    ratio = operations.PlanningRatio(
        id="medics", label="Medics", per_pilgrims=10_000_000.0, basis="daily_mean", minimum=8
    )
    table = _table(config(ratios=[ratio]))
    assert (table["need_medics"] == 8).all()


def test_unknown_basis_is_rejected_at_load(tmp_path):
    import yaml

    path = tmp_path / "operations.yaml"
    path.write_text(yaml.safe_dump({
        "model": "naive", "horizons": [1],
        "planning": {"ratios": [
            {"id": "x", "per_pilgrims": 100, "basis": "per_fortnight"}]},
    }), encoding="utf-8")
    with pytest.raises(ConfigError, match="basis"):
        operations.load_config(path)


def test_shipped_config_declares_no_ratios():
    """The repository must not ship planning numbers that look authoritative."""
    from pathlib import Path

    path = Path(__file__).resolve().parent.parent / "experiments/configs/operations.yaml"
    assert not operations.load_config(path).ratios, (
        "experiments/configs/operations.yaml ships non-empty planning ratios. "
        "Resourcing ratios are site policy; a default shipped here would appear "
        "in a briefing looking like an evidence-based figure."
    )


# --- model choice and briefing text ---------------------------------------


def test_best_clean_picks_the_lowest_clean_mase():
    frame = metrics_frame()
    assert operations.choose_model(frame, "best_clean") == "alpha"


def test_named_model_absent_from_metrics_raises():
    with pytest.raises(ConfigError, match="no rows in results/metrics.csv"):
        operations.choose_model(metrics_frame(), "gamma")


def test_briefing_states_the_monthly_versus_daily_limitation():
    """The caveat that stops a monthly total being read as a peak-day figure.

    If this ever disappears from the template, the briefing starts implying
    something it cannot support, so it is asserted rather than trusted.
    """
    cfg = config()
    text = operations.briefing(_table(cfg), cfg, "alpha", observations(),
                               operations.error_spread(metrics_frame(), "alpha", 0.9))
    assert "per month" in text
    assert "Peak-hour or peak-day load" in text
    assert "do **not** predict the load at any given hour" in text


def test_briefing_reports_the_shock_contingency_separately():
    cfg = config()
    text = operations.briefing(_table(cfg), cfg, "alpha", observations(),
                               operations.error_spread(metrics_frame(), "alpha", 0.9))
    assert "If a disruption occurs" in text
    assert "Plan the contingency to this" in text


def test_unmeasurable_shock_band_says_so_rather_than_showing_a_blank():
    """A blank in a contingency table must not read as 'no risk'.

    Horizons with fewer than five scored shock forecasts get no range. The
    briefing has to say that is a gap in observation, not an absence of danger.
    """
    frame = metrics_frame(shock_every=10_000)      # effectively no shock rows
    cfg = config()
    spread = operations.error_spread(frame, "alpha", cfg.confidence)
    forecast = pd.Series([50_000.0], index=pd.PeriodIndex(["2026-09"], freq="M"))
    table = operations.planning_table(forecast, spread, [1], cfg, 5_000.0, None)

    assert not np.isfinite(table["shock_hi"]).any()
    text = operations.briefing(table, cfg, "alpha", observations(), spread)
    assert "not measurable" in text
    assert 'not "no risk."' in text or "is not \"no risk.\"" in text

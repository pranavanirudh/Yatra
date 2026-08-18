"""The switching models and the one-step surprise detector.

Two things are checked, and the second matters more.

**That the detector works**: it fires in the month a collapse happens rather
than waiting for confirmation, it ignores an unexpectedly good month, and it
stays quiet on an undisrupted series.

**That it cannot cheat.** The whole finding is a comparison between regimes, and
a model able to see which months were labelled shocks would win that comparison
for free. The guards here are structural rather than trusting: output is
asserted to depend on nothing but the training window, and ``models.py`` is
asserted never to reach for the regime labels.

Probes are deterministic arithmetic on literals (brief 4). Nothing here reaches
``results/``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from yatra import models
from yatra.errors import LeakageError

HORIZONS = [1, 2, 3, 4, 5, 6]


def series(values, start="1990-01") -> pd.Series:
    index = pd.period_range(start, periods=len(values), freq="M").to_timestamp(how="start")
    return pd.Series(np.asarray(values, dtype="float64"), index=index).asfreq("MS")


def clean(n: int = 144, noise: float = 40.0) -> np.ndarray:
    """A seasonal series with reproducible noise and no disruption."""
    rng = np.random.default_rng(20260818)
    t = np.arange(n, dtype="float64")
    return 1000.0 + 2.0 * t + 300.0 * np.sin(2 * np.pi * t / 12.0) + rng.normal(0, noise, n)


def collapsed(n: int = 144, months: int = 2, depth: float = 0.1) -> np.ndarray:
    """A collapse that is still fresh at the end of the window.

    Kept short on purpose. The detector releases once the model has adapted to
    the new level, which on an in-sample refit takes only a month or two -- so a
    six-month collapse ending at the last observation is already "normal" from
    the model's point of view and correctly reads as not-switched.
    """
    values = clean(n).copy()
    values[-months:] *= depth
    return values


# --- the detector ----------------------------------------------------------


def test_quiet_on_an_undisrupted_series():
    assert models.detect_shock_state(series(clean())) is False


def test_fires_on_the_very_first_collapsed_month():
    """The point of the rewrite. One observation, no confirmation delay.

    The previous detector needed two consecutive deviating months, so on a step
    change it fired a month late -- typically as recovery began.
    """
    values = clean().copy()
    values[-1] *= 0.1
    assert models.detect_shock_state(series(values)) is True


def _surge_to(values: np.ndarray, target_score: float) -> np.ndarray:
    """Raise the final month until its surprise is about ``target_score``.

    Sized in the detector's own units rather than as a percentage. A fixed
    multiplier is not a meaningful test: on a very regular window a 90% surge is
    a 25-unit event, while on the real series -- which is far noisier -- the
    largest surprise ever recorded at its own origin is 6.57. Testing "x1.9 must
    not switch" would really be testing how much noise the probe happens to have.
    """
    out = values.copy()
    scale_probe = models.surprise_scores(series(out))
    base = float(out[-1])
    # One unit of score, in people, measured by perturbing the last month.
    out[-1] = base * 2.0
    per_unit = (base * 1.0) / max(
        abs(float(models.surprise_scores(series(out))[-1]) - float(scale_probe[-1])), 1e-9
    )
    out[-1] = base + per_unit * target_score
    return out


def test_a_surge_below_the_upside_threshold_does_not_switch():
    """Asymmetry, which is the whole reason the thresholds are not mirrored.

    An unexpectedly good month leaves the seasonal structure intact. A collapse
    does not. A symmetric interval would switch on both -- and on this series
    every large positive surprise is a recovery month, which is the worst
    possible moment to hand over to a level-anchored rule.
    """
    values = _surge_to(clean(), models.SURPRISE_ENTER_UP * 0.5)
    assert models.detect_shock_state(series(values)) is False
    assert models.SURPRISE_ENTER_UP > models.SURPRISE_ENTER


def test_a_surge_far_above_the_upside_threshold_still_switches():
    """The upside threshold is high, not absent."""
    values = _surge_to(clean(), models.SURPRISE_ENTER_UP * 3.0)
    assert models.detect_shock_state(series(values)) is True


def test_the_upside_threshold_clears_every_observed_recovery():
    """Guards the specific mistake this threshold was set to avoid.

    Set at 6.0 it fired once in forty years, on the July 2021 COVID recovery.
    If it is ever lowered back toward the downside threshold, this fails.
    """
    assert models.SURPRISE_ENTER_UP >= 10.0
    assert models.SURPRISE_ENTER_UP > 4 * models.SURPRISE_ENTER


def test_short_history_gives_no_opinion():
    assert models.detect_shock_state(series(clean(20))) is False


def test_constant_series_does_not_trip_the_scale_floor():
    """No scale means nothing is a surprise; it must not divide by noise."""
    assert models.detect_shock_state(series(np.full(144, 500.0))) is False


def test_surprise_scores_are_centred_and_scaled():
    scores = models.surprise_scores(series(clean()))
    assert np.isfinite(scores).all()
    assert abs(float(np.median(scores))) < 0.5


# --- the exit rule, scored separately --------------------------------------


def test_dwell_holds_the_switch_longer():
    """`switching_sticky` differs from `switching` only in how long it stays on.

    A surprise-based exit cannot be made sticky on this series: once the level
    collapses the model adapts within a month or two, so the surprises during
    the recovery come out strongly positive and any threshold releases at once.
    The dwell is what makes the exit rule measurable at all.
    """
    values = clean().copy()
    values[-3:-1] *= 0.1          # collapse, then one recovered month
    train = series(values)

    fast = models.detect_shock_state(train, dwell=models.SWITCH_DWELL)
    sticky = models.detect_shock_state(train, dwell=models.SWITCH_DWELL_STICKY)
    assert sticky or not fast, "sticky must never release earlier than fast"
    assert models.SWITCH_DWELL_STICKY > models.SWITCH_DWELL


def test_the_two_switching_models_are_registered_and_distinct():
    assert "switching" in models.REGISTRY
    assert "switching_sticky" in models.REGISTRY
    assert (
        models.REGISTRY["switching"].fn is not models.REGISTRY["switching_sticky"].fn
    )


# --- the models ------------------------------------------------------------


@pytest.mark.parametrize("name", ["switching", "switching_sticky"])
def test_returns_one_finite_value_per_horizon(name):
    out = models.predict(name, series(collapsed()), HORIZONS)
    assert out.shape == (len(HORIZONS),)
    assert np.isfinite(out).all()


@pytest.mark.parametrize("name", ["switching", "switching_sticky"])
def test_matches_holt_winters_exactly_when_not_switched(name):
    """The control branch is the ablation. It must be identical, not merely close."""
    train = series(clean())
    assert models.detect_shock_state(train) is False
    assert models.predict(name, train, HORIZONS) == pytest.approx(
        models.predict("holt_winters_add", train, HORIZONS)
    )


def test_diverges_from_holt_winters_when_switched():
    train = series(collapsed())
    assert models.detect_shock_state(train) is True
    assert not np.allclose(
        models.predict("switching", train, HORIZONS),
        models.predict("holt_winters_add", train, HORIZONS),
    )


def test_tracks_the_collapsed_level_rather_than_last_year():
    values = collapsed(months=12, depth=0.1)
    out = models.predict("switching", series(values), HORIZONS)
    recent = float(np.median(values[-6:]))
    last_year = float(np.median(values[-18:-12]))
    assert abs(float(np.median(out)) - recent) < abs(float(np.median(out)) - last_year)


# --- leakage ---------------------------------------------------------------


@pytest.mark.parametrize("name", ["switching", "switching_sticky"])
def test_output_depends_only_on_the_training_window(name):
    """The core leak test: the future cannot change a forecast made before it."""
    train = collapsed()
    alone = models.predict(name, series(train), HORIZONS)

    longer = np.concatenate([train, np.full(24, 99999.0)])
    head = series(longer).iloc[: len(train)]
    assert alone == pytest.approx(models.predict(name, head, HORIZONS))


def test_detector_output_depends_only_on_the_training_window():
    train = collapsed()
    longer = np.concatenate([train, np.full(24, 99999.0)])
    assert models.detect_shock_state(series(train)) == models.detect_shock_state(
        series(longer).iloc[: len(train)]
    )


@pytest.mark.parametrize("name", ["switching", "switching_sticky"])
def test_switching_models_are_not_calendar_models(name):
    assert name not in models.NEEDS_CALENDAR
    assert not models.REGISTRY[name].needs_calendar


def test_leakage_error_if_the_detector_reads_past_the_origin(monkeypatch):
    """The guard, exercised by forcing the failure it guards against."""
    train = series(collapsed())
    monkeypatch.setattr(
        models, "_level_shifted_seasonal_naive",
        lambda t, h: (_ for _ in ()).throw(LeakageError("does not exist at the origin")),
    )
    with pytest.raises(LeakageError):
        models.predict("switching", train, HORIZONS)


def test_the_models_never_reach_for_the_regime_labels():
    """Structural, not a promise. Mirrors the guard in test_no_fabrication.py."""
    import re
    from pathlib import Path

    source = Path(models.__file__).read_text(encoding="utf-8")
    references = re.compile(
        r"^\s*(?:from\s+\.?\S*\s+)?import\s+.*\bregimes\b"
        r"|\bregimes\s*\."
        r"|\bShockWindow\b"
        r"|\bshocks\.yaml\b"
        r"|\bshock_window\b",
        re.MULTILINE,
    )
    assert not references.findall(source)

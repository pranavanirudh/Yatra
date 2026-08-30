"""Figures.

Rendering correctness is not testable here without pixel comparison, which is
brittle and would fail on a matplotlib upgrade for no useful reason. What is
worth asserting is that every figure is produced from the artefacts, that a
missing regime is refused rather than drawn as an empty half of a comparison,
and that the module holds no numbers of its own.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from yatra import backtest, figures, regimes
from yatra.errors import ConfigError

from test_bootstrap import metrics_frame


def observations(n: int = 120) -> pd.Series:
    t = np.arange(n, dtype="float64")
    index = pd.period_range("2000-01", periods=n, freq="M").to_timestamp(how="start")
    return pd.Series(1000.0 + 5.0 * t + 200.0 * np.sin(2 * np.pi * t / 12), index=index).asfreq("MS")


def windows() -> list[regimes.ShockWindow]:
    return [
        regimes.ShockWindow(
            id="probe_window",
            label="Probe window",
            start=pd.Period("2003-01", freq="M"),
            end=pd.Period("2003-06", freq="M"),
            rationale="probe",
            source={"publisher": "P", "title": "T", "url": "https://example.invalid",
                    "accessed": "2026-08-18"},
            verified=False,
        )
    ]


def scored_frame() -> pd.DataFrame:
    """A metrics frame with the columns the forecast/actual figure needs."""
    frame = metrics_frame()
    rng = np.random.default_rng(4)
    frame["actual"] = 1000.0 + rng.normal(0, 50, len(frame))
    frame["predicted"] = frame["actual"] + rng.normal(0, 40, len(frame))
    return frame


def test_every_figure_is_written(tmp_path):
    frame = scored_frame()
    table = backtest.per_regime_table(frame)
    written = figures.build_all(observations(), frame, table, windows(), tmp_path)
    assert len(written) == 7
    assert {path.name for path in written} == {
        "series_shocks.png",
        "forecast_vs_actual_h1.png",
        "regime_ranking.png",
        "rank_shift.png",
        "inversion_hero.png",
        "horizon_profile.png",
        "shock_type_agreement.png",
    }
    for path in written:
        assert path.exists()
        assert path.stat().st_size > 5_000, f"{path.name} is suspiciously small"


def test_bootstrap_figure_is_added_when_the_frame_is_present(tmp_path):
    from yatra import bootstrap

    frame = scored_frame()
    table = backtest.per_regime_table(frame)
    result = bootstrap.run(frame, bootstrap.BootstrapConfig(
        n_resamples=120, block_origins=4, confidence=0.9, seed=1, metric="mase"))
    written = figures.build_all(observations(), frame, table, windows(), tmp_path, result)
    assert len(written) == 8
    assert (tmp_path / "bootstrap_intervals.png").exists()


def test_a_single_regime_is_refused_rather_than_half_drawn(tmp_path):
    """Half a comparison drawn as though it were whole is the failure to avoid."""
    frame = scored_frame()
    frame = frame[frame["regime"] == regimes.CLEAN]
    table = backtest.per_regime_table(frame)
    with pytest.raises(ConfigError, match="no comparison"):
        figures.regime_ranking(table, tmp_path / "x.png")


def test_the_hero_figure_refuses_a_single_regime(tmp_path):
    """The hero figure is the inversion. One regime has no inversion in it."""
    frame = scored_frame()
    frame = frame[frame["regime"] == regimes.CLEAN]
    table = backtest.per_regime_table(frame)
    with pytest.raises(ConfigError, match="no inversion"):
        figures.inversion_hero(table, tmp_path / "x.png")


def test_the_hero_figure_draws_every_model(tmp_path, monkeypatch):
    """No model is dropped to make the headline figure legible.

    The two regime winners are highlighted and the rest are greyed, which is a
    presentation choice. Dropping the rest would be a selective one, and this
    project's objection to the pooled leaderboard is exactly that a tidier
    summary hides what it left out. Checked against the artists the figure
    actually draws, not against what it was asked to draw.
    """
    captured = {}
    real_save = figures._save

    def spy(fig, path):
        axes = fig.axes[0]
        captured["texts"] = [artist.get_text() for artist in axes.texts]
        captured["lines"] = len(axes.lines)
        return real_save(fig, path)

    monkeypatch.setattr(figures, "_save", spy)

    frame = scored_frame()
    table = backtest.per_regime_table(frame)
    figures.inversion_hero(table, tmp_path / "hero.png")

    left = f"{regimes.CLEAN}_rank"
    right = f"{regimes.SHOCK}_rank"
    texts = captured["texts"]

    for name, row in table.iterrows():
        # Exact labels, not substring matching: `switching` is a substring of
        # `switching_sticky` and `naive` of `seasonal_naive`, so a loose check
        # would count a model that had been dropped.
        assert f"{int(row[left])}  {name}" in texts, (
            f"{name} is missing its label in the ordinary-months column."
        )
        assert f"{name}  {int(row[right])}" in texts, (
            f"{name} is missing its label in the disrupted-months column."
        )

    # One slope line per model, plus the two column uprights.
    assert captured["lines"] == len(table) + 2, (
        f"Expected {len(table)} slope lines plus 2 uprights, drew "
        f"{captured['lines']}. A missing line is a dropped model."
    )


def test_the_hero_headline_follows_the_data(tmp_path, monkeypatch):
    """The headline claims an inversion only when the table shows one.

    An unconditional "the ranking inverts" would be a caption that had stopped
    being true without anything failing, which is the class of quiet wrong
    answer this project exists to refuse.
    """
    captured = {}
    real_save = figures._save

    def spy(fig, path):
        captured["title"] = fig.axes[0].get_title()
        return real_save(fig, path)

    monkeypatch.setattr(figures, "_save", spy)

    frame = scored_frame()
    table = backtest.per_regime_table(frame)
    figures.inversion_hero(table, tmp_path / "hero.png")

    clean, shock = regimes.CLEAN, regimes.SHOCK
    inverts = table[clean].idxmin() != table[shock].idxmin()
    if inverts:
        assert captured["title"] == "The ranking inverts"
    else:
        assert captured["title"] == "The same model wins in both regimes"


def test_an_absent_horizon_names_the_available_ones(tmp_path):
    frame = scored_frame()
    with pytest.raises(ConfigError, match="available"):
        figures.forecast_vs_actual(frame, windows(), tmp_path / "x.png", horizon=99)


def test_horizon_profile_refuses_a_single_regime(tmp_path):
    """One panel of a two-panel comparison is not the comparison."""
    frame = scored_frame()
    frame = frame[frame["regime"] == regimes.CLEAN]
    with pytest.raises(ConfigError, match="no per-horizon comparison"):
        figures.horizon_profile(frame, tmp_path / "x.png")


def test_horizon_profile_refuses_a_frame_without_horizons(tmp_path):
    frame = scored_frame().drop(columns=["horizon"])
    with pytest.raises(ConfigError, match="horizon"):
        figures.horizon_profile(frame, tmp_path / "x.png")


def test_figures_module_contains_no_literal_results():
    """Figures are drawn from artefacts, never from a number typed into the file."""
    text = Path(figures.__file__).read_text(encoding="utf-8")
    import re

    # Colours and layout constants are fine; anything that looks like a footfall
    # figure or a score is not.
    offenders = [
        line.strip()
        for line in text.splitlines()
        if re.search(r"=\s*\d{4,}(\.\d+)?\s*(#|$)", line) and "DPI" not in line
    ]
    assert not offenders, f"Literal magnitudes in figures.py: {offenders}"

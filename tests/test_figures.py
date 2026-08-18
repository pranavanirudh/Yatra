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
    assert len(written) == 4
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
    assert len(written) == 5
    assert (tmp_path / "bootstrap_intervals.png").exists()


def test_a_single_regime_is_refused_rather_than_half_drawn(tmp_path):
    """Half a comparison drawn as though it were whole is the failure to avoid."""
    frame = scored_frame()
    frame = frame[frame["regime"] == regimes.CLEAN]
    table = backtest.per_regime_table(frame)
    with pytest.raises(ConfigError, match="no comparison"):
        figures.regime_ranking(table, tmp_path / "x.png")


def test_an_absent_horizon_names_the_available_ones(tmp_path):
    frame = scored_frame()
    with pytest.raises(ConfigError, match="available"):
        figures.forecast_vs_actual(frame, windows(), tmp_path / "x.png", horizon=99)


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

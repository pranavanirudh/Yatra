"""The horizon split has to reach the README, especially when it disagrees.

The leaderboard pools h=1..6. Nobody forecasts at the average of six lead
times: the briefing hands a planner one horizon. If the inversion held only at
the long end, the pooled table would look exactly as it does now, and the
short-horizon reader would act on a claim that did not cover them.

The frames below are report-rendering fixtures. They never leave the test and
describe no shrine; see docs/claude_code_brief.md section 4.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from yatra import backtest, report

MODELS = ["alpha", "beta", "gamma"]


def _frame(scores: dict[int, dict[str, dict[str, float]]]) -> pd.DataFrame:
    """``scores[horizon][regime][model] = mase``. Two rows per cell, so the mean is it."""
    rows = [
        {
            "origin": f"2000-{1 + replicate:02d}",
            "target": f"2000-{2 + replicate:02d}",
            "horizon": horizon,
            "model": model,
            "regime": regime,
            "mase": value,
        }
        for horizon, by_regime in scores.items()
        for regime, by_model in by_regime.items()
        for model, value in by_model.items()
        for replicate in range(2)
    ]
    return pd.DataFrame(rows)


def _inverted(offset: float = 0.0) -> dict[str, dict[str, float]]:
    """alpha wins clean and loses shock; gamma the reverse."""
    return {
        "clean": {"alpha": 1.0 + offset, "beta": 2.0 + offset, "gamma": 3.0 + offset},
        "shock": {"alpha": 6.0 + offset, "beta": 5.0 + offset, "gamma": 4.0 + offset},
    }


def _agreeing(offset: float = 0.0) -> dict[str, dict[str, float]]:
    """No inversion: the clean order is the shock order."""
    return {
        "clean": {"alpha": 1.0 + offset, "beta": 2.0 + offset, "gamma": 3.0 + offset},
        "shock": {"alpha": 4.0 + offset, "beta": 5.0 + offset, "gamma": 6.0 + offset},
    }


def test_inversion_at_every_horizon_is_stated_as_such():
    frame = _frame({h: _inverted(0.1 * h) for h in (1, 2, 3)})
    text = "\n".join(report._by_horizon(frame))

    assert "3 of 3" in text
    assert "not an artefact of pooling horizons" in text
    assert "`alpha`" in text and "`gamma`" in text
    assert "| h=1 | `alpha` | 3 of 3 | `gamma` | 3 of 3 | -1.000 |" in text


def test_a_horizon_where_it_does_not_hold_is_reported():
    """The case the pooled table would hide, which is the reason for the section."""
    frame = _frame({1: _agreeing(), 2: _inverted(), 3: _inverted()})
    text = "\n".join(report._by_horizon(frame))

    assert "2 of 3" in text
    assert "h=2, h=3" in text
    assert "rather than about the series" in text


def test_a_crown_changing_hands_is_not_reported_as_a_stable_pair():
    scores = {1: _inverted(), 2: _inverted()}
    # At h=2, beta takes the clean crown instead of alpha.
    scores[2]["clean"] = {"alpha": 2.0, "beta": 1.0, "gamma": 3.0}
    text = "\n".join(report._by_horizon(_frame(scores)))

    assert "The crown changes hands across horizons" in text or "crown changes hands" in text
    assert "name the lead time" in text
    assert "not an artefact of pooling" not in text


def test_one_horizon_is_not_a_horizon_comparison():
    assert report._by_horizon(_frame({1: _inverted()})) == []


def test_a_frame_without_horizons_renders_nothing():
    frame = _frame({1: _inverted(), 2: _inverted()}).drop(columns=["horizon"])
    assert report._by_horizon(frame) == []


def test_the_pooled_table_can_hide_a_horizon_where_the_finding_fails():
    """The premise of the section, asserted rather than assumed.

    A frame built to invert strongly at the long horizons and not at all at
    h=1 still pools to a clean inversion. If this ever stopped being true the
    section would be answering a question nobody needed to ask.
    """
    frame = _frame({1: _agreeing(), 2: _inverted(), 3: _inverted()})
    pooled = backtest.per_regime_table(frame)
    assert pooled["clean"].idxmin() == "alpha"
    assert pooled["shock"].idxmin() == "gamma"

    h1 = backtest.per_regime_table(frame[frame["horizon"] == 1])
    assert h1["shock"].idxmin() == "alpha", "h=1 does not invert, which is the point"


def test_the_section_reaches_the_rendered_readme():
    if not Path("results/metrics.csv").exists():
        pytest.skip("no committed metrics; run `make backtest`")
    body = report.render()
    assert "### Does the finding survive at every forecast lead time?" in body

    frame = backtest.read("results/metrics.csv")
    for horizon in sorted(frame["horizon"].unique()):
        assert f"| h={int(horizon)} |" in body

"""The README's first screen.

The lead is generated for the same reason as the results section, but it earns
its own tests because of who reads it. It is the block most likely to be quoted
into a slide, an abstract or a viva answer, and the least likely to be checked
against `results/metrics.csv` before that happens.

One sentence in it makes a claim the rest of the block does not: that a
leaderboard *averaged over all months* would recommend a particular model. That
is a statement about a third ranking -- neither of the two columns in the table
above it -- and on the committed record the pooled winner and the clean winner
are the same model, because ordinary months outnumber disrupted ones by more
than ten to one. Agreement of that kind is a property of the sample, not of the
method. So what is tested here is that the sentence is *derived* from the pooled
column rather than assumed from the clean one, and that it changes when the
pooled winner does.
"""

from __future__ import annotations

import pandas as pd
import pytest

from yatra import backtest, regimes, report
from yatra.errors import ConfigError


def lead_frame(clean: dict[str, float], shock: dict[str, float], *,
               clean_rows: int = 10, shock_rows: int = 2) -> pd.DataFrame:
    """A scored panel with declared per-model error in each regime.

    ``clean_rows`` and ``shock_rows`` set how many forecasts each regime
    contributes, which is what decides the pooled ranking. The default ratio is
    lopsided in the same direction as the real record -- ordinary months
    dominate -- so a test that wants the pooled winner to differ from the clean
    winner has to say so explicitly by changing it.

    Arithmetic on literals. No observation is involved.
    """
    rows = []
    origin = pd.Period("2010-01", freq="M")
    step = 0
    for regime, levels, count in (
        (regimes.CLEAN, clean, clean_rows),
        (regimes.SHOCK, shock, shock_rows),
    ):
        for _ in range(count):
            for model, level in levels.items():
                rows.append({
                    "origin": origin + step,
                    "target": origin + step + 1,
                    "horizon": 1,
                    "model": model,
                    "mase": level,
                    "regime": regime,
                    "shock_window": "" if regime == regimes.CLEAN else "w1",
                })
            step += 1
    return pd.DataFrame(rows)


def lead_of(frame: pd.DataFrame) -> str:
    table = backtest.per_regime_table(frame, "mase")
    pooled = frame.groupby("model")["mase"].mean()
    return "\n".join(report._lead(table, pooled))


def test_the_pooled_claim_names_the_pooled_winner_not_the_clean_winner():
    """The load-bearing case: pooling picks a model neither regime picks.

    `mid` loses both columns -- `fast` wins on ordinary months, `tough` wins on
    disrupted ones -- but it is the least bad on the pooled average. A lead that
    derived its closing sentence from the clean column would announce that the
    pooled leaderboard recommends `fast`, which is a claim about a ranking that
    does not recommend it. Nothing would crash and the sentence would read
    perfectly well, which is exactly why it is tested.
    """
    frame = lead_frame(
        clean={"fast": 1.0, "mid": 1.4, "tough": 9.0},
        shock={"fast": 9.0, "mid": 1.4, "tough": 1.0},
        clean_rows=6,
        shock_rows=6,
    )
    pooled = frame.groupby("model")["mase"].mean()
    assert pooled.idxmin() == "mid", "fixture does not set up the case under test"

    text = lead_of(frame)
    assert "recommends `mid`" in text
    assert "wins neither" in text
    assert "recommends `fast`" not in text, (
        "The lead named the clean winner as the pooled recommendation. The "
        "pooled winner must be read from the pooled column."
    )


def test_the_headline_cost_is_stated_when_pooling_picks_the_clean_winner():
    """The ordinary case, and the one the committed record is in.

    Clean months dominate, so the pooled winner is the clean winner, and the
    cost of pooling is that it recommends a model ranked low where it mattered.
    """
    frame = lead_frame(
        clean={"fast": 1.0, "mid": 2.5, "tough": 9.0},
        shock={"fast": 9.0, "mid": 4.0, "tough": 1.0},
    )
    pooled = frame.groupby("model")["mase"].mean()
    assert pooled.idxmin() == "fast", "fixture does not set up the case under test"

    text = lead_of(frame)
    assert "recommends `fast`" in text
    assert "discards `tough`" in text
    assert "invert the recommendation" in text


def test_no_cost_is_claimed_when_pooling_already_picks_the_shock_winner():
    """Restraint: the inversion is real but this particular cost is not.

    Here the shock winner also wins pooled, so pooling does not misdirect the
    choice. Asserting that it did would overclaim in the direction the project
    wants the answer to fall, which is the failure this codebase is least
    entitled to commit.
    """
    frame = lead_frame(
        clean={"fast": 1.0, "tough": 1.02},
        shock={"fast": 9.0, "tough": 1.0},
        clean_rows=3,
        shock_rows=6,
    )
    pooled = frame.groupby("model")["mase"].mean()
    assert pooled.idxmin() == "tough", "fixture does not set up the case under test"

    text = lead_of(frame)
    assert "does not misdirect" in text
    assert "invert the recommendation" not in text, (
        "The lead claimed pooling inverted the recommendation in a case where "
        "pooling picked the shock winner."
    )


def test_the_lead_refuses_a_single_regime():
    """Half a comparison is not the comparison, and the first screen says so."""
    frame = lead_frame(clean={"fast": 1.0, "tough": 2.0}, shock={}, shock_rows=0)
    table = backtest.per_regime_table(frame, "mase")
    pooled = frame.groupby("model")["mase"].mean()
    with pytest.raises(ConfigError, match="cannot be"):
        report._lead(table, pooled)


def test_the_lead_contains_no_numeric_literal_of_its_own():
    """Every figure in the first screen is interpolated from the table.

    Same rule as the answer console's cards (CLAUDE.md §3.8) and the same reason
    as §3.1: a number typed into this block would render identically to one a
    row produced, and no reader could tell them apart. Checked against the
    source of the two functions that build the block, not its output.
    """
    import inspect
    import re

    for function in (report._lead, report._selection_cost):
        source = inspect.getsource(function)
        body = source.partition('"""')[0] + source.partition('"""')[2].partition('"""')[2]
        # Numbers that would read as a result: a decimal, or a grouped integer.
        offenders = re.findall(r"(?<![\w.])(\d+\.\d+|\d{1,3}(?:,\d{3})+)(?![\w])", body)
        assert not offenders, (
            f"{function.__name__} contains numeric literals {offenders}. Every "
            "figure in the lead must be interpolated from the scored table."
        )

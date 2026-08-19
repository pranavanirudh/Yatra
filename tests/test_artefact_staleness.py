"""Artefacts must not disagree with the metrics.csv they were derived from.

This is a regression test for a drift that actually happened. The shock
windows gained `article_370`, `metrics.csv` was relabelled (180 shock
forecasts per model, up from 162), and `results/briefing.md` was left as it
was. Nothing crashed. The briefing kept quoting a contingency range measured
on a smaller set of disrupted months, and it looked exactly like a current one
-- a plausible number emitted quietly, which is the failure mode in
docs/claude_code_brief.md section 5.

`assert_labels_current` already existed and already caught the *other*
direction (config edited after the backtest). Three stages called it and the
one that writes the document a duty officer reads did not.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from yatra import backtest, cli, regimes

# Every stage that reads metrics.csv and splits it by regime. A stage added
# here without the guard fails this test rather than shipping a stale table.
REGIME_CONSUMING_STAGES = ("run_bootstrap", "figures", "build_report", "operations")


@pytest.mark.parametrize("stage", REGIME_CONSUMING_STAGES)
def test_every_regime_consuming_stage_checks_its_labels(stage):
    source = inspect.getsource(getattr(cli, stage))
    assert "assert_labels_current" in source, (
        f"cli.{stage} reads metrics.csv and splits by regime without checking "
        "that the labels still match shocks.yaml. That is how a stale split "
        "reaches an artefact without anything crashing."
    )


def _committed():
    metrics = Path("results/metrics.csv")
    briefing = Path("results/briefing.md")
    if not (metrics.exists() and briefing.exists()):
        pytest.skip("no committed artefacts; run `make all`")
    return backtest.read(metrics), briefing.read_text(encoding="utf-8")


def test_the_committed_briefing_counts_match_the_committed_metrics():
    """The exact check that would have caught the drift."""
    frame, text = _committed()
    model = None
    for line in text.splitlines():
        if line.startswith("| Model |"):
            model = line.split("`")[1]
            break
    assert model, "briefing provenance names no model"

    mine = frame[frame["model"] == model]
    shock = int((mine["regime"] == regimes.SHOCK).sum())
    assert f"| Shock-month errors used | {shock} |" in text, (
        f"metrics.csv holds {shock} shock forecasts for {model}, but the "
        "committed briefing was built from a different number. Re-run "
        "`python make.py operations`."
    )


def test_the_committed_briefing_names_the_windows_it_was_built_from():
    frame, text = _committed()
    stored = sorted(frame["shocks_hash"].dropna().unique())
    assert len(stored) == 1, f"metrics.csv carries mixed shock labels: {stored}"
    assert f"| Shock windows | `{stored[0]}` |" in text, (
        "The committed briefing does not carry the shock-window fingerprint of "
        "the metrics.csv beside it. A briefing is read away from the run that "
        "produced it and has to say which windows it used."
    )


def test_the_committed_briefing_matches_the_shocks_file_on_disk():
    frame, text = _committed()
    config = Path("experiments/configs/shocks.yaml")
    if not config.exists():
        pytest.skip("no shocks.yaml")
    current = backtest.shocks_fingerprint(config)
    assert f"| Shock windows | `{current}` |" in text, (
        "shocks.yaml has been edited since the briefing was written. Run "
        "`python make.py relabel` then `python make.py operations`."
    )
    backtest.assert_labels_current(frame, config)

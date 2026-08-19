"""What each design choice bought, and whether the record can settle it.

The README's hand-written prose has always promised these readings -- "the gap
between those two columns isolates the switch itself" -- while the generated
section reported only a leaderboard, from which a reader had to subtract two
rows by eye. These tests cover the section that states the gaps, and in
particular that it states the ones that went the wrong way.

The frames are report-rendering fixtures. They never leave the test and
describe no shrine; see docs/claude_code_brief.md section 4.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from yatra import backtest, models, report

PAIR = models.Ablation(
    name="probe",
    treatment="treated",
    control="untreated",
    varies="the probe setting",
    question="does the probe setting help?",
)


def _table(clean: dict[str, float], shock: dict[str, float]) -> pd.DataFrame:
    frame = pd.DataFrame({"clean": clean, "shock": shock})
    for regime in ("clean", "shock"):
        frame[f"{regime}_rank"] = frame[regime].rank(method="min").astype(int)
    return frame


def _bootstrap(tmp_path: Path, shares: dict[str, float],
               confidence: float = 0.95) -> Path:
    """A minimal bootstrap artefact: ``p_beats`` for the probe pair per regime."""
    rows = [
        {
            "statistic": "p_beats",
            "model": PAIR.treatment,
            "opponent": PAIR.control,
            "regime": regime,
            "point": share,
            "n_usable": 2000,
            "confidence": confidence,
        }
        for regime, share in shares.items()
    ]
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "bootstrap.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


@pytest.fixture(autouse=True)
def one_declared_pair(monkeypatch):
    monkeypatch.setattr(models, "ABLATIONS", (PAIR,))


def test_a_choice_that_flips_sign_is_named_as_a_trade(tmp_path):
    table = _table({"treated": 1.0, "untreated": 1.2}, {"treated": 5.0, "untreated": 4.0})
    text = "\n".join(report._ablations(table, _bootstrap(tmp_path, {"clean": 0.9, "shock": 0.1})))

    assert "the sign flips between regimes" in text
    assert "better on clean months, worse on shock ones" in text
    assert "trades one regime against the other" in text
    assert "| -0.200 |" in text and "| +1.000 |" in text


def test_a_choice_that_helps_everywhere_is_not_dressed_as_a_trade(tmp_path):
    table = _table({"treated": 1.0, "untreated": 1.2}, {"treated": 4.0, "untreated": 4.5})
    text = "\n".join(report._ablations(table, _bootstrap(tmp_path, {"clean": 0.9, "shock": 0.9})))

    assert "lower error in both regimes" in text
    assert "sign flips" not in text
    assert "trades one regime" not in text


def test_a_choice_that_helps_nowhere_is_still_reported(tmp_path):
    """Constraint 7: a losing configuration stays in the table with its number."""
    table = _table({"treated": 1.5, "untreated": 1.2}, {"treated": 5.0, "untreated": 4.0})
    text = "\n".join(report._ablations(table, _bootstrap(tmp_path, {"clean": 0.1, "shock": 0.1})))

    assert "higher error in both regimes" in text
    assert "because it was tried, not because it worked" in text
    assert "`treated`" in text


def test_the_resolved_count_uses_the_bootstrap_declared_level(tmp_path):
    """The bar is read from the artefact, not typed into report.py."""
    table = _table({"treated": 1.0, "untreated": 1.2}, {"treated": 5.0, "untreated": 4.0})

    strict = "\n".join(report._ablations(
        table, _bootstrap(tmp_path / "a", {"clean": 0.90, "shock": 0.10}, confidence=0.95)))
    assert "**0** clear the bootstrap's declared 95% level" in strict

    lenient = "\n".join(report._ablations(
        table, _bootstrap(tmp_path / "b", {"clean": 0.90, "shock": 0.10}, confidence=0.90)))
    assert "**2** clear the bootstrap's declared 90% level" in lenient


def test_a_single_resolved_comparison_reads_as_singular(tmp_path):
    table = _table({"treated": 1.0, "untreated": 1.2}, {"treated": 5.0, "untreated": 4.0})
    text = "\n".join(report._ablations(
        table, _bootstrap(tmp_path, {"clean": 0.99, "shock": 0.50})))
    assert "**1** clears the bootstrap" in text


def test_the_table_renders_without_any_bootstrap(tmp_path):
    """The gaps are computable from metrics.csv alone; only the shares are not."""
    table = _table({"treated": 1.0, "untreated": 1.2}, {"treated": 5.0, "untreated": 4.0})
    text = "\n".join(report._ablations(table, tmp_path / "absent.csv"))

    assert "| -0.200 |" in text
    assert "With it better in" not in text
    assert "clear the bootstrap" not in text


def test_a_pair_whose_arms_are_missing_renders_nothing(tmp_path):
    table = _table({"other": 1.0}, {"other": 4.0})
    assert report._ablations(table, _bootstrap(tmp_path, {"clean": 0.9, "shock": 0.1})) == []


def test_the_section_reaches_the_rendered_readme(monkeypatch):
    monkeypatch.undo()
    if not Path("results/metrics.csv").exists():
        pytest.skip("no committed metrics; run `make backtest`")
    body = report.render()
    assert "### What each design choice is worth" in body
    for ablation in models.ABLATIONS:
        assert f"`{ablation.treatment}` vs `{ablation.control}`" in body

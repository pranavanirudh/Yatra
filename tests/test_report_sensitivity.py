"""The sensitivity arms have to reach the README, including when they disagree.

``sensitivity.py`` answers the one question that could unmake the headline: is
the inversion a property of the series, or of where somebody drew the shock
boundaries? It wrote that answer to a CSV and printed it to stdout, and for a
while that was where it stopped -- a reader of the README saw the finding and
not the check on it.

The numbers in these fixtures are report-rendering fixtures. They never leave
``tmp_path`` and describe no shrine; see docs/claude_code_brief.md section 4.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from yatra import report

ARMS = ["declared", "refined"]


def _write_arms(
    directory: Path,
    rho: dict[str, float],
    ranks: dict[str, dict[str, tuple[int, int]]],
) -> tuple[Path, Path]:
    """Write a sensitivity pair. ``ranks[arm][model] = (clean_rank, shock_rank)``."""
    directory.mkdir(parents=True, exist_ok=True)
    summary = pd.DataFrame(
        [
            {
                "arm": arm,
                "windows": f"experiments/configs/{arm}.yaml",
                "description": f"{arm} windows",
                "n_windows": 3,
                "shock_forecasts_per_model": 180,
                "rank_correlation": rho[arm],
                "p_value": 0.3,
                "inverts": rho[arm] < 0,
            }
            for arm in ranks
        ]
    )
    per_model = pd.DataFrame(
        [
            {
                "arm": arm,
                "model": model,
                "clean": float(clean_rank),
                "shock": float(shock_rank),
                "clean_rank": clean_rank,
                "shock_rank": shock_rank,
            }
            for arm, models in ranks.items()
            for model, (clean_rank, shock_rank) in models.items()
        ]
    )
    summary_path = directory / "sensitivity_summary.csv"
    per_model_path = directory / "sensitivity.csv"
    summary.to_csv(summary_path, index=False)
    per_model.to_csv(per_model_path, index=False)
    return summary_path, per_model_path


def _stable_ranks() -> dict[str, dict[str, tuple[int, int]]]:
    return {
        arm: {"sarima": (1, 3), "theta": (2, 2), "naive": (3, 1)} for arm in ARMS
    }


def test_agreeing_arms_render_and_name_the_two_winners(tmp_path: Path):
    paths = _write_arms(tmp_path, {"declared": -0.5, "refined": -0.4}, _stable_ranks())
    text = "\n".join(report._sensitivity(*paths))

    assert "2 of 2" in text
    assert "not an artefact of where the boundaries were drawn" in text
    assert "`sarima`" in text and "`naive`" in text
    assert "No model changes rank" in text


def test_a_disagreeing_arm_is_reported_not_hidden(tmp_path: Path):
    """The bad news has to render too, or the section's silence would carry it."""
    paths = _write_arms(tmp_path, {"declared": -0.5, "refined": +0.6}, _stable_ranks())
    text = "\n".join(report._sensitivity(*paths))

    assert "1 of 2" in text
    assert "depends on the boundary" in text
    assert "| `refined` — refined windows | 3 | 180 | +0.600 | no |" in text


def test_a_moving_winner_is_called_out(tmp_path: Path):
    ranks = _stable_ranks()
    ranks["refined"] = {"sarima": (2, 3), "theta": (1, 2), "naive": (3, 1)}
    paths = _write_arms(tmp_path, {"declared": -0.5, "refined": -0.4}, ranks)
    text = "\n".join(report._sensitivity(*paths))

    assert "do **not** hold first place" in text
    assert "boundary-dependent" in text
    assert "clean rank moves" in text
    assert "`sarima`" in text and "`theta`" in text


def test_multiline_arm_description_stays_on_one_table_row(tmp_path: Path):
    """The refined arm's description is a YAML block; a raw newline breaks the table."""
    summary_path, per_model_path = _write_arms(
        tmp_path, {"declared": -0.5, "refined": -0.4}, _stable_ranks()
    )
    summary = pd.read_csv(summary_path)
    summary.loc[summary["arm"] == "refined", "description"] = "line one\nline two\n"
    summary.to_csv(summary_path, index=False)

    lines = report._sensitivity(summary_path, per_model_path)
    rows = [line for line in lines if line.startswith("| `")]
    assert len(rows) == 2
    assert "line one line two" in rows[1]


def test_missing_artefacts_render_nothing_rather_than_raising(tmp_path: Path):
    assert report._sensitivity(tmp_path / "nope.csv", tmp_path / "also-nope.csv") == []


def test_a_single_arm_is_not_a_sensitivity_analysis(tmp_path: Path):
    ranks = {"declared": _stable_ranks()["declared"]}
    paths = _write_arms(tmp_path, {"declared": -0.5}, ranks)
    assert report._sensitivity(*paths) == []


def test_the_section_reaches_the_rendered_readme():
    """The committed artefacts must actually produce the section in `make report`."""
    if not Path("results/sensitivity_summary.csv").exists():
        pytest.skip("no committed sensitivity artefacts; run `make sensitivity`")
    body = report.render()
    assert "### Does the finding survive a different boundary?" in body

    summary = pd.read_csv("results/sensitivity_summary.csv")
    for row in summary.itertuples():
        assert f"{float(row.rank_correlation):+.3f}" in body

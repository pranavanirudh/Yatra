"""The per-window shock section.

The claim it makes is unusual for this project: not "here is a number" but
"here is a pattern across columns, none of which is individually resolvable".
That shape is easy to overstate, so what is tested here is mostly restraint.

Three things must hold. The section must derive its winners from the frame
rather than describing a fixed set of models. It must state the per-window
counts, because they are the reason no single column carries a claim. And the
block-structure paragraph -- the strongest sentence in the section -- must
appear only when the panel actually shows a block, never as boilerplate that
happens to be true of the committed data.
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd
import pytest

from yatra import regimes, report

from test_bootstrap import metrics_frame


def frame_with_windows(assignments: dict[str, float]) -> pd.DataFrame:
    """A shock panel where each window has a declared per-model error level.

    ``assignments`` maps window id -> a multiplier applied to a fixed per-model
    profile, so the caller decides whether two windows agree or disagree about
    the ordering. Arithmetic on literals, no observations involved.
    """
    profile = {"winner": 1.0, "middle": 2.0, "loser": 3.0}
    rows = []
    origin = pd.Period("2010-01", freq="M")
    for index, (window, sign) in enumerate(assignments.items()):
        for step in range(6):
            for model, level in profile.items():
                value = level if sign > 0 else (4.0 - level)
                rows.append({
                    "origin": origin + index * 12 + step,
                    "target": origin + index * 12 + step + 1,
                    "horizon": 1,
                    "model": model,
                    "regime": regimes.SHOCK,
                    "mase": value,
                    "shock_window": window,
                })
    return pd.DataFrame(rows)


def test_the_section_is_absent_without_the_column():
    frame = metrics_frame().drop(columns=["shock_window"])
    assert report._by_shock_type(frame) == []


def test_the_section_is_absent_with_a_single_window():
    frame = frame_with_windows({"only_one": 1.0})
    assert report._by_shock_type(frame) == []


def test_a_ragged_panel_is_refused_rather_than_ranked():
    """A model missing from one window would make the columns incomparable.

    Ranks would then be computed over different model sets column to column,
    and the table would look exactly as it does now. That is the ragged-panel
    failure the backtest already guards, reappearing at report time.
    """
    frame = frame_with_windows({"a": 1.0, "b": -1.0})
    frame = frame[~((frame["shock_window"] == "b") & (frame["model"] == "loser"))]
    assert report._by_shock_type(frame) == []


def test_winners_are_read_from_the_frame_not_named_in_the_source():
    """Flip the ordering in one window and the reported winner must follow."""
    agreeing = report._by_shock_type(frame_with_windows({"a": 1.0, "b": 1.0}))
    flipped = report._by_shock_type(frame_with_windows({"a": 1.0, "b": -1.0}))

    agreeing_text, flipped_text = "\n".join(agreeing), "\n".join(flipped)
    assert "2 different winners" not in agreeing_text
    assert "1 different winners" in agreeing_text or "winner" in agreeing_text
    assert "`b` &rarr; `loser`" in flipped_text, (
        "the ordering in window b was inverted, so its winner must be the model "
        "that is worst everywhere else. A section naming a fixed winner would "
        "pass the committed data and be wrong on any other."
    )


def test_disagreement_is_reported_as_disagreement():
    lines = "\n".join(report._by_shock_type(frame_with_windows({"a": 1.0, "b": -1.0})))
    row = [l for l in lines.splitlines() if l.startswith("| `a` | `b` |")]
    assert row, "no pairwise row for the two windows"
    assert row[0].rstrip().endswith("| no |"), (
        f"windows with opposite orderings were reported as agreeing: {row[0]}"
    )


def test_the_counts_are_stated_and_render_as_a_table_row():
    """The counts are the reason no column carries a claim, so they must show.

    They also have to sit inside the table. A one-row table with no header
    separator does not render as a table at all, which is how this shipped the
    first time.
    """
    lines = report._by_shock_type(frame_with_windows({"a": 1.0, "b": -1.0}))
    counts = [l for l in lines if "Forecasts per model" in l]
    assert counts, "the per-window counts are not stated"
    assert counts[0].startswith("| ") and counts[0].rstrip().endswith(" |")

    body = "\n".join(lines)
    header = [i for i, l in enumerate(lines) if l.startswith("| Model |")]
    separator = lines[header[0] + 1]
    assert set(separator.replace("|", "").replace("-", "").strip()) == set(), (
        f"the main table has no header separator: {separator!r}"
    )
    assert "resolvable on its own" in body, (
        "the section states per-window counts without saying what they mean for "
        "reading a single column"
    )


@pytest.mark.parametrize("assignments,expect_block", [
    ({"covid_one": 1.0, "covid_two": 1.0, "floods_x": -1.0}, True),
    ({"covid_one": 1.0, "covid_two": -1.0, "floods_x": -1.0}, False),
])
def test_the_block_claim_appears_only_when_the_panel_shows_a_block(
    assignments, expect_block
):
    """The strongest sentence in the section is also the easiest to overstate.

    It asserts that every COVID pair agrees and every straddling pair does not.
    When the COVID windows disagree among themselves that is simply false, and
    the section must fall silent rather than print it anyway.
    """
    body = "\n".join(report._by_shock_type(frame_with_windows(assignments)))
    claim = "Every pair of COVID-era windows agrees" in body
    assert claim is expect_block, (
        "the block-structure claim was printed for a panel that does not show "
        "one" if claim else
        "the block-structure claim was withheld from a panel that does show one"
    )


QUALIFIER = "cannot carry the weight the picture suggests"


@pytest.mark.parametrize("n_other", [1, 2, 3, 4])
def test_the_contrast_is_qualified_until_three_non_covid_windows_exist(n_other):
    """One non-COVID window compared against four COVID ones is one observation.

    Every "these disagree" correlation in that table involves the same single
    window, so four negative cells are one window counted four times. The
    heatmap renders that as a clean block of colour, and the cleanliness comes
    from having one window on one side rather than from the evidence. The
    generated text has to say so until there are enough non-COVID windows for
    the contrast to be something other than one window's idiosyncrasy.

    Same reasoning as CLAUDE.md 3.9 applies to per-window bootstrap intervals:
    do not let a presentation imply weight the panel does not have.
    """
    assignments = {"covid_a": 1.0, "covid_b": 1.0}
    for index in range(n_other):
        assignments[f"other_{index}"] = -1.0

    body = "\n".join(report._by_shock_type(frame_with_windows(assignments)))
    qualified = QUALIFIER in body

    assert qualified is (n_other < report.NON_COVID_FLOOR), (
        f"with {n_other} non-COVID window(s) the contrast was "
        f"{'qualified' if qualified else 'left unqualified'}, which is wrong: "
        f"below {report.NON_COVID_FLOOR} it rests on too few windows to "
        "distinguish a type effect from one window being odd."
    )


def test_the_qualification_counts_the_windows_it_actually_has():
    body = "\n".join(report._by_shock_type(
        frame_with_windows({"covid_a": 1.0, "covid_b": 1.0, "floods_x": -1.0})
    ))
    assert "rests on 1 non-COVID window (`floods_x`)" in body
    assert "one window compared 2 times" in body, (
        "the qualification must state how many of the negative correlations are "
        "the same window, derived from the panel rather than described"
    )


def test_the_mechanism_is_marked_as_a_hypothesis_not_a_finding():
    """A story fitted to one window is a hypothesis and must be labelled one.

    "It handles the shock shape it was designed for" is exactly the sentence a
    reader carries away and repeats, and on a single window there is nothing
    separating it from that window having an odd winner for no reason.
    """
    body = "\n".join(report._by_shock_type(
        frame_with_windows({"covid_a": 1.0, "covid_b": 1.0, "floods_x": -1.0})
    ))
    assert "hypothesis fitted to one window" in body
    assert "not evidence for itself" in body


def test_the_section_types_no_numbers_of_its_own(committed_frame):
    """Every figure in the section has to come off the panel, 3.1 as usual.

    The pooled shock count was typed here once, which survived a re-run only
    because the number happened not to change.
    """
    import ast
    import inspect
    import textwrap

    # Parsed rather than pattern-matched. A regex over the source spans from a
    # quote in one literal to a quote in the next and reports the arithmetic in
    # between -- which is how this test first "found" the *100 in a percentage.
    tree = ast.parse(textwrap.dedent(inspect.getsource(report._by_shock_type)))
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            offenders += [
                (node.value[:60], found)
                for found in re.findall(r"\b\d{2,}\b", node.value)
            ]
    assert not offenders, (
        f"numeric literals inside the section's own strings: {offenders}. "
        "Derive them from the frame; a number typed here cannot be traced to a "
        "row."
    )


def test_the_committed_section_reports_its_thinnest_window(committed_frame):
    """Whatever the record says, the section must quote the smallest count."""
    lines = report._by_shock_type(committed_frame)
    if not lines:
        pytest.skip("committed metrics carry fewer than two shock windows")
    body = "\n".join(lines)

    rows = committed_frame[
        (committed_frame["regime"] == regimes.SHOCK)
        & committed_frame["shock_window"].notna()
    ]
    per_window = rows.groupby("shock_window").size() / rows["model"].nunique()
    assert f"{int(per_window.min())} forecasts per model" in body


@pytest.fixture
def committed_frame():
    from pathlib import Path

    from yatra import backtest

    path = Path("results/metrics.csv")
    if not path.exists():
        pytest.skip("no committed metrics.csv; run `make all`")
    return backtest.read(path)

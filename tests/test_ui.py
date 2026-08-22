"""The answer console must refuse, cite, and disclose.

Three properties are worth a test here, and they are not the ones a UI usually
gets tested for.

**It must not answer the wrong question confidently.** A keyword matcher that
returns its least-bad match will hand somebody the forecast when they asked how
many marshals to deploy, and the card will look exactly as authoritative either
way. That routing is exercised through the real matcher in node, because
asserting things about the HTML cannot catch it.

**Every number must still trace to a row.** The page is where a typed constant
would be least visible: nobody cross-checks a sentence. So every artefact an
answer cites has to exist, and the losing models have to be on the page.

**It must disclose what the project has not settled.** The unverified shock
windows and the absent planning ratios are the two open items, and a friendly
page is exactly where they would be quietly dropped.
"""

from __future__ import annotations

import inspect
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from yatra import cli, ui

REQUIRED = (
    Path("results/metrics.csv"),
    Path("results/bootstrap.csv"),
    Path("results/operations.csv"),
    Path("results/sensitivity_summary.csv"),
    Path("results/festivals.csv"),
    Path("data/raw/monthly.csv"),
)


def _artefacts():
    missing = [str(p) for p in REQUIRED if not p.exists()]
    if missing:
        pytest.skip(f"no committed artefacts ({missing[0]}); run `make all`")
    return ui.load()


@pytest.fixture(scope="module")
def artefacts():
    return _artefacts()


@pytest.fixture(scope="module")
def answers(artefacts):
    return ui.build_answers(artefacts)


@pytest.fixture(scope="module")
def page(artefacts, answers):
    return ui.render(artefacts, answers)


# --------------------------------------------------------------------------
# the declared-not-inferred scar, applied to the answer bank
# --------------------------------------------------------------------------

def test_every_answer_builder_is_declared_in_the_bank():
    """CLAUDE.md 3.3, in its third incarnation.

    A bank assembled by scanning the module for ``_answer_`` functions would
    survive a rename. A bank assembled from a literal tuple loses a member
    loudly -- and this test is what makes it loud, because the page's own
    failure mode is silent: it just says it cannot answer a question it used to.
    """
    defined = {
        name for name, obj in vars(ui).items()
        if name.startswith("_answer_") and inspect.isfunction(obj)
    }
    declared = {builder.__name__ for builder in ui.BUILDERS}
    assert defined == declared, (
        f"answer builders defined but not in ui.BUILDERS: {defined - declared}; "
        f"declared but not defined: {declared - defined}. A builder missing from "
        "the tuple is an answer the page silently stops giving."
    )


def test_the_bank_is_not_empty_and_every_answer_is_complete(answers):
    assert len(answers) >= 8
    for answer in answers:
        assert answer.headline.strip(), f"{answer.id} has no headline"
        assert answer.body.strip(), f"{answer.id} has no body"
        assert answer.sources, f"{answer.id} cites nothing"
        assert answer.question.strip().endswith("?"), (
            f"{answer.id} is keyed to something that is not a question"
        )


# --------------------------------------------------------------------------
# provenance
# --------------------------------------------------------------------------

def test_every_cited_artefact_exists(answers):
    """An answer citing a file that is not there is worse than one citing nothing."""
    for answer in answers:
        for source in answer.sources:
            assert Path(source.artefact).exists(), (
                f"answer '{answer.id}' cites {source.artefact}, which does not "
                "exist. The citation line on the card is the only thing letting a "
                "reader check a number, so it has to point somewhere real."
            )
            assert source.detail.strip(), (
                f"answer '{answer.id}' cites {source.artefact} without saying "
                "which rows"
            )


def test_the_page_names_every_model_including_the_losers(page, artefacts):
    """Constraint 7: a model that underperforms stays in the table with its number."""
    for model in sorted(artefacts.metrics["model"].unique()):
        assert model in page, (
            f"{model} is scored in metrics.csv but does not appear on the page. "
            "Dropping a losing configuration from the reader-facing surface is "
            "falsification even when the CSV still has it."
        )


def test_the_page_reports_the_model_that_could_not_be_fitted(page, artefacts):
    if artefacts.applicability is None or artefacts.applicability.empty:
        pytest.skip("no model reported unfittable")
    for model in artefacts.applicability["model"]:
        assert model in page, (
            f"{model} could not be fitted and is absent from the page. An "
            "unfittable model is a result about the record, not a bug to hide."
        )


# --------------------------------------------------------------------------
# disclosure
# --------------------------------------------------------------------------

def test_the_monthly_caveat_survives(page):
    """docs/operations.md: the briefing must keep saying these are monthly.

    Same reasoning, higher stakes. This page reads like a planning tool to
    someone who will never open the briefing.
    """
    assert "per month" in page
    assert "crush" in page, (
        "The page does not say anywhere that a monthly total cannot identify a "
        "crush risk. That caveat is the reason this project does not pretend to "
        "size a single afternoon."
    )


def test_no_planning_ratios_are_invented(page):
    """CLAUDE.md 3.5. The friendly surface is where a default would hide best."""
    assert "No resourcing ratios are declared" in page
    assert "operational authority" in page


def test_unverified_shock_windows_are_disclosed(page, artefacts):
    from yatra import regimes

    pending = regimes.unverified(artefacts.windows)
    if not pending:
        pytest.skip("all windows verified")
    assert "not yet audited" in page
    for window in pending:
        assert window.id in page, (
            f"shock window {window.id} is unverified and is not named on the "
            "page. The regime split rests on it, so a reader has to be able to "
            "see which boundary is unaudited."
        )


# --------------------------------------------------------------------------
# self-containment
# --------------------------------------------------------------------------

def test_the_page_loads_nothing_from_the_network(page):
    """One file. It is opened from a filesystem, often offline, sometimes years later.

    Anchors are exempt and deliberately so: the shock-window citations link out
    to the reporting behind them, and a page whose premise is traceability has
    to let a reader follow one. What must not happen is the page *fetching*
    anything to render itself.
    """
    fetched = re.findall(r'\bsrc\s*=\s*"([^"]*)"', page)
    fetched += re.findall(r'<link\b[^>]*\bhref\s*=\s*"([^"]*)"', page)
    remote = [url for url in fetched if not url.startswith("data:")]
    assert not remote, (
        f"the page fetches {remote} at open time. It is meant to be one "
        "self-contained file that renders from a USB stick with no network."
    )


def test_shock_window_citations_are_reachable_from_the_page(page, artefacts):
    for window in artefacts.windows:
        assert window.source.url in page, (
            f"the citation for {window.id} is not linked on the page. A reader "
            "who wants to check where a shock window came from should not have "
            "to open a YAML file to find out."
        )


def test_the_payload_is_valid_json_and_cannot_close_its_own_script_tag(page):
    blob = re.search(r"window\.__YATRA__=(.*?);</script>", page, re.S)
    assert blob, "no payload found in the page"
    raw = blob.group(1)
    assert "</script" not in raw.lower(), (
        "an unescaped closing script tag in the payload would truncate the page"
    )
    payload = json.loads(raw)
    assert payload["answers"], "the payload carries no answers"
    assert payload["observations"], "the payload carries no observations"


def test_the_lookup_payload_invents_no_months(artefacts):
    """The observation table in the page must be the observation file, exactly."""
    tables = ui.lookup_tables(artefacts)
    expected = {
        str(row["month"]): int(row["pilgrims"])
        for _, row in artefacts.monthly.iterrows()
    }
    assert tables["observations"] == expected


def test_part_years_are_not_reported_as_annual_totals(artefacts):
    """A seven-month total shown beside twelve-month ones reads as a collapse."""
    tables = ui.lookup_tables(artefacts)
    counts: dict[str, int] = {}
    for month in tables["observations"]:
        counts[month[:4]] = counts.get(month[:4], 0) + 1
    for year in tables["annual"]:
        assert counts[year] == 12, (
            f"{year} is reported as an annual total from {counts[year]} months"
        )


# --------------------------------------------------------------------------
# routing -- the part only the real matcher can answer
# --------------------------------------------------------------------------

#: (question, id of the answer it must reach). "?" means it must be refused.
#: These are the confusions that actually happened while the matcher was being
#: built, kept as the regression set.
ROUTES = (
    ("how many marshals do I need", "How many marshals"),
    ("what can this NOT tell me?", "What can this NOT tell"),
    ("which model is best", "Which forecasting model"),
    ("how accurate is this really", "How accurate"),
    ("what data is this built on", "What data"),
    ("did any model fail to run", "Did any model fail"),
    ("what counts as a disrupted month", "What counts as a disrupted"),
    ("what if there is a disruption", "What happens to these numbers"),
    ("do different kinds of disruption behave differently", "Is a disruption a disruption"),
    ("how does this whole thing work", "How does this whole thing"),
    ("how are the festival dates worked out", "How are the festival dates"),
    ("how many pilgrims are expected next month", "Forecast for"),
    ("what is the forecast for October 2026", "Forecast for October 2026"),
    ("how many people came in March 2020", "The record for March 2020"),
    ("how many pilgrims in 2019", "The record for 2019"),
    ("how many people came in 1985", "The record for 1985"),
    ("when is Diwali", "Diwali"),
    ("what is the capital of France", "Not understood"),
    ("hello", "Not understood"),
    ("", None),
)


@pytest.fixture(scope="module")
def routed(page, tmp_path_factory):
    if shutil.which("node") is None:
        pytest.skip("node not available; matcher routing not exercised")
    built = tmp_path_factory.mktemp("ui") / "yatra.html"
    built.write_text(page, encoding="utf-8")
    probe = Path(__file__).parent / "ui_probe.js"
    questions = "\n".join(q for q, _ in ROUTES if q)
    result = subprocess.run(
        ["node", str(probe), str(built)],
        input=questions, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    return {
        json.loads(line)["q"]: json.loads(line)
        for line in result.stdout.splitlines() if line.strip()
    }


@pytest.mark.parametrize("question,expected", [r for r in ROUTES if r[0]])
def test_questions_reach_the_answer_they_asked_for(routed, question, expected):
    got = routed[question]
    assert expected in got["asked"], (
        f"asked {question!r} and got the answer to {got['asked']!r}. A page that "
        "answers a question the reader did not ask, in the same confident "
        "typeface, is the failure mode in the brief wearing a friendly face."
    )


def test_a_forecast_answer_always_carries_the_monthly_caveat(routed):
    for question, expected in ROUTES:
        if not question or not expected or "Forecast for" not in expected:
            continue
        caveats = " ".join(routed[question]["caveats"])
        assert "per month" in caveats, (
            f"the answer to {question!r} gives a planning number with no "
            "statement that it is monthly"
        )


def test_every_answer_the_matcher_returns_cites_something(routed):
    for question, expected in ROUTES:
        if not question:
            continue
        got = routed[question]
        if got["asked"] == "Not understood":
            continue
        assert got["sources"], f"{question!r} answered with no citation"


# --------------------------------------------------------------------------
# wiring
# --------------------------------------------------------------------------

def test_ui_is_a_stage_and_runs_after_the_artefacts_it_reads():
    assert "ui" in cli.STAGES
    order = cli.ALL_ORDER
    assert "ui" in order, "`ui` is not part of `all`, so the page goes stale"
    for produced_first in ("backtest", "bootstrap", "sensitivity", "figures",
                           "operations"):
        assert order.index(produced_first) < order.index("ui"), (
            f"`ui` runs before `{produced_first}`, so it would render the "
            "previous run's artefacts"
        )

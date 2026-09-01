"""The answer console must refuse, cite, and disclose.

Three properties are worth a test here, and they are not the ones a UI usually
gets tested for.

**It must not answer the wrong question confidently.** A keyword matcher that
returns its least-bad match will hand somebody the forecast when they asked how
many marshals to deploy, and the card will look exactly as authoritative either
way. The routing is defined in `ui.resolve` and exercised here directly; the
copy of it the page carries is driven over the same battery through node and
required to reach the same card, byte for byte.

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


@pytest.fixture(scope="module")
def payload(artefacts, answers):
    return ui.build_payload(artefacts, answers)


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
    # The page must distinguish a boundary somebody announced from one this
    # project inferred, and must not present the second as a pending chore --
    # no amount of diligence turns a judgement about the series into a citation.
    assert "from the figures" in page
    assert "not a gap waiting to be" in page, (
        "the page describes the inferred boundaries as unfinished work. They are "
        "correctly marked, and calling them a gap implies the split gets sounder "
        "once somebody checks them, which it does not."
    )
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


#: Things the browser must not be seen doing. Every one of them was in the
#: matcher before the answers were rendered in Python: it divided by 1e5 to get
#: lakh, rounded a year-on-year change to one place, and grouped thousands with
#: a regex -- a second, untested copy of `_lakh`, `_people` and `_pct` living
#: inside a string constant. A number a reader sees has to come from the same
#: function every other number in this project comes from.
BROWSER_ARITHMETIC = ("toFixed", "toLocaleString", "Math.round", "1e5",
                      "parseFloat", "reduce(")


def test_the_browser_formats_no_numbers():
    found = [token for token in BROWSER_ARITHMETIC if token in ui.SCRIPT]
    assert not found, (
        f"ui.SCRIPT contains {found}. The page's job is to look a card up; a "
        "figure it formats itself is one no test in this repository can reach, "
        "and one that can drift from the artefact it was read out of."
    )


def test_every_route_addresses_a_card_and_every_card_is_addressed(payload):
    """The routing tables and the deck must agree in both directions.

    An index off the end of the deck is a question that answers with nothing.
    A card nothing addresses is the other failure this project keeps meeting:
    an answer built, shipped, and silently unreachable -- CLAUDE.md 3.3 in its
    fourth incarnation.
    """
    cards = payload["cards"]

    addressed: set[int] = {
        payload["outsideMonth"], payload["outsideYear"], payload["unknown"],
        payload["nextMonth"], payload["festivals"]["none"],
    }
    addressed.update(a["card"] for a in payload["answers"])
    for table in ("forecast", "observations", "years"):
        addressed.update(payload[table].values())
    for route in payload["festivals"]["routes"] + [payload["festivals"]["generic"]]:
        addressed.update(route["years"].values())
        addressed.add(route["upcoming"])

    out_of_range = sorted(i for i in addressed if not 0 <= i < len(cards))
    assert not out_of_range, f"routes point at cards {out_of_range}, which do not exist"

    orphans = sorted(set(range(len(cards))) - addressed)
    assert not orphans, (
        f"{len(orphans)} cards are rendered into the page and reachable by no "
        f"question: {[cards[i]['asked'] for i in orphans[:5]]}"
    )


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
# routing -- which card a question reaches
# --------------------------------------------------------------------------
#
# `ui.resolve` is the definition and is exercised by pytest alone. The page
# carries a copy of it, because a query does not exist until somebody types
# one; the copy is not left on trust, and the conformance test below drives
# both over the same battery through node and requires the same card out of
# each. If node is absent only that check skips -- the routing itself is still
# tested, which it was not while it lived in a string constant.

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
    # The question a reader is most likely to arrive with. It returned
    # "Not understood" until the scope answer existed, which reads as
    # "probably, but I cannot say" when the answer is a flat no.
    ("does this apply to Tirupati", "Does any of this apply"),
    ("what about sabarimala", "Does any of this apply"),
    ("can I use this for another temple", "Does any of this apply"),
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


#: Questions the regression set does not cover, run only for conformance. Each
#: is a place the two copies could disagree without either looking wrong on its
#: own: a month word that is also a modal verb, an ISO date with an impossible
#: month, the guard that keeps "horizon" from being read as a year, a festival
#: spelled with a diacritic, punctuation the tokeniser strips.
CONFORMANCE_EXTRAS = (
    "MARCH 2020",
    "2020/03",
    "2020-3",
    "2085/13",
    "when is navratri in 2027",
    "navratri 1993",
    "festivals in 1999",
    "when is the next festival",
    "how many people may come",
    "may 2019",
    "what about the horizon in 2019",
    "sep 2021",
    "sept 2021",
    "diwali & lakshmi puja!",
    "Navrātri 2026",
    "how many, in October?",
)

#: Everything both copies are driven over.
BATTERY = tuple(q for q, _ in ROUTES if q) + CONFORMANCE_EXTRAS


@pytest.mark.parametrize("question,expected", [r for r in ROUTES if r[0]])
def test_questions_reach_the_answer_they_asked_for(payload, question, expected):
    got = ui.resolve(payload, question)
    assert expected in got["asked"], (
        f"asked {question!r} and got the answer to {got['asked']!r}. A page that "
        "answers a question the reader did not ask, in the same confident "
        "typeface, is the failure mode in the brief wearing a friendly face."
    )


def test_a_question_that_asked_nothing_is_answered_with_nothing(payload):
    """An empty box is not a question, and must not open a card."""
    for blank in ("", "   ", "\t"):
        assert ui.resolve(payload, blank) is None


def test_a_forecast_answer_always_carries_the_monthly_caveat(payload):
    for question, expected in ROUTES:
        if not question or not expected or "Forecast for" not in expected:
            continue
        assert "per month" in ui.resolve(payload, question)["html"], (
            f"the answer to {question!r} gives a planning number with no "
            "statement that it is monthly"
        )


def test_every_answer_the_matcher_returns_cites_something(payload):
    for question in BATTERY:
        got = ui.resolve(payload, question)
        if got["asked"] == "Not understood":
            continue
        assert 'class="prov"' in got["html"], (
            f"{question!r} answered with no citation"
        )


@pytest.fixture(scope="module")
def routed(page, tmp_path_factory):
    if shutil.which("node") is None:
        pytest.skip("node not available; the browser's copy is not checked")
    built = tmp_path_factory.mktemp("ui") / "yatra.html"
    built.write_text(page, encoding="utf-8")
    probe = Path(__file__).parent / "ui_probe.js"
    # utf-8 explicitly, and a timeout. The battery carries a question with a
    # diacritic in it; piped under the Windows locale encoding the write fails
    # in a thread, node never sees end-of-input, and the test hangs rather than
    # failing.
    result = subprocess.run(
        ["node", str(probe), str(built)],
        input="\n".join(BATTERY), capture_output=True, text=True,
        encoding="utf-8", timeout=120,
    )
    assert result.returncode == 0, result.stderr
    return {
        json.loads(line)["q"]: json.loads(line)
        for line in result.stdout.splitlines() if line.strip()
    }


@pytest.mark.parametrize("question", BATTERY)
def test_the_browser_routes_exactly_as_python_does(routed, payload, question):
    """The one duplicated rule in the page, pinned.

    Everything else the console shows is written once, in Python, and looked up.
    This cannot be: the query is not knowable until it is typed, so the routing
    exists twice. Two definitions of one rule is what the rest of this module
    was changed to stop having, so the second one is checked against the first
    rather than believed -- not only on the card it picks, but on every byte of
    what that card renders, because a slot filled differently on the two sides
    would show a reader a date nothing in `results/` holds.
    """
    expected = ui.resolve(payload, question)
    got = routed[question]
    assert got["asked"] == expected["asked"], (
        f"asked {question!r}: the page answers {got['asked']!r} and ui.resolve "
        f"answers {expected['asked']!r}. The page's copy of the routing has "
        "drifted from the definition in ui.py."
    )
    assert got["html"] == expected["html"], (
        f"asked {question!r}: both reached {expected['asked']!r} and rendered "
        "it differently."
    )


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


def test_every_drawn_figure_has_a_caption_on_the_page():
    """A figure the pipeline draws and the console ignores is a silent omission.

    `_figures` skips any file that is not in `FIGURE_CAPTIONS`, and skips any
    caption whose file is absent, without either case raising. That is the right
    behaviour at render time -- a page that half-exists is worse than one that
    quietly shows less -- but it means the two lists can drift apart with
    nothing failing, which is the scar of CLAUDE.md §3.3, §3.7 and §3.8 in its
    figure-shaped form. `inversion_hero.png` was exactly that for one commit:
    drawn by `make figures`, absent from the console, and no test the poorer.

    Checked against `figures.build_all`, which is the declaration of what the
    pipeline draws, rather than against `results/figures/` on disk -- a stale
    PNG left behind by a deleted figure must not be able to satisfy this.
    """
    from yatra import figures

    source = inspect.getsource(figures.build_all)
    drawn = set(re.findall(r'directory / "([^"]+\.png)"', source))
    assert drawn, "Could not read the figure list out of figures.build_all."

    captioned = {name for name, _, _ in ui.FIGURE_CAPTIONS}

    uncaptioned = sorted(drawn - captioned)
    assert not uncaptioned, (
        f"{uncaptioned} are drawn by make figures but carry no caption in "
        "ui.FIGURE_CAPTIONS, so the console silently omits them. Add a caption "
        "saying what each one is evidence of, or stop drawing it."
    )


def test_no_caption_names_a_figure_nothing_draws():
    """The other direction: a caption for a figure that no longer exists.

    `_figures` skips it silently, so the page loses a panel and the console
    still renders cleanly.

    `bootstrap_intervals.png` is exempted rather than matched. It is named in
    `build_all` like the others, so it satisfies this check today, but it is
    the one figure drawn conditionally -- only when a bootstrap frame is passed
    -- and a refactor that moved it behind a helper would fail this test for a
    figure the console is right to caption. The exemption records that, so the
    failure would have to be a real one.
    """
    from yatra import figures

    source = inspect.getsource(figures.build_all)
    drawn = set(re.findall(r'directory / "([^"]+\.png)"', source))
    conditional = {"bootstrap_intervals.png"}

    captioned = {name for name, _, _ in ui.FIGURE_CAPTIONS}
    orphans = sorted(captioned - drawn - conditional)
    assert not orphans, (
        f"ui.FIGURE_CAPTIONS names {orphans}, which figures.build_all does not "
        "draw. The console would silently render without them."
    )


def test_figure_captions_are_unique_and_say_something():
    """Each entry must name a distinct file and carry a real caption.

    A duplicated filename would render the same panel twice; an empty caption
    would make the figure decoration, which is the thing FIGURE_CAPTIONS exists
    to prevent.
    """
    names = [name for name, _, _ in ui.FIGURE_CAPTIONS]
    assert len(names) == len(set(names)), f"Duplicate figure entries: {names}"

    for name, title, caption in ui.FIGURE_CAPTIONS:
        assert title.strip(), f"{name} has no title."
        assert len(caption.strip()) > 40, (
            f"{name} has a caption too short to say what it is evidence of."
        )

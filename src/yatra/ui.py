"""Answer console: one self-contained HTML page, built from artefacts only.

The rest of this project talks to people who read Markdown and run `pytest`.
This stage exists for the people who do not: a duty officer, a planning
committee, somebody who wants to know how many pilgrims are expected in October
and has no interest in what a MASE is.

**What this is not.** It is not a dashboard, a server, or a web application, and
it adds no dependency to `pyproject.toml`. It is one HTML file written to
`results/yatra.html` by `make ui`, in the same way `figures.py` writes PNGs. It
holds no live code path into the models: by the time this module runs, every
number it can show has already been computed, scored and committed. Opening the
file does not run a forecast, and closing it does not lose one.

**Why it is generated rather than hand-written.** The same reason the README's
results section is (CLAUDE.md 3.1). A page that answers "how many people are
expected next month" in plain language is exactly the surface where a typed
number would be least visible and most trusted -- nobody cross-checks a sentence
the way they cross-check a table. So no answer in this file contains a numeric
literal. Every figure in every sentence is interpolated from an artefact, and
every answer carries the artefact and row it came from, rendered on the card
where the reader can see it rather than in a footnote.

**Why it refuses rather than guesses.** The matcher is a keyword scorer over a
declared bank of answers plus a small set of lookup handlers for months, years
and festivals. When nothing scores above the floor it says so and lists what it
can answer. It never picks the least-bad match and presents it as the answer,
because a confident answer to a question the reader did not ask is the same
failure this project is built against: a plausible output emitted quietly.
"""

from __future__ import annotations

import base64
import datetime as dt
import json
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from . import regimes, report
from .errors import ConfigError

RESULTS_DIR = Path("results")
DATA_DIR = Path("data/raw")
CONFIG_DIR = Path("experiments/configs")

#: Minimum match score before an answer is shown. Below this the page says it
#: does not know rather than showing the least-bad match.
MATCH_FLOOR = 2

#: Suggested questions shown beside the box. The rest of the bank is browsable
#: below it, so this is a starting point rather than a menu.
CHIP_COUNT = 6

#: The caveat that travels with every forecast answer, in the same words the
#: briefing uses. docs/operations.md explains why it is not optional: a monthly
#: total cannot size a single afternoon, and a page that reads like a planning
#: tool has to say so where the planning number is, not three screens away.
MONTHLY_CAVEAT = (
    "These are pilgrims <strong>per month</strong>. They size what a month needs. "
    "They cannot tell you the load on any given day or hour, so they cannot "
    "identify a crush risk on a particular afternoon."
)


# --------------------------------------------------------------------------
# formatting
# --------------------------------------------------------------------------

def _people(value: float) -> str:
    return f"{value:,.0f}"


def _lakh(value: float) -> str:
    # An exact zero is a real floor here -- the shrine has closed -- and it
    # appears in headlines. "0.00 lakh" reads like a rounding artefact of some
    # small number; "zero" reads like what it is.
    if value == 0:
        return "zero"
    return f"{value / 1e5:,.2f} lakh"


def _both(value: float) -> str:
    return f"{_lakh(value)} &middot; {_people(value)} people"


def _pct(value: float, places: int = 1) -> str:
    return f"{value * 100:.{places}f}%"


def _num(value: float, places: int = 3) -> str:
    return f"{value:.{places}f}"


def _month_name(period: pd.Period) -> str:
    return period.strftime("%B %Y")


# --------------------------------------------------------------------------
# artefact loading
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Source:
    """Where an answer's numbers came from, shown on the answer card itself."""

    artefact: str
    detail: str

    def as_dict(self) -> dict[str, str]:
        return {"artefact": self.artefact, "detail": self.detail}


@dataclass
class Answer:
    """One declared question the page can answer.

    ``keywords`` are scored, not matched: a query needs several hits to clear
    :data:`MATCH_FLOOR`, so one incidental word does not resolve an answer.
    """

    id: str
    question: str
    headline: str
    body: str
    keywords: tuple[str, ...]
    sources: tuple[Source, ...]
    caveats: tuple[str, ...] = ()
    chip: str | None = None

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "question": self.question,
            "headline": self.headline,
            "body": self.body,
            "keywords": list(self.keywords),
            "sources": [s.as_dict() for s in self.sources],
            "caveats": list(self.caveats),
            "chip": self.chip,
        }


@dataclass
class Artefacts:
    """Everything read off disk, loaded once so the answers cannot disagree."""

    metrics: pd.DataFrame
    bootstrap: pd.DataFrame
    operations: pd.DataFrame
    sensitivity: pd.DataFrame
    festivals: pd.DataFrame
    monthly: pd.DataFrame
    windows: list[regimes.ShockWindow]
    applicability: pd.DataFrame | None = None
    calendar_config: dict = field(default_factory=dict)
    figures: list[tuple[str, str, str]] = field(default_factory=list)


def _read(path: Path, required: bool = True) -> pd.DataFrame | None:
    if not path.exists():
        if required:
            raise ConfigError(
                f"{path} is missing. The answer console is built from committed "
                "artefacts and computes nothing itself -- run "
                "`python make.py all` first."
            )
        return None
    return pd.read_csv(path)


#: Figure files, with the sentence each one is there to make. A figure without a
#: caption is decoration; these are evidence, and the caption says of what.
FIGURE_CAPTIONS: tuple[tuple[str, str, str], ...] = (
    ("series_shocks.png", "The record, with the disrupted months shaded",
     "Every month in the observation set. The shaded bands are the declared "
     "shock windows -- the months the leaderboard is split on."),
    ("regime_ranking.png", "The same models, scored twice",
     "Mean error on ordinary months against mean error on disrupted ones. If "
     "the ranking were stable the two columns would agree. They do not."),
    ("rank_shift.png", "How far each model moves between the two",
     "One line per model, from its clean-month rank to its shock-month rank. "
     "The crossing lines are the finding."),
    ("bootstrap_intervals.png", "How much of this the record can settle",
     "Block-bootstrap intervals over the origin set. The shock intervals are "
     "the wide ones, because there are far fewer disrupted months."),
    ("shock_type_agreement.png", "Whether two disruptions agree on the model",
     "One cell per pair of declared shock windows. Blue is agreement, red is "
     "disagreement. The COVID windows agree with each other and all of them "
     "disagree with the 2025 landslide -- that block is the finding."),
    ("horizon_profile.png", "Whether the lead time changes the answer",
     "Error by forecast horizon, within each regime."),
    ("forecast_vs_actual_h1.png", "One month ahead, against what happened",
     "The one-step-ahead forecast track across the record."),
)


def _figures(directory: Path) -> list[tuple[str, str, str]]:
    """Embed each figure as a data URI so the page stays one shareable file."""
    out: list[tuple[str, str, str]] = []
    if not directory.exists():
        return out
    for filename, title, caption in FIGURE_CAPTIONS:
        path = directory / filename
        if not path.exists():
            continue
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        out.append((title, caption, f"data:image/png;base64,{encoded}"))
    return out


def load(
    results_dir: Path = RESULTS_DIR,
    data_dir: Path = DATA_DIR,
    config_dir: Path = CONFIG_DIR,
) -> Artefacts:
    """Read every artefact the page draws on. Raises if a required one is absent."""
    import yaml

    calendar_path = config_dir / "calendar.yaml"
    calendar_config: dict = {}
    if calendar_path.exists():
        calendar_config = yaml.safe_load(calendar_path.read_text(encoding="utf-8")) or {}

    return Artefacts(
        metrics=_read(results_dir / "metrics.csv"),
        bootstrap=_read(results_dir / "bootstrap.csv"),
        operations=_read(results_dir / "operations.csv"),
        sensitivity=_read(results_dir / "sensitivity_summary.csv"),
        festivals=_read(results_dir / "festivals.csv"),
        monthly=_read(data_dir / "monthly.csv"),
        windows=regimes.load_windows(config_dir / "shocks.yaml"),
        applicability=_read(results_dir / "applicability.csv", required=False),
        calendar_config=calendar_config,
        figures=_figures(results_dir / "figures"),
    )


# --------------------------------------------------------------------------
# derived tables
# --------------------------------------------------------------------------

def leaderboard(metrics: pd.DataFrame) -> pd.DataFrame:
    """Mean MASE per model per regime, with the rank within each column.

    This is the same aggregation ``report.py`` performs for the README. It is
    recomputed here from the same file rather than parsed back out of the
    Markdown, because a page that scraped the README would go stale the moment
    somebody reworded a heading.
    """
    table = (
        metrics.groupby(["model", "regime"])["mase"]
        .mean()
        .unstack("regime")
        .rename(columns={regimes.CLEAN: "clean", regimes.SHOCK: "shock"})
    )
    table["clean_rank"] = table["clean"].rank(method="min").astype(int)
    table["shock_rank"] = table["shock"].rank(method="min").astype(int)
    table["move"] = table["shock_rank"] - table["clean_rank"]
    return table.sort_values("clean")


def _bootstrap_value(frame: pd.DataFrame, statistic: str, **filters) -> pd.Series | None:
    rows = frame[frame["statistic"] == statistic]
    for column, value in filters.items():
        rows = rows[rows[column] == value]
    if rows.empty:
        return None
    return rows.iloc[0]


# --------------------------------------------------------------------------
# the answer bank
# --------------------------------------------------------------------------
#
# Each builder below returns one Answer. They are assembled from a literal
# tuple at the bottom rather than discovered by name, for the reason given in
# CLAUDE.md 3.3: a bank collected by string-matching function names loses a
# member the moment somebody renames one, and a missing answer is invisible --
# the page simply says it does not know, to a question it used to answer.


def _table(headers: list[str], rows: list[list[str]],
           aligns: list[str] | None = None) -> str:
    aligns = aligns or ["left"] * len(headers)
    head = "".join(f'<th class="{a}">{h}</th>' for h, a in zip(headers, aligns))
    body = "".join(
        "<tr>" + "".join(f'<td class="{a}">{c}</td>' for c, a in zip(row, aligns))
        + "</tr>"
        for row in rows
    )
    return (f'<div class="scroll"><table><thead><tr>{head}</tr></thead>'
            f"<tbody>{body}</tbody></table></div>")


def _kv(pairs: list[list[str]]) -> str:
    body = "".join(
        f'<tr><th class="left">{k}</th><td class="right">{v}</td></tr>'
        for k, v in pairs
    )
    return f'<div class="scroll"><table class="kv"><tbody>{body}</tbody></table></div>'


def _answer_forecast(art: Artefacts) -> Answer:
    ops = art.operations
    first = ops.iloc[0]
    rows = []
    for _, row in ops.iterrows():
        period = pd.Period(row["month"], freq="M")
        raw = row.get("festival_dates")
        cell = "&mdash;"
        if isinstance(raw, str) and raw.strip():
            count = len([d for d in raw.split(";") if d.strip()])
            cell = f"{count} day" + ("s" if count > 1 else "")
        rows.append([
            _month_name(period),
            _lakh(row["forecast"]),
            f"{_lakh(row['lo'])} &ndash; {_lakh(row['hi'])}",
            f"{row['daily_mean']:,.0f}",
            cell,
        ])
    return Answer(
        id="forecast",
        question="How many pilgrims are expected in the coming months?",
        headline=(
            f"About <strong>{_lakh(first['forecast'])}</strong> pilgrims in "
            f"{_month_name(pd.Period(first['month'], freq='M'))}, with the next "
            f"{len(ops) - 1} months below."
        ),
        body=(
            "<p>The <em>likely range</em> is where 90% of this model's past errors "
            "fell on ordinary months. It is not a guarantee, and it is not the "
            "range to plan a disruption against &mdash; ask about a disruption "
            "for that.</p>"
            + _table(
                ["Month", "Expected", "Likely range (90%)", "Per day (avg)",
                 "Festival days"],
                rows,
                ["left", "right", "right", "right", "right"],
            )
        ),
        # No generic question openers here. "how many" was once in this list
        # and it captured "how many marshals do I need" -- a question this
        # answer must not take, because the resourcing answer's whole job is to
        # refuse it.
        keywords=("forecast", "expected", "expect", "predict", "prediction",
                  "coming", "next", "future", "pilgrims", "footfall",
                  "visitors", "months", "ahead", "outlook", "projection",
                  "yatris", "crowd", "arrivals"),
        sources=(
            Source("results/operations.csv",
                   f"all {len(ops)} forecast rows, {ops.iloc[0]['month']} to "
                   f"{ops.iloc[-1]['month']}"),
        ),
        caveats=(MONTHLY_CAVEAT,),
        chip="How many pilgrims are expected next month?",
    )


def _answer_disruption(art: Artefacts) -> Answer:
    ops = art.operations
    rows = [
        [
            _month_name(pd.Period(row["month"], freq="M")),
            f"{_lakh(row['lo'])} &ndash; {_lakh(row['hi'])}",
            f"{_lakh(row['shock_lo'])} &ndash; {_lakh(row['shock_hi'])}",
        ]
        for _, row in ops.iterrows()
    ]
    widest = ops.loc[(ops["shock_hi"] - ops["shock_lo"]).idxmax()]
    floor_note = ""
    if bool((ops["shock_lo"] == 0).all()):
        floor_note = (
            "<p>Every lower bound is zero. That is a <strong>measurement, not a "
            "placeholder</strong>: the record contains months when this shrine "
            "was closed and the count really was zero. The band stops at zero "
            "rather than going negative, but the floor itself is something that "
            "has happened.</p>"
        )
    return Answer(
        id="disruption",
        question="What happens to these numbers if there is a disruption?",
        headline=(
            "The range widens enormously. In "
            f"{_month_name(pd.Period(widest['month'], freq='M'))} a disrupted "
            f"month could fall anywhere from {_lakh(widest['shock_lo'])} to "
            f"{_lakh(widest['shock_hi'])}."
        ),
        body=(
            "<p>The ordinary range is measured on ordinary months. Months inside a "
            "declared shock window &mdash; a closure, a security shock, a "
            "landslide &mdash; behave differently, and the same model's error "
            "there is far wider. Plan a contingency against the right-hand "
            "column, not the left.</p>"
            + _table(["Month", "Ordinary range", "If disrupted"], rows,
                     ["left", "right", "right"])
            + floor_note
        ),
        keywords=("disruption", "disrupted", "shock", "closure", "closed",
                  "flood", "floods", "landslide", "covid", "emergency",
                  "contingency", "worst", "risk", "crisis", "wide", "goes wrong",
                  "suspended"),
        sources=(
            Source("results/operations.csv", "the shock_lo and shock_hi columns"),
            Source("results/metrics.csv",
                   "the shock-labelled forecast errors those bounds are measured "
                   "from"),
        ),
        caveats=(
            MONTHLY_CAVEAT,
            "This band describes a disruption <em>like the ones already in the "
            "record</em>. A disruption beginning after the last observed month is "
            "in no number on this page.",
        ),
        chip="What if there is a disruption?",
    )


def _answer_inversion(art: Artefacts) -> Answer:
    table = leaderboard(art.metrics)
    best_clean = str(table["clean"].idxmin())
    best_shock = str(table["shock"].idxmin())
    inversion = _bootstrap_value(art.bootstrap, "p_inversion")
    rho = _bootstrap_value(art.bootstrap, "rank_correlation")

    rows = [
        [
            f"<code>{model}</code>",
            _num(row["clean"]),
            str(int(row["clean_rank"])),
            _num(row["shock"]),
            str(int(row["shock_rank"])),
            f"{int(row['move']):+d}" if int(row["move"]) else "0",
        ]
        for model, row in table.iterrows()
    ]

    share = ""
    if inversion is not None:
        share = (
            " Across the block-bootstrap resamples of the record, the two "
            "rankings came out inverted in <strong>"
            f"{_pct(float(inversion['point']))}</strong> of them."
        )
    rho_note = ""
    if rho is not None:
        rho_note = (
            "<p>The rank correlation between the two orderings is <strong>"
            f"{_num(float(rho['point']))}</strong> &mdash; negative, which is what "
            "an inversion looks like. Its interval spans zero, so that single "
            "statistic on its own would not clear the conventional significance "
            "threshold: the record simply does not contain many disrupted months. "
            "The specific substitutions a planner would actually make are sharper "
            "on the same evidence, and are reported in the README.</p>"
        )

    return Answer(
        id="inversion",
        question="Which forecasting model is best?",
        headline=(
            f"There isn't one. <code>{best_clean}</code> is best on ordinary "
            f"months and ranks {int(table.loc[best_clean, 'shock_rank'])} of "
            f"{len(table)} during disruptions; <code>{best_shock}</code> is best "
            f"during disruptions and ranks "
            f"{int(table.loc[best_shock, 'clean_rank'])} of {len(table)} on "
            f"ordinary months."
        ),
        body=(
            "<p>That reversal is the whole point of this project. A single "
            "leaderboard averaged over all months does not merely lose precision "
            "&mdash; it recommends the model that fails exactly when a forecast "
            f"would have mattered most.{share}</p>"
            "<p>Lower is better. Rank is within its own column, and every model is "
            "scored on an identical set of forecast origins, so the two columns "
            "are directly comparable.</p>"
            + _table(
                ["Model", "Ordinary months", "Rank", "Disrupted months", "Rank",
                 "Move"],
                rows,
                ["left", "right", "right", "right", "right", "right"],
            )
            + rho_note
        ),
        keywords=("best", "model", "models", "which", "winner", "wins", "beat",
                  "ranking", "rank", "leaderboard", "compare", "comparison",
                  "inversion", "invert", "finding", "result", "conclusion",
                  "recommend", "hypothesis"),
        sources=(
            Source("results/metrics.csv",
                   f"{len(art.metrics):,} scored forecasts, grouped by model and "
                   "regime"),
            Source("results/bootstrap.csv",
                   "the p_inversion and rank_correlation rows"),
        ),
        chip="Which forecasting model is best?",
    )


def _answer_accuracy(art: Artefacts) -> Answer:
    """How wrong the forecasts are, in the units a reader actually thinks in.

    The MASE denominator is the seasonal-naive error measured **in-sample on the
    training window** (CLAUDE.md 3.2), which is not the same quantity as the
    error seasonal-naive posts as a forecaster. An earlier version of this
    answer read a MASE above 1 as "worse than using last year's same month" and
    said so on the card. It is not: the `seasonal_naive` model is scored on this
    same page and lands well above 1 itself.

    So the baseline comparison here is model against model, taken from the
    leaderboard, and the headline is a percentage error, because that is the
    thing a planner can act on.
    """
    frame = art.metrics
    table = leaderboard(frame)
    best_clean = str(table["clean"].idxmin())
    clean = float(table.loc[best_clean, "clean"])
    shock = float(table.loc[best_clean, "shock"])
    origins = int(frame["origin"].nunique())
    horizons = sorted(int(h) for h in frame["horizon"].unique())

    mine = frame[frame["model"] == best_clean].copy()
    mine["ape"] = (mine["ae"] / mine["actual"].replace(0, pd.NA)) * 100
    clean_rows = mine[mine["regime"] == regimes.CLEAN]
    shock_rows = mine[mine["regime"] == regimes.SHOCK]

    rows = []
    for horizon in horizons:
        at = clean_rows[clean_rows["horizon"] == horizon]
        rows.append([
            f"{horizon} month" + ("s" if horizon > 1 else "") + " ahead",
            f"{at['ape'].median():.1f}%",
            f"{(at['ape'] <= 10).mean() * 100:.0f}%",
            f"{(at['ape'] <= 25).mean() * 100:.0f}%",
        ])

    baseline = "seasonal_naive"
    baseline_note = ""
    if baseline in table.index:
        baseline_note = (
            "<p>A note on that scale, because it is easy to misread and this page "
            "got it wrong once. The denominator is the seasonal-naive error "
            "measured <em>inside the training window</em>, not the error "
            "seasonal-naive posts as a forecaster. So a score above 1 does "
            "<strong>not</strong> mean the model is beaten by last-year's-same-"
            f"month. Actually forecasting with last year's same month scores "
            f"<strong>{_num(float(table.loc[baseline, 'clean']), 2)}</strong> on "
            f"ordinary months against this model's "
            f"<strong>{_num(clean, 2)}</strong> &mdash; the model is ahead of it, "
            "by about "
            f"{(1 - clean / float(table.loc[baseline, 'clean'])) * 100:.0f}%. The "
            "number is for comparing models against each other, which is the only "
            "thing this project uses it for.</p>"
        )

    return Answer(
        id="accuracy",
        question="How accurate is this, really?",
        headline=(
            "On an ordinary month one step ahead, the forecast is typically within "
            f"<strong>{clean_rows[clean_rows['horizon'] == min(horizons)]['ape'].median():.0f}%</strong> "
            "of what happens. On a disrupted month it is typically out by "
            f"<strong>{shock_rows['ape'].median():.0f}%</strong>."
        ),
        body=(
            "<p>Half of all forecasts land inside the first figure below and half "
            "outside it, so read the last two columns too: they are the share of "
            "months that came in close.</p>"
            + _table(
                ["Lead time", "Typical error", "Within 10%", "Within 25%"],
                rows,
                ["left", "right", "right", "right"],
            )
            + "<p>Accuracy decays with lead time, as it should, but gently. What "
            "does not decay gently is the regime: the same model on disrupted "
            f"months is out by {shock_rows['ape'].median():.0f}% at the median, "
            "and that is the number worth carrying around. <strong>Nothing here "
            "predicts a shrine closure.</strong> What the system is worth is the "
            "range it puts around a month and its honesty about how far that "
            "range widens when things go wrong.</p>"
            + baseline_note
            + "<p>Scored on the same footing everywhere in this project: "
            f"<strong>{clean:.2f}</strong> mean MASE on ordinary months and "
            f"<strong>{shock:.2f}</strong> on disrupted ones. None of it is "
            "measured on data the model was fitted on &mdash; every figure comes "
            f"from a rolling backtest of <strong>{origins:,}</strong> separate "
            f"forecast origins, each forecasting {min(horizons)} to "
            f"{max(horizons)} months past what it was allowed to see.</p>"
        ),
        keywords=("accurate", "accuracy", "reliable", "trust", "error", "wrong",
                  "mase", "confidence", "how well", "performance", "validated",
                  "backtest", "tested", "proof", "good", "believe", "off by"),
        sources=(
            Source("results/metrics.csv",
                   f"all {len(mine):,} scored forecasts for {best_clean}, "
                   "by regime and horizon"),
        ),
        chip="How accurate is this, really?",
    )


def _answer_windows(art: Artefacts) -> Answer:
    rows = []
    for window in art.windows:
        status = "verified" if window.verified else "not yet audited"
        badge = "ok" if window.verified else "warn"
        # The citation is a link, not a footnote reference. This page's whole
        # premise is that a reader can get from a claim to its evidence without
        # asking anybody, and a window's evidence is the reporting behind it.
        cite = (
            f'<a href="{window.source.url}" rel="noopener noreferrer" '
            f'target="_blank">{window.source.publisher}</a>'
        )
        rows.append([
            f"<code>{window.id}</code>",
            window.label,
            f"{window.start} &ndash; {window.end}",
            str(window.n_months),
            cite,
            f'<span class="badge {badge}">{status}</span>',
        ])
    verified = sum(1 for w in art.windows if w.verified)
    return Answer(
        id="windows",
        question="What counts as a disrupted month?",
        headline=(
            f"{len(art.windows)} windows are declared, covering "
            f"{sum(w.n_months for w in art.windows)} months. {verified} of them "
            "have been checked against their source so far."
        ),
        body=(
            "<p>A month is <em>disrupted</em> only if it falls inside one of these "
            "declared windows. Everything else is ordinary. There is no third "
            "category, and no window can be declared without a source citation "
            "&mdash; the loader refuses to start without one.</p>"
            + _table(
                ["Window", "What it was", "Months", "Length", "Source", "Checked?"],
                rows,
                ["left", "left", "left", "right", "left", "left"],
            )
            + "<p>These labels are used only to <strong>score</strong> results. No "
            "model ever receives one. A model that could see which months were "
            "disrupted would post a spectacular result on exactly those months "
            "and mean nothing at all.</p>"
            "<p>Two candidates were considered and <em>rejected</em> &mdash; the "
            "2019 Article 370 period and the 2022 New Year stampede &mdash; "
            "because the monthly series shows no disruption in either. Both stay "
            "on record with the reasoning, because a window somebody examined and "
            "declined is part of the audit trail.</p>"
        ),
        keywords=("window", "windows", "disrupted", "disruption", "regime",
                  "regimes", "define", "definition", "count as", "covid",
                  "flood", "closure", "which months", "declared", "shock",
                  "categories"),
        sources=(
            Source("experiments/configs/shocks.yaml",
                   f"all {len(art.windows)} declared windows, with citations"),
        ),
        chip="What counts as a disrupted month?",
    )


def _answer_limits(art: Artefacts) -> Answer:
    unverified = regimes.unverified(art.windows)
    citation_note = ""
    if unverified:
        names = ", ".join(f"<code>{w.id}</code>" for w in unverified)
        citation_note = (
            "<li><strong>Some shock boundaries are not yet audited.</strong> "
            f"{len(unverified)} of the {len(art.windows)} declared windows "
            f"({names}) carry a citation the project owner has not yet checked "
            "against its source. The regime split therefore rests in part on an "
            "unaudited boundary, and this page says so rather than waiting until "
            "it is tidy.</li>"
        )
    return Answer(
        id="limits",
        question="What can this NOT tell me?",
        headline="Several things, and the first matters most for crowd safety.",
        body=(
            "<ul>"
            "<li><strong>Peak-hour or peak-day load.</strong> The series is "
            "monthly throughout. Sizing a single day's barricading, queue geometry "
            "or medical cover needs daily &mdash; ideally hourly &mdash; arrival "
            "counts, and those are not in this project. A month of ordinary "
            "throughput can contain a fatal crush without the monthly total "
            "moving at all.</li>"
            "<li><strong>Where crowding happens.</strong> Footfall counts people "
            "entering. It is not a density anywhere on the track. Chokepoints are "
            "a site-geometry question this data cannot see.</li>"
            "<li><strong>Any disruption that has not started yet.</strong> The "
            "break detector reacts to a break only after it appears in observed "
            "data. A disruption beginning after the last observed month is in no "
            "number here.</li>"
            "<li><strong>Anything about another shrine.</strong> This is one site, "
            "and its disruptions are its own.</li>"
            f"{citation_note}"
            "</ul>"
        ),
        keywords=("cannot", "can't", "limits", "limitations", "weakness",
                  "caveat", "caveats", "problem", "problems", "not tell",
                  "shortcoming", "blind", "miss", "peak", "hour", "daily",
                  "crush", "stampede", "safety", "hourly"),
        sources=(
            Source("docs/operations.md", "the declared limitations of the briefing"),
            Source("experiments/configs/shocks.yaml",
                   "the per-window verification flags"),
        ),
        chip="What can this NOT tell me?",
    )


def _answer_resourcing(art: Artefacts) -> Answer:
    return Answer(
        id="resourcing",
        question="How many marshals, medical posts or gates do I need?",
        headline="This project will not tell you, and that is deliberate.",
        body=(
            "<p>No resourcing ratios are declared, so none are computed. Marshals "
            "per thousand pilgrims a day, medical posts, gate counts &mdash; those "
            "are site policy, set by people with operational authority and site "
            "experience. They are not model output.</p>"
            "<p>A default invented here would render in the briefing table in the "
            "same typeface as one signed off by an operations lead, and no reader "
            "could tell the two apart. So the field ships empty and the briefing "
            "says so out loud.</p>"
            "<p>To supply them: add them under <code>planning.ratios</code> in "
            "<code>experiments/configs/operations.yaml</code> and re-run the "
            "operations stage. The forecast volumes on this page are the input "
            "they would multiply.</p>"
        ),
        keywords=("marshal", "marshals", "staff", "staffing", "resourcing",
                  "resource", "medical", "posts", "gates", "police", "security",
                  "deploy", "deployment", "ratio", "ratios", "need", "roster",
                  "manpower"),
        sources=(
            Source("experiments/configs/operations.yaml",
                   "planning.ratios, shipped empty on purpose"),
        ),
        chip="How many marshals do I need?",
    )


def _answer_data(art: Artefacts) -> Answer:
    monthly = art.monthly
    first = str(monthly["month"].iloc[0])
    last = str(monthly["month"].iloc[-1])
    zeros = monthly[monthly["pilgrims"] == 0]
    peak = monthly.loc[monthly["pilgrims"].idxmax()]
    return Answer(
        id="data",
        question="What data is this built on?",
        headline=(
            f"<strong>{len(monthly):,} months</strong> of published pilgrim "
            f"counts, {_month_name(pd.Period(first, freq='M'))} to "
            f"{_month_name(pd.Period(last, freq='M'))}, with no gaps."
        ),
        body=(
            "<p>The counts are transcribed from the shrine board's published "
            "month-wise figures. Every row carries the source it came from, and "
            "every annual total reconciles against the sum of its own months "
            "&mdash; the pipeline refuses to run if one does not.</p>"
            + _kv([
                ["Months on record", f"{len(monthly):,}"],
                ["First month", _month_name(pd.Period(first, freq="M"))],
                ["Last observed month", _month_name(pd.Period(last, freq="M"))],
                ["Busiest month on record",
                 f"{_month_name(pd.Period(str(peak['month']), freq='M'))} &mdash; "
                 f"{_lakh(peak['pilgrims'])}"],
                ["Months recording zero pilgrims", str(len(zeros))],
            ])
            + "<p>Nothing here is generated, simulated or filled in &mdash; not to "
            "patch a gap, and not to make the pipeline run. The zero months are "
            "real: the shrine was closed, the publisher reports zero, and the "
            "record says zero rather than treating it as missing.</p>"
        ),
        keywords=("data", "dataset", "source", "sources", "record", "history",
                  "historical", "observations", "how far back", "since", "years",
                  "coverage", "where from", "who published"),
        sources=(
            Source("data/raw/monthly.csv", f"{len(monthly):,} observed months"),
            Source("data/raw/annual.csv",
                   "the annual totals those months reconcile against"),
        ),
        chip="What data is this built on?",
    )


def _answer_calendar(art: Artefacts) -> Answer:
    config = art.calendar_config or {}
    festivals = art.festivals
    labels = sorted(str(x) for x in festivals["label"].unique())
    backend = config.get("backend", "declared in experiments/configs/calendar.yaml")
    ayanamsa = config.get("ayanamsa", "lahiri")
    return Answer(
        id="calendar",
        question="How are the festival dates worked out?",
        headline=(
            "They are <strong>computed from an astronomical ephemeris</strong>, "
            f"not looked up in a table &mdash; {len(festivals):,} dates across the "
            "span."
        ),
        body=(
            "<p>There is no hardcoded date table anywhere in this project. The "
            "positions of the sun and moon are computed, the lunar day and solar "
            "ingress are derived from them, and each festival's own civil-day rule "
            "decides which calendar date it lands on. Those rules genuinely differ "
            "&mdash; some festivals are fixed by sunrise, one by midnight, one by "
            "dusk &mdash; and which rule applies decides more dates than any "
            "disagreement between ephemerides does.</p>"
            + _kv([
                ["Astronomy backend", f"<code>{backend}</code>"],
                ["Ayanamsa", f"<code>{ayanamsa}</code>"],
                ["Festivals tracked", str(len(labels))],
                ["Dates resolved", f"{len(festivals):,}"],
            ])
            + "<p>Tracked: "
            + ", ".join(f"<strong>{label}</strong>" for label in labels)
            + ". These are the five that move the monthly count at this shrine, "
            "not a general almanac.</p>"
            "<p>The dates are checked against published almanacs in the test "
            "suite. If they ever disagree, the fix goes to the computation, never "
            "to the test.</p>"
        ),
        keywords=("festival", "festivals", "calendar", "navratri", "diwali",
                  "shivaratri", "shivratri", "raksha", "bandhan", "tithi",
                  "panchang", "ephemeris", "astronomy", "lunar", "dates",
                  "holiday", "holidays"),
        sources=(
            Source("results/festivals.csv",
                   f"{len(festivals):,} computed festival dates"),
            Source("results/calendar.csv",
                   "the monthly features derived from them"),
        ),
        chip="How are the festival dates worked out?",
    )


def _answer_shock_types(art: Artefacts) -> Answer | None:
    """Whether "disrupted" behaves as one regime or several.

    The console has to carry this, not just the README, because it is the
    finding that changes what somebody would actually *do*. A planner told
    "use the naive forecast during disruptions" would have reached for the
    wrong model in the one disruption in this record that was not COVID.
    """
    frame = art.metrics
    if "shock_window" not in frame.columns:
        return None
    rows = frame[(frame["regime"] == regimes.SHOCK) & frame["shock_window"].notna()]
    per_window = rows.groupby(["model", "shock_window"])["mase"].mean().unstack()
    if per_window.shape[1] < 2 or per_window.isna().to_numpy().any():
        return None

    counts = (rows.groupby("shock_window").size() / rows["model"].nunique()).astype(int)
    ranks = per_window.rank(method="min").astype(int)
    order = sorted(per_window.columns, key=lambda w: -counts[w])
    winners = {w: str(per_window[w].idxmin()) for w in order}
    pooled = rows.groupby("model")["mase"].mean()
    pooled_winner = str(pooled.idxmin())

    table_rows = [
        [
            f"<code>{window}</code>",
            str(counts[window]),
            f"<code>{winners[window]}</code>",
            f"{int(ranks.loc[pooled_winner, window])} of {len(per_window)}",
        ]
        for window in order
    ]

    covid = [w for w in order if "covid" in w or "delta" in w]
    other = [w for w in order if w not in covid]
    structure = ""
    if covid and other:
        share = counts[covid].sum() / counts.sum() * 100
        odd = other[0]
        structure = (
            f"<p>The COVID windows supply <strong>{share:.0f}%</strong> of the "
            "pooled disrupted column, so the pooled answer is largely an answer "
            f"about one event. On <code>{odd}</code> the winner is "
            f"<code>{winners[odd]}</code>, and the pooled winner "
            f"<code>{pooled_winner}</code> comes "
            f"{int(ranks.loc[pooled_winner, odd])} of {len(per_window)}.</p>"
        )
        # The same qualification the README carries, in the same conditions.
        # This surface reaches the reader least equipped to supply it himself,
        # so it is the last place it should be dropped for brevity.
        if len(other) < report.NON_COVID_FLOOR:
            plural = "s" if len(other) > 1 else ""
            structure += (
                f"<p><strong>Read that comparison carefully: it rests on "
                f"{len(other)} non-COVID window{plural}.</strong> The COVID "
                "windows are one event subdivided, so every disagreement in "
                f"this table involves the same {len(other)} window{plural} "
                "again and again &mdash; it is one comparison repeated, not "
                "several independent ones. Nothing here separates <em>"
                "different kinds of disruption need different models</em> from "
                f"<em><code>{odd}</code> happens to have an odd winner</em>, "
                "and those are not the same claim. A second disruption "
                "unrelated to COVID is what would tell them apart.</p>"
            )

    return Answer(
        id="shock_types",
        question="Is a disruption a disruption, or do different kinds behave differently?",
        headline=(
            f"Different kinds behave differently. {len(order)} declared windows, "
            f"<strong>{len(set(winners.values()))} different winning models</strong>."
        ),
        body=(
            "<p>The ordinary/disrupted split is binary, and that hides the same "
            "kind of averaging this project objects to in the overall "
            "leaderboard. These windows are not variations on a theme: a cliff "
            "to zero, a slow climb, a second cliff inside that climb, and a "
            "compound security-and-landslide event.</p>"
            + _table(
                ["Window", "Forecasts", "Best model here",
                 f"Where {pooled_winner} lands"],
                table_rows,
                ["left", "right", "left", "right"],
            )
            + structure
            # Deliberately weaker than the obvious sentence. That the winners
            # differ window to window is a counting fact about the table above.
            # That they differ *because* the disruptions are of different kinds
            # is a causal claim this record cannot support, and it is the one a
            # reader will carry away if the two are not kept apart.
            + "<p><strong>This does not overturn the headline finding, it "
            "sharpens the warning.</strong> Ordinary and disrupted rankings "
            "still invert. What the table adds is narrower: the pooled "
            "disrupted leaderboard does not describe every disrupted month "
            "inside it, so \"best during disruptions\" is not a safe thing to "
            "read off it. Whether that is because disruptions come in kinds, or "
            "because one window in this record is unusual, is a question this "
            "site's data cannot answer.</p>"
        ),
        keywords=("kinds", "kind", "type", "types", "different disruptions",
                  "per window", "each window", "landslide", "flood", "covid",
                  "closure", "compare disruptions", "same", "differ"),
        sources=(
            Source("results/metrics.csv",
                   f"{len(rows):,} shock-labelled forecasts, grouped by window"),
        ),
        caveats=(
            "The thinnest window carries "
            f"<strong>{int(counts.min())}</strong> forecasts per model. No single "
            "column here is resolvable on its own, and none is offered as one. "
            "What this supports is the pattern across windows, not any cell in "
            "it.",
        ),
        chip="Do different kinds of disruption behave differently?",
    )


def _answer_other_sites(art: Artefacts) -> Answer:
    """Whether any of this describes another shrine. It does not.

    This is the question a reader is most likely to arrive with and the one the
    page can least afford to refuse, because a refusal reads as "probably, but
    I cannot say" when the answer is a flat no with reasons behind it. It was
    a genuine gap: asking about Tirupati or Sabarimala got "not understood"
    until this answer existed.
    """
    monthly = art.monthly
    first = _month_name(pd.Period(str(monthly["month"].iloc[0]), freq="M"))
    last = _month_name(pd.Period(str(monthly["month"].iloc[-1]), freq="M"))
    return Answer(
        id="other_sites",
        question="Does any of this apply to Tirupati, Sabarimala or another shrine?",
        headline=(
            "<strong>No.</strong> This is one shrine's record, and nothing here "
            "has been tested anywhere else."
        ),
        body=(
            f"<p>Every number on this page comes from {first} to {last} at this "
            "one site. No second shrine has been scored, so there is no evidence "
            "either way about whether any of it holds elsewhere &mdash; and the "
            "detail of these tables is not evidence that they travel.</p>"
            "<p>There is a specific reason to expect <em>less</em> transfer "
            "rather than more. Ask about kinds of disruption and you will see "
            "that the best model already differs between disruptions "
            "<em>within</em> this single site. If the answer changes between two "
            "shocks at one shrine, there is little reason to expect it to hold "
            "across shrines with different geography, different seasons and "
            "different disruptions entirely.</p>"
            "<p>A second site was searched for. Four candidates were examined and "
            "rejected, and the obstacle is usually not that the shrine is "
            "unimportant but that <strong>monthly footfall for Indian pilgrimage "
            "sites is largely unpublished</strong>:</p>"
            "<ul>"
            "<li><strong>Tirumala / Tirupati</strong> publishes daily counts, but "
            "as one news post per day and with no annual total on its own site "
            "to check a compiled series against.</li>"
            "<li><strong>Sabarimala</strong> reports by season rather than by "
            "month, and splitting a season across its months would be inventing "
            "numbers.</li>"
            "<li><strong>Tamil Nadu temples</strong> &mdash; no published "
            "attendance series was found; what is published is revenue and land "
            "rather than footfall.</li>"
            "<li><strong>District tourism data</strong> is published exactly as "
            "one would want, and its publishers state that it excludes "
            "pilgrimage sites. It is a different quantity that resembles this "
            "one.</li>"
            "<li><strong>Kedarnath</strong> is the one candidate still open, "
            "because its major disruptions are not the pandemic. Its figures are "
            "not published either, and the temple is shut half of every year, "
            "which is a harder problem than sourcing.</li>"
            "</ul>"
            "<p>That search is written up in full, including what would change "
            "the verdict.</p>"
        ),
        keywords=("tirupati", "tirumala", "sabarimala", "velankanni",
                  "tiruvannamalai", "kedarnath", "other", "shrine", "shrines",
                  "temple", "temples", "elsewhere", "apply", "transfer",
                  "generalise", "generalize", "district", "state", "everywhere",
                  "another", "same", "india", "country", "nationwide",
                  "national", "anywhere", "valid", "hold", "holds"),
        sources=(
            Source("docs/second_site.md",
                   "the second-site search and the verdict on each candidate"),
            Source("data/raw/monthly.csv",
                   f"the only observation set scored here, {len(monthly):,} months "
                   "from one site"),
        ),
        chip="Does this apply to other shrines?",
    )


def _answer_sensitivity(art: Artefacts) -> Answer:
    sens = art.sensitivity
    rows = [
        [
            f"<code>{row['arm']}</code>",
            str(int(row["n_windows"])),
            _num(float(row["rank_correlation"])),
            "yes" if bool(row["inverts"]) else "no",
        ]
        for _, row in sens.iterrows()
    ]
    inverting = int(sens["inverts"].astype(bool).sum())
    return Answer(
        id="sensitivity",
        question="Does the finding survive a different boundary?",
        headline=(
            f"Yes. The ranking inverts under <strong>{inverting} of {len(sens)}"
            "</strong> different definitions of what counts as a disrupted month."
        ),
        body=(
            "<p>The shock windows are drawn by hand, which is the obvious place a "
            "finding like this could turn out to be an artefact. So the "
            "<em>same</em> forecasts are re-scored under a deliberately different "
            "set of boundaries &mdash; one window dropped for showing no signal, "
            "another trimmed, a third extended. Nothing is refitted; only the "
            "labels move, because no model ever saw a label in the first "
            "place.</p>"
            + _table(["Window set", "Windows", "Rank correlation", "Still inverts?"],
                     rows, ["left", "right", "right", "left"])
            + "<p>The correlation stays negative either way. The inversion is not "
            "an artefact of where the lines were drawn.</p>"
        ),
        keywords=("sensitivity", "robust", "survive", "boundaries", "boundary",
                  "artefact", "artifact", "cherry", "arbitrary", "alternative",
                  "hold up", "different definition", "sceptical", "skeptical"),
        sources=(
            Source("results/sensitivity_summary.csv",
                   f"all {len(sens)} declared window sets"),
        ),
        chip="Does the finding survive a different boundary?",
    )


def _answer_applicability(art: Artefacts) -> Answer | None:
    frame = art.applicability
    if frame is None or frame.empty:
        return None
    rows = [
        [
            f"<code>{row['model']}</code>",
            f"{int(row['origins_failed'])} of {int(row['origins_total'])}",
            str(row["first_failure_origin"]),
        ]
        for _, row in frame.iterrows()
    ]
    names = ", ".join(f"<code>{m}</code>" for m in frame["model"])
    return Answer(
        id="applicability",
        question="Did any model fail to run?",
        headline=(
            f"Yes &mdash; {names}. It is reported here rather than quietly dropped "
            "from the leaderboard."
        ),
        body=(
            "<p>A model that cannot be fitted on part of the record is a result "
            "about the record, not a bug to hide. Dropping it from the table would "
            "be falsification, so it stays, with its reason.</p>"
            + _table(["Model", "Origins it could not fit", "First failure"], rows,
                     ["left", "right", "right"])
            + "<p>The cause is the closure months. Multiplicative seasonality "
            "cannot be estimated on a series containing a zero, and this series "
            "contains several. That is a real limitation of the method on this "
            "kind of data, and it belongs in the results.</p>"
        ),
        keywords=("fail", "failed", "failure", "broken", "crash", "unfittable",
                  "dropped", "excluded", "applicability", "did not run",
                  "didn't run", "missing model"),
        sources=(
            Source("results/applicability.csv",
                   f"{len(frame)} model(s) reported unfittable"),
        ),
        chip="Did any model fail to run?",
    )


def _answer_how(art: Artefacts) -> Answer:
    origins = int(art.metrics["origin"].nunique())
    horizons = int(art.metrics["horizon"].nunique())
    model_count = int(art.metrics["model"].nunique())
    return Answer(
        id="how",
        question="How does this whole thing work?",
        headline="Forecast the past, over and over, and score what actually happened.",
        body=(
            "<p>Every claim on this page comes out of one procedure. Pick a month "
            "in the past. Give a model only the data available up to that month. "
            "Ask it for the next six. Compare against what actually happened. Move "
            "forward one month and do it again.</p>"
            + _kv([
                ["Forecast origins", f"{origins:,}"],
                ["Horizons per origin", str(horizons)],
                ["Models compared", str(model_count)],
                ["Forecasts scored", f"{len(art.metrics):,}"],
            ])
            + "<p>Every model is scored on <em>exactly</em> the same origins "
            "against the same baseline, and the pipeline refuses to finish if any "
            "model is missing from any cell of that grid. Different origins is not "
            "a comparison.</p>"
            "<p>Only then are the results split into ordinary and disrupted months "
            "and the two leaderboards compared. That split is applied "
            "<em>afterwards</em>, purely as a label. It never reaches a model.</p>"
        ),
        keywords=("how does", "how it works", "method", "methodology", "approach",
                  "explain", "work", "works", "pipeline", "process", "built",
                  "what is this", "about", "overview", "project"),
        sources=(
            Source("results/metrics.csv",
                   "the full origin x horizon x model grid, "
                   f"{len(art.metrics):,} rows"),
        ),
        chip="How does this whole thing work?",
    )


#: The bank, declared. Adding a builder without adding it here means the page
#: silently loses an answer, so tests/test_ui.py asserts every ``_answer_``
#: function in this module appears below.
BUILDERS = (
    _answer_forecast,
    _answer_disruption,
    _answer_inversion,
    _answer_accuracy,
    _answer_windows,
    _answer_shock_types,
    _answer_other_sites,
    _answer_limits,
    _answer_resourcing,
    _answer_data,
    _answer_calendar,
    _answer_sensitivity,
    _answer_applicability,
    _answer_how,
)


def build_answers(art: Artefacts) -> list[Answer]:
    """Assemble the bank. Builders returning ``None`` had no artefact to speak
    from and drop out rather than rendering an empty card."""
    built = [builder(art) for builder in BUILDERS]
    return [answer for answer in built if answer is not None]


# --------------------------------------------------------------------------
# lookup payload
# --------------------------------------------------------------------------
#
# The answer bank covers questions about the project. These tables cover
# questions about a specific month: "how many came in March 2020", "what is
# expected in October". They are the observation and forecast rows themselves,
# carried into the page verbatim -- no interpolation, no smoothing, and no
# value for a month that has none. A query landing outside the covered span
# gets told the span, not a nearby number.


def lookup_tables(art: Artefacts) -> dict:
    monthly = art.monthly
    observations = {
        str(row["month"]): int(row["pilgrims"]) for _, row in monthly.iterrows()
    }

    annual: dict[str, int] = {}
    for month, count in observations.items():
        annual[month[:4]] = annual.get(month[:4], 0) + count

    # A year is only reported if all twelve of its months are present. A
    # part-year total rendered beside full ones reads as a collapse that did not
    # happen -- the current year is always short, and 2026 is not down 40%.
    per_year: dict[str, int] = {}
    for month in observations:
        per_year[month[:4]] = per_year.get(month[:4], 0) + 1
    complete_years = {y: t for y, t in annual.items() if per_year[y] == 12}

    forecast = {}
    for _, row in art.operations.iterrows():
        raw = row.get("festival_dates")
        dates = (
            [d.strip() for d in str(raw).split(";") if d.strip()]
            if isinstance(raw, str) and raw.strip() else []
        )
        labels_raw = row.get("festival_labels")
        forecast[str(row["month"])] = {
            "forecast": float(row["forecast"]),
            "lo": float(row["lo"]),
            "hi": float(row["hi"]),
            "shock_lo": float(row["shock_lo"]),
            "shock_hi": float(row["shock_hi"]),
            "daily": float(row["daily_mean"]),
            "days": int(row["days_in_month"]),
            "festival_dates": dates,
            "festival_labels": (
                str(labels_raw) if isinstance(labels_raw, str) and labels_raw.strip()
                else ""
            ),
        }

    shock_months: dict[str, str] = {}
    for window in art.windows:
        for period in pd.period_range(window.start, window.end, freq="M"):
            shock_months[str(period)] = window.label

    festivals = [
        {"date": str(row["date"]), "label": str(row["label"]),
         "id": str(row["festival_id"]), "day": int(row["day_index"])}
        for _, row in art.festivals.iterrows()
    ]

    return {
        "observations": observations,
        "annual": complete_years,
        "forecast": forecast,
        "shockMonths": shock_months,
        "festivals": festivals,
        "firstMonth": str(monthly["month"].iloc[0]),
        "lastMonth": str(monthly["month"].iloc[-1]),
    }


# --------------------------------------------------------------------------
# the page
# --------------------------------------------------------------------------

#: The page's visual identity, and why it is what it is.
#:
#: A statistical return you can interrogate -- not a brochure, not a dashboard.
#: Ledger paper, hairline rules under the section heads, monospace for every
#: eyebrow, citation and column label, tabular numerals wherever digits stack.
#: The one raised element on an otherwise flat page is the ask bar, because it
#: is the only thing on the page you operate.
#:
#: No webfonts, and that is a decision rather than an omission: this file has to
#: render from a USB stick with no network, so a font host would break the one
#: promise the page makes. Three typographic roles are carried by system stacks
#: instead, separated by weight and width rather than by family.
#:
#: Raw string. CSS escapes like \2212 are octal escapes to Python otherwise, and
#: the fold marker silently became a control character the first time round.
STYLE = r"""
:root {
  --paper: #eef1f0;
  --panel: #f9fbfa;
  --ink: #101917;
  --muted: #586663;
  --line: #d7dfdc;
  --rule: #b3c1bd;
  --accent: #0d5c53;
  --accent-soft: #dfeae7;
  --ok: #1f6a3d;
  --ok-soft: #e2efe6;
  --warn: #8a5100;
  --warn-soft: #f6ecdc;
  --raise: 0 1px 1px rgba(16,25,23,.04), 0 10px 28px -18px rgba(16,25,23,.45);
  --sans: ui-sans-serif, -apple-system, "Segoe UI Variable Text", "Segoe UI",
          Roboto, "Helvetica Neue", Arial, sans-serif;
  --mono: ui-monospace, "SF Mono", "Cascadia Mono", Consolas, "Liberation Mono",
          monospace;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --paper: #0d1211;
    --panel: #141b19;
    --ink: #e8edeb;
    --muted: #8b9a96;
    --line: #232e2c;
    --rule: #33403d;
    --accent: #58c9b2;
    --accent-soft: #11241f;
    --ok: #7fc79a;
    --ok-soft: #12211a;
    --warn: #d9a55f;
    --warn-soft: #241d12;
    --raise: 0 1px 1px rgba(0,0,0,.5), 0 10px 28px -18px rgba(0,0,0,.9);
  }
}
:root[data-theme="dark"] {
  --paper: #0d1211;
  --panel: #141b19;
  --ink: #e8edeb;
  --muted: #8b9a96;
  --line: #232e2c;
  --rule: #33403d;
  --accent: #58c9b2;
  --accent-soft: #11241f;
  --ok: #7fc79a;
  --ok-soft: #12211a;
  --warn: #d9a55f;
  --warn-soft: #241d12;
  --raise: 0 1px 1px rgba(0,0,0,.5), 0 10px 28px -18px rgba(0,0,0,.9);
}

* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--paper);
  color: var(--ink);
  font-family: var(--sans);
  font-size: 16px;
  line-height: 1.62;
  -webkit-font-smoothing: antialiased;
}
.wrap { max-width: 54rem; margin: 0 auto; padding: 3.5rem 1.25rem 5rem; }
:focus-visible {
  outline: 2px solid var(--accent); outline-offset: 2px; border-radius: 3px;
}
@media (prefers-reduced-motion: reduce) {
  * { animation: none !important; transition: none !important;
      scroll-behavior: auto !important; }
}

/* --- masthead --------------------------------------------------------- */
header { margin-bottom: 2.25rem; }
.eyebrow {
  font-family: var(--mono); font-size: .69rem; letter-spacing: .16em;
  text-transform: uppercase; color: var(--accent); margin: 0 0 1rem;
}
h1 {
  font-size: clamp(2rem, 5.5vw, 2.85rem); line-height: 1.08;
  margin: 0 0 .8rem; letter-spacing: -.025em; font-weight: 700;
  text-wrap: balance; max-width: 21ch;
}
.lede {
  font-size: 1.02rem; color: var(--muted); margin: 0 0 1.6rem; max-width: 64ch;
}
.meta {
  display: flex; flex-wrap: wrap; gap: 0 1.5rem;
  border-top: 1px solid var(--rule); border-bottom: 1px solid var(--line);
  padding: .55rem 0;
}
.meta span {
  font-family: var(--mono); font-size: .71rem; color: var(--muted);
  font-variant-numeric: tabular-nums;
}

.scope {
  margin: .9rem 0 0; padding: .7rem .9rem;
  border-left: 2px solid var(--accent); background: var(--accent-soft);
  font-size: .88rem; color: var(--ink); max-width: 68ch;
}
.scope strong { color: var(--accent); }

/* --- the one thing you operate ---------------------------------------- */
.ask { margin-bottom: 1.75rem; }
.askbar { display: flex; gap: .5rem; }
#q {
  flex: 1; min-width: 0;
  font: inherit; color: var(--ink); background: var(--panel);
  border: 1px solid var(--rule); border-radius: .45rem;
  padding: .8rem .95rem; box-shadow: var(--raise);
}
#q:focus {
  outline: none; border-color: var(--accent);
  box-shadow: var(--raise), 0 0 0 3px var(--accent-soft);
}
#q::placeholder { color: var(--muted); }
button.go {
  font: inherit; font-weight: 650; cursor: pointer; letter-spacing: .01em;
  color: var(--panel); background: var(--accent);
  border: 1px solid var(--accent); border-radius: .45rem; padding: .8rem 1.5rem;
  box-shadow: var(--raise);
}
button.go:hover { filter: brightness(1.12); }
.chips { display: flex; flex-wrap: wrap; gap: .4rem; margin-top: .85rem; }
.chip {
  font: inherit; font-size: .81rem; cursor: pointer; text-align: left;
  color: var(--muted); background: transparent;
  border: 1px solid var(--line); border-radius: .35rem; padding: .28rem .7rem;
}
.chip:hover {
  color: var(--accent); border-color: var(--accent); background: var(--accent-soft);
}

/* --- answer cards ------------------------------------------------------ */
.card {
  background: var(--panel); border: 1px solid var(--line);
  border-radius: .5rem; padding: 1.5rem 1.5rem 1.1rem; margin-bottom: 1.1rem;
}
#answer .card { border-top: 2px solid var(--accent); }
.card .asked {
  font-family: var(--mono); font-size: .69rem; letter-spacing: .11em;
  text-transform: uppercase; color: var(--accent); margin: 0 0 .8rem;
}
.headline {
  font-size: 1.3rem; line-height: 1.32; text-wrap: balance;
  margin: 0 0 1.1rem; font-weight: 650; letter-spacing: -.015em;
}
.headline strong { color: var(--accent); font-weight: 750; }
.card p { margin: 0 0 .9rem; max-width: 68ch; }
.card ul { margin: 0 0 .9rem; padding-left: 1.15rem; max-width: 68ch; }
.card li { margin-bottom: .55rem; }
code {
  font-family: var(--mono); font-size: .85em;
  background: var(--accent-soft); color: var(--accent);
  padding: .08em .35em; border-radius: .25em;
}
.muted { color: var(--muted); font-size: .9rem; }
.card a {
  color: var(--accent); text-decoration-thickness: 1px;
  text-underline-offset: .18em;
}

/* --- tabulation -------------------------------------------------------- */
.scroll { overflow-x: auto; margin: 0 0 1.1rem; }
table {
  border-collapse: collapse; width: 100%; font-size: .885rem;
  font-variant-numeric: tabular-nums;
}
th, td {
  padding: .45rem .7rem; border-bottom: 1px solid var(--line); white-space: nowrap;
}
th:first-child, td:first-child { padding-left: 0; }
thead th {
  font-family: var(--mono); font-size: .66rem; letter-spacing: .09em;
  text-transform: uppercase; color: var(--muted); font-weight: 600;
  border-bottom: 1px solid var(--rule);
}
table.kv th {
  font-family: var(--sans); text-transform: none; letter-spacing: 0;
  font-size: .89rem; color: var(--muted); font-weight: 400; white-space: normal;
  border-bottom: 1px solid var(--line);
}
table.kv td { font-weight: 600; }
tbody tr:last-child td, tbody tr:last-child th { border-bottom: none; }
.left { text-align: left; }
.right { text-align: right; }

.badge {
  font-family: var(--mono); font-size: .66rem; letter-spacing: .05em;
  border-radius: .25rem; padding: .1rem .45rem; white-space: nowrap;
}
.badge.ok { background: var(--ok-soft); color: var(--ok); }
.badge.warn { background: var(--warn-soft); color: var(--warn); }

/* --- the browsable bank ------------------------------------------------ */
.fold { padding: .85rem 1.5rem; margin-bottom: .4rem; }
.fold > summary {
  cursor: pointer; font-weight: 500; list-style: none;
  display: flex; align-items: baseline; gap: .65rem;
}
.fold > summary::-webkit-details-marker { display: none; }
.fold > summary::before {
  content: "+"; font-family: var(--mono); color: var(--accent);
  font-weight: 700; flex: none;
}
.fold[open] > summary::before { content: "\2212"; }
.fold[open] > summary { color: var(--accent); }
.fold .headline { font-size: 1.1rem; margin: 1rem 0 .9rem; }

.caveat {
  border-left: 2px solid var(--warn); background: var(--warn-soft);
  padding: .65rem .85rem; font-size: .91rem; margin: 0 0 .8rem; max-width: 68ch;
}
.prov {
  border-top: 1px solid var(--line); margin-top: 1.2rem; padding-top: .85rem;
  font-size: .79rem; color: var(--muted);
}
.prov b {
  font-family: var(--mono); font-size: .66rem; letter-spacing: .11em;
  text-transform: uppercase; font-weight: 600; display: block; margin-bottom: .4rem;
}
.prov li { margin-bottom: .25rem; }
.prov code {
  background: transparent; color: var(--muted); padding: 0; border-radius: 0;
}

/* --- sections ---------------------------------------------------------- */
h2.section {
  font-size: 1.02rem; font-weight: 650; letter-spacing: .01em;
  margin: 3.25rem 0 0; padding-bottom: .45rem;
  border-bottom: 1px solid var(--rule);
}
h2.section + .section-note {
  border-top: 1px solid var(--line); padding-top: .85rem;
  color: var(--muted); margin: 0 0 1.4rem; max-width: 68ch; font-size: .93rem;
}

figure { margin: 0 0 2.25rem; }
figure img {
  width: 100%; height: auto; display: block; border-radius: .35rem;
  border: 1px solid var(--line); background: #fff;
}
figcaption {
  font-size: .87rem; color: var(--muted); margin-top: .6rem; max-width: 68ch;
}
figcaption b {
  color: var(--ink); display: block; font-size: .95rem; font-weight: 650;
  margin-bottom: .2rem;
}

ul.open-items { margin: 0 0 1rem; padding-left: 1.15rem; max-width: 68ch; }
ul.open-items li { margin-bottom: .6rem; }

footer.page {
  border-top: 1px solid var(--rule); margin-top: 3rem; padding-top: 1.4rem;
  font-size: .85rem; color: var(--muted);
}
footer.page p { max-width: 68ch; }
"""

SCRIPT = r"""
(function () {
  "use strict";

  var D = window.__YATRA__;
  var MONTHS = ["january","february","march","april","may","june","july",
                "august","september","october","november","december"];
  var SHORT = ["jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec"];

  function esc(s) {
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
  function lakh(n) {
    // Matches _lakh() in ui.py: an exact zero is a measured floor, not a
    // rounded-down small number, and "0.00 lakh" hides that.
    if (n === 0) return "zero";
    return (n / 1e5).toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ",") + " lakh";
  }
  function people(n) {
    return Math.round(n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  }
  function both(n) { return lakh(n) + " · " + people(n) + " people"; }
  function monthLabel(key) {
    var parts = key.split("-");
    return MONTHS[parseInt(parts[1], 10) - 1].replace(/^./, function (c) {
      return c.toUpperCase();
    }) + " " + parts[0];
  }
  function pad(n) { return n < 10 ? "0" + n : "" + n; }

  // ---- month / year parsing -------------------------------------------
  function findYear(q) {
    var m = q.match(/\b(19\d{2}|20\d{2})\b/);
    return m ? m[1] : null;
  }
  function findMonthWord(q) {
    var hasYear = findYear(q) !== null;
    for (var i = 0; i < MONTHS.length; i++) {
      // "may" is a modal verb far more often than it is a month. Reading it as
      // May would turn "how many people may come" into a lookup for a month
      // nobody named, so it counts only when a year is named beside it.
      if (MONTHS[i] === "may" && !hasYear) continue;
      if (new RegExp("\\b" + MONTHS[i] + "\\b").test(q)) return i + 1;
    }
    for (var j = 0; j < SHORT.length; j++) {
      if (SHORT[j] === "may" && !hasYear) continue;
      if (new RegExp("\\b" + SHORT[j] + "\\b\\.?").test(q)) return j + 1;
    }
    return null;
  }
  function findMonthKey(q) {
    var iso = q.match(/\b(19\d{2}|20\d{2})[-\/](\d{1,2})\b/);
    if (iso) return iso[1] + "-" + pad(parseInt(iso[2], 10));
    var word = findMonthWord(q);
    if (!word) return null;
    var year = findYear(q);
    if (year) return year + "-" + pad(word);
    // A month named without a year. Prefer the forecast horizon if it covers
    // that month, otherwise the most recent time it occurred in the record.
    // The card always states which month it answered, so this cannot pass for
    // a different one.
    var keys = Object.keys(D.forecast);
    for (var i = 0; i < keys.length; i++) {
      if (parseInt(keys[i].split("-")[1], 10) === word) return keys[i];
    }
    var obs = Object.keys(D.observations).sort();
    for (var j = obs.length - 1; j >= 0; j--) {
      if (parseInt(obs[j].split("-")[1], 10) === word) return obs[j];
    }
    return null;
  }

  // ---- lookup answers --------------------------------------------------
  function forecastAnswer(key) {
    var f = D.forecast[key];
    var rows = [
      ["Expected", lakh(f.forecast)],
      ["Likely range (90%)", lakh(f.lo) + " – " + lakh(f.hi)],
      ["Average per day", people(f.daily) + " over " + f.days + " days"],
      ["If a disruption occurs", lakh(f.shock_lo) + " – " + lakh(f.shock_hi)]
    ];
    if (f.festival_dates.length) {
      rows.push(["Festival days", f.festival_dates.length + " — " +
                 esc(f.festival_labels)]);
    }
    var body = "<p>This is a forecast, not an observation — " +
      monthLabel(key) + " has not happened yet.</p>" + kv(rows);
    if (f.festival_dates.length) {
      body += "<p>Festival days in this month: <code>" +
        f.festival_dates.join("</code> <code>") + "</code>. Arrivals concentrate " +
        "on these dates, so they are where surge cover belongs.</p>";
    }
    return {
      asked: "Forecast for " + monthLabel(key),
      headline: "About <strong>" + lakh(f.forecast) + "</strong> pilgrims in " +
        monthLabel(key) + ", or roughly " + people(f.daily) + " a day.",
      body: body,
      caveats: [D.monthlyCaveat],
      sources: [{ artefact: "results/operations.csv", detail: "the row for " + key }]
    };
  }

  function observationAnswer(key) {
    var n = D.observations[key];
    var shock = D.shockMonths[key];
    var body = "";
    var rows = [["Pilgrims recorded", people(n)], ["In lakh", lakh(n)]];
    var prev = key.split("-");
    var yearBefore = (parseInt(prev[0], 10) - 1) + "-" + prev[1];
    if (D.observations[yearBefore] !== undefined) {
      var was = D.observations[yearBefore];
      var change = was === 0 ? null : ((n - was) / was) * 100;
      rows.push(["Same month, year before", people(was)]);
      if (change !== null) {
        rows.push(["Change", (change >= 0 ? "+" : "") + change.toFixed(1) + "%"]);
      }
    }
    body += kv(rows);
    if (shock) {
      body += "<p>This month falls inside a declared <strong>shock window</strong>: " +
        esc(shock) + ". It is scored separately from ordinary months everywhere " +
        "in this project.</p>";
    }
    if (n === 0) {
      body += "<p>Zero is what the publisher reports, and it is recorded as an " +
        "observation rather than as missing data. The shrine was closed.</p>";
    }
    return {
      asked: "The record for " + monthLabel(key),
      headline: "<strong>" + people(n) + "</strong> pilgrims in " +
        monthLabel(key) + " (" + lakh(n) + ").",
      body: body,
      caveats: [],
      sources: [{ artefact: "data/raw/monthly.csv", detail: "the observed row for " + key }]
    };
  }

  function yearAnswer(year) {
    var total = D.annual[year];
    if (total === undefined) {
      var known = Object.keys(D.annual).sort();
      var partial = 0, count = 0;
      Object.keys(D.observations).forEach(function (k) {
        if (k.slice(0, 4) === year) { partial += D.observations[k]; count++; }
      });
      if (count > 0) {
        return {
          asked: "The record for " + year,
          headline: "<strong>" + people(partial) + "</strong> pilgrims so far in " +
            year + ", across " + count + " month" + (count > 1 ? "s" : "") + ".",
          body: "<p>" + year + " is incomplete in the record, so this is a " +
            "part-year total and is not comparable with a full year. The last " +
            "complete year on record is " + known[known.length - 1] + ".</p>" +
            kv([["Months counted", String(count)],
                ["Total so far", people(partial)],
                ["In lakh", lakh(partial)]]),
          caveats: [],
          sources: [{ artefact: "data/raw/monthly.csv",
                      detail: count + " observed months in " + year }]
        };
      }
      // A year named that the record does not reach. Saying so is the answer.
      // Falling through to the keyword bank here is how "how many came in
      // 1985" once returned next August's forecast.
      return {
        asked: "The record for " + year,
        headline: year + " is outside what this project covers.",
        body: "<p>The observations run from <strong>" + monthLabel(D.firstMonth) +
          "</strong> to <strong>" + monthLabel(D.lastMonth) + "</strong>. There " +
          "is no figure here for " + year + ", and this page will not estimate " +
          "one.</p>",
        caveats: [],
        sources: [{ artefact: "data/raw/monthly.csv",
                    detail: "covers " + D.firstMonth + " to " + D.lastMonth }]
      };
    }
    var before = String(parseInt(year, 10) - 1);
    var rows = [["Pilgrims in " + year, people(total)], ["In lakh", lakh(total)]];
    if (D.annual[before] !== undefined) {
      var was = D.annual[before];
      rows.push([before + " for comparison", people(was)]);
      rows.push(["Change", (total >= was ? "+" : "") +
                 (((total - was) / was) * 100).toFixed(1) + "%"]);
    }
    return {
      asked: "The record for " + year,
      headline: "<strong>" + lakh(total) + "</strong> pilgrims visited in " +
        year + ".",
      body: kv(rows),
      caveats: [],
      sources: [{ artefact: "data/raw/monthly.csv",
                  detail: "the twelve observed months of " + year }]
    };
  }

  function outsideAnswer(key) {
    return {
      asked: "The record for " + monthLabel(key),
      headline: "That month is outside what this project covers.",
      body: "<p>The observations run from <strong>" + monthLabel(D.firstMonth) +
        "</strong> to <strong>" + monthLabel(D.lastMonth) + "</strong>, and the " +
        "forecast reaches " + monthLabel(Object.keys(D.forecast).sort().pop()) +
        ". There is no number here for " + monthLabel(key) + ", and this page " +
        "will not estimate one for you.</p>",
      caveats: [],
      sources: [{ artefact: "data/raw/monthly.csv",
                  detail: "covers " + D.firstMonth + " to " + D.lastMonth }]
    };
  }

  // ---- festivals -------------------------------------------------------
  var FESTIVAL_WORDS = [
    { re: /navratri|navaratri|navratra/, match: /navratri/i },
    { re: /\bsharad\b/, match: /sharad/i },
    { re: /\bchaitra\b/, match: /chaitra/i },
    { re: /diwali|deepavali|lakshmi\s*puja/, match: /diwali|lakshmi/i },
    { re: /shivaratri|shivratri|mahashivratri/, match: /shivaratri/i },
    { re: /raksha|rakhi|bandhan/, match: /raksha/i }
  ];

  function festivalAnswer(q) {
    var picked = null;
    for (var i = 0; i < FESTIVAL_WORDS.length; i++) {
      if (FESTIVAL_WORDS[i].re.test(q)) { picked = FESTIVAL_WORDS[i]; break; }
    }
    var wantsUpcoming = !picked && /\bwhen\b|\bnext\b|\bupcoming\b/.test(q) &&
                        /festival/.test(q);
    if (!picked && !wantsUpcoming) return null;

    var year = findYear(q);
    var today = D.lastMonth + "-01";
    var hits = D.festivals.filter(function (f) {
      if (picked && !picked.match.test(f.label)) return false;
      if (year) return f.date.slice(0, 4) === year;
      return f.date >= today;
    });
    if (!hits.length) {
      return {
        asked: "Festival dates",
        headline: "No computed date matches that.",
        body: "<p>This project computes five festivals only — the ones that " +
          "move the monthly count at this shrine. It is not a general almanac, " +
          "and it will not guess a date it has not computed.</p>",
        caveats: [],
        sources: [{ artefact: "results/festivals.csv", detail: "no matching row" }]
      };
    }
    hits = hits.slice(0, 14);
    var rows = hits.map(function (f) {
      return [f.label + (f.day > 1 ? " — day " + f.day : ""), f.date];
    });
    var first = hits[0];
    var scope = picked ? first.label : "Festival dates";
    return {
      asked: scope + (year ? " in " + year : ", upcoming"),
      headline: "<strong>" + esc(first.label) + "</strong> falls on <strong>" +
        first.date + "</strong>.",
      body: kv(rows) + "<p>These dates are computed from an astronomical " +
        "ephemeris, not read from a table. Ask how the festival dates are worked " +
        "out for what that means.</p>",
      caveats: [],
      sources: [{ artefact: "results/festivals.csv",
                  detail: hits.length + " computed date(s)" }]
    };
  }

  function kv(rows) {
    var body = rows.map(function (r) {
      return '<tr><th class="left">' + r[0] + '</th><td class="right">' +
        r[1] + "</td></tr>";
    }).join("");
    return '<div class="scroll"><table class="kv"><tbody>' + body +
      "</tbody></table></div>";
  }

  // ---- the bank --------------------------------------------------------
  //
  // Scoring is deliberately dull. Each answer owns a vocabulary: the words of
  // the question it answers, plus its declared keywords. A query scores one
  // point per distinct content word it shares with that vocabulary, and the
  // word count of any declared multi-word phrase it contains outright.
  //
  // The bar is relative, not absolute. A three-word question that matches one
  // incidental word has not been understood; a one-word question that matches
  // its only word has been. An absolute floor gets one of those two wrong
  // whichever value it takes.

  var STOP = {};
  ("a an and are as at be by can could do does for from has have how i in into is " +
   "it its me my of on or please should show tell that the their there these this " +
   "to was were what when where which who will with would you your about give get " +
   "many much am we us")
    .split(" ").forEach(function (w) { STOP[w] = true; });

  function contentWords(q) {
    var seen = {}, out = [];
    q.replace(/[^a-z0-9\s-]/g, " ").split(/\s+/).forEach(function (w) {
      if (!w || STOP[w] || w.length < 2 || seen[w]) return;
      seen[w] = true;
      out.push(w);
    });
    return out;
  }

  var VOCAB = null;
  function vocabulary(a) {
    var words = {};
    contentWords(a.question.toLowerCase()).forEach(function (w) { words[w] = true; });
    a.keywords.forEach(function (k) {
      k.split(" ").forEach(function (w) { if (!STOP[w] && w.length > 1) words[w] = true; });
    });
    return words;
  }

  function scoreBank(q) {
    if (!VOCAB) { VOCAB = D.answers.map(vocabulary); }
    var words = contentWords(q);
    if (!words.length) return null;

    var best = null, bestScore = 0;
    D.answers.forEach(function (a, index) {
      var vocab = VOCAB[index];
      var score = 0;
      words.forEach(function (w) { if (vocab[w]) score += 1; });
      a.keywords.forEach(function (k) {
        if (k.indexOf(" ") === -1) return;
        if (q.indexOf(k) > -1) score += k.split(" ").length;
      });
      if (score > bestScore) { bestScore = score; best = a; }
    });

    var required = Math.min(D.floor, words.length);
    if (!best || bestScore < required) return null;
    return {
      asked: best.question,
      headline: best.headline,
      body: best.body,
      caveats: best.caveats,
      sources: best.sources
    };
  }

  function unknown() {
    var list = D.answers.map(function (a) {
      return '<li><button class="chip" data-q="' + esc(a.question) + '">' +
        esc(a.question) + "</button></li>";
    }).join("");
    return {
      asked: "Not understood",
      headline: "I don't have an answer to that, and I won't invent one.",
      body: "<p>This page answers from artefacts that have already been computed " +
        "and committed. When nothing matches, it says so rather than showing you " +
        "the nearest thing and letting it read like an answer.</p>" +
        "<p>Here is everything it can answer:</p>" +
        '<ul style="list-style:none;padding:0;display:flex;flex-wrap:wrap;gap:.45rem">' +
        list + "</ul>" +
        "<p class=\"muted\">You can also ask about any single month or year in " +
        "the record — for example <em>March 2020</em>, <em>how many came in " +
        "2019</em>, or <em>when is Diwali</em>.</p>",
      caveats: [],
      sources: []
    };
  }

  function resolve(raw) {
    var q = raw.toLowerCase().trim();
    if (!q) return null;

    var fest = festivalAnswer(q);
    if (fest) return fest;

    if (/\bnext month\b/.test(q)) {
      return forecastAnswer(Object.keys(D.forecast).sort()[0]);
    }

    var key = findMonthKey(q);
    if (key) {
      if (D.forecast[key]) return forecastAnswer(key);
      if (D.observations[key] !== undefined) return observationAnswer(key);
      return outsideAnswer(key);
    }

    var year = findYear(q);
    if (year && !/\bhorizon\b/.test(q)) {
      var ya = yearAnswer(year);
      if (ya) return ya;
    }

    return scoreBank(q) || unknown();
  }

  // ---- rendering -------------------------------------------------------
  function render(answer, raw) {
    var el = document.getElementById("answer");
    var prov = "";
    if (answer.sources && answer.sources.length) {
      prov = '<div class="prov"><b>Where this comes from</b><ul style="margin:0;' +
        'padding-left:1.1rem">' + answer.sources.map(function (s) {
          return "<li><code>" + esc(s.artefact) + "</code> — " +
            esc(s.detail) + "</li>";
        }).join("") + "</ul></div>";
    }
    var caveats = (answer.caveats || []).map(function (c) {
      return '<p class="caveat">' + c + "</p>";
    }).join("");
    el.innerHTML =
      '<article class="card">' +
        '<p class="asked">' + esc(answer.asked) + "</p>" +
        '<h2 class="headline">' + answer.headline + "</h2>" +
        '<div class="body">' + answer.body + "</div>" +
        caveats + prov +
      "</article>";
    el.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function ask(raw) {
    var answer = resolve(raw);
    if (!answer) return;
    document.getElementById("q").value = raw;
    render(answer, raw);
  }

  document.addEventListener("click", function (event) {
    var chip = event.target.closest("[data-q]");
    if (chip) { ask(chip.getAttribute("data-q")); }
  });
  document.getElementById("go").addEventListener("click", function () {
    ask(document.getElementById("q").value);
  });
  document.getElementById("q").addEventListener("keydown", function (event) {
    if (event.key === "Enter") { ask(this.value); }
  });

  window.__ask = ask;
  // Exposed so the matcher can be exercised without a DOM. tests/test_ui.py
  // drives it through node against a battery of questions, because "the page
  // answers the wrong question confidently" is not a failure any Python-side
  // assertion about the HTML would catch.
  window.__resolve = resolve;

  // Open on the question most readers arrive with, so the page is never a
  // blank box waiting to be interrogated.
  ask(D.opening);
})();
"""


def _card(answer: Answer) -> str:
    """One answer rendered statically, for the browsable section below the box.

    The whole bank is in the page as plain HTML, not only inside the script.
    A reader with JavaScript disabled loses the ask box and keeps every answer.
    """
    caveats = "".join(f'<p class="caveat">{c}</p>' for c in answer.caveats)
    sources = "".join(
        f"<li><code>{s.artefact}</code> &mdash; {s.detail}</li>"
        for s in answer.sources
    )
    prov = (
        '<div class="prov"><b>Where this comes from</b>'
        f'<ul style="margin:0;padding-left:1.1rem">{sources}</ul></div>'
        if sources else ""
    )
    return (
        f'<details class="card fold"><summary>{answer.question}</summary>'
        f'<h3 class="headline">{answer.headline}</h3>'
        f'<div class="body">{answer.body}</div>{caveats}{prov}</details>'
    )


def render(art: Artefacts, answers: list[Answer] | None = None,
           generated: dt.date | None = None) -> str:
    """Assemble the page. Every number in it arrives through ``art``."""
    answers = answers if answers is not None else build_answers(art)
    generated = generated or dt.date.today()

    payload = lookup_tables(art)
    payload["answers"] = [a.as_dict() for a in answers]
    payload["floor"] = MATCH_FLOOR
    payload["monthlyCaveat"] = MONTHLY_CAVEAT
    payload["opening"] = answers[0].question

    # `</script>` inside a JSON string would close the block early. Escaping the
    # angle brackets is the standard fix and keeps the payload valid JSON.
    blob = (
        json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )

    # Only the first few, in declared order. Every answer is browsable in full
    # below, and a chip row carrying the whole bank stops being a starting point
    # and becomes a menu nobody reads.
    chips = "".join(
        f'<button class="chip" data-q="{a.chip}">{a.chip}</button>'
        for a in [a for a in answers if a.chip][:CHIP_COUNT]
    )

    site_short = "Shri Mata Vaishno Devi, Katra"
    first_month = _month_name(pd.Period(payload["firstMonth"], freq="M"))
    last_month = _month_name(pd.Period(payload["lastMonth"], freq="M"))
    meta = "".join(
        f"<span>{item}</span>"
        for item in (
            f"{len(art.monthly):,} months observed",
            f"last observed: {last_month}",
            f"{len(art.metrics):,} forecasts scored",
            f"generated {generated.isoformat()}",
        )
    )

    figures = "".join(
        f'<figure><img alt="{title}" src="{uri}">'
        f"<figcaption><b>{title}</b>{caption}</figcaption></figure>"
        for title, caption, uri in art.figures
    )
    figures_section = (
        '<h2 class="section">The evidence, drawn</h2>'
        '<p class="section-note">Every figure below was drawn from the same '
        "committed artefacts the answers are read from. None of them is an "
        "illustration.</p>" + figures
        if figures else ""
    )

    unverified = regimes.unverified(art.windows)
    open_items = [
        "<li><strong>No resourcing ratios are declared.</strong> Marshals, "
        "medical posts and gate counts are site policy and are not model "
        "output, so none are computed or shown.</li>",
    ]
    if unverified:
        names = ", ".join(f"<code>{w.id}</code>" for w in unverified)
        open_items.append(
            f"<li><strong>{len(unverified)} of {len(art.windows)} shock windows "
            f"are not yet audited</strong> ({names}). Their citations were "
            "drafted from public reporting and have not been checked against "
            "the sources.</li>"
        )

    # Precomputed rather than inlined below: an f-string expression that reuses
    # the enclosing quote character is a syntax error before Python 3.12, and
    # pyproject declares 3.11 as the floor.
    cards = "".join(_card(a) for a in answers)
    open_html = "".join(open_items)

    return f"""<title>Vaishno Devi Footfall</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>{STYLE}</style>
<div class="wrap">
<header>
  <p class="eyebrow">Shri Mata Vaishno Devi &middot; Katra, J&amp;K</p>
  <h1>How many pilgrims, and how sure are we?</h1>
  <p class="lede">Ask a question in plain words. Every answer below comes from a
  row in a committed results file, and names which one. Nothing on this page is
  computed when you open it, and nothing on it was typed by hand.</p>
  <div class="meta">{meta}</div>
  <p class="scope"><strong>One shrine only.</strong> Every number here is the
  record of {site_short}. Nothing on this page describes Tirupati, Sabarimala,
  or any other site &mdash; this one&rsquo;s disruptions are its own, and no
  second site has been scored, so there is no evidence either way about whether
  any of it holds elsewhere.</p>
</header>

<section class="ask">
  <div class="askbar">
    <input id="q" type="text" autocomplete="off"
           placeholder="e.g. how many pilgrims are expected in October?">
    <button class="go" id="go" type="button">Ask</button>
  </div>
  <div class="chips">{chips}</div>
</section>

<section id="answer"></section>

<h2 class="section">Every question this page answers</h2>
<p class="section-note">The full bank, open to read without asking. The ask box
above matches against exactly these, plus any single month or year in the
record.</p>
{cards}

{figures_section}

<h2 class="section">What is still open</h2>
<p class="section-note">Neither of these is a bug, and neither has a default.
Both are recorded here for the same reason they are recorded in the README:
a reader should not have to find out from someone else.</p>
<ul class="open-items">{open_html}</ul>

<footer class="page">
  <p>Observations run {first_month} to {last_month}, transcribed from the shrine
  board's published month-wise figures. This page is generated by
  <code>make ui</code> from <code>results/</code> and is a static file: it holds
  no live connection to the models, and opening it runs no forecast.</p>
  <p>Forecasts are monthly. They size what a month needs. They cannot identify a
  crush risk on a particular day or hour, and nothing here should be used as if
  they could.</p>
</footer>
</div>
<script>window.__YATRA__={blob};</script>
<script>{SCRIPT}</script>
"""


def write(html: str, path: str | Path = "results/yatra.html") -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(html, encoding="utf-8")
    return destination

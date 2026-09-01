# Yatra

Regime-separated forecasting of pilgrimage footfall at Shri Mata Vaishno Devi.

The spec is [docs/claude_code_brief.md](docs/claude_code_brief.md). Read it
first. This file is the working agreement: what to run, where things live, and
the decisions that are already settled so they don't get re-litigated.

---

## 1. Run it

There is no `make` on the owner's machine (Windows, Git Bash, no MSYS make), so
every stage is reachable two ways and they call the same code:

```bash
make all                 # if you have make
python make.py all       # if you don't -- same targets, same order
```

Targets, in dependency order:

| Target | Does | Writes |
|--------|------|--------|
| `ingest` | converts owner-supplied figures into contract shape | `data/raw/*` |
| `validate` | data contract: contiguity, annual reconciliation, citations | nothing |
| `calendar` | festival dates from the ephemeris | `results/calendar.csv`, `festivals.csv` |
| `backtest` | rolling-origin, all models, h=1..6 | `results/metrics.csv` |
| `bootstrap` | block bootstrap over origins | `results/bootstrap.csv` |
| `sensitivity` | re-scores the same forecasts under every declared window set | `results/sensitivity*.csv` |
| `figures` | series + shock shading, forecast vs actual, intervals | `results/figures/*.png` |
| `report` | rewrites the generated block in README.md | `README.md` |
| `operations` | forward forecast → crowd-planning briefing | `results/operations.csv`, `briefing.md` |
| `ui` | artefacts → one self-contained answer page | `results/yatra.html` |
| `test` | pytest, calendar tests first | nothing |
| `all` | validate → calendar → backtest → bootstrap → sensitivity → figures → report → operations → ui → test | |

`ingest` is **not** in `all`. It writes into `data/raw/`, and the observation
set must never change underneath a pipeline run. Invoke it by name, once.

Use the venv: `.venv/Scripts/python.exe` on Windows, `.venv/bin/python`
elsewhere. `make.py` finds it itself.

## 2. Layout

```
src/yatra/
  contract.py    data loading + the invariants that must hold. No defaults.
  regimes.py     shock windows. Raises without a citation.
  ephemeris.py   thin port over the astronomy backend. One backend at a time.
  panchanga.py   tithi/sankranti/festival rules. Backend-independent.
  calendarfeat.py  festival dates -> monthly feature frame.
  models.py      the 9 models, the registry, NEEDS_CALENDAR, ABLATIONS,
                 and the switching model's break detector.
  metrics.py     MASE and friends. One denominator definition, used by all.
  backtest.py    the origin set, and the assertion that everyone shares it.
  bootstrap.py   block bootstrap over origins. Resampling unit is the origin.
  sensitivity.py re-labelling under alternative shock windows. Cheap, because
                 regimes are labels: see 3.4.
  figures.py     every figure, drawn from artefacts only.
  ingest.py      owner's figures -> contract shape. Transcribes, never invents.
  operations.py  forward forecast -> crowd-planning briefing.
  report.py      README generation from results/metrics.csv.
  ui.py          artefacts -> results/yatra.html. Answers, or refuses. See 3.8.
  cli.py         stage entry points.
experiments/configs/   yaml. Nothing numeric is hardcoded in src/.
data/raw/              observations. Owner-supplied. Never generated.
results/               committed artefacts.
```

## 3. Settled decisions

Do not undo these without saying so out loud.

### 3.1 The README's numbers are generated, not typed

`report.py` owns **two** regions of the README and rewrites each wholesale:

| Region | Markers | Written by |
|---|---|---|
| The first screen — the finding, the rank table, the hero figure | `<!-- BEGIN LEAD -->` / `<!-- END LEAD -->` | `report.render_lead()` |
| The results section — leaderboard, ablations, horizons, sensitivity | `<!-- BEGIN GENERATED -->` / `<!-- END GENERATED -->` | `report.render()` |

This is how constraint 2 ("every README number traces to a row in
metrics.csv") is made mechanical rather than aspirational. If you find yourself
typing a number into the README, you are doing it wrong — put it in the
generator.

Two regions rather than one because the finding belongs above the fold and the
method belongs below it, and neither may be hand-typed. The lead is the block
most likely to be quoted into a slide or an abstract and the least likely to be
re-checked against the CSV first, which makes it the worst place in the
repository for a rank a re-run has since moved. `update_readme` raises on a
missing marker pair rather than creating one: the generator does not guess at
document structure.

The rank table itself is rendered by one function, `_rank_table`, and shown in
both regions. Rendering it twice independently would let an edit to one leave a
visitor reading ranks the results section contradicts further down.

**The lead's closing sentence is about a third ranking.** It says what a
leaderboard *averaged over all months* would recommend — neither of the two
columns in the table above it. That model is read from the pooled column in
`_selection_cost`, never inferred from the clean winner. The two coincide on the
committed record only because ordinary months outnumber disrupted ones by more
than ten to one, which is a property of this sample and not of the method. The
function branches on all three cases (pooling picks the clean winner, the shock
winner, or neither) because the paragraph claims something different in each,
and `tests/test_report_lead.py` exercises each branch.

Prose outside the markers is hand-written and survives regeneration. Prose
outside every marker pair must not contain numbers;
`tests/test_no_fabrication.py` strips both regions and asserts what is left has
no decimal or thousands-grouped figure in it.

### 3.2 MASE has exactly one denominator

Seasonal-naive (m=12) mean absolute error, computed **in-sample on the training
window ending at the forecast origin**. Defined once in `metrics.py`, computed
once per origin in `backtest.py`, and handed to every model's scoring.

Why it matters: if the denominator varied by model, the per-regime tables would
not be comparable and the whole inversion finding would be an artefact of
normalisation. It is computed per origin, not per model, so it cannot.

### 3.3 Calendar routing is an explicit set

`NEEDS_CALENDAR` in `models.py` is a literal `frozenset` of model names.
It is not derived from a name suffix, a prefix, or any string match.
`tests/test_registry.py` asserts every member resolves in the registry.

This is a scar, not a preference. See §5 of the brief.

### 3.4 Shock windows are labels, never inputs

`regimes.py` exists to *score* results, not to inform them. No model receives a
shock label, a shock date, or anything derived from one. The Step 3 switching
model detects breaks from the observation window alone, using only data
available at the forecast origin.

A model that reads the shock windows would post a spectacular result and mean
nothing. `backtest.py` never passes the regime frame into a fit call.

### 3.5 Planning ratios are never shipped with a default

`experiments/configs/operations.yaml` ships `ratios: []` and the briefing says
so out loud. Resourcing ratios — marshals per thousand pilgrims a day, medical
posts, gates — are site policy set by people with operational authority, not
model output.

A default invented here would render in the briefing table in the same typeface
as one signed off by an operations lead, and no reader could tell them apart.
`tests/test_operations.py` asserts the shipped config stays empty.

Related: the briefing must keep stating that these are **monthly** forecasts and
cannot identify a peak-day or peak-hour crush. A test asserts that caveat is
still in the template. See [docs/operations.md](docs/operations.md).

### 3.6 The ephemeris backend is declared, not discovered

`ephemeris.py` selects a backend from config and fails loudly if it is
unavailable. It does **not** try Swiss Ephemeris, catch ImportError, and quietly
use something else — that is the §5 failure mode wearing a different hat. If
the configured backend cannot load, the calendar stage crashes.

### 3.7 Ablation pairs are declared, not inferred

`ABLATIONS` in `models.py` is a literal tuple naming, for each design choice
under test, the arm that has it and the arm that does not. The report's
"what each design choice is worth" section is generated from it.

Same reasoning as §3.3, and the same scar. A pair inferred from names — a
`_cal` suffix, a shared prefix — stops being a pair the moment somebody
renames a model, and a comparison of an arm against itself reports a
difference of zero. Zero is indistinguishable from "this choice does not
matter", which is a publishable-looking finding.

`_validate_ablations()` runs at import and raises if a pair names an
unregistered model, compares a model with itself, is declared twice, or — for
the calendar pair specifically — has both arms inside `NEEDS_CALENDAR` or
neither. `tests/test_registry.py` covers each case.

The resolved/unresolved bar in that section is read from the bootstrap
artefact's own `confidence` column. Do not type a significance threshold into
`report.py`: that would put a number in the README that no row produced.

### 3.8 The answer console is a reader, and it is allowed to refuse

`ui.py` writes one self-contained HTML file from committed artefacts. The brief
forbade dashboards (§3 constraint 5); the owner asked for a UI after the demo,
so the constraint was amended rather than ignored. What it was protecting still
holds and is what makes this an acceptable amendment:

- **No framework, server, database or container**, and no new dependency. One
  file, opened from the filesystem, working offline.
- **It computes nothing.** By the time it runs, every number it can show has
  been scored and committed. It reads `results/`; it never calls a model. There
  is no code path from the page back into `models.py`.
- **The answers are rendered in Python, not in the browser.** `ui.py` builds a
  card — finished HTML — for every question the page can answer, including one
  per month, per year and per festival in the record, and ships them as a deck
  the payload addresses by index. The browser routes: it reads the query, finds
  an index, and shows that card. It composes exactly one string, the date a
  refusal names back to the reader, and does no arithmetic at all.

  This is §3.1 applied one surface further out. The matcher used to format lakh,
  sum a part year and work out a year-on-year change in the browser — numbers a
  reader saw, in a second copy of `_lakh` and `_people` that lived inside a
  string constant where neither `pytest` nor the node probe could reach it. A
  formatting rule with two definitions has two places to be wrong.
  `tests/test_ui.py` asserts `SCRIPT` contains no `toFixed`, `toLocaleString`,
  `Math.round` or `1e5`, and that the routing tables and the deck address each
  other exactly — an index off the end is a question that answers with nothing,
  and an unaddressed card is an answer the page silently stops giving.

  The cost is the file: pre-rendering every month and festival card roughly
  doubles the payload. That is the trade taken deliberately. It buys a page
  whose every sentence was produced by a function the tests can call.
- **It runs inside `all`, after every stage it reads**, and calls
  `assert_labels_current` like the other regime-consuming stages. It is the
  second document a non-technical reader opens away from the run that produced
  it, so a stale regime split reaching it is the failure `operations` already
  guards against. `tests/test_artefact_staleness.py` lists it.

Three properties are load-bearing and tested:

**It refuses.** When nothing clears the match bar, it says so and lists what it
can answer. It does not show the nearest match. A confident answer to a question
nobody asked is §5 of the brief in a friendlier typeface — and worse here than
anywhere else, because the reader is the one least equipped to notice.

**It cites on the card.** Every answer names its artefact and rows in the page,
not in a footnote. No answer body contains a numeric literal; every figure is
interpolated from an artefact, for the same reason as §3.1.

**It discloses.** Unverified windows are named, the empty planning ratios are
stated (§3.5), and the unfittable model is reported (constraint 7). A friendly
surface is where those go quiet first.

`BUILDERS` is a literal tuple, not a scan for `_answer_*` functions, and
`tests/test_ui.py` asserts the two agree. Same scar as §3.3 and §3.7: a builder
missing from the tuple is an answer the page silently stops giving.

**Routing is defined in `ui.resolve`, and the page's copy is held to it.**
Which card a question reaches is not a property any assertion about the HTML
can catch, and "answers the wrong question confidently" is the failure this
project is built against — so it is settled in Python, against the same payload
the page carries, and `pytest` exercises it with no browser in sight.

The browser keeps a copy because a query does not exist until somebody types
one; that is the single rule in this module with two definitions, and it is not
left on trust. `tests/test_ui.py` drives both over one battery through node
(`tests/ui_probe.js`) and requires the same card out of each, compared on the
rendered bytes and not just the title — a refusal that filled its date slot
differently on the two sides would show a reader a month nothing in `results/`
holds. The battery carries the cases where the two could plausibly diverge:
case, diacritics, an impossible ISO month, and "may" as a modal verb. If node
is absent only that conformance check skips; the routing is still tested,
which it was not while it lived in a string constant.

**The committed page is marked generated.** `.gitattributes` carries
`results/yatra.html linguist-generated=true`. The page is output, not source:
`make ui` rewrites it whole from `ui.py` and the artefacts, and a hand edit to
it is gone on the next run. The attribute tells GitHub two true things — keep
it out of the language statistics, which describe what somebody wrote, and fold
it in diffs, where two megabytes of regenerated markup is noise around the
change that caused it. It stays committed either way: a reader should be able
to open the console without running the pipeline first.

### 3.9 The per-window shock section states a pattern, never a cell

`report._by_shock_type()` unpools the shock leaderboard into the individual
declared windows. It is the same objection this project raises against the
overall leaderboard, applied one level down: "shock" is a cliff to zero, a
slow climb, a second cliff inside that climb, and a compound security-and-
landslide event, and averaging them produces an ordering no single disruption
need resemble.

Two rules hold it honest, and both are the kind a later edit would flatten:

**The block-structure sentence is conditional.** It claims every COVID pair
agrees and every straddling pair does not. That is true of the committed
record; it is not true by construction. The code checks the panel and stays
silent when the panel does not show it. Turning it into an unconditional
sentence would make it boilerplate that happens to be right, which is
indistinguishable from a finding until the data changes.

**A ragged panel returns nothing.** A model absent from one window would have
its ranks computed over a different model set column to column, and the table
would look exactly as it does now. That is `RaggedPanel` reappearing at report
time, and the section refuses rather than ranking incomparable columns.

The per-window counts run to tens, not thousands. No column here is resolvable
on its own and the section says so in those words; what it supports is the
pattern across columns. Do not add a bootstrap interval per window to make it
look settled — on 18 forecasts the interval would span the table.

## 4. Things that must crash, not warn

A short list, because the temptation to downgrade these to warnings recurs:

- Missing observation file → `MissingObservations`, names the path.
- Gap in the monthly series → `ContractViolation`, names the months.
- Annual total not matching its months → `ContractViolation`, shows both.
- Shock window without a citation → `MissingCitation`.
- `needs_calendar` model fit without calendar features → `CalendarRoutingError`.
- Model missing from a cell of the origin × horizon grid → `RaggedPanel`.
- Configured ephemeris backend unavailable → `EphemerisUnavailable`.
- Declared ablation pair naming an unregistered model, comparing a model
  with itself, or (for the calendar pair) failing to straddle
  `NEEDS_CALENDAR` → `ConfigError` at import.
- Sankranti falling within minutes of a new moon → `ConfigError` naming the
  date. Which side it lands on decides a lunar month's name and can create or
  erase an adhika month, shifting every festival label for that year. That
  margin is finer than the Lahiri ayanamsa is *defined* to, so it is not a
  precision problem more decimals would fix. Adjudicate against a published
  panchang; do not widen the tolerance to make it go away.

- Break detector returning a position at or past the forecast origin →
  `LeakageError`. The `switching` model may read the observation window up
  to its origin and nothing else, and never the declared shock windows.
  A detector that peeked would post a spectacular shock-regime score that
  meant nothing at all.

None of these has a `strict=False` escape hatch. Adding one re-opens §5.

## 5. Data

`data/raw/` is owner-supplied. The observations are now present — monthly
counts from 1986-01, with the annual file they reconcile against. See
[docs/data_schema.md](docs/data_schema.md) for the exact files and columns the
contract expects. The pipeline will not run without them and will not pretend
to: `make validate` is the first target for that reason.

`data/raw/` is written only by `make ingest`, which is not part of `all`. Do not
edit those files by hand and do not let a pipeline stage write into them: the
observation set must not change underneath a run that is scoring against it.

Do not add a sample file, a fixture with plausible footfall values, or a
`--demo` flag. If you need to exercise the pipeline without data, run the unit
tests — they cover pure functions on literals, which is the only synthetic
input this project permits (brief §4).

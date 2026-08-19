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
| `test` | pytest, calendar tests first | nothing |
| `all` | validate → calendar → backtest → bootstrap → sensitivity → figures → report → operations → test | |

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
  cli.py         stage entry points.
experiments/configs/   yaml. Nothing numeric is hardcoded in src/.
data/raw/              observations. Owner-supplied. Never generated.
results/               committed artefacts.
```

## 3. Settled decisions

Do not undo these without saying so out loud.

### 3.1 The README's numbers are generated, not typed

`report.py` reads `results/metrics.csv` and rewrites everything between the
`<!-- BEGIN GENERATED -->` and `<!-- END GENERATED -->` markers. This is how
constraint 2 ("every README number traces to a row in metrics.csv") is made
mechanical rather than aspirational. If you find yourself typing a number into
the README, you are doing it wrong — put it in the generator.

Prose outside the markers is hand-written and survives regeneration. Prose
outside the markers must not contain numbers.

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

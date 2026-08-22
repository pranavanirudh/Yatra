# Yatra

Regime-separated forecasting of pilgrimage footfall at Shri Mata Vaishno Devi,
Katra, Jammu & Kashmir.

The question is not "which forecasting model is best". It is whether the answer
to that question changes depending on whether the month was ordinary or
disrupted — and if it does, what a single averaged leaderboard is hiding.

**The hypothesis under test:** model rankings invert across regimes. A method
that wins on ordinary months loses during shocks, and the reverse. If that
holds, then a leaderboard averaged over all months does not merely lose
precision — it recommends the model that fails exactly when a forecast would
have mattered.

---

## Status

The pipeline has run end to end on the owner-supplied observations. The results
section below is generated from `results/metrics.csv`, and every figure in
`results/figures/` was drawn from committed artefacts by the same run.

| Stage | State |
|---|---|
| Data contract | observations loaded, contiguous, annual totals reconciling |
| Shock windows | declared with citations — **owner verification part-complete** |
| Model registry | complete; one model reported as unfittable rather than dropped |
| Backtest harness | run; one origin set, shared MASE denominator |
| Calendar layer | computed from the ephemeris, validated against published almanacs |
| Bootstrap intervals | run; block resampling over origins |
| Shock-window sensitivity | run; reported in the results section below |
| Switching model | run and scored, leak guards live |
| Figures | regenerated from artefacts |
| Crowd-planning briefing | written; **awaiting site planning ratios** |
| Answer console | generated from artefacts; refuses rather than guesses |

Two items are open and neither is code. The shock-window citations were drafted
from public reporting; the owner has since checked some of them against the
sources, and the rest are still outstanding. Until they all are, the regime
split rests in part on an unaudited boundary — the generated section says so
and names which windows are still unverified. And the briefing ships with no
resourcing ratios, because those are site policy rather than model output.

There are no placeholder numbers anywhere in this file, and there will not be
any: the results section is written by `src/yatra/report.py` directly from
`results/metrics.csv`, so a number can appear here only if a row produced it.

## Running it

The observations are in the repository, so this runs as-is:

```bash
python -m venv .venv

# Windows
.venv/Scripts/python.exe -m pip install -e ".[dev]"
# macOS / Linux
.venv/bin/python -m pip install -e ".[dev]"

python make.py all      # or `make all` where make exists
```

`make.py` re-executes itself inside `.venv`, so `python make.py` is enough once
the environment exists — it does not matter which interpreter you invoke it
with. The minimum Python version is declared in `pyproject.toml`.

Two things are fetched or built rather than committed. The virtual environment
is yours to create, above. The ephemeris kernel is downloaded on demand the
first time the calendar stage runs — it is a large binary reproducible from a
stable public URL, so it is git-ignored rather than stored. That download is the
only step that needs network access; everything else runs offline.

Bringing your own observations is a separate path, and is described under
[Getting your data in](#getting-your-data-in) below. You do not need it to run
what is here.

`all` runs `validate`, `calendar`, `backtest`, `relabel`, `bootstrap`,
`applicability`, `sensitivity`, `figures`, `report`, `operations`, `ui`, `test`,
in that order. A stage that fails stops the run rather than being skipped.

`ingest` is deliberately **not** part of `all`: it writes `data/raw/`, and the
observation set must never change underneath a pipeline run.

`make validate` is deliberately first. It refuses to proceed without the
observation files, and it refuses to proceed if a declared shock window has no
citation.

### Getting your data in

This is only needed to bring in a **different** dataset — a longer series, a
correction from the publisher, or another site. The observations this project
reports on are already in `data/raw/`, and running ingest would overwrite them.

`make ingest --inspect <file>` reads a CSV or spreadsheet, shows you what is in
it, and prints a config template with the columns pre-filled. You edit the
template — in particular declaring the **unit**, since figures for this shrine
are usually published in lakh — and run `make ingest`.

Nothing about that conversion is guessed. Units, column names and date formats
are all declared, because a series read as absolute when it was published in
lakh is wrong by a factor of a hundred thousand and nothing downstream can
detect it. Gaps in the source stay gaps in the output; `make validate` then
names the missing months.

## Data

The observations are in this repository, under `data/raw/`. They are
owner-supplied, transcribed from the shrine board's published month-wise
figures, and every row carries the source id it came from; the schema they
satisfy is in [docs/data_schema.md](docs/data_schema.md). The closure months of
2020 are recorded as observed zeros, not as missing values, because that is what
the publisher reports.

They are written only by `make ingest`, which is not part of `make all`. Nothing
in the pipeline writes to `data/raw/`, so the observation set cannot change
underneath a run that is scoring against it.

This project does not generate, simulate, or impute observations — not to fill a
gap, and not to exercise the pipeline. The loader has no default, no bundled
sample, and no code path capable of inventing a footfall value. Missing data
stays missing, and `make validate` reports the missing months by name.

## Method

**Regimes.** Shock windows are declared in
[experiments/configs/shocks.yaml](experiments/configs/shocks.yaml), each with a
source citation; `regimes.py` raises without one. Windows are *evaluation
labels* — no model ever sees them. A forecast is scored on the regime of its
**target** month, not its origin, because the target is the month the model got
wrong.

**Comparability.** Every model is scored on one origin set, built before any
model runs and asserted complete afterwards. MASE has exactly one denominator —
in-sample seasonal-naive error over the training window ending at the origin —
computed once per origin and shared by all models, so no model can be flattered
by a scale of its own.

**Calendar.** Festival dates are computed from an ephemeris, never tabulated.
There is no date table in `src/`, and a test asserts there is none. Reference
dates appear only in `tests/test_calendar.py`, as validation against published
almanacs; if one of those tests fails, the computation is wrong, not the test.

The backend is declared in
[experiments/configs/calendar.yaml](experiments/configs/calendar.yaml) and
never discovered — if the named one cannot load, the stage crashes rather than
substituting another, because two ephemerides disagreeing by minutes is enough
to move a contested festival date and nothing downstream would say why. Which
one, and why, is recorded in [docs/ephemeris.md](docs/ephemeris.md).

Mapping a tithi onto a civil day is a rule, not a calculation, and the rule
differs by festival: most follow sunrise, Shivaratri follows ritual midnight,
Diwali's Lakshmi Puja follows the evening. Each is declared per festival in the
config, because that choice decides more dates than any plausible difference
between ephemerides does.

**A model that could not be scored at all.** Holt-Winters with multiplicative
seasonality is excluded from the comparison, and that exclusion is a result
rather than housekeeping. Multiplicative seasonality is undefined on a training
window containing a zero, and the shrine was closed for part of 2020, so from
that point onward the estimator cannot be fit at any origin. Scoring it only on
the earlier origins it survives would compare it against models scored on an
easier stretch of history, which is not a comparison; relaxing the
failure-on-error rule reopens exactly that; nudging the zeros upward would
fabricate observations. So it is excluded and said out loud. That a standard
seasonal method becomes unfittable once a closure enters the record is itself
something worth knowing about forecasting through shocks.

**Sensitivity.** The shock windows are drawn by hand, so the headline
comparison depends on where the lines go. `make sensitivity` re-scores the same
forecasts under alternative window definitions and reports whether the ranking
moves. This costs almost nothing precisely because no model ever sees a regime
label — re-labelling is a join, not a refit. Had the windows been model inputs,
the boundary choice could not have been tested without repeating the whole
backtest, which is how a boundary artefact gets published as a finding.

**Switching.** One model changes its behaviour depending on the regime it
thinks it is in. Everything it knows it reads out of its own training window,
which ends at the forecast origin — it never sees the declared shock windows,
because a model scored against the labels it was given would win the comparison
this project exists to make. Its no-break branch is deliberately identical to
plain Holt-Winters, so the gap between those two columns isolates the switch
itself rather than a change of estimator.

## Using the output

`make operations` writes `results/briefing.md`, a plain-language planning
document, and `results/operations.csv` alongside it. Full guidance is in
[docs/operations.md](docs/operations.md); two points matter enough to repeat
here.

**These are monthly forecasts.** They size the resourcing a season needs. They
cannot identify a crush risk on a particular afternoon — that is a question
about minutes, and this series has a resolution of months. What partly bridges
the gap is the calendar layer, which names the exact dates in each month that
concentrate arrivals; those are the days that need surge cover. No peak-day
multiplier is reported, because estimating one honestly requires daily arrival
counts this project does not have. If such data exists, adding it is the single
highest-value extension.

**Planning ratios are yours, not the model's.** The shipped config declares
none, and the briefing says so rather than falling back on a default. How many
marshals per thousand pilgrims a day is safe depends on track geometry,
chokepoints and statutory requirements — none of which a footfall model knows
anything about. A default invented here would render in the same typeface as
one signed off by an operations lead.

Each forecast carries two ranges: the ordinary-month band, and a wider
shock-regime band measured on disrupted months. Plan contingency to the second.

### Asking it questions

`make ui` writes `results/yatra.html` — a page you open by double-clicking it,
where somebody who will never run `pytest` can type a question in plain words
and get an answer back with the file and rows it came from printed underneath.
It answers questions about the project, and it answers questions about any
single month or year in the record.

It is one file. There is no server, no framework, no database and nothing to
install; the figures are embedded, so it works offline, from a USB stick, and
years from now. Opening it runs no forecast — by the time the page exists every
number on it has already been computed, scored and committed, and the page is a
reader over those artefacts in exactly the way the generated section of this
README is.

Three properties of it are deliberate and are held in place by tests:

- **It refuses.** When nothing matches, it says so and lists what it can answer.
  It never returns its least-bad match, because a confident answer to a question
  nobody asked is this project's central failure mode wearing a friendlier face.
- **It cites.** Every answer card carries the artefact and the rows behind it.
  No number in it is typed; all of them are interpolated from `results/`.
- **It discloses.** The unverified shock windows are named on it, the absent
  planning ratios are stated on it, and the model that could not be fitted is
  reported on it rather than dropped. A friendly surface is exactly where those
  would otherwise go quiet.

This is a departure from the brief's constraint against dashboards, taken on the
owner's instruction and recorded in [CLAUDE.md](CLAUDE.md) rather than made
quietly. What the constraint was protecting — that results live in committed
artefacts, and that nothing computes behind glass — is intact.

## Design notes

Two decisions carry more weight than the rest, and both are scars:

- **`NEEDS_CALENDAR` is a literal set of model names**, not a name-suffix rule.
  Suffix routing broke once on a rename, and the ablation arm trained without
  the features it existed to test — which reads as a null result, not a bug. The
  set is now checked against the registry at import time and again in the test
  suite.
- **Every failure in the list in [CLAUDE.md](CLAUDE.md) crashes rather than
  warning.** A pipeline that quietly emits a plausible number is worse than one
  that stops.

Losing configurations are reported. A model that underperforms stays in the
table with its number.

---

## Results

<!-- BEGIN GENERATED -->

> **Generated section.** Everything between the markers is written by `src/yatra/report.py` from `results/metrics.csv`. Edits here are overwritten by `make report`. Numbers do not belong in the hand-written prose outside the markers.

### Run provenance

| | |
|---|---|
| Forecast origins | 362 (1995-12 to 2026-01) |
| Horizons | 1, 2, 3, 4, 5, 6 |
| Models | 9 |
| Forecasts scored | 19,548 |
| Backtest config hash | `f1310f570fef` |

### Regime split

| Regime | Forecasts | Per model |
|---|---:|---:|
| clean | 18,090 | 2,010 |
| shock | 1,458 | 162 |

| Shock window | Forecasts | Per model |
|---|---:|---:|
| covid_closure | 432 | 48 |
| covid_recovery_post_delta | 324 | 36 |
| covid_recovery_pre_delta | 270 | 30 |
| delta_wave | 162 | 18 |
| floods_2025 | 270 | 30 |

### Mean MASE by regime

Lower is better. Rank is within the column. Every model is scored on an identical origin set, so the two columns are comparable.

| Model | Clean MASE | Rank | Shock MASE | Rank | Rank change |
|---|---:|---:|---:|---:|---:|
| `sarimax_cal` | 1.354 | 1 | 4.616 | 4 | +3 |
| `sarima` | 1.372 | 2 | 4.562 | 3 | +1 |
| `holt_winters_add` | 1.431 | 3 | 5.979 | 9 | +6 |
| `switching` | 1.435 | 4 | 5.870 | 8 | +4 |
| `switching_sticky` | 1.516 | 5 | 5.624 | 6 | +1 |
| `seasonal_naive` | 1.520 | 6 | 5.724 | 7 | +1 |
| `theta` | 1.964 | 7 | 4.760 | 5 | -2 |
| `naive` | 4.155 | 8 | 3.133 | 1 | -7 |
| `drift` | 4.197 | 9 | 3.147 | 2 | -7 |

### The inversion

- Best on clean months: `sarimax_cal` — ranks 4 of 9 during shocks.
- Best on shock months: `naive` — ranks 8 of 9 on clean months.

Across **2,000 block-bootstrap resamples** of the origin set, the clean-month and shock-month rankings came out inverted in **95.8%** of them.

A rank correlation over every model is a blunt summary. These are the substitutions someone would actually make, and the share of resamples in which each one pays:

| Comparison | Regime | Share of resamples |
|---|---|---:|
| `naive` beats `sarimax_cal` | shock | 96.1% |
| `naive` beats `sarima` | shock | 96.0% |
| `naive` beats `holt_winters_add` | shock | 96.8% |
| `sarimax_cal` beats `naive` | clean | 100.0% |

The Spearman correlation between the two rankings is **-0.383**, with a 95% interval of [-0.717, +0.550]. That interval spans zero, so on the conventional threshold the rank correlation on its own would not be called significant.

That threshold is answering a harder question than the one being asked. Rho tests whether the *whole* ordering of every model reverses, and it has only the disrupted months in the record to estimate a full permutation from — so its interval is wide by construction. The pairwise proportions above test the claims anyone would act on, and are correspondingly sharper on the same evidence. Both are reported; they are not in conflict, they are different questions.

### Does the finding survive a different boundary?

The shock windows are drawn by hand. Below, the *same* forecasts are re-scored under each declared window set — a re-labelling, not a refit, because no model ever receives a regime label.

| Window set | Windows | Shock forecasts per model | Rank correlation | Inverts |
|---|---:|---:|---:|---|
| `declared` — the owner's declared windows, as shipped | 5 | 162 | -0.383 | yes |
| `refined` — Boundaries redrawn against the observations: article_370 dropped (no monthly signal at the shrine), covid trimmed to 2021-08 (recovery completes in autumn 2021), floods_2025 extended to 2025-10. | 2 | 144 | -0.400 | yes |

The rank correlation is negative under **2 of 2** window definitions. The inversion is not an artefact of where the boundaries were drawn.

The two models the finding turns on do not move: `sarimax_cal` ranks first on clean months and `naive` ranks first on shock months under every window set.

Models whose clean rank moves between window sets: `holt_winters_add`, `switching`.
Models whose shock rank moves between window sets: `holt_winters_add`, `seasonal_naive`, `switching`, `switching_sticky`.

### Does the finding survive at every forecast lead time?

The leaderboard above pools h=1 through h=6. A planner reading the briefing is reading one lead time, not the average of six. Here the same forecasts are split by horizon.

| Horizon | Best on clean | Its shock rank | Best on shock | Its clean rank | Rank correlation |
|---:|---|---:|---|---:|---:|
| h=1 | `sarimax_cal` | 5 of 9 | `naive` | 8 of 9 | -0.367 |
| h=2 | `sarimax_cal` | 5 of 9 | `naive` | 8 of 9 | -0.483 |
| h=3 | `sarimax_cal` | 4 of 9 | `naive` | 8 of 9 | -0.383 |
| h=4 | `sarimax_cal` | 4 of 9 | `naive` | 8 of 9 | -0.383 |
| h=5 | `sarimax_cal` | 4 of 9 | `naive` | 8 of 9 | -0.350 |
| h=6 | `sarimax_cal` | 4 of 9 | `naive` | 8 of 9 | -0.333 |

The correlation is negative at **6 of 6** lead times, and the same two models take the two crowns at every one of them: `sarimax_cal` on clean months, `naive` on shock months. The inversion is not an artefact of pooling horizons — it is present at each horizon separately.

### What each design choice is worth

The leaderboard says which model won; it does not say what any one decision bought, because two models differ in many things at once. Each pair below differs by exactly one, and both arms are scored on the same origins against the same denominator.

| Comparison | What varies | Regime | With | Without | Difference | With it better in |
|---|---|---|---:|---:|---:|---:|
| `sarimax_cal` vs `sarima` | festival calendar features | clean | 1.354 | 1.372 | -0.018 | 85.0% |
|  |  | shock | 4.616 | 4.562 | +0.053 | 7.6% |
| `switching` vs `holt_winters_add` | whether the model switches at a detected break | clean | 1.435 | 1.431 | +0.005 | 35.7% |
|  |  | shock | 5.870 | 5.979 | -0.109 | 66.0% |
| `switching_sticky` vs `switching` | how long the switched regime is held before release | clean | 1.516 | 1.435 | +0.081 | 0.7% |
|  |  | shock | 5.624 | 5.870 | -0.246 | 90.3% |

Lower MASE is better, so a **negative** difference means the choice helped. The last column is the share of block-bootstrap resamples in which it helped, which is what carries the claim — a difference in the third decimal is not a result on its own. Every arm is scored on the same 2,010 clean and **162 shock** forecasts, and the shock column is the thin one: read every difference in it against that number.

- **Festival calendar features** — the sign flips between regimes — better on clean months, worse on shock ones.
- **Whether the model switches at a detected break** — the sign flips between regimes — better on shock months, worse on clean ones.
- **How long the switched regime is held before release** — the sign flips between regimes — better on shock months, worse on clean ones.

Every one of these choices trades one regime against the other. That is the headline finding reappearing inside pairs of models differing by a single decision: on this record there is no design choice here that is simply better, only choices that are better somewhere.

The calendar pair is worth reading twice, because the calendar layer is this project's largest single investment. A festival regressor asserts a surge on a date the ephemeris computed, and a closure or a flood does not move that date — the feature goes on predicting an arrival pattern that policy or the weather has cancelled. The sign above is consistent with that.

**It is an observation, not a basis to build on.** It is one pair of models on 162 shock forecasts from a single shrine, and it is not among the comparisons that clear the declared level below. The obvious thing to do with it — route calendar features by regime, so the model drops them once it thinks it is in a shock — has deliberately not been built. Doing so would fit a mechanism to a difference this record cannot resolve, and the resulting model would then be scored on the same disrupted months that suggested it. What would justify building it is more disrupted months, from a site whose disruptions are not these ones.

Of the 6 pair-and-regime comparisons above, **1** clears the bootstrap's declared 95% level in one direction or the other. The rest are directional and unresolved by this record, and are reported as such rather than as findings.

### What the calendar layer contains

`sarimax_cal` wins the clean regime and is one arm of the ablation above, so what its features are made of is part of reading both results. The dates are computed from an ephemeris — there is no date table in `src/` — under the declarations below.

| | |
|---|---|
| Backend | `skyfield` (de421.bsp) |
| Ayanamsa | lahiri |
| Lunar month scheme | purnimanta |
| Reference location | Shri Mata Vaishno Devi Bhawan |
| Span computed | 1985-01-01 to 2030-12-31 |
| Festival dates resolved | 966 |

**5 festivals, not a general almanac.** The civil-day rule is declared per festival because it genuinely differs, and it decides more dates than any plausible disagreement between ephemerides does.

| Festival | Tithi rule | Civil-day rule | Duration |
|---|---|---|---:|
| Chaitra Navratri (day 1) | chaitra shukla 1 | sunrise | 9 days |
| Sharad Navratri (day 1) | ashvina shukla 1 | sunrise | 9 days |
| Maha Shivaratri | phalguna krishna 14 | nishita | 1 day |
| Diwali (Lakshmi Puja) | kartika krishna 30 | pradosha | 1 day |
| Raksha Bandhan | shravana shukla 15 | sunrise | 1 day |

The monthly columns handed to the model are `festival_days`, `sharad_navratri_days`, `is_navratri_month`, `lunar_drift_days`. Each is a function of the calendar alone and touches no observation, so none of them can carry a future footfall value into a forecast.

Across the 552 months in the feature frame, **238** carry at least one festival day. In the other 314 the festival counts are zero, so whatever the arm contributes there comes from `lunar_drift_days`.

### Models that could not be scored

These are registered and were attempted, but cannot be fit on this series. They are absent from the tables above for that reason, not because they were untested.

| Model | Origins where the fit is impossible | First such origin |
|---|---:|---|
| `holt_winters_mul` | 70 of 362 | 2020-04 |

Multiplicative seasonality divides by a seasonal index, so it requires every month in its training window to be above zero. The shrine closed completely for part of 2020 and those months are recorded as zero. From the first origin whose history contains a closed month, the model is undefined — and every later origin inherits that history, so it never becomes fittable again.

It was not quietly replaced with the additive variant. Doing so would put a number in the table under this model's name that a different model produced. **Applicability is part of the comparison:** a method that stops existing once a shock enters the record is not a safe default, however well it scores in ordinary months.

### Caveat: unverified shock windows

3 of 5 declared shock windows carry citations that the project owner has not yet checked against the source: `covid_recovery_pre_delta`, `delta_wave`, `covid_recovery_post_delta`. The dates were drafted from public reporting. Until they are verified, the regime split — and therefore every number above — rests on an unaudited boundary.

<!-- END GENERATED -->

---

## Layout

```
src/yatra/       contract, regimes, ephemeris, panchanga, calendarfeat,
                 models, metrics, backtest, report, ui, cli
experiments/     configs. Nothing numeric is hardcoded in src/.
data/raw/        observations. Owner-supplied, never generated.
results/         committed artefacts. metrics.csv is the source of truth.
docs/            the spec, the data schema, the ephemeris decision.
tests/           pytest.
```

See [CLAUDE.md](CLAUDE.md) for the working agreement and
[docs/claude_code_brief.md](docs/claude_code_brief.md) for the spec.

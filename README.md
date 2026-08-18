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

This repository is under construction and **has not produced a result yet**.

| Stage | State |
|---|---|
| Data contract | code complete, no observations on disk |
| Shock windows | declared with citations, awaiting owner verification |
| Model registry | code complete |
| Backtest harness | code complete, never run |
| Calendar layer | computed, validated against published almanacs |
| Bootstrap intervals | built, block resampling over origins |
| Shock-window sensitivity | built, ranking holds under both definitions |
| Switching model | built, leak-guarded, unscored until data lands |
| Figures | built, regenerated from artefacts |
| Crowd-planning briefing | built, awaiting site planning ratios |

Nothing below the generated marker exists yet, because no backtest has run.
There are no placeholder numbers anywhere in this file, and there will not be
any: the results section is written by `src/yatra/report.py` directly from
`results/metrics.csv`, so a number can appear here only if a row produced it.

## Running it

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e ".[dev]"

# One-time: get your figures into the shape the contract expects.
python make.py ingest --inspect path/to/your-figures.csv   # describes the file
#   ... edit experiments/configs/ingest.yaml from the template it prints ...
python make.py ingest                                      # writes data/raw/

python make.py all      # or `make all` where make exists
```

`all` runs `validate`, `calendar`, `backtest`, `bootstrap`, `figures`,
`report`, `operations`, `test`, in that order. A stage that fails stops the run
rather than being skipped.

`ingest` is deliberately **not** part of `all`: it writes `data/raw/`, and the
observation set must never change underneath a pipeline run.

`make validate` is deliberately first. It refuses to proceed without the
observation files, and it refuses to proceed if a declared shock window has no
citation.

### Getting your data in

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

The observations are not in this repository. They are owner-supplied, and the
schema they must satisfy is in [docs/data_schema.md](docs/data_schema.md).

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
| clean | 17,928 | 1,992 |
| shock | 1,620 | 180 |

| Shock window | Forecasts | Per model |
|---|---:|---:|
| article_370 | 162 | 18 |
| covid | 1,188 | 132 |
| floods_2025 | 270 | 30 |

### Mean MASE by regime

Lower is better. Rank is within the column. Every model is scored on an identical origin set, so the two columns are comparable.

| Model | Clean MASE | Rank | Shock MASE | Rank | Rank change |
|---|---:|---:|---:|---:|---:|
| `sarimax_cal` | 1.359 | 1 | 4.234 | 4 | +3 |
| `sarima` | 1.376 | 2 | 4.196 | 3 | +1 |
| `holt_winters_add` | 1.436 | 3 | 5.467 | 9 | +6 |
| `switching` | 1.440 | 4 | 5.370 | 8 | +4 |
| `switching_sticky` | 1.522 | 5 | 5.151 | 6 | +1 |
| `seasonal_naive` | 1.529 | 6 | 5.207 | 7 | +1 |
| `theta` | 1.969 | 7 | 4.421 | 5 | -2 |
| `naive` | 4.167 | 8 | 3.103 | 1 | -7 |
| `drift` | 4.209 | 9 | 3.119 | 2 | -7 |

### The inversion

- Best on clean months: `sarimax_cal` — ranks 4 of 9 during shocks.
- Best on shock months: `naive` — ranks 8 of 9 on clean months.

Across **2,000 block-bootstrap resamples** of the origin set, the clean-month and shock-month rankings came out inverted in **90.4%** of them.

A rank correlation over every model is a blunt summary. These are the substitutions someone would actually make, and the share of resamples in which each one pays:

| Comparison | Regime | Share of resamples |
|---|---|---:|
| `naive` beats `sarimax_cal` | shock | 90.3% |
| `naive` beats `sarima` | shock | 90.2% |
| `naive` beats `holt_winters_add` | shock | 93.4% |
| `sarimax_cal` beats `naive` | clean | 100.0% |

The Spearman correlation between the two rankings is **-0.383**, with a 95% interval of [-0.717, +0.783]. That interval spans zero, so on the conventional threshold the rank correlation on its own would not be called significant.

That threshold is answering a harder question than the one being asked. Rho tests whether the *whole* ordering of every model reverses, and it has only the disrupted months in the record to estimate a full permutation from — so its interval is wide by construction. The pairwise proportions above test the claims anyone would act on, and are correspondingly sharper on the same evidence. Both are reported; they are not in conflict, they are different questions.

### Models that could not be scored

These are registered and were attempted, but cannot be fit on this series. They are absent from the tables above for that reason, not because they were untested.

| Model | Origins where the fit is impossible | First such origin |
|---|---:|---|
| `holt_winters_mul` | 70 of 362 | 2020-04 |

Multiplicative seasonality divides by a seasonal index, so it requires every month in its training window to be above zero. The shrine closed completely for part of 2020 and those months are recorded as zero. From the first origin whose history contains a closed month, the model is undefined — and every later origin inherits that history, so it never becomes fittable again.

It was not quietly replaced with the additive variant. Doing so would put a number in the table under this model's name that a different model produced. **Applicability is part of the comparison:** a method that stops existing once a shock enters the record is not a safe default, however well it scores in ordinary months.

### Caveat: unverified shock windows

3 of 3 declared shock windows carry citations that the project owner has not yet checked against the source: `article_370`, `covid`, `floods_2025`. The dates were drafted from public reporting. Until they are verified, the regime split — and therefore every number above — rests on an unaudited boundary.

<!-- END GENERATED -->

---

## Layout

```
src/yatra/       contract, regimes, ephemeris, panchanga, calendarfeat,
                 models, metrics, backtest, report, cli
experiments/     configs. Nothing numeric is hardcoded in src/.
data/raw/        observations. Owner-supplied, never generated.
results/         committed artefacts. metrics.csv is the source of truth.
docs/            the spec, the data schema, the ephemeris decision.
tests/           pytest.
```

See [CLAUDE.md](CLAUDE.md) for the working agreement and
[docs/claude_code_brief.md](docs/claude_code_brief.md) for the spec.

# Yatra

Regime-separated forecast evaluation: rank inversions a pooled leaderboard
hides. Monthly pilgrimage footfall at Shri Mata Vaishno Devi, Katra, Jammu &
Kashmir.

<!-- BEGIN LEAD -->

## The finding

Rank 9 forecasting models by average error on ordinary months, then rank them again on disrupted months, and the two orders disagree: **`sarimax_cal` wins on ordinary months but ranks 4 of 9 during shocks, while `naive` wins during shocks but ranks 8 of 9 on ordinary months.**

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

All 9 models, ranked in each regime and joined. The two picked out are the winner of each regime; the rest are drawn in grey rather than dropped. The lines cross.

![Slope chart: each model's rank on ordinary months joined to its rank on disrupted months. The line for `sarimax_cal` falls from first to 4 and the line for `naive` rises from 8 to first, crossing in the middle.](results/figures/inversion_hero.png)

**What this costs you at selection time.** A leaderboard averaged over all months recommends `sarimax_cal`, which ranks 4 of 9 in exactly the months a forecast would have mattered — and it discards `naive`, which is the one that wins there. Averaging over regimes does not lose precision so much as invert the recommendation.

Scored on one shared origin set against one shared MASE denominator, so the two columns are comparable. The evidence behind each claim, the bootstrap intervals and the boundary sensitivity are in [Results](#results); what this project has deliberately left open, and why each item waits on someone's authority rather than on someone's time, is in [What is deliberately unfinished](#what-is-deliberately-unfinished).

<!-- END LEAD -->

---

## What was being tested

The question is not "which forecasting model is best". It is whether the answer
to that question changes depending on whether the month was ordinary or
disrupted — and if it does, what a single averaged leaderboard is hiding.

**The hypothesis under test:** model rankings invert across regimes. A method
that wins on ordinary months loses during shocks, and the reverse. If that
holds, then a leaderboard averaged over all months does not merely lose
precision — it recommends the model that fails exactly when a forecast would
have mattered.

The table above is the test of that, and the sections below are what makes it
checkable: where the observations came from, how the regimes were declared, how
the models were scored against each other, and how to re-run the whole thing.

## Status

The pipeline has run end to end on the owner-supplied observations. The results
section below is generated from `results/metrics.csv`, and every figure in
`results/figures/` was drawn from committed artefacts by the same run.

| Stage | State |
|---|---|
| Data contract | observations loaded, contiguous, annual totals reconciling |
| Shock windows | declared with citations; two anchored to announcements, three inferred from the series and marked so |
| Model registry | complete; one model reported as unfittable rather than dropped |
| Backtest harness | run; one origin set, shared MASE denominator |
| Calendar layer | computed from the ephemeris, validated against published almanacs |
| Bootstrap intervals | run; block resampling over origins |
| Shock-window sensitivity | run; reported in the results section below |
| Switching model | run and scored, leak guards live |
| Figures | regenerated from artefacts |
| Crowd-planning briefing | written; **awaiting site planning ratios** |
| Answer console | generated from artefacts; refuses rather than guesses |

One item is open and it is not code: the briefing ships with no resourcing
ratios, because those are site policy rather than model output.

**The unverified shock windows are not a second open item.** They are correctly
marked, and they will stay that way. Two windows are anchored to announcements —
a suspension, a reopening, a landslide, a resumption — and the owner checked
those against primary reporting. The rest are phases *within* a longer
disruption, and nobody announced where one phase ends and the next begins; this
project inferred those points from the observations. A citation cannot evidence
an inference, so marking them verified would launder a judgement into a
citation. The generated section names which are which and explains the
distinction, and the sensitivity arm exists precisely to test whether the
inferred boundaries are load-bearing.

The search for supporting sources is recorded in
[docs/citation_research.md](docs/citation_research.md) — URLs opened, read and
quoted, and matched against what each window claims. It found one thing worth
knowing: one recovery window's *start* coincides with a published capacity
order, so that edge is documented even though its other edge is not. It also
records the boundaries no reporting evidences at all, which is the more useful
half.

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

Installing also puts a `yatra` command on the path. It runs the same stages
through the same dispatcher `make.py` uses, so there is nothing it can do that
`make.py` cannot and no way for the two to disagree:

```bash
yatra --help            # the targets, and what each one does
yatra validate          # one stage
yatra ingest --inspect published.csv   # options after a target go to the stage
yatra                   # no target means `all`, the way a bare `make` does
```

A bare `yatra` running the whole pipeline is deliberate, and the help says so
where you will read it before finding out: `all` is what the command is for,
and it rewrites `results/`.

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

Every answer it can give is written by `ui.py` at build time — the ones about
the project, and one for each month, year and festival in the record. The page
carries those finished cards and looks one up. What is left in the browser is
routing: read the question, find the card, show it. It formats nothing and adds
nothing up, so there is no second copy of a rule like *how a count is written in
lakh* sitting where no test can reach it.

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

## Scope

**Demonstrated at one site:** Shri Mata Vaishno Devi, Katra, Jammu & Kashmir.
The exact span and month count are in the generated Scope table below, because
they are numbers and numbers live inside the markers.

That is a **scope condition, not a shortfall.** The claim under test is about how
forecasting models are *selected* — whether ranking them by average error
survives being split by regime. Two rankings at one well-documented site, scored
on a shared origin set against a shared denominator, are adequate evidence for a
claim of that shape. A second site would not make the inversion at this one more
or less real.

**What one site leaves open is transfer, and that question is left open rather
than answered.** Whether these particular rankings hold at another shrine is not
addressed here, and nothing below should be read as bearing on it. The per-window
section gives a reason to expect transfer to be *harder* than it looks — the
winning model already differs across kinds of disruption within this single site
— but that is a reason for caution, not a finding about other sites.

## What publication practice permits

The second site was searched for seriously, and the search produced a result
worth reporting on its own account.

**Four administering bodies were assessed. One publishes what reproducible
monthly forecasting requires** — a month-wise series with a separately published
annual total that independently checks it.

| Body | Site | What is published | Why it does not support this work |
|---|---|---|---|
| SMVDSB | Vaishno Devi | month-wise series since the 1980s, with annual totals beside it | — this is the one that works |
| TTD | Tirumala | daily counts, as one news post per day | no annual total anywhere to reconcile a compiled series against; the pre-2020 archive interleaves two different measurement windows without labelling them |
| TDB | Sabarimala | season totals, through press releases | not month-wise, and splitting a season across months would be imputation |
| HR&CE | Tamil Nadu temples | revenue and land holdings | attendance is not published at all |

The Uttarakhand bodies administering Kedarnath were assessed on the same
criteria and fall the same way: figures reach the press daily through the
season, and none is published as a series.

**The finding is that reproducible forecasting research on Indian pilgrimage
sites is constrained by publication practice, not by absence of data.** Every
body above counts pilgrims, most report those counts publicly in some form, and
almost none publishes them as a series with an independent check. The obstacle
is the shape of publication rather than the existence of records — which is a
different problem from the one it is usually taken for, and a more tractable one,
because it is answerable by request rather than by instrumentation.

Outside the inversion itself, this is the most generalisable thing here: it
applies to any site, any researcher, and any method, and it explains why
multi-site work on this subject is rare. The assessments are in
[docs/second_site.md](docs/second_site.md) and
[docs/site2_tirumala.md](docs/site2_tirumala.md), and the requests that would
change the answer are drafted in `docs/data_request_*.md`.

A second site was searched for. Four candidates were examined and rejected;
[docs/second_site.md](docs/second_site.md) records what each failed on and what
would change the verdict. It is kept for the same reason the rejected shock
windows are kept in the config: a candidate somebody examined and declined is
part of the audit trail, and without it a later reader cannot tell it from one
nobody thought of.

### Site 2 is Tirumala, and what it will and will not settle

Recorded **before any data is collected**, so the results cannot later be read
as closing a gap they do not close.

**It will not strengthen the non-pandemic evidence.** Tirumala's dominant
disruption is COVID, which this project already holds in four subdivided
windows. A second site whose major shock is the same pandemic adds forecasts
without adding an independent disruption. The single non-pandemic window remains
single, and the qualification on the per-window block structure stands
completely unchanged. No result from the second site is to be described as
though it moved that.

**It will test whether the headline claim replicates.** The clean-versus-shock
rank inversion has never been examined anywhere but here, and Tirumala differs
in three ways that could plausibly break it: it counts darshan rather than
pilgrims entering, it draws a different pilgrim population, and its principal
observances are anchored differently in the calendar from the lunar festivals
this project computes. Replication across those differences is worth more than
another pandemic window. Failure to replicate is worth more still, and would be
reported as prominently.

**Its usable series is short, and it starts inside the pandemic.** The archive
depth has now been measured rather than estimated, from the site's own sitemaps.
Daily statistics in a consistent, machine-readable convention begin in mid-2020
— at the reopening — and run to the present. Posts exist back to 2013, but the
pre-2020 ones interleave a partial-day and a full-day figure without reliably
saying which is which, and most dates carry two competing values, so extending
the series backwards is an adjudication problem across thousands of ambiguous
records rather than a collection problem that effort solves.

That matters more than the month count alone. A second site whose clean months
are nearly all post-recovery is a weaker test of a clean-versus-shock contrast
than the same number of months from an undisturbed period would be.

**Training depth therefore differs between the sites, and is reported rather
than buried.** The two cannot be given the same run-up before their first
forecast origin. Where that differs it is stated in this README rather than left
in config; per-site origin counts appear wherever a site comparison appears; and
**the two sites are never pooled into a single averaged number.** A combined
leaderboard is the natural thing to reach for when presenting two sites, and it
is precisely the move this project exists to argue against — averaging across
heterogeneous regimes produces a number that describes none of them, and sites
are more heterogeneous than regimes.

**The recommendation is not to scrape it.** The contract requires a published
annual total that independently checks the monthly series, and TTD publishes
none — its own publications carry no annual figure, and the ones in circulation
come from press reporting. Summing a scrape into that slot would be the scrape
checking itself; using a rounded press total would require a tolerance the
contract deliberately does not have; exempting the second site would hold the
two to different standards of evidence. A request to the administering body,
answered with month-wise figures and separately-compiled annual totals, meets
the requirement exactly and costs a stamp rather than days of work on a series
the pipeline should refuse.

Depth, collection mechanics, the measurement-window ambiguity and a candidate
non-pandemic shock to check are assessed in
[docs/site2_tirumala.md](docs/site2_tirumala.md). Nothing has been transcribed
and `data/raw/` is untouched.

One further candidate is open rather than rejected. **Kedarnath** is the only site
examined whose major disruptions are not the pandemic — which is the thing this
record is short of, since all but one of its own declared windows are COVID
subdivisions. Its month-wise figures are not published but are held by public
authorities, so [docs/data_request_kedarnath.md](docs/data_request_kedarnath.md)
drafts the request that would make them citable. That would settle availability
and not the harder problem: the temple is shut for half of every year, so a
monthly series carries deterministic zeros, and those are a different object
from the unpredicted closure months in this record. Which frame to model it in
is a decision to take before any figure arrives, not after.

---

## Results

<!-- BEGIN GENERATED -->

> **Generated section.** Everything between the markers is written by `src/yatra/report.py` from `results/metrics.csv`. Edits here are overwritten by `make report`. Numbers do not belong in the hand-written prose outside the markers.

### Scope

| | |
|---|---|
| Site | Shri Mata Vaishno Devi, Katra, Jammu & Kashmir |
| Months observed | 487 |
| Span | 1986-01 to 2026-07 |
| Sites in this study | 1 |

**One site, and that is the scope of the claim rather than a shortfall against it.** What is under test is whether ranking models by average error survives being split by regime. Two rankings at one well-documented site, scored on a shared origin set against a shared denominator, answer that. A second site would not make the inversion here more or less real.

**What one site leaves open is transfer, and it is left open.** Whether these particular rankings hold at another shrine is not addressed by anything below. The per-window section gives a reason to expect transfer to be harder than it looks &mdash; the winning model already differs across kinds of disruption within this site, across its 5 declared windows &mdash; but that is a reason for caution about other sites, not a finding about them.

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

### Is "shock" one thing?

The split above is binary, and that is the same averaging this project objects to in the overall leaderboard, one level down. The declared windows are not variations on a theme: they are a cliff to zero, a slow climb, a second cliff inside that climb, and a compound security and landslide event. Below, the same shock forecasts are scored within each window instead of pooled across them.

Mean MASE, rank in brackets. Lower is better.

| Model | Pooled shock | `covid_closure` | `covid_recovery_post_delta` | `covid_recovery_pre_delta` | `floods_2025` | `delta_wave` |
|---|---|---|---|---|---|---|
| `drift` | 3.15 (2) | 3.63 (2) | 2.81 (1) | 2.85 (1) | 3.51 (8) | 2.42 (3) |
| `holt_winters_add` | 5.98 (9) | 8.14 (6) | 4.98 (8) | 6.29 (9) | 3.10 (2) | 6.48 (9) |
| `naive` | 3.13 (1) | 3.59 (1) | 2.83 (2) | 2.85 (2) | 3.49 (7) | 2.40 (2) |
| `sarima` | 4.56 (3) | 7.55 (4) | 3.55 (3) | 2.91 (4) | 3.11 (3) | 3.79 (5) |
| `sarimax_cal` | 4.62 (4) | 7.62 (5) | 3.59 (4) | 3.12 (5) | 3.16 (5) | 3.58 (4) |
| `seasonal_naive` | 5.72 (7) | 9.66 (9) | 6.35 (9) | 2.86 (3) | 3.61 (9) | 2.27 (1) |
| `switching` | 5.87 (8) | 8.85 (8) | 4.60 (7) | 5.60 (8) | 2.90 (1) | 5.88 (7) |
| `switching_sticky` | 5.62 (6) | 8.73 (7) | 3.82 (5) | 5.15 (7) | 3.13 (4) | 5.88 (7) |
| `theta` | 4.76 (5) | 6.15 (3) | 3.94 (6) | 4.89 (6) | 3.31 (6) | 4.88 (6) |
| **Forecasts per model** | **162** | **48** | **36** | **30** | **30** | **18** |

**5 windows, 4 different winners.** `covid_closure` &rarr; `naive`; `covid_recovery_post_delta` &rarr; `drift`; `covid_recovery_pre_delta` &rarr; `drift`; `floods_2025` &rarr; `switching`; `delta_wave` &rarr; `seasonal_naive`.

Whether two disruptions agree about which model to use, for every pair of windows:

| Window | Window | Rank correlation | Agree? |
|---|---|---:|---|
| `covid_closure` | `covid_recovery_post_delta` | 0.82 | yes |
| `covid_closure` | `covid_recovery_pre_delta` | 0.53 | yes |
| `covid_closure` | `floods_2025` | -0.30 | no |
| `covid_closure` | `delta_wave` | 0.28 | yes |
| `covid_recovery_post_delta` | `covid_recovery_pre_delta` | 0.63 | yes |
| `covid_recovery_post_delta` | `floods_2025` | -0.23 | no |
| `covid_recovery_post_delta` | `delta_wave` | 0.33 | yes |
| `covid_recovery_pre_delta` | `floods_2025` | -0.82 | no |
| `covid_recovery_pre_delta` | `delta_wave` | 0.91 | yes |
| `floods_2025` | `delta_wave` | -0.86 | no |

That table has a block structure. **Every pair of COVID-era windows agrees, and every pair that straddles COVID and a non-COVID disruption disagrees.** The COVID windows are one event subdivided, so their mutual agreement is close to tautological; the part that would carry information is what they collectively disagree with.

The COVID windows supply **81%** of the pooled shock column, so the pooled shock ranking is largely a ranking on one event. On `floods_2025`, `switching` wins and the pooled winner `naive` ranks 7 of 9.

**That block rests on 1 non-COVID window (`floods_2025`), and it cannot carry the weight the picture suggests.** The 4 negative correlations in the table are not 4 independent pieces of evidence: every one of them involves `floods_2025`, so they are one window compared 4 times. The apparent block is what 4 subdivisions of a single event and 1 other would look like whether or not disruption type matters at all.

Two claims are indistinguishable on this panel, and they are not the same claim:

1. COVID-era disruptions call for different models than non-COVID disruptions do.
2. `floods_2025` happens to have an idiosyncratic winner.

The obvious mechanism for the second &mdash; that `switching` suits this kind of shock because of how it is built &mdash; is a **hypothesis fitted to one window**, not a finding. It is written down here so it can be tested later, and it is not evidence for itself. What would separate the two claims is a second non-COVID disruption, from this site or another.

The heatmap in `results/figures/` shows this contrast as a clean block of colour. That cleanliness is a property of having one window on one side, not of the strength of the evidence, and it should not be read as the latter.

**Read all of this against the counts.** The thinnest window carries 18 forecasts per model. No single column above is resolvable on its own, and none of these orderings is offered as one: the bootstrap intervals reported earlier are already wide on the 162 pooled shock forecasts and would be wider still here. What the section supports is the pattern across columns, not any cell in them. A second site whose disruptions are not these ones is what would settle it, and [docs/second_site.md](docs/second_site.md) records why none was added.

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

### Which shock boundaries are documented

**2 of 5** declared windows have dates the owner checked against primary reporting: `covid_closure`, `floods_2025`.

The remaining 3 (`covid_recovery_pre_delta`, `delta_wave`, `covid_recovery_post_delta`) are marked unverified, and that is the **correct state rather than an outstanding task.** Their boundaries are derived from the observed series, not from an announced closure or resumption.

The difference matters more than the count. A citation can evidence that an event occurred and when it was announced — a suspension, a reopening, a capacity order, a landslide. It cannot evidence where one phase of a continuing disruption ends and the next begins, because nobody announced that; this project inferred it from the observations. Marking such a boundary verified would launder a judgement into a citation, which is why the flag is per-window and why these stay false.

What follows for the reader is not that the split is provisional, but that it is of two kinds. Windows anchored to an announcement can be checked by anyone. Windows drawn from the series carry the risk that a boundary sits where the data made it convenient, and the sensitivity arm above exists to test exactly that: the same forecasts re-scored under a different set of boundaries.

<!-- END GENERATED -->

---

## What is deliberately unfinished

Three things in this repository are open. None of them is a task nobody got
round to. Each is blocked on an authority this project does not hold, and in
each case supplying the missing piece from inside the repository would produce
output indistinguishable from the real thing — which is the specific failure
this whole design is built to prevent. They are collected here so a reader does
not have to reconstruct the list from footnotes.

**The briefing carries no resourcing ratios.** `make operations` forecasts
volumes and stops there: no marshals per thousand pilgrims a day, no medical
posts, no gate counts. Those are site policy, set by people with operational
authority over the track. A ratio invented here would render in the briefing
table in the same typeface as one signed off by an operations lead, and nothing
in the output would tell a reader which they were looking at. So the config
ships its ratio list empty, the briefing says so in place of a table, and a test
asserts it stays empty — see the working agreement in [CLAUDE.md](CLAUDE.md).
What unblocks this is a signature, not a commit.

**Three of the five shock windows are marked unverified, and are meant to stay
that way.** Two are anchored to announcements — a suspension, a resumption — and
were checked against primary reporting. The other three are phase boundaries
*within* a longer disruption, and nobody announced where one phase ended and the
next began; this project inferred them from the observed series. A citation
cannot evidence an inference, so marking them verified would launder a judgement
into a source — a worse defect than the label it would remove. The sensitivity
arm exists to test whether those boundaries carry the result, and it reports the
answer either way. The label is a finding about the evidence, not an
outstanding chore.

**No second site has been collected, and the search is itself a result.**
Tirumala is the selected candidate, on the reasoning above. What stops it is
that TTD publishes no annual total, and the data contract requires one that
independently checks the monthly series; summing a scrape into that slot would
be the scrape checking itself. Requests to TTD and to the Kedarnath authorities
are drafted in `docs/data_request_*.md` and unsent. Sending them is
correspondence rather than code, and until one is answered `data/raw/` stays as
it is. The single-site limit is the [scope of the claim](#scope), not a
shortfall against it: the claim is about how forecasting models are *selected*,
and two rankings at one well-documented site are evidence of that shape.

The common structure is worth naming. Every one of these could be closed this
afternoon by inventing the missing piece, and in every case the invented version
would be indistinguishable, in the generated output, from a real one. Leaving
them visible costs less than that would.

## Layout

```
src/yatra/       contract, regimes, ephemeris, panchanga, calendarfeat,
                 models, metrics, backtest, report, ui, cli
experiments/     configs. Nothing numeric is hardcoded in src/.
data/raw/        observations. Owner-supplied, never generated.
results/         committed artefacts. metrics.csv is the source of truth.
docs/            the spec, the data schema, the ephemeris decision, the
                 second-site search that did not find one, and how to present
                 the finding without overstating it.
tests/           pytest.
```

See [CLAUDE.md](CLAUDE.md) for the working agreement and
[docs/claude_code_brief.md](docs/claude_code_brief.md) for the spec.
[docs/README.md](docs/README.md) indexes every document in `docs/` with a status
against each, because several of them record decisions that were later revised
and this project keeps superseded reasoning rather than deleting it.

## Licence

The code is MIT, per [LICENSE](LICENSE).

**The observations are not this project's to licence, and the MIT grant does not
reach them.** The series under `data/raw/` is transcribed from the shrine
board's published month-wise figures; every row carries the source id it came
from, and `data/raw/sources.yaml` names the publisher. Reuse of those counts is
governed by whatever terms the publisher attaches to them, not by this file.
The same goes for the shock-window citations in
`experiments/configs/shocks.yaml`, which point at reporting this project does
not own.

What the licence does cover is the apparatus: the contract, the calendar layer,
the model registry, the backtest and everything generated into `results/`.

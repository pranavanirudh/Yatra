# Yatra — working brief

This file is the spec. It was reconstructed on 2026-08-18 from the project
owner's instructions, because the repository directory was found empty and no
prior spec existed on disk. Where the owner's instructions described work as
already complete, that description is recorded below as a **target**, not as a
fact. Nothing here asserts that a result exists.

---

## 1. What the project is

Regime-separated forecasting of pilgrimage footfall at Shri Mata Vaishno Devi,
Katra, Jammu & Kashmir. Monthly pilgrim counts, 1986-01 onward. The question is
not "which forecasting model is best" but "does the answer to that question
change depending on whether the month was normal or disrupted".

The hypothesis under test: **model rankings invert across regimes.** A method
that wins on ordinary months loses during shocks, and vice versa. If true, a
single leaderboard averaged over all months is not just imprecise, it is
actively misleading — it recommends the model that fails exactly when a forecast
would have mattered.

## 2. Targets

The status column was written on 2026-08-18, when the repository held no
observations and nothing had run. It is kept as it was, because a spec that
rewrites its own history stops being evidence of what was promised before the
work was done. The **Now** column is the current state.

| # | Target | Status 2026-08-18 | Now |
|---|--------|-------------------|-----|
| T1 | Verified monthly observations, no gaps, every annual total reconciling against the sum of its months | **blocked — no data on disk** | done — 487 months, 1986-01 to 2026-07 |
| T2 | Shock windows declared with source citations | scaffolded, 3 windows drafted | declared; **citations still unverified by the owner**, and the README says so |
| T3 | Rolling-origin backtest, all models on one origin set | code complete, cannot run without T1 | run — 362 origins × 6 horizons × 9 models |
| T4 | Regime-split metrics in `results/metrics.csv` | blocked on T1 | done, and reported by horizon and by window definition as well as pooled |
| T5 | Calendar layer computed from an ephemeris, never tabulated | **done** — skyfield declared, festival dates match published almanacs | unchanged; what it contains is now stated in the README |
| T6 | Block bootstrap over origins, `results/bootstrap.csv` | **built** — resamples origins in blocks; unrun until T1 | run — 2,000 resamples |
| T7 | `switching` model, leak-free break detector | **built** — detector + leak guards tested; unscored until T1 | scored; it does not rescue the shock regime, and that is reported |
| T8 | Figures regenerating from `make all` | **built** — five figures, all drawn from artefacts | six figures |
| T9 | A page a non-technical reader can question directly | *not in the 2026-08-18 brief; requested by the owner on 2026-08-22, and constraint 5 amended for it* | built — `results/yatra.html`, generated from artefacts, refuses rather than guesses |

## 3. Hard constraints

These are the owner's, verbatim in substance. They are enforced in code where
enforcement is possible; where it is not, they are enforced by review.

1. **Never generate, simulate, or impute observations.** Not even to test the
   pipeline. Missing data stays missing. See §4 for the one narrow reading of
   this that is permitted.
2. **Every README number must trace to a row in `results/metrics.csv`.**
   Enforced mechanically: the results section of the README is *generated* from
   the CSV by `src/yatra/report.py`. Hand-editing it is overwritten on the next
   `make all`.
3. **Every shock window needs a source citation.** `regimes.py` raises on a
   window without one. Not a warning.
4. **All models are scored on the same origin set.** The backtest builds the
   origin list once and asserts, after the fact, that every model produced a
   forecast for every (origin, horizon) cell. Different origins is not a
   comparison.
5. **No web frameworks, databases, containers, or dashboards.**
   **AMENDED 2026-08-22 by the owner**, after the demo, to permit a
   reader-facing page. The constraint is kept above as written rather than
   edited, because what was ruled out before the work was done is evidence and
   editing it away would destroy that. What the amendment permits is narrow, and
   the four nouns in the original are still all forbidden: `make ui` writes one
   self-contained HTML file from committed artefacts, with no framework, no
   server, no database, no container and no new dependency. It computes nothing
   when opened and has no code path back into the models. See CLAUDE.md §3.8.
6. **Festival dates are computed, never tabulated.** No hardcoded date table in
   `src/`. If a test in `tests/test_calendar.py` fails, fix the computation,
   never the test.
7. **Report losing configurations.** A model that underperforms stays in the
   table with its number. Silently dropping it is falsification.

## 4. The one permitted reading of constraint 1

Constraint 1 forbids **fabricating observations**. It does not forbid unit
tests over pure functions.

- Forbidden: writing a synthetic row into `data/`, filling a gap in the
  footfall series by interpolation, "seeding" the pipeline with plausible
  numbers so it runs end to end, or letting any invented value reach `results/`
  or the README.
- Permitted: asserting that `naive.forecast([1, 2, 3], h=1) == 3`. That is
  arithmetic on a literal, not a claim about how many people visited a shrine.

The dividing line is enforced structurally: the data loader has no default, no
sample file, and no `generate` path. It raises `MissingObservations` and names
the file it wanted. There is no code path that invents a footfall value.

## 5. Known failure mode to design against

Calendar routing once keyed off a `_cal` name suffix. A rename broke it
silently, and the ablation arm trained without the features it existed to test.
That reads as a null result, not as a bug — the pipeline emitted a plausible
number and nothing crashed.

The general form: **a pipeline that quietly emits a plausible number is worse
than one that crashes.** Countermeasures adopted here:

- `NEEDS_CALENDAR` in `src/yatra/models.py` is an explicit literal set of model
  names, not a string-matching rule.
- `tests/test_registry.py` asserts every name in that set resolves in the
  registry, so a rename fails the test suite instead of degrading an arm.
- The backtest raises if a model declaring `needs_calendar` is fit with an empty
  or absent calendar frame. It does not fit it anyway and log a warning.

## 6. Sequencing

The owner works in numbered steps and stops between them for review. Do not run
ahead of the current step. Steps 1–4 are in the owner's instructions and are not
restated here.

Step 0 — build the thing the later steps operate on — is complete, as are the
steps that produced the results now in `results/`. What is outstanding is not
code: the shock-window citations need checking against their sources, and the
crowd-planning briefing needs resourcing ratios from someone with operational
authority. Both are recorded as open in the README, and neither has a default.

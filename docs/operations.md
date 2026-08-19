# Using the output for crowd planning

`make operations` writes two things:

- `results/operations.csv` — one row per forecast month, machine-readable.
- `results/briefing.md` — the same content written for a duty officer.

This document is about what those numbers can and cannot carry.

---

## The one thing to get right

**This project forecasts pilgrims per month. A stampede happens in ninety
seconds.**

Those are different scales of question, and no amount of statistics turns the
first into the second. A monthly forecast tells you how much capacity a season
needs — how many shifts to roster, how much accommodation to open, when to bring
seasonal staff on. It cannot tell you that the queue at a particular gate will
exceed safe density at 4pm on a particular afternoon.

What partially bridges the gap is the calendar layer. It computes, from the
ephemeris, exactly which dates carry festivals — and arrivals concentrate on
those dates. So the briefing reports the month's expected volume **and names the
specific dates inside it**. Those dates are where surge cover belongs.

What is deliberately *not* reported is a "peak day" number. Estimating how much
heavier a Navratri day is than an ordinary one requires daily arrival counts.
This project has monthly totals. Multiplying a monthly mean by an invented peak
factor would produce a number that looks like exactly the thing an operations
plan needs, and is not.

**If daily footfall data exists, that is the single highest-value addition to
this project.** It would make peak-day estimation a real computation instead of
an omission.

## What the bands mean

Each month gets two ranges.

**The likely range** is the middle 90% (configurable) of how wrong the chosen
model has *actually been* at that horizon, on ordinary months, across the whole
backtest. It is measured, not derived from the model's own assumptions — a
model's analytic prediction interval assumes the model is correctly specified,
which is the assumption that fails first when something unusual happens.

**The shock-regime range** is the same measurement restricted to months inside a
declared shock window. It is much wider, and it is what a contingency has to
absorb. Planning to the likely range and then meeting a disruption is how a site
ends up under-resourced.

**A shock-regime lower bound of zero is a measurement, not a placeholder.** The
record contains months when this shrine was closed and the count was zero, so a
band measured on disrupted months reaches zero honestly. The band is clamped
there rather than going negative — a negative attendance is not a plan — but the
floor is something that has happened. The briefing says so beneath the table,
because a zero in a planning document reads like a rendering fault, and a reader
who dismisses it as one has dismissed the only entry in the document that is a
matter of record.

**If you edit the shock windows, regenerate the briefing.** The bands are split
by regime, so the briefing depends on the labels in `results/metrics.csv`. Run
`python make.py relabel` (seconds; no model is refit) and then `python make.py
operations`. The operations stage refuses to run against labels that no longer
match `shocks.yaml`, and the briefing's provenance table records the
shock-window fingerprint it was built from, so a briefing read months later can
be checked against the windows in force at the time.

Both are expressed in units of the MASE denominator internally and converted to
people at the current level. That detail matters for one reason: an earlier
version used a ratio of actual to predicted, and during a closure — when the
model predicts a normal month and almost nobody comes — the ratio explodes. It
turned a 1,500-pilgrim forecast into an upper bound of half a million. A band
that wide is not conservative, it is broken, and it would have appeared in the
briefing looking like analysis.

## Planning ratios are yours, not the model's

`experiments/configs/operations.yaml` ships with `ratios: []`, and the briefing
says plainly that no resourcing was computed.

That is deliberate and it should stay that way until someone with operational
authority fills it in. How many marshals per thousand pilgrims a day is safe
depends on track geometry, chokepoint locations, statutory requirements, weather
and shift patterns. The model knows the volume. It knows nothing about the site.

A default ratio shipped here would appear in the rendered table in exactly the
same typeface as one signed off by an operations lead, and nobody reading the
output could tell which they were looking at.

Each entry:

| field | meaning |
|---|---|
| `id` | short key; becomes an `operations.csv` column |
| `label` | column heading in the briefing |
| `per_pilgrims` | one unit of the resource per this many pilgrims |
| `basis` | `monthly_total`, `daily_mean`, or `festival_day_total` |
| `minimum` | floor, applied however low the forecast goes |

Choose the basis carefully. `daily_mean` spreads the month evenly, which
**understates festival days** — the days that actually need the cover.
`festival_day_total` sizes against the festival-day share instead. Neither is a
peak-day figure.

## Choosing the forecasting model

`model: best_clean` uses whichever model scored best on ordinary months in the
last backtest. That is right for routine planning and **wrong during an ongoing
disruption** — the whole hypothesis of this project is that the clean-month
winner may be among the worst choices exactly when a forecast matters.

Check `results/bootstrap.csv` before trusting a ranking. If the clean-vs-shock
rank correlation interval spans zero, the inversion is not established by the
run, and neither ranking should be treated as settled. Name a model explicitly
if you have a reason to.

## What is out of scope

- **Where** crowding occurs. Footfall counts people entering; it says nothing
  about density at any point on the track.
- **Undeclared shocks.** The switching model reacts to a break only once it
  appears in observed data. A disruption starting after the last observed month
  is in none of these numbers.
- **Anything about individuals.** This is aggregate monthly counts throughout.

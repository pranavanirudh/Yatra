# Site 2: what it has to provide, and why

**Status: preparation only. No data has been collected, and none should be until
this document has been read and a candidate chosen.**

Every claim below about a specific shrine's data is marked **[UNVERIFIED]**.
Nothing here has been checked against a publisher in preparing this document.
The numbers about *this* project are computed from `results/metrics.csv` and are
not marked, because they are.

---

## 1. Why a second site, and why not for the reason we first thought

The original argument for a second site was **calendar contrast** — a shrine on a
different festival cycle would test whether the calendar layer generalises.

That is no longer the binding reason. The calendar ablation came back roughly
null: adding computed festival regressors changes mean MASE by −0.018 on clean
months and +0.053 on shock months, and only one of the six pair-and-regime
comparisons in the ablation table clears the bootstrap's declared 95% level. A
second site would measure a second null more precisely. That is worth something,
but it is not worth a data-collection programme.

**The binding constraint is shock sample size.** The whole finding — that model
rankings invert between ordinary and disrupted months — rests on **162 disrupted
forecasts per model, from 27 disrupted months, at one shrine.**

## 2. The number that sets the criteria

Our disrupted evidence is not just small. It is concentrated:

| Window | Disrupted months | Forecasts per model | Share of shock evidence |
|---|---:|---:|---:|
| `covid_closure` | 8 | 48 | 29.6% |
| `covid_recovery_post_delta` | 6 | 36 | 22.2% |
| `covid_recovery_pre_delta` | 5 | 30 | 18.5% |
| `delta_wave` | 3 | 18 | 11.1% |
| `floods_2025` | 5 | 30 | 18.5% |
| **Total** | **27** | **162** | |

**81.5% of everything we know about forecasting through disruption is one
pandemic.** The remaining 18.5% is a single compound event in a single year at
the same shrine.

This is the fact that sets every criterion below. A second site whose only
disruption is COVID would add forecasts but would not add an *independent*
disruption: it would be a second measurement of how models behave during the
same worldwide event, correlated with ours through the cause itself. The
apparent sample would roughly double while the number of independent shocks
stayed at two. That is the failure mode this document exists to prevent —
replication that looks like replication and is not.

## 3. Hard criteria

A candidate must satisfy all four. These are not preferences.

### C1. Monthly resolution, published as counts

The unit of this project is a month. A site publishing only annual totals cannot
enter, and one publishing daily counts is fine provided the daily series can be
summed to months **without gaps** — a daily archive with missing days silently
becomes a monthly series that is wrong by an unknown amount, which is worse than
one that is absent.

### C2. Enough history *before* the disruption, not just enough history

"At least 10 years" is the training floor, not the total requirement, and the
distinction decides whether a site is usable at all.

The backtest requires `min_train_months: 120` and scores horizons 1–6, so:

```
origins = observations − 120 − 6 + 1
```

For this project: 487 − 120 − 6 + 1 = 362 origins. A site with exactly ten years
of history yields **zero** scoreable origins.

What actually matters is that **the disruption falls at least 126 months after
the series begins**, because a disrupted month before that point cannot be a
forecast target and contributes nothing. A site with a 2013 shock therefore needs
its record to begin no later than about 2002.

### C3. At least one major disruption that is not COVID

The criterion the other three exist to serve. "Major" means, concretely:

- a fall of the order this project treats as unambiguous — the declared windows
  contain months at −100%, −94% and −73% year-on-year — not a soft dip. The
  `article_370` candidate was rejected at −12.8% fading to −0.4% in two months,
  and that rejection is the standard;
- **at least 5 disrupted months**, which is what it takes to match the 30
  non-COVID forecasts we currently have (5 months × 6 horizons). Fewer than that
  and the second site contributes less independent evidence than the one event
  we already have;
- a cause with **no common driver** with ours. A second Himalayan shrine closed
  by the same 2013 monsoon system as a third would not be independent of it.

A site that also has COVID months is not disqualified — COVID months are still
evidence, and more of them narrows the intervals. The requirement is that COVID
is *not the only* disruption.

### C4. A published, citable source for the counts and for every shock window

Same contract as this project: `regimes.py` raises on a window without
publisher, title, URL and access date. A site whose disruption is well known but
whose dates cannot be cited to a source cannot have a declared window, and
without a declared window its disrupted months are unusable — they would be
scored as clean, which is worse than not having them.

## 4. What disqualifies a site outright

- **Seasonal closure.** A shrine that closes for part of every year produces
  structural zeros that are not disruptions. They would either have to be
  declared as shocks — flooding the shock bucket with routine months and
  destroying the comparison — or left as clean zeros, which makes the clean
  regime unrecognisable. They also make multiplicative seasonality undefined at
  *every* origin rather than only after 2020, so the applicability finding this
  project reports would become trivially true rather than informative.
- **Reconstructed or interpolated history.** If a publisher has filled its own
  gaps, the series carries invented observations and cannot enter under
  constraint 1. This must be asked about explicitly; it is rarely volunteered.
- **A revision policy that rewrites past months.** If figures are restated, the
  series is not a fixed record and a backtest run twice gives two answers.

## 5. Candidates

**Everything in this section is [UNVERIFIED].** These are starting points for
checking, not findings. No page was fetched, no archive was opened, and no
publication claim below has been confirmed.

| Candidate | C1 monthly | C2 history | C3 non-COVID shock | C4 citable | Verdict |
|---|---|---|---|---|---|
| Tirumala (TTD) | [UNVERIFIED] | [UNVERIFIED] | **[UNVERIFIED] — the open question** | [UNVERIFIED] | check first |
| Kedarnath | [UNVERIFIED] | [UNVERIFIED] | 2013 floods, [UNVERIFIED] | [UNVERIFIED] | check, but see the closure problem |
| Sabarimala | n/a | n/a | n/a | n/a | **structurally disqualified** |

### Tirumala — Tirumala Tirupati Devasthanams

**What is believed, unverified.** TTD publishes pilgrim and darshan counts, and
does so at daily granularity. The scale is the largest of any candidate, which
matters because a larger series makes a given proportional fall easier to
distinguish from noise.

**What is unknown and must be checked, in this order:**

1. How far back the archive actually goes, and whether the early years are
   retrievable in the same form as the recent ones. "Daily archive" is
   [UNVERIFIED] as to *extent* — a two-year rolling window would fail C2
   outright.
2. Whether the daily series is complete. Summing a daily archive with missing
   days into months is the specific failure C1 warns about.
3. **Whether any non-COVID disruption exists at all.** This is the decisive
   question and the reason to check Tirumala first: it is the strongest
   candidate on every criterion except the one that matters most. If its only
   major disruption is 2020, it fails C3 and adds correlated evidence — the
   exact thing section 2 warns against — despite being the best data source.

### Kedarnath

**What is believed, unverified.** The 2013 North India floods devastated the
town and suspended the yatra. That is a genuinely independent shock: a different
cause, a different decade, and no common driver with either COVID or the 2025
J&K events.

**The problem, which is structural and may be fatal.** Kedarnath is [UNVERIFIED]
believed to close for winter — roughly November to April — reopening on dates
set each year by the temple committee. If so, it falls under section 4's first
disqualifier: roughly half of every year is a structural zero rather than a
disruption. That is not a data-quality issue that better sourcing fixes; it is a
different forecasting problem.

Two things follow, and both should be settled before any collection:

- If the closure months are genuinely zero, the site is disqualified on the same
  grounds as Sabarimala, and the 2013 shock is unusable however well documented.
- If the closure is partial, or if figures are published only for the open
  season, then the series is a *seasonal-window* series and would need a
  different contract than the one in `docs/data_schema.md`. That is a larger
  change than adding a site.

**What must be checked:** whether monthly figures are published at all
[UNVERIFIED], what happens to the record in closed months, and whether the
record reaches back to ~2002 as C2 requires for a 2013 shock.

### Sabarimala — structurally disqualified

Sabarimala is [UNVERIFIED] believed to open only for defined pilgrimage periods
— the Mandalam–Makaravilakku season and short monthly pooja openings — rather
than continuously.

**Why that disqualifies it for this project specifically**, rather than merely
complicating it: in a monthly series, most months would carry no yatra at all.
The resulting seasonality would be an artefact of the *opening calendar*, not of
demand — the model would be learning when the doors are open, which is published
in advance and known with certainty, rather than how many people come. Every
seasonal model in the registry would score well for a reason that has nothing to
do with forecasting, and the clean/shock comparison would be run over a handful
of genuinely open months per year.

The applicability finding compounds it: with zeros in every year,
`holt_winters_mul` is undefined at every origin rather than only after a
closure, so the one result this project reports about method applicability would
become uninformative.

This is a judgement about fit, not about the site. Sabarimala is a serious
subject for a model built for it. It is not a second site for this one.

## 6. What to do next, in order

Nothing on this list involves collecting a series.

1. **Tirumala, C3 first.** Establish whether a non-COVID disruption exists before
   spending any effort on the archive. It is the criterion most likely to fail
   and the cheapest to check.
2. **Kedarnath, closure regime first.** Establish what the published record does
   in winter months. If they are zeros, stop — the 2013 shock does not rescue it.
3. Only for a candidate that survives both: check C2 by finding the first month
   in the record, and C1 by checking a sample of months for gaps.
4. Only then: identify citable sources for the shock windows, per C4.
5. Bring the result back here before any file is written into `data/`.

## 7. One thing this document cannot settle

Two sites give two independent disruptions plus COVID. That is enough to say
whether the inversion reproduces at all, and not enough to say what it depends
on — shrine size, disruption type, closure versus deterrence, or recovery shape.
If the inversion does reproduce at site 2, the honest next question is a third
site, and the criteria will be the same ones.

It is worth knowing that before starting, so that a positive result at site 2 is
not over-read.

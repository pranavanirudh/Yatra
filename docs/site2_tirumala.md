# Site 2: Tirumala (TTD) — preparation and assessment

Assessed 2026-08-24. **Nothing has been transcribed.** `data/raw/` is untouched
and stays that way until the owner confirms a span.

This supersedes the Tirumala verdict in [second_site.md](second_site.md), which
rejected it on the reasoning that its dominant disruption is COVID. That
reasoning still holds and is restated in §2 — what changed is the question being
asked of a second site, not the answer about its shocks.

---

## 1. Archive depth — measured, not estimated

**Two corrections to an earlier draft of this file, recorded rather than
silently fixed.** It said the site was blocked at the transport layer and that a
human with a browser would have to walk the month archives. Neither is true. The
TLS failure was in one fetch tool, not on the owner's machine, where the site
answers `200`. And `robots.txt` **allows** everything except `/wp-admin/`, and
advertises a sitemap:

```
User-agent: *
Disallow: /wp-admin/
Allow: /wp-admin/admin-ajax.php
Sitemap: https://news.tirumala.org/wp-sitemap.xml
```

So depth was measured directly, from 14 post sitemaps carrying **27,892 indexed
posts** with `lastmod` dates. Nothing was transcribed: what follows is a count
of posts and a reading of URL slugs.

### The answer: a consistent daily series runs 2020-06 to 2026-08

That is **75 months**, against this shrine's 487.

Daily statistics posts in the current convention carry the date *and the count*
in the slug:

```
/total-pilgrims-who-had-darshan-on-01-01-2025-69630/
```

There are 2,230 of them, at roughly 365 a year from 2021 onward — complete daily
coverage. Five months are short of a full complement (2020-06 has 6, 2020-07 has
18, 2023-01 has 16, 2025-11 has 20, and 2026-08 is the current month). A month
missing days is a partial month and must be recorded missing, not summed.

**The series begins inside the pandemic.** June 2020 is not a neutral start
date: it is the reopening. Tirumala would arrive with almost no pre-COVID clean
baseline, so its clean regime would be substantially post-recovery. For a
project whose claim is a contrast between clean and shock months, a second site
whose clean months are nearly all post-2021 is a weaker replication than the
month count alone suggests.

### Why the archive reaching 2013 does not extend the series

The oldest indexed post is dated 2013-10-03, and posts exist in every year from
2013. This is exactly the distinction flagged before the measurement — archive
depth is not series depth — and it resolves against the site.

Pre-2020 posts do carry counts, in a prose slug:

```
/about-32124-pilgrims-had-srivari-darshan-from-3am-to-6pm-on-october-24/
```

There are 1,809 such posts spanning 2013–2021. They are not usable as a series
without per-record adjudication, for three compounding reasons:

**The slug has no year.** The date is prose — `on-october-24`, `on-dec-31` — so
the year must come from `lastmod`, which is a *modification* timestamp and not a
publication date. The same month-day string recurs across years.

**Two different quantities are interleaved.** 855 posts state a window of
`3am-to-6pm`; **934 state no window at all**; a handful state `3am-to-7pm`,
`4am-to-10pm`, `2am-to-6pm`. The window is not fixed and is often absent.

**Most dates carry competing figures.** 570 date-keys have two or more posts
between them, covering 1,146 of the 1,809 — about 63%. The paired values are not
near-duplicates:

| Date key | Competing counts |
|---|---|
| 2013 `on-december-15` | 40,057 and 72,528 |
| 2013 `on-december-21` | 40,894 and 64,836 |
| 2013 `on-december-22` | 4,344 and 68,289 |
| 2014 `on-april-17` | 35,200 and 55,384 |

The pattern is consistent with one post reporting a partial day and the other
the full day. Choosing wrong roughly halves the series, and **934 posts do not
state which they are.** Extending Tirumala before 2020 is therefore not a
scraping problem that effort solves; it is an adjudication problem across
~1,800 records, most of which are ambiguous by construction.

### What this does to the design

`min_train` must differ by site — see §5 — and the gap is larger than the raw
month counts imply, because 75 months starting at a reopening contains fewer
usable clean origins than 75 months anywhere else would.

The annual-reconciliation objection is **unchanged and still unanswered**. A
series compiled from 2,230 individual posts has nothing independent to check it
against, and `docs/data_schema.md` requires exactly that. Measuring the depth
did not address it, and the depth being adequate would not have.

## 2. What site 2 tests, and what it does not

Written before any data arrives, deliberately, so the results cannot later be
read as closing a gap they do not close.

### It does NOT strengthen the non-COVID evidence

Tirumala's dominant disruption is COVID. This project already holds COVID in
four subdivided windows. Adding a second site whose major shock is the same
pandemic adds forecasts without adding an independent disruption.

**`floods_2025` remains the only non-COVID window in the study, and the
block-structure qualification stands unchanged.** Every "COVID-era windows
disagree with non-COVID ones" correlation is still one window compared
repeatedly. Site 2 does not move that, and no result from site 2 should be
described as though it did.

### It DOES test replication of the headline claim

The clean-versus-shock rank inversion is the headline, and it has never been
tested anywhere but here. Tirumala is a genuine independent test of it because
it differs in three ways that could plausibly break it:

- **Different counting methodology.** This shrine counts pilgrims entering.
  TTD publishes *darshan* counts — a different event in a different place, and
  a quantity that can be capped administratively in ways a gate count is not.
- **Different pilgrim population.** Different catchment, different travel
  distances, different seasonality of arrival.
- **A solar-anchored festival calendar rather than a lunar-anchored one.**
  This project's calendar layer computes lunar festivals whose civil dates drift
  by weeks across years, and `lunar_drift_days` is one of the features. A site
  whose principal observances are fixed differently is a real test of whether
  the calendar arm's contribution is about festivals or about this particular
  drift pattern.

If the inversion replicates across those three differences, that is worth
considerably more than a third COVID window. If it does not replicate, that is
worth more still, and it should be reported as loudly.

## 3. The January 2025 stampede — a candidate shock to check

**8 January 2025.** Six devotees killed and about forty injured at token
counters during distribution for the Vaikuntha Dwara Darshanam period. Reported
at multiple counters — Srinivasam, Bairagipatteda, Satyanarayanapuram — where
crowds formed the previous evening for counters opening at 5am.

Two outcomes, both useful, and **neither is to be assumed**:

- **It moved monthly footfall** → a non-COVID shock, landing in a peak month,
  which is structurally more interesting than a shock in a quiet one.
- **It did not** → a second negative control beside the 2022 Vaishno Devi
  stampede, which also killed pilgrims without disrupting the monthly series.

### What the press figures suggest, and why that is not the check

Indicative only, from reporting rather than from TTD's own tables:

- The Vaikuntha Dwara Darshanam period **proceeded as scheduled**, 10–19 January.
- Around 6.8 to 8 lakh devotees are reported for the January 2025 period,
  against about 6.47 lakh reported for the equivalent 2024 window.
- Single-day figures either side of the New Year are up year on year
  (01.01.2024 against 01.01.2025).

That points toward the **negative-control** outcome: a fatal incident at the
token counters that did not suppress, and possibly coincided with a rise in,
the month's throughput.

**It is not the check.** Those are festival-window figures from press coverage,
not monthly totals from the publisher, and the two are not interchangeable. The
check is January 2025 against January 2024 in the compiled monthly series, once
that series exists. Record the prediction now — negative control — so that
confirming it is a test rather than a rationalisation.

If it does turn out to be a second negative control, it is a valuable one. The
2022 stampede rejection in `shocks.yaml` argues that severity of an incident and
disruption of a monthly total are different quantities. One case makes that an
argument; two cases at different sites, with different crowd-management regimes,
makes it a pattern.

## 4. Structural notes to settle before collection

- **Counting basis.** Darshan counts, not gate entries. The question of whether
  the published figure is the same quantity throughout is now **answered, and
  the answer is no** — see §1. Before 2020 the archive interleaves a partial-day
  and a full-day figure without reliably labelling which is which. Within the
  2020-06 onward series the convention is stable, which is the main reason to
  treat that window as the series and the rest as background.
  A definitional change mid-series is a break no model should be asked to
  explain, and splicing the two eras would introduce one deliberately.
- **Annual reconciliation.** Still unsolved. `docs/data_schema.md` requires a
  published annual total that is an independent check, and TTD publishes none on
  its own site. A compiled series with nothing to reconcile against does not
  satisfy the contract, and this is the objection that must be answered before
  any transcription, not after.
- **Daily to monthly.** Rolling daily figures up to months requires every day of
  a month to be present. A month with missing days is a partial month and must
  be recorded missing, not summed and presented as complete.

## 5. Verdict: do not scrape. File a request instead.

**Recommendation, 2026-08-24: do not transcribe from the archive.** Not because
the depth is inadequate — 75 months is thin but workable — but because a
compiled series cannot satisfy the data contract, and the ways of making it
satisfy the contract are all worse than not having it.

### The blocking argument

`docs/data_schema.md` requires `annual.csv` to be a *published* annual total,
independent of the monthly series, because its whole job is to check it.
TTD publishes no annual figure: its own publications page carries none, and the
annual numbers in circulation come from press reporting.

That leaves three options and none is acceptable:

1. **Sum the scrape into `annual.csv`.** Then the check is the scrape checking
   itself, which confirms nothing while passing `make validate`. This is the
   quiet-plausible-output failure the whole project is built against.
2. **Use a press annual figure.** Genuinely independent, and unusable: press
   totals are rounded and approximate, so exact reconciliation fails and
   `ContractViolation` fires correctly. Making it pass means introducing a
   tolerance — a `strict=False` escape hatch in all but name, and §4 of
   CLAUDE.md says none of those exists here for a reason.
3. **Exempt the second site from reconciliation.** Then the two sites are held
   to different standards of evidence, and every cross-site comparison inherits
   that asymmetry silently.

Option 2 is the tempting one, because a press total *is* independent and would
land close. It is still wrong: the contract's value is that it has no dial. A
tolerance added to admit one site is a tolerance that admits everything after.

### What to do instead

**File an RTI request with TTD.** It is drafted at
[data_request_tirumala.md](data_request_tirumala.md), on the same reasoning as
[data_request_kedarnath.md](data_request_kedarnath.md). A reply
carrying both month-wise figures *and* separately-compiled annual totals
satisfies the contract exactly, and an RTI reference number is a stronger
citation than 2,230 individual URLs.

Ask TTD for the four things that document asks for, plus two specific to what
the archive measurement turned up:

- **The measurement window.** Whether the published daily figure is a full-day
  count or a fixed-hours count, and on what dates that definition changed. The
  archive shows `3am-to-6pm`, `3am-to-7pm`, `4am-to-7pm` and no window at all,
  which is either several definitions or one definition inconsistently stated.
- **The pre-2020 duplicates.** Whether the two figures published for many dates
  before 2020 are a partial-day and a full-day count, and which is which.
  A single sentence in reply would make roughly 1,800 records interpretable that
  are otherwise not.

Filing this costs a stamp and a statutory wait. Scraping costs days of work and
produces a series the pipeline should refuse — and would refuse, correctly.

### If the request fails

Then Tirumala is rejected on the same ground as the candidates in
[second_site.md](second_site.md), and it is rejected for a better-documented
reason than any of them. Recording that is worth more than a series nobody can
verify: it establishes that the obstacle to a second Indian pilgrimage site is
publication practice rather than absence of data, across four administering
bodies now rather than three.

## 6. Asymmetry discipline

If the sites have different training depths — and they will — the following are
obligations, not preferences.

1. **`min_train` differing by site is documented in the README**, not left in
   config for a reader to discover. A reader comparing two sites is entitled to
   know they were not given the same run-up.
2. **Per-site origin counts appear wherever a site comparison appears.** Every
   table, every figure caption. A rank from ninety origins and a rank from four
   hundred are not the same evidence and must not be printed as though they are.
3. **The two sites are never pooled into a single averaged number.** Not a
   combined leaderboard, not a mean MASE across sites, not a single rank
   correlation over both. This project exists to argue that averaging across
   heterogeneous regimes produces a number describing none of them; doing it
   across heterogeneous *sites* would be the same error, committed by the people
   who documented it.

Rule 3 is the one most likely to be violated by accident, because a combined
table is the natural thing to reach for when presenting two sites at once. There
is no version of it that is acceptable here.

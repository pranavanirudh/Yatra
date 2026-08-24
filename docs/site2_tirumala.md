# Site 2: Tirumala (TTD) — preparation and assessment

Assessed 2026-08-24. **Nothing has been transcribed.** `data/raw/` is untouched
and stays that way until the owner confirms a span.

This supersedes the Tirumala verdict in [second_site.md](second_site.md), which
rejected it on the reasoning that its dominant disruption is COVID. That
reasoning still holds and is restated in §2 — what changed is the question being
asked of a second site, not the answer about its shocks.

---

## 1. Archive depth — the number that decides viability

**Established:** the daily statistics are published as individual posts on
`news.tirumala.org`, and the site exposes **WordPress-style month archives** at
`/YYYY/MM/`. A December 2019 archive page is indexed and reachable.
Search indexing also surfaces category archives referencing 2016–2018.

**Not established, and this is the one that matters:** whether the *daily
darshan statistics series* runs as far back as the site's general news does.
Those are different questions. A news site can carry press releases from 2016
while the daily figures began later, and only the second is a series.

**Blocked at the transport layer.** `news.tirumala.org` fails TLS certificate
verification from this environment — automated fetching does not get as far as
`robots.txt`. Archive.org is likewise unreachable from here, so the usual
fallback for establishing depth is closed too.

### What a human with a browser must establish

Walk the month archives backwards and record, for each month, whether a daily
statistics post exists:

```
https://news.tirumala.org/2019/12/
https://news.tirumala.org/2019/11/
...
```

Stop at the first month with no daily figures. That month, minus one, is the
start of the usable series. Record it before anything else is planned.

### Why the answer changes the design

| If the series starts | Usable months to 2026-08 | Consequence |
|---|---:|---|
| 2016-01 | ~128 | Two full seasonal cycles of training before the first origin is still tight but workable |
| 2019-01 | ~92 | COVID sits close to the start; few clean months precede it |
| 2021-01 | ~68 | Barely any pre-COVID baseline; the clean regime is mostly recovery |

Against this shrine's 487 months, every one of those is short. **`min_train`
will have to differ by site**, and that asymmetry is a reporting obligation
rather than a config detail — see §5.

### One piece of good news for collection

The daily figure is carried **in the post title and in the URL slug**:

```
/total-pilgrims-who-had-darshan-on-01-01-2025-69630/
```

So the date and the count are both readable without opening the page. That
makes an index of month-archive links sufficient to build the series, and makes
a human pass far cheaper than reading several thousand articles. It does not
change the citation problem: each value still carries its own URL, and there is
still no published annual total to reconcile a compiled series against — which
is the objection recorded in [second_site.md](second_site.md) §2 and remains
unanswered.

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

- **Counting basis.** Darshan counts, not gate entries. Establish whether the
  published figure is the same quantity throughout the archive, and whether it
  changed when caps or virtual-queue systems were introduced. A definitional
  change mid-series is a break that no model should be asked to explain.
- **Annual reconciliation.** Still unsolved. `docs/data_schema.md` requires a
  published annual total that is an independent check, and TTD publishes none on
  its own site. A compiled series with nothing to reconcile against does not
  satisfy the contract, and this is the objection that must be answered before
  any transcription, not after.
- **Daily to monthly.** Rolling daily figures up to months requires every day of
  a month to be present. A month with missing days is a partial month and must
  be recorded missing, not summed and presented as complete.

## 5. Asymmetry discipline

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

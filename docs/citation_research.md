# Citation research for the declared shock windows

Searched 2026-08-24. This file is **candidate evidence, not verification.**

`verified: true` in `experiments/configs/shocks.yaml` records that *the project
owner* checked a window against its source. Nothing in this file sets that flag
and nothing here should be read as setting it. What it does is supply URLs the
owner can check, and say plainly which boundaries it failed to find evidence
for — because a search that turns up nothing is a result about the boundary, and
the file's existing note is right that marking a judgement verified would
launder it into a citation.

Every URL below was **opened and read**, not taken from a search summary. Where
a quotation appears it is from the page itself.

---

## 1. What was already missing, and is now found

### `floods_2025` — resumption date, official source

The config records: *"the owner verified this window against Rising Kashmir
(27 Aug 2025) and Deccan Herald / PTI (17 Sep 2025). No URL for either is on
record, and a citation requires one."*

A URL for the resumption now exists, and from a stronger publisher than the one
named — Prasar Bharati's news service, which is the state broadcaster:

> **Akashvani / NewsOnAir**, "Vaishno Devi Yatra resumes after 22-day suspension
> due to landslides", published 17 September 2025.
> https://www.newsonair.gov.in/vaishno-devi-yatra-resumes-after-22-day-suspension-due-to-landslides

Read 2026-08-24. It states:

> "the Vaishno Devi Yatra atop Trikuta Hill in Reasi district has resumed today
> after remaining suspended for 22 consecutive days due to bad weather
> conditions and frequent landslides"

> "The Yatra was stopped on August 26 after a massive landslide on the yatra
> route due to heavy rains at Adhkuwari, which claimed multiple lives."

This carries three of the rationale's claims at once: the 26 August start, the
22-day halt, and the 17 September resumption.

**It does not carry the death toll.** The rationale states 34 and explains at
length why 34 rather than 30, 32 or 35. This article says only "multiple lives".
Nothing in the project computes from the figure, but it is still uncited by this
source and a different one is needed if it is to be carried.

### `floods_2025` — the Rising Kashmir piece, partially

A Rising Kashmir article on the resumption exists —
https://risingkashmir.com/vaishno-devi-yatra-resumes-after-22-days-pilgrims-say-we-had-been-waiting/
— but it covers the **resumption**, not the 27 August landslide report the
config names. The landslide piece from that publisher was not located. Do not
record this URL as though it were the one the owner checked; they are different
articles.

## 2. A boundary that turns out to be evidenced

### `covid_recovery_pre_delta` — its start date is an administrative fact

This window runs 2020-11 to 2021-03 and is marked `verified: false`. The file's
reasoning for that is that the recovery boundaries "are this project's judgement
and have not been checked against anything".

**That is true of the end date. It is not true of the start date.**

> **The Tribune**, "15 thousand devotees to be allowed to offer prayers at
> Vaishnodevi temple from November 1", published 30 October 2020.
> https://www.tribuneindia.com/news/j-k/15-thousand-devotees-to-be-allowed-to-offer-prayers-at-vaishnodevi-temple-from-november-1-163393

Read 2026-08-24. It quotes the order directly:

> "the upper limit for permissible number of pilgrims to SMVD Shrine, Katra,
> shall be 15000, w.e.f. 01.11.2020"

> "Earlier, only 7,000 pilgrims were allowed to visit the shrine due to COVID-19
> restrictions."

So 2020-11 is not an arbitrary cut. It is the month a published administrative
order more than doubled the throughput ceiling, from 7,000 to 15,000 a day. The
window boundary coincides with a documented change in the constraint that was
suppressing the series.

**This is offered to the owner, not applied.** It evidences *one edge of one
window*. Whether that is enough to move a `verified` flag is the owner's call,
and the flag is per-window, so a window with one documented edge and one
judgement edge is not obviously "verified".

## 3. Detail that corroborates what is already written

The `covid_closure` rationale states the reopening cap as "2,000 per day of whom
only 100 could come from outside J&K". Reporting from the reopening confirms
this and adds the complementary figure: of the 2,000, **1,900 were reserved for
J&K residents** and 100 for everyone else. Three weeks later the outside-J&K
quota was raised to 500.

The intermediate cap of 7,000 a day, quoted above, sits between the 2,000 of
August 2020 and the 15,000 of November 2020, so the rationale's "caps relaxed in
stages" is a fair description of a documented sequence rather than a gloss.

## 4. What was searched for and not found

Recorded because a failed search is evidence about the boundary.

### `delta_wave` (2021-04 to 2021-06) — no boundary evidence found

No reporting was located on yatra-specific restrictions, suspensions or cap
changes at this shrine during the second wave. The collapse is unambiguous in
the observations — May 2021 at 45,155 against April's 321,735 — but the
*window edges* rest on the series, not on a published measure.

This matters more than it might look. Every other window in the file is anchored
to something announced: a suspension, a reopening, a cap order, a landslide.
This one is anchored to the shape of the data. That is a different kind of
declaration and arguably a weaker one, since it risks drawing the boundary
where the model would most like it to be.

### `covid_recovery_post_delta` (2021-07 to 2021-12) — unchanged

Nothing found bearing on the end date. The config already calls this "the most
arguable boundary in this file" and that assessment stands unaltered. This is
the boundary `shocks_refined.yaml` moves, and the sensitivity arm exists for it.

## 5. Something the record does not currently contain

Reporting from October 2025 describes a further **three-day suspension** of the
yatra for weather —
https://www.newsonair.gov.in/shri-mata-vaishno-devi-yatra-resumes-after-3-day-suspension-due-to-weather
(not read in full; listed here as a lead, not as evidence).

`shocks.yaml` ends `floods_2025` at 2025-09, and `shocks_refined.yaml` extends
it to 2025-10. If that October suspension is real and material, it bears on
which of the two boundaries is better drawn. Worth checking before the next time
the windows are revised.

## 6. Honest limits of this search

Six searches and four page fetches on 2026-08-24. Not exhaustive. Unexplored:
SMVDSB press releases and circulars, J&K government orders and disaster
management bulletins, PTI's own archive, and newspaper archives behind
paywalls — which is where announcements of the 2021 restrictions would most
likely sit if they exist.

A negative result from a search this size is not proof that a boundary is
undocumented. It is a reason to record what was looked for.

# A second site: what was looked for, and why none was added

Scoped 2026-08-22, at the owner's request, after the question was raised of
whether this project could cover Tirupati, Sabarimala, Velankanni,
Tiruvannamalai, or footfall by district rather than one shrine.

> **The Tirumala verdict below was later reversed.** This file rejected it;
> [site2_tirumala.md](site2_tirumala.md) is the live second-site decision and
> explains what changed — the question being asked of a second site, not the
> answer about its shocks. Everything else here stands. See
> [README.md](README.md) for the status of every document in this folder.

**No second site was added.** This file records what was searched and why each
candidate failed, for the same reason `experiments/configs/shocks.yaml` keeps
its rejected windows: without the record, a later reader cannot tell a site that
was never considered from one that was examined and declined. The second kind is
evidence; the first is an omission.

---

**Status, as of this file's own scoping.** Four candidates are rejected. One —
**Kedarnath** — is open, pending a data request, and is the only one whose
disruptions are not the pandemic. That distinction became the deciding criterion
after the per-window analysis showed this project's non-COVID evidence is a
single window; see section 1.

**Status now.** **Tirumala** is site 2, reversing the verdict this file records
for it; see [site2_tirumala.md](site2_tirumala.md). **Kedarnath** remains open on
exactly the terms below — its figures would need requesting, and the
seasonal-zero problem is a decision about the modelling frame that no data
settles. The other three rejections stand. Nothing has been collected and
`data/raw/` is untouched.

## 1. Why a second site is the right thing to want

The headline finding rests on 162 disrupted forecasts from one shrine. The
README says outright what would justify building on it: *more disrupted months,
from a site whose disruptions are not these ones*. The standing objection to the
work is "is this Vaishno Devi, or is this forecasting?", and no amount of extra
depth at Katra can answer it. Only a second site can.

So this was scoped seriously, and the conclusion is not that the idea is wrong.
It is that the data does not exist in a form this project's contract will
accept.

**Contrast matters more than count.** Three shrines that all closed for COVID is
close to one observation repeated three times, because their disruptions are the
same disruption. What would actually test the finding is a site whose shocks are
*unlike* these — a cancelled season, a different security situation, a shock
with a different shape. That criterion is what the candidates below were
measured against, not simply "is there a number somewhere".

**And the criterion sharpened after the per-window analysis.** That section
established that of five declared windows, four are COVID subdivisions and one
is not, so every COVID-versus-other contrast in this project rests on a single
window. The binding shortage is therefore specific: not disrupted months, and
not sites, but **a disruption unrelated to the pandemic**. A second site whose
own dominant shock is COVID would add rows to the panel without touching that
shortage. This is why Kedarnath was scoped after the others and why it ranks
above Tirumala despite Tirumala having far better data.

## 2. The test that decides it

Not availability. **Verifiability.**

`docs/data_schema.md` requires `data/raw/annual.csv` to come from a *published
annual total*, never from summing the monthly file, because its entire job is to
be an **independent check** on the monthly series. `contract.py` enforces the
reconciliation and `make validate` refuses to proceed without it.

That requirement is what disqualifies every candidate below, and it is worth
stating plainly: a series assembled by scraping has nothing independent to
reconcile against. Summing a scrape to check the same scrape is not a check. It
would pass `validate` while confirming nothing, which is precisely the class of
quiet, plausible output this project is built against.

Shri Mata Vaishno Devi passes because the shrine board publishes **both**: a
month-wise matrix from 1986 and the annual totals beside it, on the same page.
That turns out to be rare.

## 3. Candidates examined

### Kedarnath (BKTC / UTDB) — scoped 2026-08-24, and the strongest candidate

Scoped after the others, and deliberately: the per-window section had by then
shown that this project's only non-COVID shock is a single window, so what it
needs is not more disrupted months but a disruption **unrelated to COVID**.
Kedarnath has two, and neither involves the pandemic:

- The **2013 floods**. Roughly 312,000 pilgrims in 2013 against roughly 41,000
  in 2014 — an ~87% collapse with a multi-year recovery.
- The **31 July 2024 disaster**, which halted the yatra from 1 to 10 August.
  August 2024 records roughly 7,400 pilgrims.

On shock structure it is the best candidate examined. It fails on two other
things, and the second is the more interesting one.

**No official body publishes a month-wise series.** Checked: the
[UTDB registration portal](https://registrationandtouristcare.uk.gov.in/),
which is transactional and carries no statistics section; BKTC's own web
presence; and the Uttarakhand statistical handbooks. Figures reach the press
daily through the season, so the data plainly exists internally — it is simply
not published as a series. What is available is year-wise totals from
[a secondary aggregator](https://www.sacredyatra.com/kedarnath-pilgrim-stats.html)
covering 1990 to 2024 with **no citations given**, a paywalled and derived
[Statista](https://www.statista.com/statistics/1360201/india-number-of-tourist-visits-of-kedarnath/)
series, and a one-off
[SDC Foundation](https://www.sdcuk.in/sdc-releases-report-on-char-dham-yatra-2024/)
report on the 2024 season which quotes one monthly figure in passing, states no
source, and is not an annual series.

**The temple is shut for half of every year, and that is the deeper problem.**
Kedarnath opens near Akshaya Tritiya in April or May and closes on Bhai Dooj in
October or November; the deity moves to Ukhimath for the winter. A monthly
series therefore carries roughly six **deterministic** zeros a year, every year.

That is a different object from the zeros in this project's own record, and the
difference is the whole reason this site cannot simply be added:

- Vaishno Devi's zero months are an **unpredicted shock**, which is the thing
  under study. Kedarnath's are **calendar-determined and known in advance**.
- Half of every year becomes perfectly predictable from a calendar rule, so
  every error metric deflates and a model can place well largely by knowing the
  temple is shut.
- **It breaks the one-denominator rule.** The MASE scale is in-sample
  seasonal-naive error over the training window (CLAUDE.md 3.2). Computed on a
  series dominated by structural zeros it is not the same scale as this
  shrine's, so the two sites' MASEs would not be comparable — and that
  comparability is what the entire design rests on.
- The effective sample is about six months a year, not twelve.

This is Sabarimala's problem again, milder — six months open rather than two —
and it is not fixed by better sourcing. Obtaining the monthly figures would
solve availability and leave this untouched.

**Not rejected outright, unlike the candidates below.** The month-wise figures
exist and are held by public authorities, so an RTI request would make them both
published and citable, which is exactly what the contract needs.
[docs/data_request_kedarnath.md](data_request_kedarnath.md) is the drafted
request. What it cannot resolve is the seasonal-zero problem, and a decision to
add this site has to answer that separately — probably by modelling the open
season rather than the calendar year, which is a change to the frame and not a
change to the data.

### Tirumala / Tirupati (TTD) — rejected here, and later chosen as site 2

**This verdict no longer holds.** Tirumala is site 2; the assessment that
reversed it is [site2_tirumala.md](site2_tirumala.md), which measured the archive
rather than estimating it and re-weighed what a second site is *for*. The
reasoning below is kept because it is still correct about Tirumala's shocks —
what it got wrong was treating non-pandemic shock evidence as the only thing a
second site could contribute, when replication of the headline inversion across
a different counting basis and a different pilgrim population is worth more. The
paragraph as originally written follows.

**Superseded by Kedarnath above**, on the reasoning in section 1: Tirumala's
dominant disruption is COVID, which this project already holds in four
subdivisions. Adding it would add forecasts without adding the one thing the
record is short of, which is a shock that is not the pandemic.

It remains the most promising on *resolution*, because TTD publishes at **daily**
resolution — finer
than anything here — including pilgrim counts, tonsures and hundi collections.
Daily data would also address this project's largest stated limitation, that a
monthly series cannot see a peak-day crush.

It fails on form, not on substance:

- The daily figures are published as **one news post per day** on
  [news.tirumala.org](https://news.tirumala.org/), not as a consolidated table.
  A series means scraping a news archive day by day, and every value carries its
  own citation rather than sharing one.
- The **official TTD site publishes no statistics section at all** — no annual
  reports, no historical figures, no downloadable data. Checked
  [tirumala.org](https://www.tirumala.org/) across every primary menu section.
- Annual totals appear only scattered through press reporting — 2.66 crore for
  2015 and 2.73 crore for 2016, via
  [The News Minute](https://www.thenewsminute.com/article/273-crore-visitors-2016-tirumala-temple-sees-pilgrim-footfall-rise-55365)
  — not as a maintained published table.
- Two practical obstacles at the time of scoping: `news.tirumala.org` fails TLS
  certificate verification, and the third-party aggregator `ttdstats.com` no
  longer resolves.
- [Statista](https://www.statista.com/statistics/1362966/tirumala-tirupati-devasthanams-number-of-daily-pilgrims/)
  carries 2022–2024 daily figures, but paywalled and derived. A derived source
  cannot be the independent check on a scrape of the source it derives from.

**Decisive point:** with no published annual table, a scraped Tirupati monthly
series would have nothing to reconcile against. It would be a number this
project could not verify, presented beside numbers it can.

### Sabarimala (Travancore Devaswom Board) — rejected, twice over

Figures are reported **per season** through press releases rather than as a
maintained series: a season total, sometimes split into Mandala and
Makaravilakku, occasionally with forest-route counts
([Deshabhimani](https://english.deshabhimani.com/deshabhimani-english-/kerala-news/sabarimala-records-429-crore-revenue-51-lakh-pilgrims-03521),
[Onmanorama](https://www.onmanorama.com/news/kerala/2025/12/14/sabarimala-pilgrimage-forest-routes.html)).

Turning a season total into months would require **apportioning it across
them**, which is imputation. Constraint 1 forbids that outright, and it is not a
technicality here: the apportionment would encode an assumption about the
within-season shape, and the models would then be scored on that assumption.

There is a second, independent problem. The pilgrimage runs a roughly two-month
season, so a monthly series is mostly zeros by construction. The seasonal models
in this registry — SARIMA and Holt-Winters at m=12 — are not estimating the same
kind of object on a series like that, and `holt_winters_mul` is already
unfittable here for a milder version of exactly that reason.

### Tamil Nadu shrines: Tiruvannamalai, Velankanni — rejected

No published footfall statistics were found for either, from the HR&CE
department or elsewhere. Numbers surface in press reporting around specific
events — Girivalam on full-moon days, the Velankanni festival — but an
event-triggered figure in a newspaper is not a series, and the months nobody
wrote about would be missing rather than zero.

### Footfall by district — rejected, and this one is instructive

Kerala publishes exactly the shape of thing that was asked for: official,
month-wise, district-wise domestic tourist arrivals, with history reaching back
to the 1980s.

It cannot be used, and the reason is stated by the publisher. The
[Kerala State Planning Board](https://spb.kerala.gov.in/economic-review/ER2016/chapter09_03.php)
says of its own figures:

> destinations like Sabarimala and other temple/pilgrimage tourism points
> (Guruvayoor, Thiruvananthapuram, etc.) are **not included**

So district tourism data is a *different quantity* that resembles the one this
project forecasts. Substituting it would have produced a longer series, more
sites, better-looking coverage, and a comparison of two things that are not the
same thing. Nothing would have crashed.

That is the most useful rejection in this file, and it is the site-level
counterpart of the 2022 stampede window: the case where the tempting move is
available, looks like an improvement, and is wrong.

## 4. What would change the verdict

Any one of these, for any site:

- A **published annual total** to reconcile a monthly series against, from the
  administering body rather than from press coverage.
- A **maintained month-wise table**, in the way SMVDSB maintains one.
- A response to an **RTI request** carrying month-wise figures, which would be
  both published and citable.
- For Tirupati specifically: confirmation that the news archive extends far
  enough back and is uniformly parseable, **together with** an independent annual
  figure to check the roll-up against. The scrape alone is not enough, and that
  is the whole point.
- For Kedarnath specifically: a **reply to the data request**, carrying
  month-wise figures with per-season totals to reconcile them against. That
  settles availability. It does **not** settle the seasonal-zero problem, which
  is a separate decision about the modelling frame and is described in section 6.

## 5. Scope of this search, stated honestly

Roughly half a dozen web searches and a handful of page fetches on 2026-08-22,
and a further six searches and five fetches for Kedarnath on 2026-08-24. It is a
first pass, not an exhaustive hunt. Specifically unexplored: TTD annual reports
and board resolutions, Andhra Pradesh and Uttarakhand state open data, state
statistical abstracts, and — until the drafted request is sent — any of the
administering bodies contacted directly.

A negative result from a limited search is a reason to record the search, not to
claim the data does not exist. It may well exist somewhere this did not look.

**Numbers quoted in section 3 are indicative, not verified.** The Kedarnath
year-wise figures come from an aggregator that cites no source. They are quoted
to describe the shape of a disruption, and nothing in this repository computes
from them. None of them has been transcribed into `data/`, and none may be until
a citable source is in hand.

## 6. Where that leaves the project

Single-site for now, deliberately, with the reason on record rather than by
default — and with one candidate open rather than none.

**The Kedarnath decision has two parts, and they should not be confused.**
Getting the data is a sourcing problem with a known route: the request in
[docs/data_request_kedarnath.md](data_request_kedarnath.md). Using it is a
modelling problem that no amount of data solves, because six deterministic zeros
a year is a property of the pilgrimage and not of the record-keeping.

If the figures arrive, the frame has to be decided before anything is scored:

- **Model the open season, not the calendar year.** Drop the closed months
  rather than scoring them, and treat the series as roughly six observations a
  year. Honest, and it means m=12 seasonality no longer describes it — so the
  registry, the MASE denominator and the origin set all need rethinking for that
  site.
- **Keep calendar months and carry the zeros.** Simpler, and it makes the two
  sites' MASE scales incomparable, which forfeits the one thing that makes a
  cross-site comparison mean anything.

Neither is free, and the first is a substantial change. That is the real cost of
a second site here, and it is worth knowing before the data arrives rather than
after.

The two directions that remain open are noted here so they are not rediscovered
from scratch:

- **Daily data for this shrine.** It would let the project speak to peak-day
  load, which is the thing the briefing currently has to refuse. This is the
  more *useful* direction and the less novel one — it is an application, not a
  finding.
- **Testing the method outside pilgrimage.** Monthly series with well-documented
  shocks are abundant and downloadable in other domains. That would test whether
  regime-separated evaluation matters in general, which is a stronger claim than
  three shrines that all shared one pandemic. It would also change what this
  project is, and that is the owner's call rather than a detail of
  implementation.

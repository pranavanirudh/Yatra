# A second site: what was looked for, and why none was added

Scoped 2026-08-22, at the owner's request, after the question was raised of
whether this project could cover Tirupati, Sabarimala, Velankanni,
Tiruvannamalai, or footfall by district rather than one shrine.

**No second site was added.** This file records what was searched and why each
candidate failed, for the same reason `experiments/configs/shocks.yaml` keeps
its rejected windows: without the record, a later reader cannot tell a site that
was never considered from one that was examined and declined. The second kind is
evidence; the first is an omission.

---

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

### Tirumala / Tirupati (TTD) — rejected, and it was the strongest candidate

The most promising by far, because TTD publishes at **daily** resolution — finer
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

## 5. Scope of this search, stated honestly

This was roughly half a dozen web searches and a handful of page fetches on
2026-08-22. It is a first pass, not an exhaustive hunt. Specifically unexplored:
TTD annual reports and board resolutions, Andhra Pradesh state open data, RTI
filings, state statistical abstracts, and any of the administering bodies
contacted directly.

A negative result from a limited search is a reason to record the search, not to
claim the data does not exist. It may well exist somewhere this did not look.

## 6. Where that leaves the project

Single-site, deliberately, and now with the reason on record rather than by
default.

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

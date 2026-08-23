# Data request: month-wise Kedarnath pilgrim figures

Drafted 2026-08-24. **Not yet sent.** Reasoning for wanting it is in
[second_site.md](second_site.md) section 3.

This is a template, not a filed application. Everything in `[SQUARE BRACKETS]`
is a placeholder the sender must fill in or verify — addresses, fee amounts and
the correct Public Information Officer are not invented here, because a request
sent to the wrong office is simply a request that gets no answer.

---

## Why the request is shaped the way it is

Four things are asked for, and each maps to something this project's data
contract will refuse to run without.

**Month-wise counts** — the series itself. Annual totals cannot be split into
months without imputing, and imputation is forbidden (brief §4).

**Per-season totals as separately published** — `docs/data_schema.md` requires
an annual figure that is an *independent* check on the monthly series, not a sum
of it. This is the requirement that disqualified every scraped candidate, so it
has to be asked for explicitly rather than derived.

**The counting definition** — a registration is not a darshan is not a gate
count. Vaishno Devi's series counts pilgrims entering. If Kedarnath's counts
online registrations, the two series are different quantities that both look
like footfall, which is the failure recorded against district tourism data in
`second_site.md`.

**Revision practice** — whether a published figure is later corrected. A series
that is silently revised cannot be reconciled twice and get the same answer, and
the contract check would fail for a reason that has nothing to do with the data
being wrong.

Ask for all four together. A reply with counts and no definition is not usable
here, and going back a second time costs another statutory cycle.

---

## Where to send it

Two authorities plausibly hold this, and they hold different parts of it.

- **Shri Badarinath Kedarnath Temple Committee (BKTC)** — administers the
  temple. Most likely to hold gate or darshan counts.
- **Uttarakhand Tourism Development Board (UTDB)** — runs the Char Dham
  registration system, so most likely to hold registration counts and any
  consolidated month-wise series.

Send to both. They are different quantities and the difference is itself worth
knowing; if the two replies disagree, that disagreement is information about
what each number means.

Filed under the **Right to Information Act, 2005**, addressed to the Public
Information Officer of each. Confirm the current Uttarakhand application fee and
the accepted payment mode before sending — it is a small prescribed sum, but the
amount and mode are set by state rules and change.

---

## Draft

> To,
> The Public Information Officer,
> `[AUTHORITY — Shri Badarinath Kedarnath Temple Committee / Uttarakhand Tourism Development Board]`
> `[FULL POSTAL ADDRESS]`
>
> **Subject:** Request for month-wise pilgrim figures for Shri Kedarnath Dham
> under the Right to Information Act, 2005
>
> Sir/Madam,
>
> I request the following information held by your office. Where a particular
> item is not held by you, I request that this be stated, and that the request
> be transferred to the appropriate public authority under Section 6(3).
>
> **1. Month-wise pilgrim figures.** The number of pilgrims recorded at Shri
> Kedarnath Dham for each calendar month of each yatra season, from the earliest
> year for which your office holds such records up to the most recently
> concluded season. Please provide these as they are recorded — I am not
> requesting any estimate, projection or apportionment of an annual figure
> across months, and would prefer the record to be left incomplete where it is
> incomplete.
>
> **2. Season totals as separately compiled.** The total pilgrim figure for each
> yatra season, for the same years, **as compiled or published by your office**
> rather than as a sum of the monthly figures in item 1. If the season total is
> in fact derived by summing the monthly figures, please state that this is so.
>
> **3. The basis of the count.** What each figure in items 1 and 2 counts —
> for example online yatra registrations, physical registrations, darshan
> tokens issued, biometric or gate counts at a specified point, or an estimate.
> If the basis has changed over the period covered, please state when it changed
> and what it changed from and to.
>
> **4. Revision practice.** Whether figures once published or supplied are
> subsequently revised, and if so, whether the version supplied in response to
> this request is the original or the latest revised figure.
>
> **5. Existing publications.** Whether any of the above is already published,
> and if so, a reference or link to where.
>
> I would prefer the information in a machine-readable format — a spreadsheet or
> CSV file, by email — but will accept any format in which it is held. I am
> willing to pay the prescribed fee and additional copying charges; please
> inform me of the amount and the mode of payment.
>
> `[NAME]`
> `[FULL POSTAL ADDRESS]`
> `[EMAIL]`
> `[PHONE]`
> `[DATE]`
>
> Enclosed: application fee of `[AMOUNT]` by `[MODE]`.

---

## When a reply arrives

Do **not** put it into `data/raw/` by hand. Nothing writes there except
`make ingest`, and that is the rule that keeps the observation set from changing
underneath a run scoring against it (CLAUDE.md §5).

The order is:

1. Record the reply as a source — authority, subject, date, reference number —
   the same way `data/raw/sources.yaml` records the shrine board's table. An RTI
   reference number is a stronger citation than a URL, and it should be kept.
2. `make ingest --inspect <file>` to see what arrived and to get a config
   template, then declare units and columns explicitly. Declare the unit even if
   it looks obviously absolute.
3. `make validate`, and expect it to have opinions. In particular the monthly
   series will have gaps where the temple was closed, and **whether those are
   zeros or missing months is a decision, not a detail.** A closed month is not
   an observation of zero pilgrims in the way April 2020 at Vaishno Devi was;
   the shrine was not open to be visited. Record it as missing unless the
   authority states it as zero.
4. Only then the frame question in `second_site.md` §6, which the data does not
   answer and which has to be settled before anything is scored.

Answer availability first. The seasonal-zero problem is unaffected by whether
this request succeeds, and succeeding at the request should not be mistaken for
having solved it.

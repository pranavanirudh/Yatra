# Data request: month-wise Tirumala pilgrim figures

Drafted 2026-08-24. **Not yet sent.** Why this is a request rather than a scrape
is in [site2_tirumala.md](site2_tirumala.md) §5; the shared reasoning about what
to ask for and why is in
[data_request_kedarnath.md](data_request_kedarnath.md) and is not repeated here.

Placeholders in `[SQUARE BRACKETS]` must be filled or verified before sending.
Addresses, fee amounts and the correct Public Information Officer are not
invented here.

---

## Why this one is asked rather than collected

TTD already publishes the daily figures, as one news post per day. They could be
compiled. They are not being compiled, for a reason that no amount of collecting
would fix: `docs/data_schema.md` requires a **published annual total** that
independently checks the monthly series, and TTD publishes none. A series
compiled from thousands of individual posts, checked against the sum of itself,
confirms nothing while passing validation — which is the failure this project
exists to prevent.

Two further questions come out of measuring the archive, and both are cheap for
the authority to answer and expensive for anyone else to resolve. They are items
5 and 6 below.

## Where to send it

Public Information Officer, **Tirumala Tirupati Devasthanams**, under the Right
to Information Act, 2005. Confirm the current Andhra Pradesh application fee and
accepted payment mode before sending.

## Draft

> To,
> The Public Information Officer,
> Tirumala Tirupati Devasthanams,
> `[FULL POSTAL ADDRESS]`
>
> **Subject:** Request for month-wise pilgrim figures for Sri Venkateswara Swamy
> Temple, Tirumala, under the Right to Information Act, 2005
>
> Sir/Madam,
>
> I request the following information held by your office. Where an item is not
> held by you, I request that this be stated, and that the request be transferred
> to the appropriate public authority under Section 6(3).
>
> **1. Month-wise pilgrim figures.** The number of pilgrims recorded at Tirumala
> for each calendar month, from the earliest year for which your office holds
> such records to the most recent completed month. Please provide these as they
> are recorded. I am not requesting any estimate or apportionment, and would
> prefer the record left incomplete where it is incomplete.
>
> **2. Annual totals as separately compiled.** The total pilgrim figure for each
> calendar year over the same period, **as compiled or published by your office**
> rather than as a sum of the monthly figures in item 1. If the annual figure is
> in fact produced by summing the monthly figures, please state that this is so.
>
> **3. The basis of the count.** What the figures in items 1 and 2 count — for
> example darshan completed, tokens issued, entries recorded at a specified
> point, or an estimate. If the basis has changed over the period covered, please
> state when, and what it changed from and to.
>
> **4. Revision practice.** Whether figures once published are subsequently
> revised, and whether the version supplied in response to this request is the
> original or the latest revised figure.
>
> **5. The measurement window for the published daily figures.** Your daily
> darshan statistics have at various times been published as covering "3am to
> 6pm", "3am to 7pm" and "4am to 7pm", and at other times with no window stated.
> Please state, for each period, whether the published figure is a full-day count
> or a count over stated hours, and the dates on which that definition changed.
>
> **6. Duplicate daily figures published before 2020.** For many dates before
> 2020 your office published two different pilgrim figures for what appears to be
> the same day — for example two figures for 15 December 2013, and two for 17
> April 2014. Please state what the two figures represent, and which of them is
> the full-day total.
>
> I would prefer the information in a machine-readable format — a spreadsheet or
> CSV file, by email — but will accept any format in which it is held. I am
> willing to pay the prescribed fee and copying charges; please inform me of the
> amount and mode of payment.
>
> `[NAME]`
> `[FULL POSTAL ADDRESS]`
> `[EMAIL]`
> `[PHONE]`
> `[DATE]`
>
> Enclosed: application fee of `[AMOUNT]` by `[MODE]`.

## Why items 5 and 6 are worth the postage on their own

Even a reply that refuses items 1 and 2 is worth having if it answers these.

The archive holds roughly **1,800 count-bearing posts from 2013 to 2021** that
cannot currently be read as a series. About half state a measurement window and
about half state none; most dates carry two competing figures, and the paired
values differ by amounts consistent with one being a partial day and the other a
full day. Nothing in the posts themselves resolves which is which.

**A single sentence from the authority makes those records interpretable.** It
would not by itself satisfy the reconciliation requirement — item 2 is what does
that — but it converts an unusable archive into a usable one, and no other
source can supply it.

## When a reply arrives

The order is the same as for the Kedarnath request: record the reply as a source
with its RTI reference number, run `make ingest --inspect`, declare units and
columns explicitly, then `make validate` and expect it to have opinions.

Two things specific to this site:

- **Daily to monthly.** A month is only complete if every day of it is present.
  A month missing days is recorded missing, not summed and presented as whole.
- **Do not splice eras.** If the reply confirms the pre-2020 figures are a
  different quantity from the post-2020 ones, they are two series and not one.
  Joining them would introduce a definitional break deliberately, which is the
  thing the contract exists to catch.

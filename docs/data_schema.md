# Data schema

Three files under `data/raw/`. None of them ship with this repository. The
pipeline raises `MissingObservations` and names the missing path rather than
proceeding — there is no sample, no fixture, and no generator.

---

## 1. `data/raw/monthly.csv`

One row per calendar month, contiguous, no gaps.

| column | type | notes |
|--------|------|-------|
| `month` | `YYYY-MM` | ISO year-month. Must sort ascending with no missing month between first and last. |
| `pilgrims` | integer ≥ 0 | Count of pilgrims registered for the month. Not a rate, not thousands, not lakhs — the raw count. |
| `source_id` | string | Foreign key into `sources.yaml`. |

```csv
month,pilgrims,source_id
1986-01,131000,smvdsb_annual_report_2001
1986-02,118000,smvdsb_annual_report_2001
```

**Unit discipline.** Published figures for this shrine are usually quoted in
lakh (10^5). Store the expanded integer. The contract has no way to detect a
column silently switched to lakh — every MASE would simply be computed on a
series 100,000× too small and nothing would crash. Convert at ingest, once, and
record the conversion in the source note.

## 2. `data/raw/annual.csv`

One row per complete calendar year. Its job is to be an independent check on
the monthly series, so it must come from a *published annual total*, not from
summing the monthly file.

| column | type | notes |
|--------|------|-------|
| `year` | integer | |
| `pilgrims` | integer ≥ 0 | As published. |
| `source_id` | string | Foreign key into `sources.yaml`. |

The contract asserts, for every year present in this file, that the sum of that
year's twelve monthly rows equals this total **exactly**. A mismatch raises
`ContractViolation` showing both numbers and the difference. Do not add a
tolerance. A year that genuinely does not reconcile is a finding about the
sources and belongs in the README, not in a fudge factor.

Partial years (the current one) belong in `monthly.csv` only. Do not put a
year-to-date figure in `annual.csv` — it would fail reconciliation for a reason
that has nothing to do with data quality.

## 3. `data/raw/sources.yaml`

```yaml
smvdsb_annual_report_2001:
  publisher: Shri Mata Vaishno Devi Shrine Board
  title: Annual Report 2000-01
  url: https://www.maavaishnodevi.org/...
  accessed: 2026-08-18
  note: >
    Table 4, "Yatra statistics". Figures published in lakh to two decimals;
    expanded to integers at ingest by multiplying by 100000.
```

Every `source_id` referenced by either CSV must resolve here, and every entry
needs `publisher`, `title`, and `accessed` at minimum. An unreferenced source
is fine; a dangling reference raises.

---

## What the contract checks

`make validate` runs all of these and stops at the first failure:

1. All three files exist.
2. `month` parses, sorts ascending, is unique, and is **contiguous** — every
   month between the first and the last is present. Reports the missing months
   by name, not just a count.
3. `pilgrims` is a non-negative integer in both files. No nulls.
4. Every `source_id` in either CSV resolves in `sources.yaml`.
5. Every year in `annual.csv` has exactly twelve monthly rows, and they sum to
   the published total exactly.
6. Reports the observation count and span so it can be compared against the
   figure quoted in the README.

Check 5 is the one worth having. It is the only check here that can catch a
transcription error inside an otherwise well-formed series — a digit dropped in
one month still leaves the file contiguous, correctly typed, and fully sourced.

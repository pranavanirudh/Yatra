# Crowd planning briefing

_Generated from `results/metrics.csv` and the observation series. Forecasting model: **sarimax_cal**. Last observed month: **2026-07**._

> **Read this first.** These are forecasts of pilgrims **per month**. They size the resourcing a month needs. They do **not** predict the load at any given hour, and a monthly total cannot identify a crush risk on a particular afternoon. The dated festival days in each row are where arrivals concentrate; treat those as the days requiring surge cover, and see the limitations section for what would be needed to put numbers on a single day.

## Forecast

| Month | Expected | Likely range (90%) | Per day (avg) | Festival days |
|---|---:|---:|---:|---|
| 2026-08 | 5.96 lakh | 3.66 lakh – 8.39 lakh | 19,211 | 2026-08-28 |
| 2026-09 | 4.86 lakh | 1.76 lakh – 7.89 lakh | 16,206 | — |
| 2026-10 | 6.38 lakh | 3.41 lakh – 9.61 lakh | 20,566 | 2026-10-11, 2026-10-12, 2026-10-13, 2026-10-14, 2026-10-15, 2026-10-16, 2026-10-17, 2026-10-18, 2026-10-19 |
| 2026-11 | 5.25 lakh | 1.85 lakh – 8.49 lakh | 17,487 | 2026-11-08 |
| 2026-12 | 5.62 lakh | 2.31 lakh – 9.00 lakh | 18,119 | — |
| 2027-01 | 5.76 lakh | 2.33 lakh – 9.20 lakh | 18,567 | — |

## If a disruption occurs

The range above is measured on **ordinary** months. Months inside a declared shock window behave differently, and the same model's error there is far wider. Plan the contingency to this, not to the range above.

| Month | Shock-regime range |
|---|---:|
| 2026-08 | 0 – 9.07 lakh |
| 2026-09 | 0 – 9.45 lakh |
| 2026-10 | 0 – 11.92 lakh |
| 2026-11 | 0 – 12.00 lakh |
| 2026-12 | 0 – 12.01 lakh |
| 2027-01 | 0 – 11.83 lakh |

**A lower bound of zero is a measurement here, not a placeholder.** For 2026-08, 2026-09, 2026-10, 2026-11, 2026-12, 2027-01 the shock-regime range reaches zero because the observed record contains months when this shrine was closed and the count was zero. The band is clamped at zero rather than going negative, but the floor itself is something that has happened, not a missing value.

## Resourcing

**No planning ratios are declared, so no resourcing was computed.** Add them under `planning.ratios` in `experiments/configs/operations.yaml` — for example, one marshal per N pilgrims per day. No defaults are supplied here on purpose: a ratio invented by this tool would appear in the table looking exactly like one grounded in site experience.

## What this cannot tell you

- **Peak-hour or peak-day load.** The series is monthly. Sizing a single day's barricading, queue geometry or medical cover needs daily (ideally hourly) arrival counts. Those are not in this project.
- **Where crowding happens.** Footfall is a count of people entering, not a density anywhere on the track. Chokepoints are a site-geometry question.
- **Anything about an undeclared shock.** The detector reacts to a break only after it appears in the observed data. A disruption beginning after the last observed month is not in any number here.

## Provenance

| | |
|---|---|
| Model | `sarimax_cal` |
| Last observed month | 2026-07 |
| Band | empirical, 90% of backtest errors |
| Clean-month errors used | 2010 |
| Shock-month errors used | 162 |
| Shock windows | `3e176f06087d` |

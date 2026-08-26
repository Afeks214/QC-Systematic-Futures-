# Macro Data Policy Matrix

Policy version: `lift1.dataset-use.v1`
Status of every row: **UNDER_REVIEW**
Reviewed: **2026-08-26**

These policies make future-data and revision risks explicit before any Alpha work.
They do not subscribe to, normalize, or certify a macro dataset. All source values
retain their source units; observation, publication, platform delivery, and retrieval
are separate clocks.

## Policy matrix

| Dataset | Observation semantics | Known publication semantics | Revision risk | Permitted use | Prohibited use | Missingness policy | Required future certification |
|---|---|---|---|---|---|---|---|
| BLS | Release-specific official observations; reference period and first release are distinct clocks | Schedules are series-specific; exact first-release and QC/platform delivery timing is not certified | Revisions and benchmark revisions require first-release or vintage history | Descriptive and risk-context research only | Forecast input, signal input, or silent revised history | Withhold absent releases; never forward-fill or replace with zero | Per-series release schedule, first-release history, revisions, delivery timing, DST, holidays, missing data, and corrections |
| U.S. Treasury Yield Curve | Official tenor observations identified by observation date separately from publication and delivery | Treasury says inputs are near 3:30 PM ET and rates are usually available by 6:00 PM ET each trading day, but can be delayed; QC/platform delivery is not certified | Corrections, methodology changes, and latest-history behavior require audit | Descriptive and risk-context research only | Forecast input, signal input, or silent revised history | Withhold absent dates/tenors; never interpolate or replace with zero | Source publication and platform delivery clocks, tenor schema, methodology/calendar version, holiday gaps, corrections, and revisions |
| FRED | Economic period, publication time, retrieval time, and real-time/vintage interval are distinct | Default API real-time bounds describe what is known today; historical as-known research requires explicit real-time/vintage parameters | Historical values and metadata may be revised; default latest history can leak later knowledge | Descriptive and risk-context research only | Forecast input, signal input, or silent latest vintage | Preserve missing values; no interpolation or zero substitution | Per-series release calendar, ALFRED/equivalent vintages, revisions, vendor delivery, holidays, and corrections |
| Economic Events | Scheduled event time, actual value, prior value, estimate, estimate vintage, and availability are separate observations | QC documents UTC event time and availability/end time for the EODHD feed, but historical schedule changes and estimate-as-known timing are not proven | Schedules, estimates, actuals, and prior values can change or be corrected | Calendar and risk-context research only | Historical surprise signal, signal input, or silent latest estimate | Unknown schedules/estimates remain missing; never infer or backfill | Schedule-as-known history, estimate vintages, actual release/delivery time, revisions, holidays, and corrections |

## Official-source support and limits

- [BLS release schedules](https://www.bls.gov/schedule/) and the agency's
  [revised-release notices](https://www.bls.gov/bls/2025-lapse-revised-release-dates.htm)
  support treating scheduled and actual publication as separate, changeable facts.
  They do not certify any QC/platform delivery timestamp.
- The Treasury's [yield-curve methodology](https://home.treasury.gov/policy-issues/financing-the-government/interest-rate-statistics/treasury-yield-curve-methodology)
  documents indicative input timing, usual publication timing, possible delay, and
  methodology change risk. It does not provide a point-in-time QC delivery audit.
- The St. Louis Fed's [real-time period documentation](https://fred.stlouisfed.org/docs/api/fred/realtime_period.html)
  states that observations and metadata have real-time periods, and its
  [vintage-date API](https://fred.stlouisfed.org/docs/api/fred/series_vintagedates.html)
  exposes dates when values were released or revised. Latest FRED history is not a
  substitute for historical vintages.
- QuantConnect's [Economic Events documentation](https://www.quantconnect.com/docs/v2/writing-algorithms/datasets/eod-historical-data/economic-events)
  describes event and availability fields. It does not prove historical estimate
  vintages or this account's observed delivery behavior.

## Enforcement boundary

The machine-readable policies live in
`systematic_futures/config/dataset_uses.py`. Validation requires all four macro rows
to remain `UNDER_REVIEW`, to state nonempty permitted/prohibited uses, and to have an
explicit missingness rule. No row is available for forecast or signal input. Moving a
row to a certified status requires a dataset-specific immutable evidence record and a
new recorded policy decision; documentation alone is insufficient.

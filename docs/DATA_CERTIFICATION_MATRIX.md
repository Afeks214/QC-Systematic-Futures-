# Data Certification Matrix

Matrix version: `lift1.closure.v1`
Reviewed: **2026-08-26**
Overall decision: **NO DATASET PROMOTED; ALL ROWS REMAIN UNDER_REVIEW**

Static schemas, policies, and official documentation are not empirical QuantConnect
delivery evidence. Python 3.11 and LEAN CLI are qualified locally, but no authorized
QC session/account state was available; neither the cloud futures probe nor the CFTC
delivery audit was executed. Accordingly, no desire-based promotion is allowed.

## Futures and CFTC datasets

| Stable dataset ID / representation | Current status | Evidence obtained | Permitted use now | Prohibited use now | Missingness / lineage rule | Evidence still required |
|---|---|---|---|---|---|---|
| `qc_futures_trade_data` — QC Futures Trade Data | `UNDER_REVIEW` | API names and point-in-time policy validated statically; no actual ES/ZN/6E rows | Schema, timing, and coverage inspection only | Feature, forecast, signal, execution/fill, P&L, or conclusion input | Preserve missing intervals; no zero fill; retain source/delivery clocks and lineage | Fixed-window real QC rows, market coverage, timestamp semantics, gaps, revisions/corrections, and artifact hash |
| `qc_futures_quote_data` — QC Futures Quote Data | `UNDER_REVIEW` | Policy exists; no actual quote observation | Schema and availability inspection only | Spread/cost, signal, execution, or P&L use | Missing quote stays missing; no trade-based substitution | Real quote coverage and timestamp/missingness audit for ES/ZN/6E |
| `qc_futures_open_interest` — QC Futures Open Interest | `UNDER_REVIEW` | Official APIs/data descriptions located; no received/non-null count | Coverage and mapping-research inspection only after observation | Signal input or silent use in mapping conclusions | Missing OI stays missing; retain age, source version, and revision flag | Empirical per-market coverage, delivery clock, staleness, revision/correction behavior, and reconciliation with mapping events |
| `qc_futures_contract_mapping` — QC Futures Contract Mapping | `UNDER_REVIEW` | Continuous/mapped semantics and environment timing difference documented; causal manager test passes; no actual event | Static identity/causality inspection only | Inferring future mapping, backdating a change, or treating backtest timestamp as live delivery | Old/new actual contracts remain separate; event visible only at `max(observed,effective)` | Real fixed-window ES/ZN/6E mappings, event times, old/new identities, expiries, and official result hash |
| `cftc_commitments_of_traders_synthetic_timing` — CFTC Commitments of Traders | `UNDER_REVIEW` | Official release rule and exact ES/ZN/6E TFF constants documented; ordinary/delayed gate tests are synthetic only | Timing-policy testing only | Context, forecast, signal, or trading use | Withhold until max of official release, observed delivery, and documented exception; no interpolation | Real `CFTCFinancialFutures` ordinary/delayed QC delivery audit, delivered market/field coverage, age, revisions, and artifact hash |
| `continuous_backwards_ratio_series` — Continuous Backwards-Ratio Series | `UNDER_REVIEW` | Official normalization and mapping semantics documented; no real mapping chain observed | Continuity research, long-horizon research representation, and normalized comparisons only after intended-use certification | **Actual execution price, actual fill simulation, actual realized P&L, and actual Volume Profile price bins** | Withhold missing intervals; retain normalization/mapping chain and retrieval lineage; actual mapped prices remain separate | Real mapping/delivery audit and certification for each intended research use |

The official [US Futures documentation](https://www.quantconnect.com/docs/v2/writing-algorithms/datasets/algoseek/us-futures)
supports actual-contract and history retrieval semantics. The
[US Futures Security Master documentation](https://www.quantconnect.com/docs/v2/writing-algorithms/datasets/quantconnect/us-futures-security-master)
supports mapping/continuous-series semantics and warns that normalized continuous
prices can differ from live order prices. The
[US Future Universe documentation](https://www.quantconnect.com/docs/v2/writing-algorithms/datasets/quantconnect/us-future-universe)
describes daily Open Interest coverage. None of those pages proves what this account
actually received in the fixed probe window.

## Macro and event datasets

| Stable dataset ID | Dataset | Current status | Permitted use now | Prohibited use now | Evidence still required |
|---|---|---|---|---|---|
| `bls_macro_releases` | BLS | `UNDER_REVIEW` | Descriptive and risk-context research | Forecast/signal input and silent revised history | Per-series first-release, revision, schedule, platform-delivery, holiday, and correction audit |
| `us_treasury_yield_curve` | U.S. Treasury Yield Curve | `UNDER_REVIEW` | Descriptive and risk-context research | Forecast/signal input and silent revised history | Publication/delivery clocks, tenor/schema and methodology versions, holidays, corrections, revisions |
| `fred_macro_series` | FRED | `UNDER_REVIEW` | Descriptive and risk-context research | Forecast/signal input and silent latest vintage | Per-series real-time/vintage, release, revision, platform-delivery, holiday, and correction audit |
| `economic_events_calendar` | Economic Events | `UNDER_REVIEW` | Calendar and risk-context research | Historical-surprise/signal input and silent latest estimates | Schedule-as-known and estimate vintages, actual release/delivery, revisions, holidays, corrections |

Full observation, publication, revision, permitted-use, prohibited-use, missingness,
and future-certification semantics are recorded in
`docs/MACRO_DATA_POLICY_MATRIX.md` and machine-validated in
`systematic_futures/config/dataset_uses.py`.

## Backwards-Ratio classification

The classification is deliberately restrictive:

```text
Continuous Backwards-Ratio Series
Purpose: continuity / long-horizon research representation
Not permitted for: actual execution price, actual fill simulation,
actual Volume Profile price bins, or actual realized P&L
```

Closing this classification ambiguity does not make the series
`CERTIFIED_SIGNAL`. Actual mapped-contract prices and identities remain separate.

## Promotion rule

A future status change must name the exact certification scope, observation period,
source/runtime version, tests passed, exceptions, permitted/prohibited uses, owner,
approval timestamp, and content hash. `CERTIFIED_CONTEXT` or `CERTIFIED_SIGNAL` may
not be inferred from passing synthetic tests or from an official API description. The
machine-readable certification matrix artifact must reproduce these statuses and map
each claim to its evidence hash.

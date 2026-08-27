# Data Certification Matrix

Version: `lift1.closure.v2`
Certified: **2026-08-27**

Certification is use-specific. `CERTIFIED_CONTEXT` permits the observed Lift 1
research/data-readiness use only; it does not imply signal, execution, or P&L use.

## Futures and CFTC

| Stable dataset / representation | Status | Empirical scope | Permitted now | Still prohibited or unresolved |
|---|---|---|---|---|
| `qc_futures_trade_data` | `CERTIFIED_CONTEXT` | ES/ZN/6E minute TradeBars, 2024-02-15 to 2024-03-25 | coverage, identity, session, and roll-state research | signal, fills, P&L, or gap interpolation |
| `qc_futures_quote_data` | `UNDER_REVIEW` | not separately captured by the TradeBar probe | schema/availability inspection only | spread/cost, execution, signal, or P&L use |
| `qc_futures_open_interest` | `CERTIFIED_CONTEXT` | non-null observations for ES 65/65, ZN 70/70, 6E 173/173 | coverage and mapping context in the certified window | signal use, unobserved periods, or assumed revision behavior |
| `qc_futures_contract_mapping` | `CERTIFIED_CONTEXT` | two actual identities and one delivered mapping event per root | causal contract identity and roll-state research | future mapping inference, backdating, or live-parity claims |
| `cftc_commitments_of_traders_synthetic_timing` | `CERTIFIED_CONTEXT` | actual QC TFF ordinary/delayed audit for ES/ZN/6E; stable ID retained for compatibility | COT research context gated by official release clock | `CERTIFIED_SIGNAL`, forecast, or trading use |
| `continuous_backwards_ratio_series` | `UNDER_REVIEW` | normalization chain observed; intended uses remain restricted | continuity and normalized-comparison research only | actual execution price, fill simulation, realized P&L, actual-contract price bins |

Evidence: `artifacts/certification/qc_futures_runtime_probe.json`,
`artifacts/certification/cftc_release_delivery_audit.json`, and the machine-readable
`artifacts/certification/lift1_dataset_certification_matrix.json`.

All missing intervals remain missing. The futures artifact retains 28
`UNADJUDICATED_MINUTE_GAP` flags per root. No value is silently filled, zeroed, or
substituted. Actual mapped-contract identities and adjusted continuous values remain
separate.

## Macro and event data

| Stable dataset | Status | Permitted | Prohibited |
|---|---|---|---|
| `bls_macro_releases` | `UNDER_REVIEW` | descriptive and risk-context research | forecast/signal input; silent revised history |
| `us_treasury_yield_curve` | `UNDER_REVIEW` | descriptive and risk-context research | forecast/signal input; silent revised history |
| `fred_macro_series` | `UNDER_REVIEW` | descriptive and risk-context research | forecast/signal input; silent latest vintage |
| `economic_events_calendar` | `UNDER_REVIEW` | calendar and risk-context research | historical-surprise/signal input; silent latest estimates |

Their observation, revision, missingness, and future-certification requirements remain
in `docs/MACRO_DATA_POLICY_MATRIX.md` and
`systematic_futures/config/dataset_uses.py`.

## Promotion rule

Any future promotion must identify exact scope, period, runtime/source version,
lineage, tests, exceptions, permitted/prohibited uses, and content hash. Synthetic
tests or official API descriptions alone never establish empirical delivery.

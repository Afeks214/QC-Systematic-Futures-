# Assumptions and Blockers

Status: **NO UNRESOLVED LIFT 1 OR LIFT 2 MEASUREMENT BLOCKER**
Reviewed: **2026-08-28**

## Verified

- The controlling private specifications were reviewed and are represented by exact
  SHA-256 digests; their bytes are not committed to the public repository.
- CPython 3.11.16 runs the complete supported local gate. Final Lift 2 QC Cloud
  evidence reports CPython 3.11.14, NumPy 1.26.4 and LEAN 2.5.0.0.18039.
- The eight-market registry validates. The real QC futures probe observed ES, ZN, and
  6E rows, mapped identities, mapping events, Open Interest, expiries, ticks,
  multipliers, session IDs, roll states, and Python.NET boundary values.
- The real QC CFTC probe observed ES, ZN, and 6E ordinary and official
  holiday-delayed delivery cases. The official-clock max gate prevents early use.
- Both cloud probe modes created zero orders, Insights, and PortfolioTargets.
- Notebook 01 is a thin client with no unique business logic; its shared registration
  path ran in the certified cloud probe. Direct interactive notebook execution is not
  claimed.

## Conservative assumptions retained

- `UNADJUDICATED_MINUTE_GAP` counts are retained as observed. No gap is filled or
  presumed to be a defect or maintenance interval without separate adjudication.
- A mapping event is a causal event-instant `ROLL_TRANSITION`, followed by
  `POST_ROLL`; no pre-roll or blackout window is inferred.
- The 182-day contract filter is inspection configuration, not an exchange or
  institutional threshold.
- The source timezone of `SymbolChangedEvent.time` remains unverified, so its UTC
  conversion is withheld.
- Session certification is pinned to one official LEAN market-hours database version,
  not all future calendars.

## Non-blocking limitations

- CFTC data stopped on 2026-05-29 inside the configured window ending 2026-08-25.
- Quote data was not separately certified by the minute TradeBar probe.
- Continuous Backwards-Ratio data remains non-executable and prohibited for fills,
  realized P&L, and actual-contract price bins.
- BLS, Treasury, FRED, and Economic Events remain `UNDER_REVIEW` and unavailable to
  forecast or signal logic.
- Empirical live mapping timing and CFTC revision history are not claimed.

## IMSI RSD v1 boundary — 2026-08-27

- `IMPLEMENTED_DESCRIPTIVE`: zero-seeded online VW-RSI; 30-prior-session time-of-day
  median; completed-bar session VWAP percentage distance; prior-only EWMA covariance;
  bounded off-diagonal shrinkage; Mahalanobis geometry; seven-bar neighbor embargo;
  bounded state; covariance diagnostics; and trade-clock fail-closed guards.
- `BLOCKED_LIFT_2`: neighbor forward returns, tanh MES, calibration, triple-barrier
  labels, IC/Sharpe tests, winsorized predictive features, confluence thresholds,
  portfolio FSM, risk allocation, execution, and orders.
- `BLOCKED_INPUT_CONTRACT`: macro-event and roll hard-neutral rules, empirical
  five-year percentile gates, and session exclusion after missing bars require
  separately certified calendars, roll/data-quality inputs, and versioned interfaces.
- The supplied IMSI formula is implemented and named
  `EWMA_DIAGONAL_SHRINKAGE_SPEC_V1`; it is not represented as formal Ledoit-Wolf.
- Regime-conditioned 63-trading-day IMSI limits remain deferred to Lift 3. Valid
  StateCore rows retain `IMSI_FULL_MODEL_DEFERRED_LIFT3` as non-blocking information;
  no unconditional substitute is applied.

## Deferred beyond Lift 2

IMSI MES, forward labels/outcomes, return and P&L calculations, forecasts, calibration,
ML, Alpha, portfolio construction, risk allocation, execution, orders, paper trading,
live trading, and true L2 order-book behavior remain unimplemented and unauthorized.

## Lift 2 runtime certification — 2026-08-27

- `MATH_READY_FOR_LIFT_2_RUNTIME`: all local mathematical reconciliation gates pass
  against the three supplied indicator specifications.
- `LIFT_2_COMPLETE_MEASUREMENT_ONLY`: source admission, semantics, lineage,
  readiness, session-safe alignment and quality propagation pass the complete
  100-test local gate and the final 3-deep plus 8-smoke QC matrix.
- `RESOLVED_CLOUD_SYNC`: build `b77ac2-941e38` failed before any market data was
  processed. Direct inspection found `data/policies.py` bytes at the cloud
  `domain/enums.py` path. All 34 deployed files were subsequently synchronized and
  independently reopened/read as byte-identical; build `4dabc4-360f32` initialized.
- `SUPERSEDED_PRE_FLOOR_QC_EVIDENCE`: the failed ES smoke
  `69edd3f1bd02d166f9170c6223349be6` found a missing same-session five-minute
  bucket. The state boundary now resets with `IAE_BAR_GAP_RESET`; the exact three-bar
  formula is unchanged and all 89 local tests pass. Corrected build
  `7de0cd-7f0de9` then completed ES smoke backtest
  `cd7b3f083a248def2d4720ae38613f5a` with required measurements and zero actions.
  A later ES deep run also completed, but ZN backtest
  `0f2c86d773425e9db2b6f81ad3f0a90b` exposed the specification's locked-market
  edge: zero true ranges are valid and the warmed ATR must be floored at `1e-6`.
  The corrected source and all math classes are recertified. Every pre-floor run is
  integration evidence only; at that checkpoint ES/ZN/6E deep and all-eight smoke
  still had to be replayed. The final resolution below supersedes that requirement.
- `RESOLVED_FINAL_QC_MATRIX`: source commit
  `ba11355a2dd8f150ad4c7a1a4ff5c457cabfc4c5`, runtime tree
  `cb48ca4b995bbb28f579fee1542076465308792105cc56a2d0f9b16f4d7d0f32`, and
  evidence commit `359333ba2ccc5f810906f9c7631b625deb3cd454` bind 11 unique
  completed backtests under LEAN 18039. All 11 report zero Orders, Insights and
  PortfolioTargets.
- `READINESS_DISCLOSURE`: all 1,771 candidate observations are retained, unique and
  explicitly not-ready under the current mathematical/quality contract. This is not
  a Lift 2 blocker because Lift 2 is descriptive; it blocks treating the bounded
  sample as a predictive-research or trading dataset.
- `READY_FOR_LIFT_3_RESEARCH_GATING`: the completed measurement layer may be used to
  design the next research gates. Alpha, profitability, allocation, paper/live
  trading and institutional approval remain unproven and unauthorized.

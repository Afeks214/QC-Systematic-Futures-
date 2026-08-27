# Assumptions and Blockers

Status: **NO UNRESOLVED LIFT 1 FOUNDATIONAL BLOCKER**
Reviewed: **2026-08-27**

## Verified

- The controlling private specifications were reviewed and are represented by exact
  SHA-256 digests; their bytes are not committed to the public repository.
- CPython 3.11.16 runs the complete supported local gate. QC Cloud reported CPython
  3.11.14, LEAN 2.5.0.0.18036, Linux x86_64.
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
- Regime-conditioned 63-trading-day IMSI limits remain
  `SPEC_DEPENDENCY_NOT_READY`; no unconditional substitute is applied.

## Deferred beyond Lift 1

Market Profile, Auction State, IMSI, ICM, IAE, L2, candidate events, labels, returns,
P&L, forecasts, ML, Alpha, portfolio construction, risk, execution, orders, paper
trading, and live trading remain unimplemented.

## Lift 2 runtime certification — 2026-08-27

- `MATH_READY_FOR_LIFT_2_RUNTIME`: all local mathematical reconciliation gates pass
  against the three supplied indicator specifications.
- `QC_REPLAY_PENDING`: build `b77ac2-941e38` exposed an eager package-initialization
  cycle before any market data was processed. The runtime-facing initializers are now
  side-effect free and locally verified; a fresh cloud build and replay must pass
  before Lift 2 can be declared complete.
- This packaging issue does not invalidate the reconciled formulas, but local success
  is not substituted for QC runtime evidence.

# Lift 1 Completion Report

Status: **SUPERSEDED_BY_FINAL_CLOSURE_REPORT**
Current decision: **READY_FOR_LIFT_2**

This document originally recorded the construction-time state before Python 3.11,
Git, official LEAN calendar, and authenticated QuantConnect cloud routes were
available. Those blockers were subsequently resolved without entering Lift 2.

The authoritative final account is `docs/LIFT_1_CLOSURE_REPORT.md`. Its evidence is
indexed by `artifacts/certification/lift_1_evidence_index.json` and bound by
`artifacts/manifests/lift_1_closure_manifest.json`.

Final certified runtime identifiers:

- source Git: `cbfee265cbf5e94c7768667d469e2773f62e3080`
- QC project: `35697180`
- QC build: `67d2fc-f0a27f`
- futures backtest: `b22d565d649c5b31650fd033cdc89cf3`
- CFTC backtest: `a7ba4f84937fb19bc3f6f63bc773e3c3`
- LEAN: `2.5.0.0.18036`
- local Python: `CPython 3.11.16`
- QC Python: `CPython 3.11.14`

No Profile, Auction State, IMSI, ICM, IAE, event-generation, label, return, P&L, ML,
Alpha, portfolio, risk, execution, order, paper-trading, or live-trading behavior was
implemented during closure.

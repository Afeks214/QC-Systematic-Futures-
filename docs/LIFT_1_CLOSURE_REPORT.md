# Lift 1 Closure Report

Status: **READY_FOR_LIFT_2**
Certified: **2026-08-27**
Boundary: research/data readiness only; no Lift 2 behavior is implemented.

## Decision

Lift 1 is complete. The fixed-window QuantConnect cloud probes observed real ES, ZN,
and 6E futures data and real CFTC TFF deliveries. The complete local Python 3.11 gate
passes, the reference session matrix is version-pinned, Notebook 01 has verified
thin-client/runtime parity, every cloud run produced zero orders, Insights, and
PortfolioTargets, and the qualified closure manifest has no foundational blocker.

This is engineering and data-readiness certification. It is not evidence of alpha,
profitability, executable prices, fill quality, or investment suitability.

## Final evidence

| Gate | Result | Artifact / identifier |
|---|---|---|
| Canonical runtime source | `PASS` | Git `cbfee265cbf5e94c7768667d469e2773f62e3080` |
| Python 3.11 quality suite | `PASS` | `artifacts/certification/python311_quality_gate.json`; final rerun under CPython 3.11.16 |
| QC runtime | `COMPLETED` | project `35697180`; build `67d2fc-f0a27f`; LEAN `2.5.0.0.18036` |
| ES | `OBSERVED` | 38,461 minute rows; 2 mapped contracts; 65/65 OI values |
| ZN | `OBSERVED` | 37,321 minute rows; 2 mapped contracts; 70/70 OI values |
| 6E | `OBSERVED` | 38,701 minute rows; 2 mapped contracts; 173/173 OI values |
| Mapping and roll | `PASS_CONTEXT` | one delivered mapping event per root; `normal`, `roll_transition`, and `post_roll` observed |
| Tick, multiplier, expiry | `OBSERVED` | per-market values in `qc_futures_runtime_probe.json` |
| Sessions/calendar | `CERTIFIED_PINNED_VERSION` | `reference_market_session_matrix.json` |
| CFTC point in time | `CERTIFIED_CONTEXT` | `cftc_release_delivery_audit.json`; 6/6 target deliveries audited |
| Point-in-time gate | `PASS` | ordinary and delayed-release tests plus official-clock max rule |
| Notebook 01 | `THIN_CLIENT_RUNTIME_PARITY_VERIFIED` | qualified manifest parity record; notebook was not claimed as interactively executed |
| ForecastPacket | `PASS_SCHEMA_ONLY` | immutable timing-validated contract; no producer exists |
| Cost scenarios | `PASS_CONTRACT_ONLY` | BASE/STRESS/SEVERE interfaces contain no invented values |
| Hard safety | `PASS_OBSERVE_ONLY` | no new capital permitted; all required blocking reasons present |
| Trading boundary | `PASS` | 0 orders; 0 Insights; 0 PortfolioTargets in both cloud modes |
| Qualified manifest | `PASS` | `artifacts/manifests/lift_1_closure_manifest.json` |

## Runtime identity

- Certified source Git SHA: `cbfee265cbf5e94c7768667d469e2773f62e3080`
- QuantConnect project: `35697180`
- Futures cloud backtest: `b22d565d649c5b31650fd033cdc89cf3`
- CFTC cloud backtest: `a7ba4f84937fb19bc3f6f63bc773e3c3`
- QC cloud build: `67d2fc-f0a27f`
- LEAN runtime: `2.5.0.0.18036`
- QC Python: `CPython 3.11.14`, Linux x86_64
- Local quality runtime: `CPython 3.11.16`, macOS arm64
- Futures probe hash: `6e400e06a985429117669a56af4e8c42ae997ece048147a99ffea9888536b741`
- CFTC probe hash: `908cb750ec8e5133a01710ac0b8fc74c16e82e0a36ccd8b9ed429e3be6f63fd7`
- Closure manifest hash: `022be41a0d23ebba4ede651b1303208fbe8bf69f8eb2c9cc8e020f7b53cd65ef`

## Empirical findings and controls

The futures run covered the configured 2024-02-15 through 2024-03-25 window and
processed 1,531,695 data points. The probe retained actual mapped identities,
mapping-event times, expiries, Open Interest counts, tick sizes, multipliers, session
IDs, roll states, and Python.NET datetime evidence. Each root reported 28
`UNADJUDICATED_MINUTE_GAP` observations. They remain visible and unfilled; the artifact
does not relabel them as defects or silently excuse them as exchange maintenance.

The CFTC run used actual `CFTCFinancialFutures` subscriptions for ES, ZN, and 6E. The
ordinary 2026-01-09 delivery matched the official 20:30 UTC release. For the official
holiday-delayed 2026-01-05 release, QC historical Slice/EndTime was 2026-01-02 20:30
UTC. Raw clocks are preserved, and the AvailabilityGate enforces:

```text
usable_from_utc = max(official release, observed QC delivery, later documented exception)
```

Therefore the delayed record is unusable before 2026-01-05 20:30 UTC. QC delivered
22 rows per market through 2026-05-29 but none after that date inside the configured
window ending 2026-08-25. That tail limitation is explicit and does not weaken the
ordinary/delayed certification examples. CFTC is `CERTIFIED_CONTEXT`, never
`CERTIFIED_SIGNAL`.

## Conservative dataset boundaries

Futures trade rows, mapping, and Open Interest are certified only for the observed
Lift 1 context. Quote data was not separately certified. Continuous Backwards-Ratio
values remain prohibited for actual execution prices, fill simulation, realized P&L,
and actual-contract price bins. BLS, Treasury, FRED, and Economic Events remain
`UNDER_REVIEW` and prohibited from forecast or signal use.

The source timezone for Python.NET `SymbolChangedEvent.time` was not independently
verified, so that field's UTC conversion is withheld in the artifact. This is an
explicit limitation, not an inferred value.

## Quality and source boundary

The supported sequence runs compileall, Ruff format, Ruff lint, strict Pyright,
pytest, notebook validation, and deterministic manifest generation under Python
3.11. All four notebooks validate. Core modules remain standard-library-only and do
not import QuantConnect. No Profile, Auction State, IMSI, ICM, IAE, L2, event
generation, label, return, P&L, ML, Alpha, portfolio, risk, execution, or order logic
was added.

The certified runtime code is the immutable source commit above. The final closure
commit adds only evidence, documentation, and contract tests and is verified against
remote `main` after push. A tracked file cannot contain the SHA of the commit that
contains itself; both SHAs are therefore reported distinctly rather than fabricating
a self-reference.

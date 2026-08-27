# Lift 1 ExecPlan

Status: **COMPLETE_READY_FOR_LIFT_2**
Started: 2026-08-26
Completed: 2026-08-27
Scope: deterministic research/data readiness only.

## Purpose

Deliver the smallest maintainable foundation that establishes market definitions,
point-in-time data semantics, session and roll identity, empirical QC observability,
provenance, research contracts, and a zero-trading runtime boundary. Lift 2 strategy
behavior is explicitly out of scope.

## Authority and invariants

The active closure directive governs, followed by the Master Specification, Intraday
Extension, repository rules, current official QuantConnect/LEAN sources, official
CFTC material, and primary sources. Domain/data/ledger core modules remain free of QC
imports. Datetimes are explicit aware UTC in the domain. Missing values are never
coerced to zero, future mappings are never inferred, and unavailable APIs fail closed.

## Delivered subsystems

| Subsystem | Outcome |
|---|---|
| Governance and provenance | controlling documents reviewed; source hashes retained; public bytes excluded |
| Market registry | exact eight roots validated; ES/ZN/6E reference subset |
| Point-in-time core | explicit observation/release/delivery clocks and max-time AvailabilityGate |
| Sessions and rolls | versioned semantic overlay; pinned official LEAN calendar fixtures; causal mapping state |
| Ledger and manifests | deterministic IDs, append-only audit, immutable source and evidence hashes |
| QC futures boundary | real cloud rows, mappings, OI, metadata, gaps, session IDs, roll states, Python.NET clocks |
| CFTC boundary | real ES/ZN/6E TFF deliveries; ordinary and holiday-delayed audit; `CERTIFIED_CONTEXT` |
| Research clients | four validated thin notebooks; Notebook 01 runtime parity verified |
| Future contracts | feature names/units, ForecastPacket schema, number-free cost scenarios, observe-only safety |
| Architecture guard | no trading, Alpha, PortfolioTarget, Profile, event, label, P&L, ML, risk, or execution behavior |

## Verification sequence

Run from repository root with `.venv/bin` first on `PATH`:

```bash
python -m compileall systematic_futures main.py
ruff format --check .
ruff check .
pyright
pytest -q
python scripts/validate_notebooks.py
python scripts/build_manifest.py
```

`scripts/run_quality_checks.sh` is the supported deterministic composition. The final
qualified source run used CPython 3.11.16. The cloud source is Git
`cbfee265cbf5e94c7768667d469e2773f62e3080`, QC project `35697180`, build
`67d2fc-f0a27f`, futures backtest `b22d565d649c5b31650fd033cdc89cf3`, and CFTC
backtest `a7ba4f84937fb19bc3f6f63bc773e3c3`.

## Milestone reconciliation

- [x] Specifications, source hierarchy, decision log, and blockers register.
- [x] Standard-library domain/config/PIT/quality core.
- [x] Sessions, contracts, roll causality, ledger, and manifest builders.
- [x] Current official QC API resolution and thin adapters.
- [x] Python 3.11 environment and complete local gate.
- [x] Official LEAN calendar matrix for ordinary, DST, holiday, early close, and
  cross-midnight cases.
- [x] Actual QC futures runtime certification for ES, ZN, and 6E.
- [x] Actual QC CFTC ordinary and holiday-delayed delivery certification.
- [x] Notebook validation and thin-client runtime parity classification.
- [x] Final data matrix, closure manifest, evidence index, and closure report.
- [x] Required evidence-only commit prepared; final handoff verifies local and remote
  SHAs are identical.

## Final decision

`READY_FOR_LIFT_2`

This permits the next phase to begin only as a separately authorized task. It makes no
alpha, profitability, live-readiness, or investment claim.

# Repository Rules

## Authority

Resolve conflicts in this order: (1) the active Lift task, (2) `Institutional_Systematic_Futures_Program_Master_Spec_v1.0`, (3) `Intraday_Alpha_Capture_Execution_Extension_v1.0`, (4) official QuantConnect documentation, (5) official LEAN repositories, (6) official public firm material, and (7) primary academic papers. Stop rather than guess.

## Structure and boundaries

- `systematic_futures/domain`, `data`, and `ledger` are standard-library core modules and never import QuantConnect.
- QuantConnect imports are allowed only in root `main.py` and `systematic_futures/qc_adapters/`.
- Notebooks are thin research clients. Business logic belongs in importable modules.
- Lift 1 contains no trading logic, signals, forecasts, P&L, Market Profile, IMSI, ICM, IAE, ML, portfolio, risk, or execution implementation.

## Commands

Run from the repository root:

```bash
python -m compileall systematic_futures main.py
ruff format --check .
ruff check .
pyright
pytest -q
python scripts/validate_notebooks.py
python scripts/build_manifest.py
```

Use `scripts/run_quality_checks.sh` for the supported deterministic sequence.

## QuantConnect APIs

Never infer an API, enum, property, future constant, or CLI command. Verify it in current official documentation or official LEAN/lean-cli source, then record the evidence in `docs/QC_API_RESOLUTION.md` before use. Unresolved integrations stay `NOT_VERIFIED`; do not create runnable-looking substitutes.

## Time, units, and failure behavior

- Domain datetimes are timezone-aware UTC; current time is an explicit input.
- Document every public function's units, time semantics, missingness, and exceptions.
- Preserve raw units and normalized representations; do not invent tick sizes, multipliers, or institutional thresholds.
- Never silently coerce missing data to zero, catch broad exceptions, backdate data, infer future mappings, or fall back to another dataset/API.

## Definition of Done

Lift 1 is done only when the current `docs/LIFT_1_EXECPLAN.md` is reconciled, all supported quality commands pass, unsupported QC runtime checks are explicitly `NOT_EXECUTED`, every research-affecting output retains lineage, and `docs/LIFT_1_COMPLETION_REPORT.md` distinguishes verified facts from blockers. Update the ExecPlan after each major subsystem. If evidence is missing or an invariant cannot be established, record it in `docs/ASSUMPTIONS_AND_BLOCKERS.md` and stop the affected path.

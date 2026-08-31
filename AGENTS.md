# Repository Rules

## Scope

The active repository is measurement-only. Allowed behavior is market identity,
point-in-time availability, revisions, sessions, rolls, actual-contract volume Profile,
IMSI, ICM, IAE, descriptive candidate events, and read-only QuantConnect integration.

Forecasts, outcome labels, alpha, ML, portfolio construction, risk allocation, execution,
orders, Insights, and PortfolioTargets are outside scope. Stop rather than scaffold them.

## Boundaries

- `domain`, `data`, and `measurement` do not import QuantConnect.
- QuantConnect imports exist only in `main.py` and `qc_adapters`.
- Domain datetimes are aware UTC. Naive boundary values require explicit timezone provenance.
- Revisable external datasets pass through `PointInTimeEntryPath`; QC ticks carry their
  observed availability directly into `TradeObservation`. Revisions remain append-only.
- Continuous, mapped, and actual-contract identities are never interchangeable.
- Profiles and measurements use the mapped actual contract and preserve native units.
- Missingness is explicit; never coerce it to zero or silently fall back to another source.
- Notebooks are thin clients. Business logic belongs in importable modules.

## QuantConnect APIs

Do not infer an API, enum, property, future constant, or CLI command. Verify it against
official QuantConnect documentation or LEAN source and record the active resolution in
`docs/QC_API_RESOLUTION.md` before use.

## Quality gate

Run from the repository root with Python 3.11:

```bash
python -m pip check
python -m compileall systematic_futures main.py
ruff format --check .
ruff check .
pyright
pytest -q
python scripts/validate_notebooks.py
```

The supported deterministic sequence is `bash scripts/run_quality_checks.sh`.

## Evidence boundary

Generated outputs belong in ignored temporary storage, not the source tree. Green local
checks prove only the tested code invariants. They do not prove market performance or a
current external runtime replay.

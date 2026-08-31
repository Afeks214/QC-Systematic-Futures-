# Systematic Futures Measurement

This repository is a read-only, deterministic futures measurement core. It converts
actual-contract trade ticks into causal market-state measurements and descriptive
candidate events. It does not forecast returns, allocate capital, or place orders.

The supported universe is ES, NQ, RTY, ZT, ZN, 6E, 6J, and 6B. Continuous symbols are
used only for mapping. Profiles and measurements are built from the mapped actual
contract.

## Active surface

- `main.py`: thin QuantConnect composition root.
- `systematic_futures/qc_adapters/runtime.py`: the single active runtime.
- `systematic_futures/domain/`: identities, schemas, errors, and canonical serialization.
- `systematic_futures/data/`: point-in-time gating, revisions, quality, sessions, and rolls.
- `systematic_futures/measurement/`: Profile, IMSI, ICM, IAE, event generation, and stream state.
- `research.ipynb`: one output-free thin client; no business logic.

See `ARCHITECTURE.md` for the data flow and current boundaries.

## Local validation

Use Python 3.11 and install `requirements.txt`, then run:

```bash
bash scripts/run_quality_checks.sh
```

The sequence checks dependencies, compilation, formatting, linting, strict type checks,
all tests, architecture boundaries, and notebook structure. It must not mutate the
worktree.

## Non-claims

Passing checks establishes deterministic software behavior for the tested source. It
does not establish alpha, profitability, execution quality, production readiness, or
investment suitability. Current-source QuantConnect replay evidence must be obtained
separately before making any runtime qualification claim.

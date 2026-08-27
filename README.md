# Systematic Futures Measurement — Lift 2

## Mission

This repository converts certified actual-contract futures trades into deterministic,
point-in-time Volume Profile, Auction, IMSI, ICM, and IAE-L1 measurements. It aligns
5-minute, 30-minute, session, contract, and indicator snapshots causally and records
unlabeled Candidate Event Observations for later hypothesis falsification.

Lift 2 is a measurement layer. It contains no strategy optimization, future outcome,
predictive model, portfolio/risk allocation, order, or execution logic.

## Scope

- Actual mapped-contract `TRADE` ticks only for Profile, bars, and VWAP.
- Integer-tick developing/final/rolling Volume Profiles with deterministic POC and
  contiguous 70% Value Area.
- Primitive Auction features and transition-once exit, re-entry, and POC-migration
  events.
- Prior-only VW-RSI/TOD/bar-VWAP/EWMA-shrunk Mahalanobis IMSI StateCore.
- Causal pseudoinverse quadratic ICM geometry with per-bar derivatives and guards.
- Symmetric completed-bar IAE-L1 formation, retest, and guarded proxy score.
- As-of snapshot alignment, deterministic event IDs, and aggregate coverage.
- One thin parameterized QC algorithm for deep ES/ZN/6E and all-eight smoke replays.

Not implemented: outcomes, P&L, Alpha, acceptance/rejection composites, supervised ML,
portfolio construction, risk, execution, L2 order-book inference, or trading actions.

## Architecture

| Area | Responsibility | Runtime dependency |
|---|---|---|
| `domain/`, `data/`, `ledger/` | Standard-library identity, clocks, sessions, rolls, lineage, and immutable contracts | Python standard library |
| `config/` | Eight-market registry, frozen measurement policy, feature semantics v1-v4 | Python standard library |
| `measurement/types.py` / `models.py` | Public facade / QC-safe implementation for frozen Lift 2 observations and snapshots | Python standard library |
| `measurement/profile.py` / `volume_profile.py` | Public facade / QC-safe implementation for tick bins, POC/Value Area, rolling profiles, and Auction primitives | Python standard library |
| `measurement/volatility.py` | Shared arithmetic 24-true-range five-minute ATR measurement | Python standard library |
| `measurement/imsi.py` | Prior-only IMSI StateCore, EWMA diagonal shrinkage, and neighbor embargo | NumPy 1.26.4 |
| `measurement/icm.py` | Scaled quadratic ICM geometry via a frozen `numpy.linalg.pinv` | NumPy 1.26.4 |
| `measurement/iae.py` | Symmetric IAE-L1 gap lifecycle and guarded absorption-proxy score | Python standard library |
| `measurement/events.py` | Transitions, as-of alignment, immutable events, aggregate coverage | Python standard library |
| `measurement/stream.py` | Session-anchored causal coordination and bounded state | Python standard library |
| `qc_adapters/lift2_runtime.py` | Verified QC mapping, actual-contract tick, and evidence boundary | QuantConnect runtime |
| `main.py` | Thin read-only QC composition root | QuantConnect runtime |

QuantConnect imports are confined to `main.py` and `qc_adapters/`. The measurement
package never reads continuous adjusted prices and never stores raw tick history.

## Environment

Target runtime: CPython 3.11. NumPy `1.26.4` is the only numerical production
dependency and is pinned to the supported QuantConnect environment.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --requirement requirements.txt
python -m pip check
```

## Quality sequence

Run from the repository root:

```bash
python -m compileall systematic_futures main.py
ruff format --check .
ruff check .
pyright
pytest -q
python scripts/validate_notebooks.py
python scripts/build_manifest.py
bash scripts/run_quality_checks.sh
```

The final commands validate compact Lift 2 manifest/evidence hashes when certification
artifacts exist. A command that did not execute is never reported as passed.

## QC runtime

`InstitutionalFuturesMeasurementAlgorithm` delegates to `Lift2Runtime`. Parameters:

- `lift2_root`: one of `ES`, `NQ`, `RTY`, `ZT`, `ZN`, `6E`, `6J`, `6B`;
- `lift2_mode`: `deep` for ES/ZN/6E over 2024-02-15 through 2024-03-25, or `smoke`
  for the bounded all-market window.

The continuous root is used only for mapping and chain identity. Each mapped actual
contract is explicitly subscribed at tick resolution; only `TickType.TRADE` enters
measurements. Contract changes finalize old state and create a clean new stream.

## Notebook workflow

Notebook 01 preserves Lift 1 data certification. Notebook 02 is the Lift 2 thin
measurement client with ten sections for Profile QA, Auction/IMSI/ICM/IAE inspection,
coverage, and quality. It imports the production classes and defines no measurement
formula. Notebook 03 remains outside the current lift.

## Evidence policy

Git contains only schemas, hashes, aggregate counts, compact representative evidence,
and manifests. Raw ticks and the full derived candidate panel remain in approved
private storage and are ignored. Required final artifacts are:

- `artifacts/certification/lift2_runtime_measurement.json`
- `artifacts/certification/lift2_candidate_coverage.json`
- `artifacts/certification/lift2_math_certification.json`
- `artifacts/certification/lift_2_evidence_index.json`
- `artifacts/manifests/lift_2_manifest.json`

The authoritative live plan is `docs/LIFT_2_EXECPLAN.md`; final status and exact QC
identifiers belong in `docs/LIFT_2_COMPLETION_REPORT.md`.

## Research boundary

Engineering determinism, replay parity, and zero trading actions do not establish
profitability or investment suitability. Lift 3 may test separately preregistered
hypotheses; no Lift 3 implementation belongs in this repository state.

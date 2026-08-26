# Systematic Futures Research Foundation — Lift 1

## Mission

This repository establishes deterministic data contracts, point-in-time availability,
contract/session/roll identity, experiment pre-registration, lineage, and audit
artifacts for futures research. Its reference data probe inspects ES, ZN, and 6E in
QuantConnect/LEAN when an authorized runtime and data access are available.

Lift 1 creates a trustworthy research environment. It does **not** test a strategy,
produce trades, estimate returns, calculate P&L, or claim Alpha.

## Lift 1 scope

- Eight explicit candidate-market definitions; only ES, ZN, and 6E are probe enabled.
- Five under-review dataset policies and a synthetic CFTC Tuesday/Friday timing proof.
- Immutable UTC domain records, deterministic IDs, canonical JSON, and SHA-256 lineage.
- Point-in-time normalization followed by a heap-backed availability gate.
- Versioned ordinary-day semantic sessions, explicit contract snapshots, and causal
  mapping/roll observations.
- Append-only hash-chained experiment registration and deterministic run manifests.
- A thin, read-only QuantConnect algorithm and thin QuantBook research support.
- One operational data-state notebook, two documentation-only later-research shells,
  and a small invariant-focused test suite.
- Closure-only schema contracts for frozen feature semantics, ForecastPacket,
  BASE/STRESS/SEVERE cost fields, and an `OBSERVE_ONLY` hard-safety policy. These
  contracts do not calculate or generate their future values.

## Closure status

Local Lift 1 work is qualified under CPython 3.11.15 and LEAN CLI 1.0.228. The only
external closure dependency is an authenticated QuantConnect account/session with the
required cloud and dataset entitlements. No QC cloud backtest, QC Research notebook,
Python.NET runtime probe, or real CFTC delivery audit is claimed. See
`docs/LIFT_1_CLOSURE_REPORT.md` and the evidence index for the exact final status.

## Non-goals

Lift 1 contains no Market/Volume Profile, Auction State, IMSI, ICM, IAE, L2 data,
candidate generation, labels, event-study statistics, transaction-cost model,
forecast, ML, portfolio construction, Kelly/risk allocation, position, Insight,
PortfolioTarget, order, execution, P&L, paper-trading, or live-trading implementation.
Later interfaces are evidence requirements only in `docs/LIFT_2_HANDOFF.md`.

## Authority

Conflicts are resolved in this order:

1. The active Lift 1 task.
2. `upload/Institutional_Systematic_Futures_Program_Master_Spec_v1.0(2).docx`.
3. `upload/Intraday_Alpha_Capture_Execution_Extension_v1.0_HE(2).docx`.
4. Current official QuantConnect documentation and official LEAN repositories.
5. Official public firm material, then primary academic papers.

`AGENTS.md` is the operational repository contract. The live implementation plan is
`docs/LIFT_1_EXECPLAN.md`; assumptions and unresolved evidence are never hidden from
`docs/ASSUMPTIONS_AND_BLOCKERS.md`.

## Architecture

| Area | Responsibility | Runtime dependency |
|---|---|---|
| `systematic_futures/domain/` | Immutable records, enums, errors, validation, canonical serialization, IDs, schema-only pre-Alpha contracts | Python standard library |
| `systematic_futures/config/` | Markets, under-review datasets, use restrictions, fixed feature semantics, research configuration | Python standard library |
| `systematic_futures/data/` | Dataset policies, PIT normalization/gating, sessions, contracts, rolls, quality | Python standard library |
| `systematic_futures/ledger/` | Pre-registration hash chain and run manifest | Python standard library |
| `systematic_futures/research_lib/` | Thin notebook-facing inspection/export functions | Standard library; raw QC objects only at boundary |
| `systematic_futures/qc_adapters/` | Verified LEAN subscription and probe-object adaptation | QuantConnect runtime |
| `main.py` | Read-only QC composition root | QuantConnect runtime |

The core imports without QuantConnect. QC imports are confined to `main.py` and
`systematic_futures/qc_adapters/`. The boundary was separately checked against official
`quantconnect-stubs==18032`; the editor-only stubs and their scientific dependency
graph are intentionally not project dependencies.

## Project tree

```text
.
├── AGENTS.md
├── README.md
├── pyproject.toml
├── requirements.txt
├── main.py
├── research.ipynb
├── .agent/PLANS.md
├── docs/
├── systematic_futures/
│   ├── config/
│   ├── domain/
│   ├── data/
│   ├── ledger/
│   ├── research_lib/
│   └── qc_adapters/
├── research_notebooks/
├── scripts/
├── tests/
├── artifacts/
│   ├── data_probes/
│   ├── manifests/
│   └── ledgers/
└── upload/                 # optional local-only private specification mount (ignored)
```

No additional production layer is authorized in Lift 1.

## Environment setup

Target runtime: Python 3.11.11 / Python 3.11.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --requirement requirements.txt
python -m pip check
```

Every direct and transitive non-standard dependency is pinned and development-only;
`requirements.txt` records why each transitive group exists:

- `pytest`: decisive invariant/architecture tests.
- `ruff`: deterministic formatting and linting.
- `pyright`: strict type checking of the runtime-independent package.
- `nbformat`: controlled notebook parsing and structural validation.

Mac M4, Docker Desktop, VS Code, LEAN CLI, local/cloud separation, and credential
warnings are documented in `docs/MAC_M4_QC_BOOTSTRAP.md`.

## Quality commands

Run in this order, or execute `bash scripts/run_quality_checks.sh`:

```bash
python -m compileall systematic_futures main.py
ruff format --check .
ruff check .
pyright
pytest -q
python scripts/validate_notebooks.py
python scripts/build_manifest.py
```

A command that cannot run is `NOT_EXECUTED`, not passed. The completion report records
the actual interpreter and every result.

## Notebook workflow

1. Open `research.ipynb` for the index.
2. In a verified QC Research Environment, open
   `research_notebooks/01_data_state_research.ipynb`.
3. Keep the QuantBook timezone UTC and the fixed probe period 2024-02-15 through
   2024-03-25.
4. Register only ES, ZN, and 6E through imported project functions.
5. Inspect continuous identity, actual contracts, expiry/OI coverage, mapping events,
   missing intervals, and session counts.
6. Export only the small summary and manifest—never raw bulk futures data.

Backwards Ratio values are full-history-adjusted by LEAN. Notebook 1 may inspect them
for identity/coverage only; they are not point-in-time-certified signal values.
Notebooks 2 and 3 are documentation-only shells marked
`NOT IMPLEMENTED IN LIFT 1`.

## QC probe workflow

`main.py` defines one parameterized `InstitutionalFuturesDataProbe(QCAlgorithm)`.
Default `futures` mode uses the fixed 2024 window and records mappings, contract chains,
expiries, daily OI coverage, session IDs, roll states, runtime metadata, and datetime
representations. `cftc` mode uses the fixed 2026 audit window and exact ES/ZN/6E TFF
constants. Neither mode has orders, Insights, targets, holdings, indicators, returns,
or P&L behavior.

Static validation is local:

```bash
python -m compileall systematic_futures main.py
pytest -q tests/test_architecture_boundaries.py
```

Actual execution requires the separately documented LEAN/QC environment. Do not
describe static validation as a successful QC backtest.

## Artifacts

- Probe summary: `artifacts/data_probes/reference_markets_summary.json` (created by
  Notebook 1 only after actual QC history retrieval).
- Historical run manifest: `artifacts/manifests/lift_1_manifest.json` (immutable).
- A local rebuild check is disposable/ignored and is never substituted for closure
  evidence.
- Sample pre-registration chain: `artifacts/ledgers/experiment_ledger.jsonl`.
- Static closure and blocker evidence: `artifacts/certification/`.
- Machine-readable frozen semantics: `artifacts/contracts/feature_semantics_v1.json`.

`artifacts/manifests/lift_1_closure_manifest.json` is intentionally absent until its
required Git, LEAN, QC, notebook, CFTC, and session fields can be supported by real
evidence.

No raw bulk data, model artifact, order, position, return, or P&L artifact belongs in
these directories.

## Known blockers

- No authorized QuantConnect login/session was available, so organization tier,
  project access, data entitlement, cloud runtime identity, and empirical ES/ZN/6E and
  CFTC observations remain unknown.
- The per-market session matrix is pinned to the current LEAN calendar and tested;
  empirical live mapping delivery remains unobserved.
- Backwards Ratio is deliberately non-executable continuous research data, and actual
  CFTC delivery/revision semantics remain under review until the probe runs.

See `docs/ASSUMPTIONS_AND_BLOCKERS.md` for the authoritative categorized register.

## Lift 2 boundary

Stop after Lift 1 validation and documentation. `docs/LIFT_2_HANDOFF.md` lists only
the interface contracts and evidence required before a separately authorized Lift 2.
This repository makes no strategy or institutional-grade claim from file creation or
static checks.

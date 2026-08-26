# Lift 1 ExecPlan

Status: `IMPLEMENTED_WITH_EXTERNAL_VALIDATION_BLOCKERS`
Started: 2026-08-26 (Asia/Jerusalem)
Scope boundary: research foundation and point-in-time data truth only.

## 1. Purpose

Create a deterministic, Python 3.11 research foundation for futures data governance and QuantConnect inspection. A researcher must be able to define markets/datasets/sessions/contracts, normalize observations under explicit availability rules, pre-register a non-trading data audit, verify append-only provenance, build a deterministic run manifest, run a read-only QC probe when a verified QC runtime is available, and open thin notebooks.

Non-goals are trading, alpha, forecasts, labels, event-study statistics, P&L, Market Profile/Auction State, IMSI/ICM/IAE, ML, portfolio/risk, order/execution logic, paper/live trading, and production deployment.

## 2. Current repository state

- Initial tree: only two uploaded DOCX specifications; no package, tests, Git repository, LEAN installation, QC credentials, or existing application code.
- Mandatory source documents: present and fully readable.
- Agent internet: available; the required official public-source review and QC API
  resolution are complete.
- Local QC/LEAN runtime: `NOT_VERIFIED`.
- Git revision: unavailable because this workspace is not a Git work tree; manifests must store `None`.
- Authoring began with `AGENTS.md`, then `.agent/PLANS.md`, then this plan, as required.
- Final local state: the required tree, generated sample ledger, and local manifest are
  present; all supported gates pass under Python 3.12.13. Target Python 3.11 and QC
  runtime execution remain blocked and are not counted as successful validation.

## 3. Source documents and authority

1. Active Lift 1 task.
2. `upload/Institutional_Systematic_Futures_Program_Master_Spec_v1.0(2).docx` (read in full; Master Specification v1.0, dated 2026-08-24).
3. `upload/Intraday_Alpha_Capture_Execution_Extension_v1.0_HE(2).docx` (read in full; Intraday Extension v1.0, dated 2026-08-25).
4. Current official QuantConnect documentation.
5. Current official QuantConnect/Lean, lean-cli, and LEAN Data Source SDK repositories.
6. Official public firm material.
7. Primary academic papers.

The active task narrows later source-document chapters and prohibits using them to implement later lifts.

## 4. Assumptions and blockers

- `ASSUMED_FOR_LOCAL_TEST_ONLY`: test fixtures may use synthetic prices, timestamps, symbols, multipliers, and ticks; they must not be described as certified market facts.
- `NOT_VERIFIED`: QC credentials, QC data entitlements, the exact installed LEAN version, and live/backtest parity.
- `BLOCKED`: full holiday and early-close certification requires a verified exchange calendar/data source and QC runtime evidence. Lift 1 implements versioned semantic windows and records this limitation.
- `BLOCKED`: actual ES/ZN/6E history, mapping events, rows, tick sizes, and multipliers cannot be claimed until the QC probe is executed in a credentialed QC/LEAN environment.
- No blocker prevents implementing and testing the standard-library core.

## 5. Dependency decisions

- Runtime core: Python 3.11 standard library only.
- Development-only and fully pinned, including transitives: `pytest` for invariant
  tests; `ruff` for format/lint; `pyright` for strict type checking; `nbformat` for
  deterministic notebook validation. `requirements.txt` records each transitive
  group’s purpose.
- `quantconnect-stubs`: add only if current Python 3.11 compatibility is verified from an official/current package source; otherwise omit and type-check QC boundaries with local exclusions and documented `object`/`TYPE_CHECKING` boundaries.
- No pandas in the core and no ML, database, web, DI, or distributed-computing dependencies.

## 6. Exact implementation sequence and file changes

### Milestone A — Governance and public evidence

Create, in order:

1. `AGENTS.md` — permanent authority, boundaries, commands, QC verification, time/units, no-silent-fallback, DoD.
2. `.agent/PLANS.md` — ExecPlan standard.
3. `docs/LIFT_1_EXECPLAN.md` — this living plan.
4. `docs/DECISION_LOG.md` — dated structured decisions.
5. `docs/ASSUMPTIONS_AND_BLOCKERS.md` — `VERIFIED`, `ASSUMED_FOR_LOCAL_TEST_ONLY`, `NOT_VERIFIED`, `BLOCKED`, `DEFERRED_TO_LIFT_2`.
6. `docs/PUBLIC_SOURCE_REVIEW.md` — official/primary sources in the required per-source format.
7. `docs/QC_API_RESOLUTION.md` — exact verified QC/LEAN symbols and unresolved items.

Acceptance: source documents are confirmed readable, every public claim has an official source or is marked blocked, and no QC code exists before API resolution.

### Milestone B — Package and deterministic domain core

Create packaging/scaffold files:

- `README.md`, `pyproject.toml`, `requirements.txt`, `.gitignore`.
- Package `__init__.py` files for every required package.
- Artifact directories with `.gitkeep` only.

Implement domain modules:

- `domain/enums.py`: exactly the seven required enums and values.
- `domain/errors.py`: exactly the ten required exception classes.
- `domain/serialization.py`: `canonicalize_for_json`, `canonical_json_bytes`, `sha256_hex`; reject naive datetimes, non-string mapping keys, unsupported objects, NaN/Infinity, and unstable representations.
- `domain/identifiers.py`: deterministic `make_run_id`, `make_experiment_id`, `make_lineage_hash`.
- `domain/schemas.py`: the ten required frozen/slotted records plus one dedicated public validator for each: `validate_raw_source_record`, `validate_point_in_time_datum`, `validate_certified_market_event`, `validate_market_definition`, `validate_session_window`, `validate_contract_snapshot`, `validate_dataset_certification`, `validate_experiment_record`, `validate_research_run_manifest`, `validate_data_probe_result`. Mapping fields are defensively normalized before record construction by explicit factory helpers where needed; records remain method-free.

Acceptance: package imports outside QC; deterministic serialization tests and schema validation compile/type-check.

### Milestone C — Configuration and point-in-time governance

Implement configuration:

- `config/markets.py`: exact ES/NQ/RTY/ZT/ZN/6E/6J/6B registry, only ES/ZN/6E enabled, `all_market_definitions`, `reference_market_definitions`, `get_market_definition`, `validate_market_registry`.
- `config/datasets.py`: five under-review dataset definitions and accessors; no signal certification.
- `config/research.py`: fixed Lift 1 probe dates, deterministic seed, and manifest configuration payload.
- `data/policies.py`: `DatasetPolicy` protocol; conservative QC futures policies that validate only universal timing/schema facts; `SyntheticCftcTimingPolicy` implementing Tuesday-observation/Friday-release principle with manual exception input and no claim of QC certification.
- `data/point_in_time.py`: `ensure_aware_utc`; `PointInTimeNormalizer.__init__` and `.normalize` with all ten invariants.
- `data/availability_gate.py`: heap-backed `AvailabilityGate` with `submit`, `release`, `pending_count`, `next_release_time`; deterministic tie key and duplicate/re-release protection.
- `data/quality.py`: small pure helpers for deterministic quality flags/status transitions; no thresholds or inferred validity.

Acceptance: naive time, impossible ordering, withholding, deterministic ties, and duplicate lineage tests pass.

### Milestone D — Sessions, contracts, and rolls

- `data/sessions.py`: `SessionEngine.__init__`, `classify`, `session_id`, `windows_for_market`; semantic ES/ZN/6E windows in local zones, cross-midnight handling, deterministic IDs. Holiday/early-close behavior remains explicitly uncertified.
- `data/contracts.py`: `FuturesContractManager.observe_contract_snapshot`, `current_snapshot`, `validate_symbol_relationship`; explicit observations only and as-of lookup.
- `data/rolls.py`: frozen/slotted `MappingObservation`, its validator, and `RollManager.observe_mapping`/`current_roll_state`; effective-time ordering and no future inference.

Acceptance: session determinism and future-mapping isolation tests pass.

### Milestone E — Experiment ledger and run manifest

- `ledger/experiment_ledger.py`: append-only hash-chained JSONL `ExperimentLedger`; atomic whole-file replacement under a same-directory temp file; duplicate ID rejection; pre-registration-before-decision; `read_all`; mutation detection in `verify_chain`; every row includes schema version.
- `ledger/run_manifest.py`: `RunManifestBuilder.build`; hash source documents, canonical configuration, dependency file bytes, deterministic ID/content hash, and explicit missing LEAN/Git values.
- `scripts/build_manifest.py`: deterministic local CLI producing `artifacts/manifests/lift_1_manifest.json` from explicit/fixed configuration, specification paths, dependency files, `lean_version=None`, `repository_revision=None`, and explicit UTC creation time policy.
- Seed `artifacts/ledgers/experiment_ledger.jsonl` with one pending pre-registration named “Reference Futures Data Availability and Contract Mapping Audit”, generated by a script/module call rather than hand-edited chain content.

Acceptance: duplicate experiment, chain mutation, and manifest determinism tests pass; script output validates against schema.

### Milestone F — Verified read-only QuantConnect boundaries

Only after `docs/QC_API_RESOLUTION.md` records every used API as `VERIFIED`:

- `qc_adapters/futures_registration.py`: isolated QC registration helpers using verified constants/enums/naming.
- `qc_adapters/probe_recorder.py`: read-only state collection and conversion to `DataProbeResult`; no trading API.
- Root `main.py`: thin `InstitutionalFuturesDataProbe(QCAlgorithm)` with only `initialize`, `on_data`, `on_symbol_changed_events`, and `on_end_of_algorithm`; fixed 2024-02-15 through 2024-03-25; ES/ZN/6E minute, extended hours, OI mapping, Backwards Ratio; logging summaries only.

If any required API remains unresolved, the affected runtime path will raise `UnverifiedQuantConnectApiError` or remain absent rather than pretending to run; this deviation and its consequence will be documented.

Acceptance: architecture scan finds no prohibited imports in core and no trading/Insight tokens in `main.py`; Python syntax is statically valid. QC execution is a separate runtime gate.

### Milestone G — Research support and notebooks

- `research_lib/quantbook_probe.py`: `add_reference_futures`, `request_reference_history`, `summarize_contract_history`, `export_probe_results`; QC types isolated behind verified adapter calls and raw `object` boundary.
- `research_lib/coverage_report.py`: pure extraction/summarization helpers for row/date/expiry/mapping/OI/missing-interval/session displays without trading statistics.
- `research_lib/export.py`: deterministic JSON export for small probe summaries only.
- `research_notebooks/01_data_state_research.ipynb`: thirteen required sections/cells, thin imports, fixed period, QC calls, session classification, JSON summary and manifest export, no return/signal/statistics/P&L logic.
- `research_notebooks/02_auction_mechanism_event_studies.ipynb` and `03_robustness_go_no_go.ipynb`: markdown-only shells with exact `NOT IMPLEMENTED IN LIFT 1` statement.
- Root `research.ipynb`: short index only.
- `scripts/validate_notebooks.py`: nbformat parsing, ordered section/token assertions, shell prohibition checks.

Acceptance: notebook validator passes; notebooks contain no duplicated business logic or prohibited Lift 2 execution.

### Milestone H — Bootstrap, documentation, and decisive tests

- `docs/MAC_M4_QC_BOOTSTRAP.md`: official commands only, ARM/Docker/LEAN caveats, manual login, minimal data use, version recording, no credentials.
- `scripts/bootstrap_mac_m4.sh`: idempotent prerequisite checks, `.venv`, pinned dev install, no login/secrets/cloud resources.
- `scripts/run_quality_checks.sh`: fail-fast checks in mandated order.
- Required test files and themes exactly as specified; combine related assertions inside those files without adding architectural layers.
- `docs/LIFT_2_HANDOFF.md`: interfaces/evidence only for Volume Profile, Auction State, corrected IMSI/ICM/IAE-L1, and candidate-event dataset.
- `docs/LIFT_1_COMPLETION_REPORT.md`: exact sixteen sections and one exact readiness value.

Acceptance: every supported quality command passes; unsupported QC runtime commands are `NOT_EXECUTED` with exact reason.

## 7. Verification commands

Run in this deterministic order:

```bash
python -m compileall systematic_futures main.py
ruff format --check .
ruff check .
pyright
pytest -q
python scripts/validate_notebooks.py
python scripts/build_manifest.py
```

Additional safe evidence commands:

```bash
bash -n scripts/bootstrap_mac_m4.sh scripts/run_quality_checks.sh
python -m pip check
rg -n "market_order|limit_order|stop_market_order|set_holdings|liquidate|emit_insights|Insight\(|PortfolioTarget\(" main.py
```

QC runtime execution is attempted only if LEAN CLI/runtime and credentials are demonstrably available. Otherwise it is `NOT_EXECUTED`, never passed.

## 8. Acceptance criteria

The task’s Definition of Done is incorporated verbatim by reference to the active Lift 1 prompt. Critical stopping conditions are: missing specification, unverified QC API in code, failed mandatory test, unresolved point-in-time behavior, unverifiable ledger chain, prohibited trading token, or undocumented assumption.

## 9. Progress checklist

- [x] Mandatory Master Specification located and fully read.
- [x] Mandatory Intraday Extension located and fully read.
- [x] `AGENTS.md` created first.
- [x] `.agent/PLANS.md` created second.
- [x] Initial living ExecPlan created third.
- [x] Decision log created fourth.
- [x] Assumptions/blockers register created fifth.
- [x] Public-source review created sixth.
- [x] QC API resolution complete.
- [x] Domain/config/PIT core complete and plan updated.
- [x] Sessions/contracts/rolls complete and plan updated.
- [x] Ledger/manifest complete and plan updated.
- [x] Verified QC boundaries/probe complete and plan updated.
- [x] Notebooks/bootstrap/docs complete and plan updated.
- [x] All supported quality gates passed.
- [x] Completion report and final reconciliation complete.

Progress log:

- 2026-08-26 — Milestone A complete: specifications reviewed; governance and official
  source/API evidence recorded before implementation code.
- 2026-08-26 — Milestones B–C complete: deterministic schemas, configuration,
  dataset policies, point-in-time normalizer, quality rules, and availability gate.
- 2026-08-26 — Milestones D–E complete: sessions, contracts, causal roll state,
  pre-registration ledger, sample record, and manifest builder.
- 2026-08-26 — Milestone F complete at the static boundary: verified QC registration,
  recorder, and four-method read-only probe source; runtime remains `NOT_EXECUTED`.
- 2026-08-26 — Milestones G–H complete: research helpers, four notebooks, bootstrap,
  documentation, and 14 decisive tests.
- 2026-08-26 — Final supported quality run passed; external Python 3.11/QC/calendar
  blockers reconciled and readiness set to `NOT_READY_FOR_LIFT_2`.

## 10. Decision log (plan-local)

- 2026-08-26: The fixed Lift 1 task structure overrides the broader Master project tree. No empty later-lift packages are created.
- 2026-08-26: Session windows will be conservative semantic research windows, not exchange-calendar certification. Holidays/early closes stay blocked.
- 2026-08-26: QC metadata values (tick/multiplier) remain probe outputs, never market-registry constants.
- 2026-08-26: Actual Git revision is `None` because the workspace is not a Git work tree.
- 2026-08-26: The pinned official LEAN evidence is commit `185c691`; lean-cli is
  release `1.0.228`. `lean project-create` is the canonical command.
- 2026-08-26: Backwards Ratio adjusted values use full-history adjustment and are
  restricted to identity/coverage inspection, not point-in-time signal use.
- 2026-08-26: `quantconnect-stubs` is omitted because no immutable current
  package-to-LEAN/Python compatibility mapping was found.
- 2026-08-26: A mapped-contract change is an event-instant `ROLL_TRANSITION`, then
  `POST_ROLL`; Lift 1 invents no persistent transition, pre-roll, or blackout window.
- 2026-08-26: The required sample is a non-forecast audit with no fabricated horizon.

## 11. Final reconciliation

All planned files were created in the required modules and directories. The only
additional visible inputs are the two supplied files under `upload/`; the only generated
non-placeholder artifacts are the required sample ledger and local manifest. No extra
production layer or later-lift executable module was added.

The final fail-fast local run passed compile, Ruff format, Ruff lint, strict Pyright,
14 tests, four-notebook validation, and manifest generation. Dependency integrity,
shell syntax, future-annotation, QC-boundary, and prohibited-token checks also passed.
The final manifest hash is
`b090f5284835305cc163e3683187849d9567d9cd272c28d7372622aea9651f3b`.

Unexecuted checks are target Python 3.11, LEAN/QC Research, the read-only probe,
Notebook 1 against actual data, local/cloud backtests, and live/backtest reconciliation.
The QC summary artifact is intentionally absent because no actual history was
retrieved. LEAN and repository revision are `None`, not placeholders.

Deviations are limited to the unavailable target interpreter/runtime, deliberate
omission of unverified QC stubs, and absence of runtime-produced probe data. Full
details, including corrected construction-time diagnostics, are in
`docs/LIFT_1_COMPLETION_REPORT.md`.

Final readiness decision: `NOT_READY_FOR_LIFT_2`.

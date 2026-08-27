# Lift 2 ExecPlan

Status: `IN_PROGRESS_QC_PENDING`
Started: 2026-08-27
Base commit: `3520c50f1eba674b074deabd7ca8b47320962b62`
Scope: causal market measurement and candidate-event observations only.

## Outcome contract

Lift 2 converts certified actual-contract trades into deterministic Profile, Auction,
IMSI, ICM, and IAE-L1 state, aligns snapshots with as-of semantics, and records
unlabeled candidate research events. It implements no outcome, Alpha, model,
portfolio, risk, execution, order, or L2 behavior.

## Subsystem plan

### 1. Governance, sources, and versioned policy

- Purpose: establish the permanent Lift 2 boundary and resolve every external API or
  numerical dependency before use.
- Existing files reused: `AGENTS.md`, `docs/PUBLIC_SOURCE_REVIEW.md`,
  `docs/QC_API_RESOLUTION.md`, `docs/DECISION_LOG.md`, `pyproject.toml`,
  `requirements.txt`.
- Files changed: the files above.
- Files added: this ExecPlan only.
- Invariants: official/primary sources only; NumPy is the sole numerical runtime
  dependency; no guessed QC API or market field.
- Tests: dependency/source guards and existing architecture checks.
- QC evidence: exact executing Python/NumPy/LEAN versions captured from cloud.
- Completion state: `COMPLETE_LOCAL`.

### 2. Measurement contracts and feature vocabulary

- Purpose: define immutable point-in-time inputs, snapshots, event records, and
  Profile/Auction/IMSI/ICM/IAE feature semantics v2.
- Existing files reused: `domain/enums.py`, `domain/research_contracts.py`,
  `config/feature_semantics.py`, `config/research.py`.
- Files changed: those existing files.
- Files added: `measurement/__init__.py`, `measurement/types.py`, and the
  QC-compatible single-source implementation `measurement/models.py`.
- Invariants: frozen/slotted records; aware UTC; exact actual contract and session;
  no outcome fields; v1 feature semantics remain unchanged.
- Tests: validation, source-schema outcome guard, v1 immutability, v2 status checks.
- QC evidence: serialized schema/version hashes included in runtime evidence.
- Completion state: `COMPLETE_LOCAL`.

### 3. Causal stream, bars, and local scale

- Purpose: ingest actual-contract trades, finalize session-anchored 5m/30m bars, and
  publish snapshots in causal boundary order.
- Existing files reused: `data/sessions.py`, `data/rolls.py`, `data/contracts.py`,
  point-in-time errors and serialization.
- Files changed: `data/sessions.py` only if `session_bounds` is required.
- Files added: `measurement/stream.py`.
- Invariants: no bar crosses contract/session/closure; late availability is never
  backdated; local scale uses only 12-24 prior completed 5m bars of one contract.
- Tests: bucket anchoring, future-tick isolation, boundary errors, scale warmup/reset.
- QC evidence: bar counts, boundary incidents, roll resets, bounded-state counters.
- Completion state: `COMPLETE_LOCAL`.

### 4. Volume Profile and Auction state

- Purpose: conserve trade volume in integer tick bins, deterministically compute POC
  and contiguous 70% Value Area, maintain bounded rolling profiles, compute primitive
  Auction features, and emit descriptive transitions once.
- Existing files reused: measurement contracts, session/roll state, canonical hashes.
- Files changed: none outside the measurement package.
- Files added: `measurement/profile.py` and the QC-compatible single-source
  implementation `measurement/volume_profile.py`.
- Invariants: actual TRADE ticks only; one root/contract/session per profile; no future
  tick; immutable final profile; no acceptance/rejection composite.
- Tests: conservation, POC tie, Value Area minimality/contiguity, boundaries, replay,
  rolling subtraction, transition deduplication/parents.
- QC evidence: profile/snapshot/finalization counts and invariant counters.
- Completion state: `COMPLETE_LOCAL`.

QC packaging note: cloud project `35697180` rejects nested `types.py` and
`profile.py`, and a `types` directory shadows Python's standard library. The two
directive-named files therefore remain thin public facades locally; the cloud runtime
uses byte-identical implementations from `models.py` and `volume_profile.py`. This is
an observed, version-recorded platform constraint rather than a second formula path.

### 5. IMSI descriptive measurement

- Purpose: forward-only VW-RSI, prior-session TOD adjustment, session VWAP distance,
  eigen-floor Mahalanobis state distance, nearest-state support, and rarity.
- Existing files reused: completed bars, session identity, deterministic snapshots.
- Files changed: none outside the measurement package.
- Files added: `measurement/imsi.py`.
- Invariants: no outcomes; current session excluded from TOD baseline; memories bounded
  to 30 sessions/300 states; 30-state covariance/rarity warmup.
- Tests: forward-only behavior, TOD leakage, VWAP reset, degeneracy, finite distance,
  prior-only rarity, prohibited-source terms.
- QC evidence: snapshot/warmup/support/quality counts and state hashes.
- Completion state: `COMPLETE_LOCAL`.

### 6. ICM descriptive measurement

- Purpose: compute scalar quadratic fair value, raw Z geometry, slope, curvature,
  robust residual scales, and regime ratio from completed 30m actual-contract bars.
- Existing files reused: market registry and measurement-policy configuration.
- Files changed: `config/research.py`.
- Files added: `measurement/icm.py`.
- Invariants: fixed market windows; scaled time index; `numpy.linalg.lstsq`; no
  repainting/winsorization/capping; reset on contract change; degenerate scale explicit.
- Tests: exact quadratic, scalar fair value, translation invariance, causal history,
  contract reset, degeneracy, prohibited behavior scan.
- QC evidence: snapshot/warmup/degeneracy counts and hashes.
- Completion state: `COMPLETE_LOCAL`.

### 7. IAE-L1 descriptive measurement

- Purpose: symmetric bullish/bearish three-bar gaps, exact geometry, bounded lifetime,
  close-based invalidation, first-retest events, and prior-session TOD volume Z.
- Existing files reused: 5m bars, local scale, event contracts.
- Files changed: none outside the measurement package.
- Files added: `measurement/iae.py`.
- Invariants: L1 only; no absorption claim; no thresholds/composite score; 48-bar
  expiry; first retest only; TOD history prior-session only.
- Tests: bullish/bearish symmetry, retest deduplication, wick/close invalidation,
  TOD leakage, gap-parent identity.
- QC evidence: gaps/retests/expiries/invalidations and quality counts.
- Completion state: `COMPLETE_LOCAL`.

### 8. Alignment, event generation, and coverage

- Purpose: as-of join snapshots, emit deterministic unlabeled candidate observations,
  enforce parent relationships/deduplication, and report aggregate breadth.
- Existing files reused: canonical hashing, domain errors, snapshot/event records.
- Files changed: `domain/research_contracts.py` only if a shared guard is required.
- Files added: `measurement/events.py`.
- Invariants: every attached snapshot has `available_at <= event available_at`; missing
  inputs remain `None`; duplicates raise; no outcome field or filtering by confluence.
- Tests: causal alignment, transition once, parents, POC crossing once, deterministic
  IDs, coverage counts, no outcome vocabulary.
- QC evidence: event family, parent, session, contract, month, alignment, and quality
  aggregates only.
- Completion state: `COMPLETE_LOCAL`.

### 9. QC runtime and research-client parity

- Purpose: adapt verified mapped-contract trade ticks into the same measurement core,
  run deep ES/ZN/6E replay and bounded all-eight smoke tests, and activate Notebook 02.
- Existing files reused: `main.py`, `qc_adapters/futures_registration.py`, market
  registry, Notebook 02, notebook validator.
- Files changed: those existing files.
- Files added: `qc_adapters/lift2_runtime.py`.
- Invariants: continuous root for mapping only; actual contract TRADE ticks for all
  measurements; one parameterized code path; bounded logs; zero trading actions.
- Tests: fake-boundary routing, tick filtering, source isolation, thin composition
  root, notebook business-logic guard.
- QC evidence: source/build/backtest IDs, versions, per-market counts, hashes, zero
  actions, and bounded samples.
- Completion state: `SOURCE_COMPLETE_QC_PENDING`.

### 10. Certification, manifest, and handoff

- Purpose: validate compact runtime/coverage evidence, answer all eleven questions,
  and publish byte-identical runtime source plus evidence commits.
- Existing files reused: quality sequence, blockers register, README, Lift 1 evidence
  conventions.
- Files changed: `scripts/run_quality_checks.sh`, README, blockers/decision documents.
- Files added: four required Lift 2 artifacts and
  `docs/LIFT_2_COMPLETION_REPORT.md`.
- Invariants: no raw ticks/candidate panel in Git; every artifact has source/config and
  content hashes; runtime and evidence SHAs distinct when required.
- Tests: manifest/evidence hash validation, required-field checks, all source guards.
- QC evidence: deep and smoke run records from project `35697180`.
- Completion state: `PENDING`.

## Supported quality sequence

```bash
python -m compileall systematic_futures main.py
ruff format --check .
ruff check .
pyright
pytest -q
python scripts/validate_notebooks.py
python scripts/build_manifest.py
```

The existing `scripts/run_quality_checks.sh` remains the sole composition command and
will be extended only to validate the required Lift 2 manifest/evidence contracts.

## Progress log

- 2026-08-27 — Base/remote SHA and clean worktree verified; controlling directive and
  repository rules read; permanent AGENTS boundary updated; initial ExecPlan created.
- 2026-08-27 — Mandatory QC/firm/academic source review appended; exact QC tick and
  actual-contract APIs plus NumPy 1.26.4 resolved before production use.
- 2026-08-27 — Contracts, Profile/Auction, IMSI, ICM, IAE-L1, stream, as-of events,
  coverage, QC adapter, and Notebook 02 completed with the authorized minimal module
  footprint. Full local sequence passed twice: 67 tests, strict Pyright, Ruff,
  notebook validation, and deterministic source rebuild check.

## Source acceptance matrix

| Area | Reused | Added now | Explicitly rejected |
|---|---|---|---|
| Identity/time | `SessionEngine`, `RollManager`, UTC/PIT errors, canonical hashes | one `session_bounds` method | second calendar, inferred clocks |
| Market data | existing eight-root registry and continuous mapping | verified actual-contract tick subscription | continuous price measurement, quote volume |
| Measurement | existing immutable-domain conventions | eight authorized `measurement/` files | factories, service/repository layers, notebook formulas |
| Numerical | existing Python 3.11 contract | NumPy 1.26.4 only | Pandas/SciPy/sklearn and heuristic shrinkage claims |
| Research events | existing lineage/hash discipline | causal references, immutable descriptive events, aggregate coverage | outcomes, confluence filter, repeated-bar pseudo-events |
| Runtime | existing registration/QC boundary | one parameterized `Lift2Runtime` | second source tree, per-market algorithms, trading APIs |

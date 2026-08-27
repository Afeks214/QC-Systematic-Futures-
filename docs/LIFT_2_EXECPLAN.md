# Lift 2 ExecPlan

Status: `MATH_READY_FOR_LIFT_2_RUNTIME`
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
  Profile/Auction/IMSI/ICM/IAE feature semantics v4, while preserving v1-v3.
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

### 3. Causal stream, bars, and shared ATR

- Purpose: ingest actual-contract trades, finalize session-anchored 5m/30m bars, and
  publish snapshots in causal boundary order.
- Existing files reused: `data/sessions.py`, `data/rolls.py`, `data/contracts.py`,
  point-in-time errors and serialization.
- Files changed: `data/sessions.py` only if `session_bounds` is required.
- Files added: `measurement/stream.py`.
- Invariants: no bar crosses contract/session/closure; late availability is never
  backdated; `ATR_5M_24` is the arithmetic mean of exactly 24 true ranges and is
  withheld before full warmup.
- Tests: independent OHLCV aggregation, bucket anchoring, future-tick isolation,
  boundary errors, exact true range, 23/24 warmup, and contract reset.
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

- Purpose: forward-only zero-seeded VW-RSI, 30-prior-session TOD adjustment,
  completed-bar session VWAP percentage distance, prior-only EWMA diagonal-shrinkage
  Mahalanobis state distance, embargoed nearest-state support, and rarity.
- Existing files reused: completed bars, session identity, deterministic snapshots.
- Files changed: none outside the measurement package.
- Files added: `measurement/imsi.py`.
- Invariants: no outcomes; current session excluded from the full 30-session TOD
  baseline; memories bounded to 30 sessions/300 states; covariance inputs prior-only;
  seven completed 30m bars embargoed from neighbor summaries; degenerate covariance
  and invalid covariance geometry fail closed.
- Tests: exact VW-RSI recurrence, TOD boundary/leakage, bar-VWAP reset and units, exact
  EWMA shrinkage arithmetic, collinearity/degeneracy, exact neighbor embargo boundary,
  prior-only rarity, online/batch parity, and prohibited-source terms.
- QC evidence: snapshot/warmup/support/quality counts and state hashes.
- Completion state: `COMPLETE_LOCAL`.

### 6. ICM descriptive measurement

- Purpose: compute scalar quadratic fair value, raw/capped/effective Z geometry,
  per-bar slope/curvature, robust residual scales, and regime ratio from completed
  30m actual-contract bars.
- Existing files reused: market registry and measurement-policy configuration.
- Files changed: `config/research.py`.
- Files added: `measurement/icm.py`.
- Invariants: fixed market windows; normalized time index; production solver is a
  precomputed `numpy.linalg.pinv`; `lstsq` is an independent test oracle; Z cap is
  4.5; flat and `R > 1.5` guards preserve raw state; contract reset is mandatory.
- Tests: exact quadratic, pinv/lstsq differential parity at every warmed observation,
  scalar fair value, chain-rule units, translation/scaling invariance, cap/guards,
  causal history, contract boundary, and degeneracy.
- QC evidence: snapshot/warmup/degeneracy counts and hashes.
- Completion state: `COMPLETE_LOCAL`.

### 7. IAE-L1 descriptive measurement

- Purpose: symmetric bullish/bearish three-bar gaps, exact formation gates/quality,
  bounded lifecycle, close-based invalidation, first-test events, prior-session TOD
  volume Z, exponential decay, and the specified guarded L1 proxy score.
- Existing files reused: 5m bars, shared ATR, event contracts.
- Files changed: none outside the measurement package.
- Files added: `measurement/iae.py`.
- Invariants: L1 proxy only; no observed OFI/institutional fact; gates are strict
  `Zdisp > 1.5`, `Edisp > 0.6`, `Zgap > 0.3`; score threshold 2.1; 48-bar expiry;
  first event only; TOD history prior-session only.
- Tests: exact formation/score vectors, full-bracket decay, price-reflection symmetry,
  zero-range/body stress, state transitions, TOD leakage, and gap-parent identity.
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
- Completion state: `SOURCE_RECERTIFIED_QC_REPLAY_PENDING`.

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
- 2026-08-27 — User-supplied IMSI RSD v1 reconciled into descriptive IMSI v2: the
  explicit forward-only EWMA diagonal-shrinkage formula, 30-session TOD baseline,
  seven-bar neighbor embargo, causal trade-clock guards, and snapshot diagnostics were
  added. Predictive MES, labels, calibration, Alpha, FSM, and execution remain outside
  Lift 2. The later full mathematical reconciliation below supersedes its provisional
  trade-tick VWAP and compatibility-helper decisions.
- 2026-08-27 — Stop-and-reconcile directive completed against the three supplied
  indicator specifications. The single reconciliation matrix is complete; 25 marked
  math tests cover 14 analytic, 9 differential, 11 metamorphic, 10 causality, and 16
  stress memberships; the complete Python 3.11 gate passes 89 tests. Whole-engine
  hashes match at 100/250/500/1000/1500 observations of the frozen 2,000-observation
  stream. Result: `MATH_READY_FOR_LIFT_2_RUNTIME`.
- 2026-08-27 — QC builds through `b77ac2-941e38` failed before data delivery. Direct
  inspection proved the cloud `domain/enums.py` path contained `data/policies.py`
  bytes. Runtime-facing initializers were also made side-effect free, and the hashed
  runtime-source closure was expanded to every deployed transitive file while
  excluding the two documented local-only filename facades. Indicator mathematics
  remain frozen; exact cloud resynchronization and fresh replay are pending.
- 2026-08-27 — Isolated-editor synchronization and an independent reopen/read audit
  established byte equality for all 34 deployed runtime files. QC build
  `4dabc4-360f32` passed initialization; ES smoke backtest
  `69edd3f1bd02d166f9170c6223349be6` then exposed a missing five-minute bucket inside
  one semantic session. The exact three-consecutive-bar IAE predicate remains frozen;
  the state engine now resets formation/active-gap state and records
  `IAE_BAR_GAP_RESET`. The complete local suite was recertified before replay.
- 2026-08-27 — Corrected source build `7de0cd-7f0de9` completed the bounded ES
  smoke run (`cd7b3f083a248def2d4720ae38613f5a`) over 16,673,720 delivered points,
  including 1,223,512 admitted mapped-contract trades, required bar/profile/indicator
  outputs, 65 unique candidates, and zero orders, Insights, or PortfolioTargets. The
  full ES deep run from build `a5f1b8-7f0de9` is in progress; remaining deep and
  all-eight rows stay explicitly uncertified until their result records complete.
- 2026-08-27 — The pre-floor ES deep run completed, but ZN deep backtest
  `0f2c86d773425e9db2b6f81ad3f0a90b` then exposed a valid locked/flat bar with
  zero true range. Reinspection of authoritative IAE Cell 02 found the explicit
  `atr.clip(lower=1e-6)` locked-market clause. Zero TR observations are now retained;
  after 24 ranges the arithmetic ATR is floored at `1e-6` native price units. The
  shared version is `atr_5m_24_arithmetic_tr_floor_1e-6_v2`; all 89 tests and the five
  independent math classes pass. All pre-floor QC runs are superseded for final
  certification, and the required matrix will restart from the recertified source.

## Source acceptance matrix

| Area | Reused | Added now | Explicitly rejected |
|---|---|---|---|
| Identity/time | `SessionEngine`, `RollManager`, UTC/PIT errors, canonical hashes | one `session_bounds` method | second calendar, inferred clocks |
| Market data | existing eight-root registry and continuous mapping | verified actual-contract tick subscription | continuous price measurement, quote volume |
| Measurement | existing immutable-domain conventions | eight authorized `measurement/` files | factories, service/repository layers, notebook formulas |
| Numerical | existing Python 3.11 contract | NumPy 1.26.4 and disclosed EWMA diagonal shrinkage | Pandas/SciPy/sklearn and false formal Ledoit-Wolf claims |
| Research events | existing lineage/hash discipline | causal references, immutable descriptive events, aggregate coverage | outcomes, confluence filter, repeated-bar pseudo-events |
| Runtime | existing registration/QC boundary | one parameterized `Lift2Runtime` | second source tree, per-market algorithms, trading APIs |

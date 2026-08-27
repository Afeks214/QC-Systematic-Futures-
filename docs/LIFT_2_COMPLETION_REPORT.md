# Lift 2 Completion Report

## 1. Executive Result

Status: `SOURCE_FORENSICALLY_CLOSED_QC_MATRIX_PENDING`; the required QC matrix must be
replayed from the source commit created after this report is reconciled.

Lift 2 implements one causal, actual-contract measurement path for Profile/Auction,
IMSI StateCore, ICM, IAE-L1, aligned candidate events, and aggregate coverage. It
contains no forecast, outcome, Alpha, position, portfolio, risk, execution, or order
behavior. Engineering correctness is not evidence of predictive value or profitability.

## 2. Base Commit and Final Commit

- Directive base: `3520c50f1eba674b074deabd7ca8b47320962b62`.
- Math-certified commit: `835c753f18ef235358fcb91231435b5182312d50`.
- Source-forensic commit: `PENDING_SOURCE_COMMIT`.
- QC runtime source commit: `PENDING_SOURCE_COMMIT`.
- Final evidence commit: `PENDING_QC_MATRIX`.

## 3. Files Changed

The production footprint is limited to the existing configuration/domain/session
boundaries, one `measurement/` package, the thin QC adapter and composition root, and
the existing research/certification surfaces. `state_models.py` is the stable facade
over the single-source `measurement_records.py` and `measurement_snapshots.py` modules;
`volume_profile.py`, `imsi.py`, `icm.py`, `iae.py`, `events.py`, and `stream.py` each
own one current measurement responsibility. The local `profile.py` and `types.py`
files are import facades required by existing notebook names and are excluded from the
QC deployment where those basenames collide with platform modules.

## 4. Public Sources Reviewed

The implementation uses the three supplied indicator specifications by exact SHA-256,
the program master/extension specifications, current official QuantConnect futures and
statistics documentation, official LEAN/lean-cli source, NumPy 1.26.4 documentation,
and the primary numerical/statistical sources recorded in
`docs/LIFT_2_MATH_RECONCILIATION.md` and `docs/PUBLIC_SOURCE_REVIEW.md`. No unrecorded
QC name or institutional convention was inferred.

## 5. Measurement Architecture

The QC boundary uses a continuous future only for mapping and admits only TRADE ticks
from the currently mapped actual contract. The standard-library core owns contract,
session, availability, roll, and error semantics. One `MeasurementStream` advances
session-anchored bars, profiles, Auction state, IMSI, ICM, IAE-L1, alignment, and
candidate events in causal order. Every output is immutable, versioned, and hashable.

## 6. Volume Profile Certification

`volume_profile_math_v2` uses an exact native-tick lattice, admitted-volume
conservation, deterministic POC ties, and the disclosed
`CONTIGUOUS_POC_EXPANSION_V1` value-area policy. Snapshot identity includes
measurement time. Suspicious, nonpositive, off-grid, duplicate-source, late, and
out-of-order ticks are quarantined; absent reliable source identity is recorded as
deduplication-unverifiable rather than guessed.

## 7. Auction-State Certification

Auction location, transition counts, POC migration, re-entry, and the explicitly named
completed-bar-close ratio use same-contract, same-session, completed bars and the
shared `ATR_5M_24_ARITHMETIC_TR_FLOOR_1E-6_V2` scale. TPO/residence time is not
implemented. Current POC has raw tick and normalized distances; every migration
feature names its Profile reference.

## 8. IMSI Measurement Certification

`imsi_state_core_math_v3|ewma_diagonal_shrinkage_spec_v1` implements zero-seed
volume-weighted RSI, prior-session time-of-day adjustment, bar-volume session VWAP,
the explicitly named project shrinkage estimator, Mahalanobis state distance, and
embargoed prior-state neighbors. MES/outcomes and regime-conditioned limits remain
deliberately deferred.

## 9. ICM Certification

`icm_quadratic_geometry_math_v3|pinv_solver_v1` uses the normalized oldest-minus-one
to current-zero coordinate, pseudoinverse least squares, scalar current fair value,
per-bar chain-rule derivatives, OLS/MAD residual scales, and separately retained raw,
capped, and regime-guarded Z measurements, plus causal lag-1 residual autocorrelation
and local-scale fair-value distance.

## 10. IAE-L1 Certification

`iae_l1_absorption_math_v2` implements exact mirrored bullish/bearish three-bar gap
geometry, strict formation gates, exact gap-ID lifecycle joins, prior-session
time-of-day volume context, raw/bounded close and volume-score inputs, per-gap retest
snapshot lineage, and full-bracket exponential score decay. Same-session
missing five-minute buckets reset formation/gap state with `IAE_BAR_GAP_RESET`; the
three-consecutive-bar formula is unchanged.

## 11. Multi-Horizon Alignment

As-of joins require `available_at_utc <= event.available_at_utc`, exact root, actual
contract and session identity, and the latest eligible snapshot only. Presence,
freshness, and mathematical readiness are separate fields; component and blocking
quality retain source provenance. The 2,000-observation frozen stream has identical
full-run and independently truncated hashes at 100, 250, 500, 1,000, and 1,500
observations, including Synergy snapshots.

## 12. Candidate Event Dataset

Candidate records contain deterministic identity, causal measurement references,
quality state, and parent excursion links only. They contain no label, horizon return,
P&L, forecast, rank, or execution field. Duplicate identities raise rather than merge.

## 13. Coverage Results

All earlier ES coverage belongs to superseded source. Full deep and all-eight aggregate
coverage is `PENDING_QC_MATRIX`. Every candidate will be retained; readiness and
missing-component counts are explicit, and low rare-event frequency alone will not be
treated as an engineering failure.

## 14. QC Runtime Evidence

- Project: `35697180` (`Geeky Sky Blue Pig`).
- LEAN: `2.5.0.0.18036`, master `v18036`.
- Cloud Python/NumPy: `3.11.14` / `1.26.4`.
- Source-forensic runtime tree hash:
  `43535ea8f01832b5b8222a1038399cef2edb8abf0c5a9dda48f7e199cd5a7008`.
- Pre-floor ES smoke/deep integration runs completed but are superseded and cannot
  qualify final evidence.
- ZN deep backtest `0f2c86d773425e9db2b6f81ad3f0a90b` exposed a valid zero true range in a locked
  bar. The source specification requires retaining that observation and flooring the
  warmed ATR at `1e-6`; the formula, version, reference vector, prefix certificate,
  and local suite were recertified before replay.
- Post-reconciliation replay `cd72b8ce4944656538ff443fd2d1f213` exposed an IAE
  ID collision when a first retest and a new formation occurred on the same bar. The
  identity now includes the changed aggregate `active_gap_count`; the deterministic
  reproducer and full local suite pass before corrected build `f3b3ae-94b66a`.
- Recertified ES/ZN/6E deep matrix: `PENDING_QC_MATRIX`.

The superseded ES smoke result contains 1,223,512 admitted trade ticks, 828 five-minute bars,
138 thirty-minute bars, 828 Auction/IAE snapshots, 137 IMSI snapshots, 69 ICM
snapshots, 13 finalized profiles, and 65 candidate events. Its measurement hash is
`59f1f65bed73dd980b1de4d1d33f231293ae92119ec59cffec584c9b5a0e6999`.

## 15. All-Eight Smoke Results

All eight roots require recertified-source smoke replay. The prior ES result remains
integration evidence only and is not part of the final acceptance matrix.

## 16. Quality Results

Python 3.11 local gate: compile PASS; Ruff format/check PASS; strict Pyright PASS;
100 tests PASS; 4 notebooks PASS; deterministic source rebuild PASS. The marked math
cases contain 19 analytic, 9 differential, 14 metamorphic, 14 causality, and 20 stress
memberships.

## 17. Performance / Memory Observations

The superseded ES smoke run completed in 432.51 seconds at approximately 39,000 data points per
second over 16,673,720 delivered points. Quote ticks were explicitly ignored
(15,404,411) while trade ticks were retained. No reliable peak-memory measurement was
emitted, so none is claimed.

## 18. Deviations

- The verified high-level actual-contract subscription supplies trade and quote ticks;
  the adapter filters `TickType.TRADE` explicitly and counts ignored quotes. It does
  not call an unverified internal trade-only subscription API.
- The authenticated web result surface is the execution/evidence path. The installed
  official LEAN CLI is version 1.0.228 but the local directory has no authenticated
  `lean.json`; no credential or persistent access was created.
- QC basename collisions require the two documented local-only facade exclusions;
  canonical implementations are deployed and byte-audited.

## 19. Remaining Limitations

The recertified QC matrix and final immutable evidence artifacts remain pending. IMSI MES,
forward outcomes, acceptance/rejection scores, true order-book OFI/MLOFI, predictive
models, costs, portfolio/risk, execution, paper trading, and live trading are outside
Lift 2. Deterministic measurement does not establish that any event is economically
useful.

## 20. Answers to the 11 Lift Questions

| Question | Result | Evidence |
|---|---|---|
| Contract/session integrity | YES LOCAL / PENDING QC | session leakage/boundary tests; QC matrix pending |
| Volume Profile correctness | YES | math reconciliation and 99-test gate |
| Cross-market normalization | YES LOCAL / PENDING QC | ES-like/ZN-like dimensional oracle; all-eight QC pending |
| Auction transitions | YES | analytic/causal tests and ES runtime counts |
| IMSI state integrity | YES | exact spec reconciliation and independent oracles |
| ICM integrity | YES | pinv/lstsq differential and numerical stress tests |
| IAE symmetry/integrity | YES | mirror, lifecycle, TOD, and missing-bar tests |
| Causal alignment | YES | as-of guards and whole-engine prefix equivalence |
| Candidate dataset | YES | deterministic schema/ID/duplicate/outcome guards |
| Coverage/breadth | PENDING | full candidate-coverage artifact |
| QC parity / zero actions | PENDING | completed 3+8 run matrix |

## 21. Lift 3 Readiness

`NOT_READY_FOR_LIFT_3` while the mandatory QC matrix and hashed final evidence set are
incomplete. This status can change only after every runtime, zero-action, quality,
manifest, evidence, commit, and remote-SHA gate passes.

## Mathematical Specification Certification

| Module | Spec parity | Oracle | Metamorphic | Causality | Numerical | Result |
|---|---|---|---|---|---|---|
| Profile/Auction | PASS | PASS | PASS | PASS | PASS | PASS |
| IMSI StateCore | PASS | PASS | PASS | PASS | PASS | PASS |
| ICM | PASS | PASS | PASS | PASS | PASS | PASS |
| IAE-L1 | PASS | PASS | PASS | PASS | PASS | PASS |
| Stream | PASS | PASS | PASS | PASS | PASS | PASS |

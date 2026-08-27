# Lift 2 Handoff

Status: interfaces and required evidence only. **Nothing in this document is an
implemented module or authorization to begin Lift 2.**

## Volume Profile

Required interface evidence:

- Versioned input contract keyed by root, actual contract, session ID, event time,
  usable-from time, price units, volume units, and lineage hash.
- Explicit rules for tick-to-price bins, partial-session cutoffs, roll separation,
  missing intervals, resets, holidays, and early closes.
- A causal replay test showing that every included observation was usable at the
  snapshot time and that old/new contracts are never pooled implicitly.
- Official product metadata and certified session calendars for every enabled market.

## Auction State

Required interface evidence:

- Versioned immutable snapshot consuming certified profile inputs without owning
  session, contract, or availability logic.
- A finite, named state vocabulary with explicit missing/unknown behavior and no
  thresholds presented as institutional facts.
- Deterministic lineage back to profile snapshot, contract snapshot, session policy,
  code revision, and configuration hash.
- Focused tests for partial sessions, roll transitions, stale inputs, and replay.

## Corrected IMSI

Required interface evidence:

- A specification-level definition of inputs, units, timing, expected direction,
  missingness, and invalidation conditions.
- Causal feature-generation proof, with no full-sample normalization or future bars.
- Pre-registered alternatives and ablations on a candidate-event dataset.
- Point-in-time replay and cross-market robustness evidence before any signal claim.

## Corrected ICM

Required interface evidence:

- Exact scalar/vector shapes, units, numerical-conditioning rules, and immutable
  versioned input/output schemas.
- Explicit interaction rationale and ablation plan; no automatic feature explosion.
- Tests for type/shape, pathological values, missing data, causality, and determinism.
- Pre-registration and certified source datasets before evaluation.

## Corrected IAE-L1

Required interface evidence:

- Symmetric long/short definitions, exact trigger/anchor join keys, and provisional
  thresholds clearly labeled as hypotheses.
- Time-of-day reference statistics computed from prior completed days only.
- Explicit event, feature, availability, and executable-entry clocks.
- Tests for gaps, stale anchors, missing joins, direction symmetry, and PIT replay.

## Candidate-event dataset

Required interface evidence:

- Append-only candidate records created before labels, model selection, portfolio,
  risk, or execution decisions.
- Stable event ID, root, actual contract, continuous identity, roll/session state,
  candidate time, usable feature snapshot time, data-quality state, and lineage.
- Certified de-duplication/clustering rules and explicit eligible-but-excluded reasons.
- Pre-registered label contract proving next-executable-entry semantics, but no label
  implementation until separately authorized.

## Entry gate for Lift 2

Lift 1's entry gate is satisfied: the real QC futures and CFTC probes completed,
reference evidence was reviewed, Python 3.11 checks pass, and the session matrix is
certified against its pinned official LEAN calendar version. Starting Lift 2 still
requires a separate explicit authorization and must retain every dataset limitation
recorded by the final certification matrix. This handoff contains no executable stubs,
Profile logic, Alpha logic, labels, statistics, positions, risk, or orders.

# Lift 2 Completion Report

## 1. Executive Result

Status: `LIFT_2_COMPLETE_MEASUREMENT_ONLY`.

The required Lift 2 measurement scope is closed end to end. One causal,
actual-contract path measures Profile/Auction, IMSI StateCore, ICM and IAE-L1,
aligns their point-in-time snapshots, and records unlabeled candidate events. The
final QuantConnect matrix contains 3/3 deep replays and 8/8 smoke replays, all
completed under LEAN `2.5.0.0.18039`, CPython `3.11.14` and NumPy `1.26.4`.
Every run reports exactly zero Orders, Insights and PortfolioTargets.

This is engineering and measurement certification only. It is not evidence of
predictive value, alpha, profitability, execution quality, live readiness or
investment suitability.

## 2. Immutable Commit Binding

- Directive base: `3520c50f1eba674b074deabd7ca8b47320962b62`.
- Math-certified source lineage: `835c753f18ef235358fcb91231435b5182312d50`.
- Exact QC runtime source: `ba11355a2dd8f150ad4c7a1a4ff5c457cabfc4c5`.
- Separately committed 11-run evidence set:
  `359333ba2ccc5f810906f9c7631b625deb3cd454`.
- Runtime source-tree hash:
  `cb48ca4b995bbb28f579fee1542076465308792105cc56a2d0f9b16f4d7d0f32`.
- Test-result contract hash:
  `49f7768d8da93b481464c46bdcb64b0b112da5aefbc197ced8f7f414cd1e3df9`.

The manifest uses a two-phase binding: it names the immutable source commit and the
later immutable evidence commit. The commit containing the manifest/report cannot
contain its own SHA and is therefore verified against remote `main` at handoff.

## 3. Source and Cloud Forensics

The local-to-cloud runtime closure contains 36 files. Every deployed file was reopened
from the authenticated QC editor and compared to the local runtime source. The audit
also removed obsolete cloud-only duplicate/staging trees and repaired the cloud
`domain/serialization.py` path, which had contained unrelated bytes.

Current LEAN master `v18039` compiles every Python file in the QC project. The
compatibility commit removed postponed-annotation imports from deployed files and
quoted two forward references. Its diff contains 2 insertions and 75 deletions, has
SHA-256
`595822a0529cb4708ab8d0326d00e63f3219806296ad1095cd79aec4297fe149`,
and changes no indicator formula or measurement policy.

QC free-tier projects cannot pin an older engine build. “Always use Master Branch” was
disabled and verified immediately before each qualifying launch; every final result
ran on the then-current `2.5.0.0.18039` engine and a build with the same source
signature `9f6d2a`.

## 4. Measurement Boundary

The continuous future is used only for causal contract mapping. Measurement inputs are
TRADE ticks from the currently mapped actual contract. Quote ticks are counted and
ignored. Session, contract, availability, roll and data-quality identities are carried
through immutable records.

Lift 2 contains no future outcomes, labels, forecasts, Alpha, ML, confluence filter,
position sizing, portfolio construction, risk allocation, execution, order creation or
L2 order-book behavior.

## 5. Certified Components

- Volume Profile `volume_profile_math_v2`: exact native-tick lattice, volume
  conservation, deterministic POC ties, contiguous 70% Value Area and immutable
  finalized profiles.
- Auction state: completed-bar location and transition measurements, explicit Profile
  references and shared causal ATR normalization; no TPO/residence-time substitute.
- IMSI
  `imsi_state_core_math_v3|ewma_diagonal_shrinkage_spec_v1`: zero-seed VW-RSI,
  prior-session TOD context, bar-volume session VWAP, prior-only covariance geometry,
  seven-bar neighbor embargo and bounded state.
- ICM `icm_quadratic_geometry_math_v3|pinv_solver_v1`: normalized quadratic geometry,
  scalar fair value, chain-rule slope/curvature, residual scales, regime guards,
  residual autocorrelation and local-scale distance.
- IAE-L1 `iae_l1_absorption_math_v2`: mirrored three-bar gaps, strict gates, exact
  lifecycle/retest lineage, prior-session TOD context, bounded proxy score and
  full-bracket decay.
- Alignment and candidates: same root/actual contract/session, as-of availability,
  deterministic IDs, explicit presence/freshness/readiness and no economic outcome
  columns.

## 6. Causality and Mathematical Evidence

The marked suite contains 19 analytic, 9 differential, 14 metamorphic, 14 causality
and 20 stress memberships. The 2,000-observation frozen stream has identical
independently truncated and full-run prefix hashes at 100, 250, 500, 1,000 and 1,500
observations.

- Reference-vector hash:
  `94db8a2e6c937d1eb176fc93816cd0573d09b17eceeaeca3669182a820edfbc5`.
- Prefix-equivalence hash:
  `152cd314c2f8b70ef3b4216f497925dcec91f66e725b52d30b0cf55aee547453`.
- Ordered QC parity-matrix hash:
  `e1485c87fa1bb16621823b8a96bb3d23a0c258d2c6914aa5574eef508a2174b6`.

## 7. QuantConnect Runtime Environment

- Project: `35697180` — `Geeky Sky Blue Pig`.
- LEAN: `2.5.0.0.18039`.
- QC Python / NumPy: `3.11.14` / `1.26.4`.
- Deep period: 2024-02-15 through 2024-03-25.
- Smoke period: 2024-03-04 through 2024-03-06.
- Aggregate delivered data points: 281,509,041.
- Aggregate chain observations: 270,664,266.
- Aggregate admitted trade ticks: 15,990,378.
- Aggregate unlabeled candidate events: 1,771.

## 8. Final Deep Replay Matrix

| Root | Build ID | Backtest ID | Contracts | Delivered points | Trade ticks | 5m / 30m bars | Final profiles | IMSI / ICM | Candidates | Actions |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| ES | `3d5184-9f6d2a` | `21ff0c9f0cac03d13b33befc122aa917` | 2 | 141,651,187 | 9,448,992 | 7,692 / 1,282 | 120 | 1,280 / 1,144 | 585 | 0 / 0 / 0 |
| ZN | `5c2681-9f6d2a` | `c15ae044a2f962388a9f175e1af29bc0` | 2 | 49,248,976 | 2,211,398 | 7,457 / 1,244 | 117 | 1,242 / 966 | 490 | 0 / 0 / 0 |
| 6E | `5e83ab-9f6d2a` | `d716f44851474e4511d43a6c346c47c8` | 2 | 33,115,011 | 893,808 | 6,839 / 1,260 | 120 | 1,258 / 1,042 | 351 | 0 / 0 / 0 |

“Actions” is Orders / Insights / PortfolioTargets.

## 9. Final All-Eight Smoke Matrix

| Root | Build ID | Backtest ID | Delivered points | Trade ticks | 5m / 30m bars | Final profiles | IMSI / ICM | Candidates | Actions |
|---|---|---|---:|---:|---:|---:|---:|---:|---|
| ES | `41268e-9f6d2a` | `396c13acd52ad20d76ec6025f24d3119` | 16,673,720 | 1,223,512 | 828 / 138 | 13 | 137 / 69 | 56 | 0 / 0 / 0 |
| NQ | `0a7efa-9f6d2a` | `2daca214cf256dffc1988c6615c9429e` | 18,841,760 | 1,325,986 | 828 / 138 | 13 | 137 / 79 | 42 | 0 / 0 / 0 |
| RTY | `210344-9f6d2a` | `8c9fd19f6479bacc778ade7e2845a273` | 6,687,462 | 268,350 | 828 / 138 | 13 | 137 / 69 | 74 | 0 / 0 / 0 |
| ZT | `0c71f2-9f6d2a` | `54ea7f6530e098c5cc6d1504b3fa5078` | 2,153,627 | 94,752 | 809 / 139 | 13 | 138 / 0 | 57 | 0 / 0 / 0 |
| ZN | `cc0106-9f6d2a` | `28c8ff85490944cb2ea87691fb596015` | 5,269,368 | 259,897 | 826 / 139 | 13 | 138 / 0 | 43 | 0 / 0 / 0 |
| 6E | `ac7eda-9f6d2a` | `4ab79439f117c3d67b72d84cc42309ca` | 4,149,445 | 111,926 | 828 / 138 | 13 | 137 / 29 | 30 | 0 / 0 / 0 |
| 6J | `939fe8-9f6d2a` | `d6a7274b5418553ad826dfee1c8930c8` | 1,994,218 | 93,967 | 828 / 138 | 13 | 137 / 19 | 14 | 0 / 0 / 0 |
| 6B | `c8e086-9f6d2a` | `e76194f4e91cfecbd655f6beaf0ea457` | 1,724,267 | 57,790 | 826 / 138 | 13 | 137 / 29 | 29 | 0 / 0 / 0 |

Zero ICM snapshots in the short ZT/ZN smoke windows are preserved as explicit
`ICM_WINDOW_WARMUP`, not imputed. Deep ZN contains 966 ICM snapshots and 936
ready states, establishing the longer-window path.

## 10. Candidate Coverage Result

All 1,771 events are unique and retained. Every final run reconciles
`raw_event_count == unique_event_count == candidate_events_total`, and
`inputs_ready + not_ready == total`.

No event in these bounded replay windows reached the complete mathematical-readiness
contract. This is explicitly recorded as 1,771 not-ready/quality-blocked observations,
with component-level missingness and quality codes; no row was silently promoted,
dropped or relabeled. This does not invalidate Lift 2 descriptive measurement. It does
mean the current evidence is not an eligible predictive-research sample until longer
history or the applicable readiness conditions are satisfied.

## 11. Evidence Artifacts

| Artifact | Content hash |
|---|---|
| `lift2_runtime_measurement.json` | `541652c4b027be483b8f6b0b90a88db0365766359b2833f4220a103d745f4298` |
| `lift2_candidate_coverage.json` | `682414b7b919b4d9be8f178bb59b004148bf56589fe5830ef472593f02252b3e` |
| `lift2_math_certification.json` | `e82dfaf8eb6a40b3226e12169aa8a77c4e6b27646da9050ecf6ba589d74ebf7f` |
| `lift_2_evidence_index.json` | `a0383505db948cc01f5fe290f54fcf35c8fea0c62078cf55647a4f32f6ea9c1c` |
| `lift_2_manifest.json` | `d8c172ebd98946fc090e73d0ab47097cda1f0c2a066d85dbb5724d9f53419879` |

The rebuild validator returns `PASS_FINAL_EVIDENCE_VALIDATED`.

## 12. Local Quality Result

Supported Python 3.11 sequence:

- compile: PASS;
- Ruff format: PASS, 72 files;
- Ruff lint: PASS;
- strict Pyright: PASS, 0 errors;
- pytest: PASS, 100 tests;
- notebook validation: PASS, 4 notebooks;
- deterministic manifest/evidence validation: PASS.

## 13. Deviations and Platform Constraints

- The verified QC subscription supplies both trade and quote ticks. The adapter
  admits only `TickType.TRADE` and counts ignored quotes; it does not invent a
  private trade-only API.
- QC basename collisions make local `profile.py` and `types.py` thin facades.
  Canonical implementations are deployed under non-colliding names and were included
  in the byte audit.
- QC master advanced from 18038 to 18039 during closure. The resulting compatibility
  change was source-audited, locally recertified and replayed in the complete final
  matrix. Older runs are superseded.
- No reliable peak-memory series was emitted; none is claimed.

## 14. Answers to the 11 Lift Questions

| Question | Result | Forensic basis |
|---|---|---|
| Contract/session integrity | YES | actual-contract identity, roll resets, same-session bars and 11 QC runs |
| Volume Profile correctness | YES | conservation/tie/value-area tests plus positive profile counts in every run |
| Cross-market normalization | YES WITHIN MEASUREMENT SCOPE | dimensional tests and all-eight runtime smoke matrix |
| Auction transitions | YES | causal transition tests and 1,771 unique runtime events |
| IMSI state integrity | YES | exact recurrence/TOD/covariance/embargo tests and runtime snapshots |
| ICM integrity | YES | pinv-vs-lstsq oracle, guards and deep runtime readiness |
| IAE symmetry/integrity | YES | mirror/lifecycle/TOD/gap-reset tests and per-gap runtime lineage |
| Causal alignment | YES | as-of/root/contract/session guards and prefix-equivalence certificate |
| Candidate dataset | YES DESCRIPTIVE ONLY | deterministic IDs, no outcomes, duplicates rejected |
| Coverage/breadth | YES, WITH READINESS DISCLOSURE | full 11-run coverage artifact; 1,771/1,771 retained and not-ready |
| QC parity / zero actions | YES | ordered parity hash and exact zero actions in 11/11 completed runs |

## 15. Remaining Limitations and Lift 3 Gate

Lift 2 is complete, but the system is not approved for paper or live trading. IMSI MES,
forward outcomes, predictive validation, transaction costs, portfolio/risk, execution,
orders and true L2 behavior remain unimplemented and unauthorized.

Status for the next phase:
`READY_FOR_LIFT_3_RESEARCH_GATING`. This authorizes designing and testing
outcome/friction/research gates only; it does not authorize Alpha, capital allocation,
execution or a claim of institutional/Citadel approval.

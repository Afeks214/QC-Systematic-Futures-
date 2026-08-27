# Decision Log

## 2026-08-26 — Lift 1 task structure governs the repository

Date: 2026-08-26
Decision: Implement exactly the Lift 1 tree and omit all executable later-lift packages, even where the Master Specification describes a broader eventual architecture.
Alternatives considered: Scaffold the full Master project tree with empty modules; begin Profile/feature interfaces early.
Reason: The active task has highest authority and explicitly prohibits empty production modules and Lift 2 implementation.
Specification support: Active Lift 1 sections 2, 6, and 9; Master sections 26 and 28.3–28.4 establish gate-driven sequencing.
Public-source support: Official OpenAI Codex guidance supports practical repository instructions, scoped plans, and milestone verification.
Consequences: Lift 2 boundaries exist only in `docs/LIFT_2_HANDOFF.md`; imports cannot accidentally depend on unfinished strategy code.
Reopen condition: A later approved Lift explicitly authorizes additional packages.

## 2026-08-26 — Standard-library domain core

Date: 2026-08-26
Decision: Keep `domain/`, `data/`, and `ledger/` free of QuantConnect and third-party runtime dependencies.
Alternatives considered: Use pandas/Pydantic throughout; directly type against QC runtime objects.
Reason: The core must import and test without QC, immutable data contracts need few dependencies, and the task explicitly requires standard library in the core.
Specification support: Active Lift 1 sections 7–8 and 24; Master sections 21.2 and 22.1.
Public-source support: Jane Street’s public reproducible-environment/core-versus-leaf discussion and G-Research’s public production-quality/reusable engineering principles.
Consequences: Raw QC objects enter only at adapter boundaries; explicit validators replace framework magic.
Reopen condition: A later Lift proves a maintained dependency is necessary and records compatibility, migration, and reproducibility consequences.

## 2026-08-26 — Conservative session semantics, not calendar certification

Date: 2026-08-26
Decision: Implement versioned semantic session windows for ES, ZN, and 6E, but mark exchange holidays, exceptional closures, and early closes as not certified.
Alternatives considered: Infer a holiday calendar; claim generic CME hours as complete session truth; omit sessions entirely.
Reason: Lift 1 requires a functional versioned engine and explicitly forbids pretending holiday handling is certified.
Specification support: Active Lift 1 section 18; Master sections 9.5–9.7 and Appendix Z.6.
Public-source support: Jane Street’s public discussion of missing, delayed, intermittent, and mis-associated market data supports explicit limitations rather than silent assumptions.
Consequences: Ordinary/DST-aware semantic classification is testable; holiday-dependent research remains blocked.
Reopen condition: Official exchange-calendar semantics and representative QC runtime evidence are verified and regression fixtures are added.

## 2026-08-26 — Market metadata is observed, not configured as fact

Date: 2026-08-26
Decision: Do not store tick sizes or multipliers in `MarketDefinition`; capture them only in read-only QC probe outputs or synthetic local fixtures.
Alternatives considered: Hard-code remembered exchange specifications; copy values from non-authoritative websites.
Reason: The task prohibits unverified metadata and makes the probe the evidence artifact.
Specification support: Active Lift 1 sections 12, 14, and 23; Master sections 4.4 and 9.7.
Public-source support: Two Sigma’s public data-contract/lineage principle supports versioned observed metadata and replayable evidence.
Consequences: Local tests cannot certify product facts; QC runtime remains a distinct validation gate.
Reopen condition: Official product sources or the verified QC runtime probe provide versioned, reconciled metadata.

## 2026-08-26 — Deterministic IDs and explicit time injection

Date: 2026-08-26
Decision: Derive research IDs from canonical inputs and pass all current timestamps explicitly; no random UUIDs or `datetime.now()` in domain code.
Alternatives considered: UUID4; process-local sequence counters; implicit wall-clock time.
Reason: Re-running identical research inputs must reproduce identifiers and hashes.
Specification support: Active Lift 1 sections 8, 13, and 21; Master sections 21.11, 22.3, and Appendix Z.8.
Public-source support: Two Sigma’s public replay/lineage principle and Jane Street’s public reproducible-environment principle.
Consequences: IDs are content-derived and collisions are treated as integrity violations; callers own clock semantics.
Reopen condition: A future external protocol mandates opaque IDs while preserving a deterministic internal lineage key.

## 2026-08-26 — No fabricated QC compatibility layer

Date: 2026-08-26
Decision: Use only QC APIs located in current official documentation/source and record them before code use; unresolved runtime paths stay not verified.
Alternatives considered: Convert C# names to snake_case by convention; define fake local QC classes so type checking passes.
Reason: Runnable-looking but invented integration code would violate zero-invented-API and corrupt the verification report.
Specification support: Active Lift 1 sections 5, 22–24, and 28; Master sections 21 and Appendix T’s warning that code is only a blueprint.
Public-source support: Official OpenAI Codex best practices emphasize explicit commands, verification, tests, and proof gaps.
Consequences: QC static and runtime validation statuses remain separate; local core delivery is not mislabeled as QC execution success.
Reopen condition: Never for guessed APIs; only new current official evidence may update a resolved entry.

## 2026-08-26 — Workspace has no Git revision

Date: 2026-08-26
Decision: Store `repository_revision=None` in the Lift 1 manifest.
Alternatives considered: Fabricate `unknown`, hash the working directory as though it were a commit, or initialize Git without user authorization.
Reason: `git rev-parse` confirms the workspace is not a Git repository; the schema explicitly permits `None`.
Specification support: Active Lift 1 section 21 and zero-silent-assumption policy.
Public-source support: Jane Street’s public source-revision/environment linkage principle supports distinguishing a real revision from an unrelated content hash.
Consequences: The configuration and artifact hashes remain deterministic, but source-control provenance is explicitly incomplete.
Reopen condition: The project is placed in an actual Git repository and a commit is available.

## 2026-08-26 — Pin current QC API evidence

Date: 2026-08-26
Decision: Pin QC API evidence to LEAN commit `185c691`, lean-cli release `1.0.228`, and the current official Python spellings recorded in `docs/QC_API_RESOLUTION.md`.
Alternatives considered: Infer Python names from C# names; use unversioned examples; defer the registry.
Reason: The task prohibits invented APIs and requires current official evidence for every used name.
Specification support: Active Lift 1 sections 5, 14, 22, 23, and 26.
Public-source support: Official QuantConnect v2 docs and pinned QuantConnect source repositories listed in `docs/QC_API_RESOLUTION.md`.
Consequences: Eight exact constant paths are configured; QC code may use only recorded interfaces; runtime success remains unclaimed.
Reopen condition: A newer official LEAN/CLI baseline is intentionally adopted and every affected name is re-resolved.

## 2026-08-26 — Restrict adjusted continuous data

Date: 2026-08-26
Decision: Treat Backwards Ratio continuous prices only as identity, coverage, and mapping inspection data in Lift 1.
Alternatives considered: Treat adjusted history as point-in-time signal data; switch the mandated normalization mode; omit continuous history.
Reason: Official documentation states that the entire futures history is used for the adjustment, while the task mandates Backwards Ratio for the probe and forbids future-data access.
Specification support: Active Lift 1 sections 5, 14, 23, and 25; Master point-in-time rules.
Public-source support: Official QuantConnect Futures universes documentation, Continuous Contracts section.
Consequences: The probe can audit identity and mapping, but no adjusted continuous value receives signal certification or supports a strategy conclusion.
Reopen condition: A separately certified causal continuous-series construction is specified and validated in a later authorized lift.

## 2026-08-26 — Omit unverified QC stubs

Date: 2026-08-26
Decision: Omit `quantconnect-stubs` from pinned dependencies.
Alternatives considered: Pin the latest PyPI release; leave it unpinned; create fake local QC aliases.
Reason: Official material recommends the generated stubs but does not publish an immutable compatibility mapping for a specific release, LEAN `185c691`, and Python 3.11.11.
Specification support: Active Lift 1 sections 5 and 7.
Public-source support: Official QuantConnect autocomplete documentation and `QuantConnect/quantconnect-stubs-generator`.
Consequences: Strict type checking excludes the isolated QC runtime boundary; core code remains strict and QC names receive static source review plus architecture tests.
Reopen condition: A compatible stubs release is directly verified in the target LEAN Python 3.11 runtime.

## 2026-08-26 — Use event-instant roll-state semantics

Date: 2026-08-26
Decision: Treat an explicit mapped-contract change as `ROLL_TRANSITION` only at `max(observed_at_utc, effective_at_utc)` and as `POST_ROLL` after that instant; never infer `PRE_ROLL`, `BLACKOUT`, or a transition duration in Lift 1.
Alternatives considered: Invent a fixed transition window; infer pre-roll from future volume; keep `ROLL_TRANSITION` indefinitely; omit post-roll distinction.
Reason: `MappingObservation` supplies event clocks but no duration policy. Event-instant semantics preserve the observed change without introducing an unverified threshold or future information.
Specification support: Active Lift 1 sections 5 and 19 require explicit mapping observations, prohibit future-volume inference, and require no future mapping to affect the past.
Public-source support: Official QuantConnect futures documentation supports explicit symbol-mapping events but does not define this project’s roll-state lifetime; no proprietary-firm behavior is attributed.
Consequences: `current_roll_state` is deterministic and causal, but persistent roll windows require a future, evidence-backed, versioned policy.
Reopen condition: A later authorized lift supplies explicit roll-window inputs, duration semantics, and tests without using future data.

## 2026-08-26 — Register the sample as a non-forecast audit

Date: 2026-08-26
Decision: Pre-register “Reference Futures Data Availability and Contract Mapping Audit” with an empty `horizons_minutes` tuple, one planned variant, and `PENDING` status.
Alternatives considered: Invent a forecast horizon; register a trading hypothesis; omit the required sample registration.
Reason: The sample evaluates data availability and identity, not a price target, return, signal, or trading outcome. A synthetic horizon would misstate its purpose.
Specification support: Active Lift 1 sections 1, 6, and 20 require this exact non-trading audit and prohibit trading hypotheses and conclusions.
Public-source support: Public scientific-research principles in the source review support explicit pre-registration, but no public source is used to invent a market horizon.
Consequences: The validator permits no horizons only for records that otherwise provide all mandatory audit fields; any declared horizon must remain positive, sorted, and unique.
Reopen condition: A separately authorized experiment has an explicit preregistered target and horizon.

## 2026-08-26 — Use a six-month inspection filter as configuration

Date: 2026-08-26
Decision: Set every candidate market’s Lift 1 contract filter to 182 calendar days and label it only as probe configuration.
Alternatives considered: Market-specific remembered horizons; an unbounded chain; a shorter filter that may omit the adjacent quarterly contract.
Reason: The fixed roll-window probe needs near and adjacent contract visibility, while a common bounded filter is deterministic and avoids claiming product-specific economics.
Specification support: Active Lift 1 sections 14 and 23 require a positive horizon sufficient to inspect near contracts and prohibit unverified market constants.
Public-source support: Official QuantConnect futures examples verify the `set_filter(0, 182)` API shape; they do not make 182 an institutional threshold.
Consequences: Registry validation is deterministic, but actual chain sufficiency remains a QC runtime fact and a shorter future policy may be warranted by evidence.
Reopen condition: Executed probe artifacts show missing adjacent contracts, unnecessary data volume, or a documented market-specific requirement.

## 2026-08-26 — Preserve runtime truth over nominal closure

Date: 2026-08-26
Decision: Keep the closure result `NOT_READY_FOR_LIFT_2` unless every mandatory empirical gate has an actual artifact; official documentation and synthetic fixtures remain separate evidence classes.
Alternatives considered: Treat documented QC APIs as executed evidence; use synthetic market data; mark unavailable commands as passing.
Reason: Docker, Python 3.11, LEAN CLI, QC account/project state, and the required data were unavailable in this workspace.
Specification support: Active Lift 1 Closure sections 4, 8–18, and 29–30.
Public-source support: Official QuantConnect documentation identifies the required runtime paths but does not attest that this repository ran them.
Consequences: The repository gains static contracts and explicit blocker artifacts, while futures, Python.NET, Notebook 01, and CFTC empirical gates remain open.
Reopen condition: The named official commands execute successfully and produce validated immutable artifacts without an unauthorized charge.

## 2026-08-26 — Do not bypass the protected Git metadata directory

Date: 2026-08-26
Decision: Attempt the authorized local `git init`, record its exact read-only-filesystem failure, and do not change permissions, delete `.git`, initialize elsewhere, create a remote, or fabricate a revision.
Alternatives considered: Remove or chmod the protected `.git`; use a directory-content hash as a commit; report an automation identity without configuring it.
Reason: The workspace provides an empty read-only `.git` directory and `git init .` exits 1 at `.git/info/`. Any bypass would violate the environment boundary or misstate repository provenance.
Specification support: Active Lift 1 Closure section 6 and zero-false-closure rule.
Public-source support: Git provenance is meaningful only when backed by a real repository object and commit.
Consequences: `repository_revision` remains null, no local identity was configured, and no qualified closure manifest is emitted.
Reopen condition: The repository is supplied with writable Git metadata; then configure only `Codex Automation <codex@localhost>`, commit locally, verify no remote, and record `HEAD`.

## 2026-08-26 — Require source-zone provenance for naive QC datetimes

Date: 2026-08-26
Decision: A naive Python/Python.NET datetime at the QC adapter boundary raises unless the caller supplies the documented IANA source timezone for that exact value.
Alternatives considered: Attach UTC to every naive value; trust host-local time; relax the domain UTC invariant.
Reason: Official QC time documentation says algorithm clocks do not carry timezone metadata, while their represented zone depends on the configured algorithm clock. Blanket UTC localization would corrupt non-UTC values.
Specification support: Active Lift 1 Closure section 12 and Lift 1 zero-future-data/time rules.
Public-source support: Official QuantConnect time-modeling documentation distinguishes algorithm time from UTC time.
Consequences: Static adapter tests prove rejection and explicit-zone conversion; actual Python.NET types, reprs, and tzinfo still require runtime evidence.
Reopen condition: A verified runtime/stub contract supplies a stronger typed representation without weakening explicit provenance.

## 2026-08-26 — Freeze pre-Alpha contracts without behavioral implementation

Date: 2026-08-26
Decision: Add only immutable ForecastPacket, cost-scenario, hard-safety, dataset-use, and feature-semantics contracts. Every future feature is `NOT_IMPLEMENTED`, cost values are absent, and the operating mode is `OBSERVE_ONLY`.
Alternatives considered: Defer the Master Definition-of-Ready contracts; implement placeholder forecasts/costs; begin Auction/Profile behavior.
Reason: The Master Specification requires stable contracts before Alpha coding, while the active closure task explicitly prohibits the systems that would generate or consume them.
Specification support: Active Lift 1 Closure sections 21–24 and 31; Master final Definition of Ready.
Public-source support: No public source is used to define proprietary behavior or numerical assumptions.
Consequences: Schema validation can run now; no forecast, probability, feature, cost estimate, position, order, or strategy output exists.
Reopen condition: Only a separately authorized later lift with its own evidence and preregistration may implement behavior.

## 2026-08-26 — Keep the historical manifest immutable

Date: 2026-08-26
Decision: Change local manifest rebuilds and future unqualified Notebook 01 output to separate paths; refuse to create `lift_1_closure_manifest.json` until every non-null qualified field has evidence.
Alternatives considered: Overwrite the original manifest; write a closure manifest with nulls or placeholders; copy synthetic IDs into qualified fields.
Reason: The original file is historical evidence and the closure schema makes Git, LEAN, QC, notebook, CFTC, and session evidence mandatory.
Specification support: Active Lift 1 Closure sections 26 and 29.
Public-source support: General lineage and replay principles support immutable historical artifacts.
Consequences: The original SHA-256 remains `a07a32362e741cd21d33b4027b987992826e221ef68b2dfda6b68b64a773505c`; qualified closure-manifest status is `ABSENT_BLOCKED`, not a fabricated failure artifact.
Reopen condition: All constructor inputs point to actual validated evidence and the resulting manifest passes its completeness test.

## 2026-08-26 — Prohibit implicit data spend

Date: 2026-08-26
Decision: Do not run LEAN research/history-provider commands, set a nonzero data-purchase limit, create paid compute, or purchase data without exact account-specific confirmation and user approval.
Alternatives considered: Assume a zero default; try the command and stop only after a charge warning; use a third-party feed.
Reason: The official local-data workflow can incur QCC/download costs, and no account state can be inspected without the CLI. Another vendor cannot certify QuantConnect delivery.
Specification support: Active Lift 1 Closure sections 5, 8, and 15.
Public-source support: Official QuantConnect local-data documentation describes provider/download licensing and purchase controls.
Consequences: Notebook 01 and all real-data probes remain `NOT_EXECUTED`; no charge or cloud resource was created.
Reopen condition: The user confirms the exact entitled zero-new-charge path, or explicitly approves a quoted charge.

## 2026-08-26 — Recover the canonical repository in a writable clone

Date: 2026-08-26
Decision: Use `/workspace/QC-Systematic-Futures-` as the canonical writable clone of the
empty target GitHub repository; mount the two private specifications locally under the
ignored `upload/` path and never publish them.
Alternatives considered: mutate the protected scratch `.git`; regenerate the project;
commit the proprietary Word files.
Reason: repository provenance can be established without bypassing filesystem controls
or leaking private material.
Specification support: active directive sections 7–8 and zero-silent-assumption rules.
Public-source support: Git/GitHub object and ref semantics.
Consequences: source/tests/evidence can be committed and pushed; the specifications are
hash-addressed but absent from the public tree.
Reopen condition: the repository owner intentionally changes repository visibility or
supplies a different canonical remote.

## 2026-08-26 — Qualify Python 3.11 and QC APIs in isolated environments

Date: 2026-08-26
Decision: Qualify project code under CPython 3.11.15, keep LEAN CLI 1.0.228 separate,
and use its official `quantconnect-stubs==18032` only for an explicit QC-boundary type
check.
Alternatives considered: accept Python 3.12 results; add the stubs and their Pandas,
NumPy, and Matplotlib dependency graph to the project; create fake QC types.
Reason: the target runtime is 3.11, while editor-only packages must not expand the
research core.
Specification support: active directive sections 10–11 and dependency minimalism.
Public-source support: official LEAN CLI release and QuantConnect-generated stubs.
Consequences: target-version and QC spelling checks are real; empirical QC runtime
status remains separate.
Reopen condition: QuantConnect publishes a smaller, runtime-pinned stubs mechanism or
the qualified cloud runtime exposes a different API.

## 2026-08-26 — Pin session exceptions to current LEAN market hours

Date: 2026-08-26
Decision: Preserve the small semantic SessionEngine and derive representative closure
fixtures from current official LEAN market-hours data at commit `07fb0182`; do not build
a second exchange-calendar service.
Alternatives considered: remembered CME dates; a full copied calendar; leaving all
exception behavior synthetic.
Reason: LEAN is authoritative for execution-calendar truth and compact fixtures are
sufficient to validate our UTC/local semantic overlay.
Specification support: active directive section 19 and Master session/roll readiness.
Public-source support: official LEAN `market-hours-database.json`.
Consequences: ordinary, DST, holiday, early-close, and cross-midnight tests are
versioned and reproducible; future calendar editions are not permanently certified.
Reopen condition: the pinned database changes or a reference market changes exchange
hours/timezone.

## 2026-08-26 — Use one parameterized read-only QC composition root

Date: 2026-08-26
Decision: Keep one `InstitutionalFuturesDataProbe` and select `futures` or `cftc` with
the verified `get_parameter` API. Extend the existing recorder/registration boundary
instead of creating a parallel project or source tree.
Alternatives considered: a second algorithm file/project; manual source swapping;
leaving the CFTC audit without executable support.
Reason: the two required windows differ, while one canonical `main.py` minimizes drift
and preserves the zero-action invariant.
Specification support: active directive sections 14–17, 22, and minimal-code rules.
Public-source support: official QuantConnect algorithm-parameter, futures, and CFTC
documentation plus stubs 18032.
Consequences: both empirical paths are statically ready; no runtime result is claimed
until authenticated execution.
Reopen condition: authenticated QC execution proves a documented API or dataset
coverage mismatch.

## 2026-08-26 — Stop QC authentication after the secure request was declined

Date: 2026-08-26
Decision: Treat QuantConnect authentication as an external secret/entitlement
dependency after checking authorized environment variables, the existing CLI session,
and the official browser login route; do not retry a declined secure authentication
request.
Alternatives considered: search arbitrary files for credentials; fabricate a session;
use another vendor; purchase data.
Reason: none is authorized, and each would violate credential, provenance, or spend
rules.
Specification support: active directive sections 13, 33, and 42.
Public-source support: official LEAN CLI authentication/cloud workflows.
Consequences: every local/Git gate continues; QC project/backtest/data artifacts remain
absent and the only permissible final result is external-access dependent.
Reopen condition: the user authorizes a QC login/session with the required cloud and
dataset entitlements.

## 2026-08-27 — Publish through the authorized GitHub integration

Date: 2026-08-27
Decision: After non-interactive HTTPS push failed for lack of shell credentials, use
the already-authorized GitHub integration to publish the exact local Git tree and move
`main` only by fast-forward.
Alternatives considered: request or store a token; force-push; leave Git externally
blocked.
Reason: the integration has verified push permission and preserves exact blob/tree
identity without exposing credentials.
Specification support: active directive sections 7, 8, and 38.
Public-source support: GitHub Git Data object and ref semantics.
Consequences: the certified source tree is public at revision
`3f1bb4294d26acbe7f4977f65b7a69483a6f124a`; final evidence is published as its
fast-forward child.
Reopen condition: remote `main` changes before the final fast-forward update.

## 2026-08-27 — Certify the immutable source in authenticated QC Cloud

Date: 2026-08-27
Decision: Use the authenticated official QC web environment and free B-MICRO node to
build and run the read-only futures and CFTC parameter modes from source revision
`cbfee265cbf5e94c7768667d469e2773f62e3080`.
Alternatives considered: remain externally blocked; download local data; require
Docker; create a second cloud project or source tree.
Reason: the authorized cloud session was available, required data was entitled, and
the existing parameterized composition root was the shortest no-purchase path.
Consequences: project `35697180`, build `67d2fc-f0a27f`, and final backtests
`b22d565d649c5b31650fd033cdc89cf3` / `a7ba4f84937fb19bc3f6f63bc773e3c3`
provide real runtime evidence with zero trading actions.
Reopen condition: a source-code change after the certified revision or a material QC
runtime/dataset change requires a new probe.

## 2026-08-27 — Gate early historical CFTC clocks with the official release

Date: 2026-08-27
Decision: Preserve QC's 2026-01-02 Slice/EndTime for the holiday-delayed 2026-01-05
release and make the official 2026-01-05 20:30 UTC timestamp the earliest usable time.
Alternatives considered: relabel raw QC data; treat the historical timestamp as public
availability; discard the observation.
Reason: the CFTC schedule is the external publication clock and the max-time
AvailabilityGate exists specifically to prevent early use without corrupting lineage.
Consequences: the ordinary and delayed examples are `CERTIFIED_CONTEXT`; CFTC remains
prohibited from signal use and its missing post-2026-05-29 tail stays explicit.
Reopen condition: official schedule corrections or new empirical delivery semantics
require a versioned audit update.

## 2026-08-27 — Use explicit eigen-floor covariance for IMSI

Date: 2026-08-27
Decision: Stabilize the empirical 2x2 prior-state covariance by replacing each
eigenvalue below `max(largest * 1e-8, 1e-12)` with that floor.
Alternatives considered: label the historical heuristic Ledoit-Wolf; add a shrinkage
library; use an inverse without conditioning; optimize a floor.
Reason: the selected rule is transparent, deterministic, numerically bounded, and
does not imply an estimator that is not implemented.
Specification support: Lift 2 sections 34–37.
Public-source support: none required; this is a disclosed numerical implementation
choice, not a market claim.
Consequences: IMSI can represent collinear prior states without fabricated zero
distances; the condition number and warmup flags remain observable.
Reopen condition: Lift 3 may register a true shrinkage estimator as an explicit
research variant without mutating this version.

## 2026-08-27 — Share semantic session shapes by futures family

Date: 2026-08-27
Decision: Preserve the certified ES, ZN, and 6E semantic partitions and apply the
same versioned shapes to NQ/RTY, ZT, and 6J/6B respectively, while retaining each
root's own session identifiers and official exchange timezone.
Alternatives considered: create another calendar engine; invent root-specific
intraday segments; leave the five smoke markets unclassifiable.
Reason: the market registry already groups these roots by asset class and timezone;
Lift 2 needs one deterministic semantic overlay, while LEAN remains authoritative
for actual tradable hours and closures.
Specification support: Lift 2 sections 20, 68–70, and 93.
Public-source support: current official LEAN market-hours database and futures data
documentation.
Consequences: all eight roots use the existing `SessionEngine`; no claim is made that
the semantic partitions are exchange products or universally optimal research
sessions.
Reopen condition: empirical QC evidence or an updated authoritative specification
requires a root-specific versioned policy.

## 2026-08-27 — Keep IAE-L1 distinct from order-flow imbalance

Date: 2026-08-27
Decision: Name and implement IAE-L1 only as completed-bar gap/retest geometry and
prior-session time-of-day volume context.
Alternatives considered: infer aggressor flow from trade ticks; treat top-of-book
quotes as depth; label the proxy OFI or MLOFI.
Reason: the reviewed OFI papers require best-quote or multi-level order-book events
that the Lift 2 data contract intentionally excludes.
Specification support: Lift 2 sections 5, 45–55, and 67.
Public-source support: Cont, Kukanov and Stoikov (2010); Xu, Gould and Howison (2019).
Consequences: no queue, cancellation, replenishment, institutional-absorption, OFI,
or MLOFI claim appears in executable measurement outputs.
Reopen condition: a later separately authorized lift certifies incremental L2 data.

## 2026-08-27 — Preserve public module facades around QC filename collisions

Date: 2026-08-27
Decision: Keep directive-specified `measurement/types.py` and
`measurement/profile.py` as thin public facades, place their implementations in
`measurement/models.py` and `measurement/volume_profile.py`, and make the QC runtime
import only the non-conflicting implementation names.
Alternatives considered: accept an initialization failure; duplicate the full modules;
create `types`/`profile` packages; rename the directive's public imports outright.
Reason: QC Cloud rejected both filenames as Python-module conflicts; a `types` package
then shadowed the standard library and broke `enum`/`re`. The selected layout keeps one
implementation per responsibility and preserves the specified local public API.
Specification support: Lift 2 sections 12, 17, and 22; the two additional modules are
an unavoidable QC packaging responsibility inside the already authorized package.
Public-source support: none; this decision is based on observed project `35697180`
compile/initialization evidence on LEAN `2.5.0.0.18036`.
Consequences: local callers retain the specified imports; the cloud source omits the
two rejected facades and executes byte-identical implementation modules instead.
Reopen condition: QC Cloud accepts nested `types.py` and `profile.py` without
flattening or standard-library conflicts.

## 2026-08-27 — Interpret delivered tick EndTime at the UTC frontier

Date: 2026-08-27
Decision: Convert a naive QC-delivered tick `EndTime` from the configured algorithm
timezone, which Lift 2 fixes to UTC, rather than from the market exchange timezone.
Alternatives considered: clip future timestamps; reuse `Algorithm.Time` as the event
timestamp; treat the delivered wall clock as exchange-local; weaken the invariant.
Reason: official LEAN time modeling makes `EndTime` the delivery frontier and states
that algorithm time equals that frontier. The failed ES replay proved that a second
exchange-timezone conversion moved the event into the future.
Consequences: event time remains the QC data timestamp, availability remains the QC
frontier, and `exchange_time_utc <= available_at_utc` stays fail-closed.
Reopen condition: an official QC API or runtime version establishes different Python
tick timestamp semantics under an explicitly UTC algorithm.

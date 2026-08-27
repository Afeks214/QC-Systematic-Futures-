# Public Source Review

`PUBLIC_SOURCE_REVIEW_STATUS = COMPLETE_OFFICIAL_PRIMARY_SOURCES_ONLY`

Verified date for this review: **2026-08-26**.

This review uses only public material published by the named owner. These sources
support general engineering principles for Lift 1. They do not establish, and this
project does not claim to reproduce, any firm's proprietary system.

## QuantConnect and LEAN

### LEAN Engine overview

Source: [LEAN Engine — Getting Started](https://www.quantconnect.com/docs/v2/lean-engine/getting-started)

Official owner: QuantConnect

Verified date: 2026-08-26

Public claim: LEAN supports Python 3.11 and separates data-feed, result-processing,
and other engine responsibilities through modular components.

Engineering implication for Lift 1: Pin the project to Python 3.11 and keep the
standard-library research core independent of the LEAN runtime.

Artifact affected: `pyproject.toml`, `AGENTS.md`, `README.md`, QC adapter boundary.

What the source does NOT reveal: It does not certify this repository's algorithm,
data entitlements, local Docker image, or runtime results.

### Futures universes and continuous contracts

Source: [Futures universes](https://www.quantconnect.com/docs/v2/writing-algorithms/universes/futures)

Official owner: QuantConnect

Verified date: 2026-08-26

Public claim: Python algorithms register futures with `add_future`; the returned
`Future.symbol` identifies the continuous series, `Future.mapped` identifies the
currently mapped actual contract, and mapping changes produce symbol-change events.
The same page documents snake_case parameter names and the Open Interest and
Backwards Ratio modes.

Engineering implication for Lift 1: Preserve continuous and mapped identities,
record mapping observations, and keep the read-only probe free of order actions.

Artifact affected: `docs/QC_API_RESOLUTION.md`, `main.py`, market configuration,
futures registration, probe recording.

What the source does NOT reveal: It does not prove which observations are present
for this account, certify a particular roll timestamp, or validate the local code.

### US futures data and research history

Source: [US Futures dataset](https://www.quantconnect.com/docs/v2/writing-algorithms/datasets/algoseek/us-futures)

Official owner: QuantConnect

Verified date: 2026-08-26

Public claim: The official page lists supported futures constants and documents
continuous history through `history` and chain history through
`QuantBook.future_history`, including its data-frame, all-data, and expiry views.

Engineering implication for Lift 1: Resolve market constants from the official
supported-assets list and make Notebook 1 request, inspect, and summarize history
without embedding domain logic.

Artifact affected: market registry, `quantbook_probe.py`, Notebook 1,
`docs/QC_API_RESOLUTION.md`.

What the source does NOT reveal: It does not guarantee coverage for the requested
dates, open-interest completeness, credentials, subscriptions, or probe output.

### Research engine behavior

Source: [Research Engine](https://www.quantconnect.com/docs/v2/research-environment/key-concepts/research-engine)

Official owner: QuantConnect

Verified date: 2026-08-26

Public claim: The Research Environment exposes `QuantBook`, can import project
code, and is not an event-driven algorithm runtime with `on_data` behavior.

Engineering implication for Lift 1: Keep notebooks thin, import package functions,
and do not imply that notebook history access provides event-time replay guarantees.

Artifact affected: `research.ipynb`, `research_notebooks/01_data_state_research.ipynb`,
README notebook workflow.

What the source does NOT reveal: It does not certify look-ahead safety for arbitrary
research code; point-in-time enforcement remains a project responsibility.

### LEAN source repository

Source: [QuantConnect/Lean](https://github.com/QuantConnect/Lean)

Official owner: QuantConnect

Verified date: 2026-08-26

Public claim: The official source repository defines futures constants, mapping
events, security properties, and engine behavior that can corroborate documentation.

Engineering implication for Lift 1: A QC symbol or API is marked VERIFIED only
after it is found in current official documentation or official source; C# names
are not mechanically converted into Python names.

Artifact affected: `docs/QC_API_RESOLUTION.md`, QC adapters, static QC review.

What the source does NOT reveal: Source presence alone does not prove Python-wrapper
availability, cloud deployment compatibility, data access, or runtime success.

### LEAN CLI

Source: [QuantConnect/lean-cli](https://github.com/QuantConnect/lean-cli)

Official owner: QuantConnect

Verified date: 2026-08-26

Public claim: The official CLI supports initialized workspaces, project creation,
local research and backtests through Docker, and cloud backtests with explicit push
options. Its current repository documentation is also evidence when command naming
differs from older documentation.

Engineering implication for Lift 1: Bootstrap instructions use only an exactly
verified long-form command and distinguish local Docker execution from cloud
execution; no cloud command is run by this task.

Artifact affected: `docs/MAC_M4_QC_BOOTSTRAP.md`, bootstrap script,
`docs/QC_API_RESOLUTION.md`.

What the source does NOT reveal: It does not establish that Docker, credentials,
paid organization features, or futures data are available in this environment.

### LEAN Data Source SDK

Source: [QuantConnect/Lean.DataSource.SDK](https://github.com/QuantConnect/Lean.DataSource.SDK)

Official owner: QuantConnect

Verified date: 2026-08-26

Public claim: The official SDK is a template for custom data types and data
conversion consumed by LEAN algorithms and the Research Environment.

Engineering implication for Lift 1: Custom external datasets require explicit data
contracts and conversion semantics; Lift 1 does not fabricate a CFTC/QC adapter.

Artifact affected: dataset-policy documentation and `docs/LIFT_2_HANDOFF.md`.

What the source does NOT reveal: It does not certify actual CFTC delivery timing,
revision handling, or a dataset subscription for this project.

## OpenAI Codex

### Repository instructions and verification

Source: [Codex best practices](https://learn.chatgpt.com/guides/best-practices)

Official owner: OpenAI

Verified date: 2026-08-26

Public claim: Codex works best with concise repository instructions, explicit plans
for longer work, repository-native tests, linting, type checks, and clear definitions
of done.

Engineering implication for Lift 1: Keep `AGENTS.md` operational, maintain an
ExecPlan with checkpoints, and reconcile every claimed result to an executed check.

Artifact affected: `AGENTS.md`, `.agent/PLANS.md`, `docs/LIFT_1_EXECPLAN.md`,
quality scripts and completion report.

What the source does NOT reveal: It does not validate this repository, replace the
two governing specifications, or authorize work beyond Lift 1.

### Codex Cloud environments

Source: [Codex Cloud environment](https://learn.chatgpt.com/docs/environments/cloud-environment)

Official owner: OpenAI

Verified date: 2026-08-26

Public claim: Cloud tasks run in an isolated repository checkout with a setup phase;
available tooling, internet access, and validation depend on the configured
environment.

Engineering implication for Lift 1: Record unavailable credentials/runtimes as
NOT_EXECUTED rather than treating static checks as cloud or LEAN execution.

Artifact affected: `docs/ASSUMPTIONS_AND_BLOCKERS.md`, completion report.

What the source does NOT reveal: It does not provide QuantConnect credentials,
futures data, a LEAN image, or permission to create cloud resources.

### ExecPlans for long-running work

Source: [Code migrations with ExecPlans](https://learn.chatgpt.com/docs/code-migrations)

Official owner: OpenAI

Verified date: 2026-08-26

Public claim: Long-running, multi-step changes benefit from a durable plan that
tracks progress, decisions, validation, and reconciliation as work evolves.

Engineering implication for Lift 1: The ExecPlan is a living audit artifact and is
updated after each subsystem rather than being a one-time checklist.

Artifact affected: `.agent/PLANS.md`, `docs/LIFT_1_EXECPLAN.md`.

What the source does NOT reveal: It does not determine domain architecture or prove
that planned work is complete.

## Public Engineering Principles from Research Firms

### Two Sigma — treating data as code

Source: [Treating Data as Code at Two Sigma](https://www.twosigma.com/articles/treating-data-as-code-at-two-sigma/)

Official owner: Two Sigma

Verified date: 2026-08-26

Public claim: The article describes data contracts, versioning, automated testing,
reproducibility, replay, quality monitoring, and lineage as software-like controls
for data systems.

Engineering implication for Lift 1: Version dataset policies, retain lineage hashes,
make availability replayable, and expose quality state rather than silently cleaning.

Artifact affected: schemas, point-in-time normalizer, availability gate, manifests.

What the source does NOT reveal: It does not reveal Two Sigma's proprietary data,
signals, systems, thresholds, or trading methods.

### Jane Street — data collection and cleaning

Source: [Real World Machine Learning, Part 1](https://blog.janestreet.com/real-world-machine-learning-part-1/)

Official owner: Jane Street

Verified date: 2026-08-26

Public claim: The article notes that collected data can be missing, corrupted,
misaligned, delayed, or associated with the wrong instrument and therefore requires
cleaning and validation before use.

Engineering implication for Lift 1: Missingness is explicit, actual contract
identity is preserved, and quality flags survive normalization and release.

Artifact affected: data schemas, quality validation, contract and probe services.

What the source does NOT reveal: It does not disclose Jane Street's platform,
datasets, signal construction, or production controls.

### Jane Street — reproducible Python environments

Source: [Building reproducible Python environments with Xars](https://blog.janestreet.com/building-reproducible-python-environments-with-xars/)

Official owner: Jane Street

Verified date: 2026-08-26

Public claim: The article supports declarative, reproducible Python environments,
source-revision awareness, and separation between reusable core code and notebook
leaf dependencies.

Engineering implication for Lift 1: Pin dependencies and keep business rules in the
package rather than notebooks.

Artifact affected: `pyproject.toml`, `requirements.txt`, notebooks, run manifest.

What the source does NOT reveal: It does not prescribe this project's dependency
versions or reveal Jane Street's production environment.

### Jane Street — focused repeatable tests

Source: [Repeatable exploratory programming](https://blog.janestreet.com/repeatable-exploratory-programming/)

Official owner: Jane Street

Verified date: 2026-08-26

Public claim: Small exploratory examples can be retained as repeatable regression
tests and provide fast feedback.

Engineering implication for Lift 1: Use a small decisive invariant suite rather
than a broad, uninformative coverage target.

Artifact affected: `tests/`, notebook validation, quality script.

What the source does NOT reveal: It does not disclose proprietary test suites,
release processes, or trading research.

### Jump Trading — non-stationary and adversarial markets

Source: [AI & ML at Jump](https://www.jumptrading.com/ai-ml)

Official owner: Jump Trading

Verified date: 2026-08-26

Public claim: The public page characterizes markets as noisy, non-stationary, and
adversarial, and emphasizes clean data, rigorous validation, fast feedback, and
collaboration among researchers, engineers, and traders.

Engineering implication for Lift 1: Build feedback around observable data quality
and reproducible probes; do not treat one historical sample as a stable truth.

Artifact affected: probe summaries, quality status, experiment preregistration.

What the source does NOT reveal: It does not reveal Jump's models, infrastructure,
latencies, data, or strategy process.

### Jump Trading — reliable infrastructure

Source: [Technology at Jump](https://www.jumptrading.com/technology)

Official owner: Jump Trading

Verified date: 2026-08-26

Public claim: The page describes engineering at scale with reliability, testing,
deployment ownership, and close technical context.

Engineering implication for Lift 1: Keep subsystem contracts narrow, verification
explicit, and failure states visible before adding scale.

Artifact affected: architecture boundaries, tests, completion report.

What the source does NOT reveal: It does not reveal a proprietary architecture,
deployment topology, or operational thresholds.

### Susquehanna — decisions under uncertainty

Source: [Game Theory and Decision Science](https://sig.com/who-we-are/game-theory-decision-science/)

Official owner: Susquehanna International Group

Verified date: 2026-08-26

Public claim: The page emphasizes expected value, decisions under uncertainty, risk
pricing, pruning decision trees, and evaluating explicit alternatives.

Engineering implication for Lift 1: Pre-register alternatives and decision criteria;
do not replace uncertainty with intuition or post-hoc labels.

Artifact affected: experiment ledger, decision log, Lift 2 handoff.

What the source does NOT reveal: It does not reveal SIG's models, probabilities,
trading decisions, or risk limits.

### Man AHL — scientific systematic research

Source: [Man AHL — About](https://www.man.com/graduate-programmes)

Official owner: Man Group

Verified date: 2026-08-26

Public claim: Man's public material describes AHL in terms of scientific rigor,
systematic research, diverse datasets, and robust technology.

Engineering implication for Lift 1: Establish testable data contracts and technology
controls before drawing research conclusions.

Artifact affected: dataset certification, manifests, quality gates.

What the source does NOT reveal: It does not disclose AHL's proprietary research,
portfolio construction, systems, or datasets.

### G-Research — reusable maintained open source

Source: [Deputy Head of Open Source Development](https://www.gresearch.com/vacancies/deputy-head-of-open-source-development/)

Official owner: G-Research

Verified date: 2026-08-26

Public claim: The public role description emphasizes methodical execution,
production-quality open-source improvements, maintained communities, governance,
documentation, and feedback.

Engineering implication for Lift 1: Prefer reusable, documented project modules and
contribute disciplined tests rather than notebook-only artifacts.

Artifact affected: package layout, documentation, tests, notebooks.

What the source does NOT reveal: It does not disclose G-Research's proprietary
platform, research, or trading infrastructure.

### G-Research — long-term open-source sustainability

Source: [How G-Research invests in open source for long-term impact](https://www.gresearch.com/news/how-g-research-invests-in-open-source-for-long-term-impact/)

Official owner: G-Research

Verified date: 2026-08-26

Public claim: The article frames open-source investment around sustainability and
the long-term health of maintained systems.

Engineering implication for Lift 1: Use standard, inspectable formats and avoid
unnecessary frameworks that create maintenance burden.

Artifact affected: dependency decisions, JSON/JSONL artifacts, project structure.

What the source does NOT reveal: It does not disclose internal proprietary systems,
research methodology, or strategy implementation.

## Review Boundary

The public review informs engineering discipline only. Exact Lift 1 requirements
come from the current task and the two supplied specifications. QuantConnect API
resolution is recorded separately, item by item, in `docs/QC_API_RESOLUTION.md`;
no API is treated as verified merely because a general source was reviewed here.

## Lift 2 — Auction-State Measurement Review

Review date: **2026-08-27**

This review changes engineering acceptance criteria only. It does not import a
public firm's strategy, claim that a descriptive feature is predictive, or relax
the Lift 2 prohibition on outcomes, Alpha, orders, and execution.

### QuantConnect / LEAN — futures identity, ticks, and time

Sources: [individual futures contracts](https://www.quantconnect.com/docs/v2/writing-algorithms/securities/asset-classes/futures/requesting-data/individual-contracts),
[handling futures data](https://www.quantconnect.com/docs/v2/writing-algorithms/securities/asset-classes/futures/handling-data),
[futures universes](https://www.quantconnect.com/docs/v2/writing-algorithms/universes/futures),
[time periods](https://www.quantconnect.com/docs/v2/writing-algorithms/key-concepts/time-modeling/periods),
[time-period consolidators](https://www.quantconnect.com/docs/v2/writing-algorithms/consolidating-data/consolidator-types/time-period-consolidators), and
[US futures data](https://www.quantconnect.com/docs/v2/writing-algorithms/datasets/algoseek/us-futures).

Official owner: QuantConnect. Living documentation inspected 2026-08-27.

Accepted for Lift 2: the continuous future identifies the root and exposes its
current mapped contract; the futures chain supplies contract identity and Open
Interest context; `SymbolChangedEvents` identifies mapping changes; and
`add_future_contract(..., Resolution.TICK, fill_forward=False,
extended_market_hours=True)` subscribes an actual contract. Tick type must be
checked because a tick subscription can contain trades and quotes. Trade ticks
carry price and quantity. Backtests batch ticks at the engine's documented
millisecond cadence, so arrival inside one callback is not interpreted as native
exchange sequencing. QC bars and consolidators are end-time based, while default
time-period consolidation is exchange-time-zone aligned.

Engineering implication: continuous adjusted prices are excluded from profile and
bar measurement. The runtime admits only `TickType.TRADE` observations for the
currently mapped actual contract, resets contract-local state on a mapping event,
and performs semantic-session-anchored aggregation in the deterministic core.
Default QC consolidator alignment is not used as a substitute for semantic session
alignment. Market hours and actual-contract history remain explicit QC boundaries.
Every exact API name used by production code is resolved separately in
`docs/QC_API_RESOLUTION.md`.

Rejected inference: QC data availability does not establish exchange-native order,
complete order-book state, or predictive value.

### Public research-engineering principles

Sources: Man AHL [About AHL](https://www.man.com/ahl?language=en-gb), Two Sigma
[About](https://www.twosigma.com/about-us/) and
[Treating Data as Code](https://www.twosigma.com/articles/treating-data-as-code-at-two-sigma/),
Jump Trading [AI & ML](https://www.jumptrading.com/ai-ml), Jane Street
[Quantitative Research](https://www.janestreet.com/quantitative-research/) and
[Quantitative Researcher: Machine Learning](https://www.janestreet.com/join-jane-street/position/8071941002/),
and Susquehanna [Decision Science](https://sig.com/who-we-are/game-theory-decision-science/).

Official owners: Man Group, Two Sigma, Jump Trading, Jane Street, and Susquehanna.
Material inspected 2026-08-27.

Accepted for Lift 2:

- Man AHL supports scientific empirical testing, testable ideas, a common research
  language and codebase, robust technology, and the path from data acquisition
  through research to implementation and practical evidence.
- Two Sigma supports explicit data sourcing, cleaning, labeling, validation,
  versioning, lineage, and treating featurization as a combination of data and
  intellectual work supported by reproducible research infrastructure.
- Jump supports clean/refined data, rigorous validation, fast feedback, and close
  integration across research, engineering, and trading in non-stationary markets.
- Jane Street supports precise experiment design, dataset generation, time-series
  analysis, feature engineering, and clear, reproducible research code.
- Susquehanna supports expected-value reasoning, decisions under uncertainty, and
  pruning decision trees. Game theory is not added to Lift 2.

Engineering implication: Lift 2 uses versioned deterministic measurements,
source-to-output lineage, explicit missingness, compact evidence, and immutable
provisional parameters. No public material is treated as a disclosed proprietary
feature, threshold, infrastructure design, or trading rule.

### Academic boundary — OFI and the IAE-L1 proxy

Sources: Cont, Kukanov, and Stoikov,
[The Price Impact of Order Book Events](https://arxiv.org/abs/1011.6402), and Xu,
Gould, and Howison,
[Multi-Level Order-Flow Imbalance in a Limit Order Book](https://arxiv.org/abs/1907.06230).

Primary papers inspected 2026-08-27. Cont et al. define imbalance from limit-order,
market-order, and cancellation events at the best bid and ask. Xu et al. extend the
measurement across multiple limit-order-book price levels.

Accepted boundary: both constructs require quote/order-book event information that
Lift 2 intentionally does not possess. IAE-L1 therefore measures only causal trade
and completed-bar geometry: gaps, impulse, retest, wick geometry, close position,
and time-of-day context. It is named a **Level-1 proxy** and is never labeled OFI,
multi-level OFI, queue imbalance, aggressor flow, or order-book pressure. L2 remains
a later incremental data test, not a hidden dependency of this lift.

# QuantConnect API Resolution

Resolution date: **2026-08-26**
Runtime certification date: **2026-08-27**

No runtime was executed during the initial API-resolution phase. The resolved source
was subsequently executed in authenticated QC Cloud project `35697180`, build
`67d2fc-f0a27f`. Runtime-qualified statuses below distinguish that later evidence from
static name resolution.

## Pinned official-source baseline

- LEAN: commit [`185c691b89f28bd68e48d53c02147415134975f0`](https://github.com/QuantConnect/Lean/tree/185c691b89f28bd68e48d53c02147415134975f0), 2026-08-25.
- lean-cli: release `1.0.228`, commit [`5277bb669507adb172b0a8ddabab728d1b0dab91`](https://github.com/QuantConnect/lean-cli/tree/5277bb669507adb172b0a8ddabab728d1b0dab91), 2026-08-12.
- LEAN Data Source SDK: commit [`c997edd7c961454ff9582be34c01782b2dc09155`](https://github.com/QuantConnect/Lean.DataSource.SDK/tree/c997edd7c961454ff9582be34c01782b2dc09155), 2026-06-18.
- QuantConnect v2 documentation: living documentation, inspected 2026-08-26;
  the pages do not expose an immutable documentation build identifier.

## Closure re-verification

- Current official LEAN source inspected at commit
  [`07fb0182bfe229edd9445cf675ac6509d0069539`](https://github.com/QuantConnect/Lean/tree/07fb0182bfe229edd9445cf675ac6509d0069539).
- Current official market-hours database SHA-256:
  `d93f0b417cc9df618da4548f78157fd2b49515e0999f16e83ffddcffd54eef41`.
- Official `lean` CLI `1.0.228` and its pinned `quantconnect-stubs==18032` were
  installed in isolated Python 3.11 environments. An explicit stub-backed basic check
  of `main.py` and both QC adapters completed with zero errors or warnings; the
  runtime-independent project remains under the separate strict gate.
- The stubs resolved callback parameter names (`slice`, `symbols_changed`),
  `set_summary_statistic`, `future_chains`, CFTC TFF classes/fields, and the exact
  reference CFTC constants recorded below.
- Final cloud backtests `b22d565d649c5b31650fd033cdc89cf3` (futures) and
  `a7ba4f84937fb19bc3f6f63bc773e3c3` (CFTC) executed the same certified source commit
  under LEAN `2.5.0.0.18036` and CPython `3.11.14`.

## Required resolutions

### Python version

Requirement: Current Python version.

Verified symbol/API: the pinned official foundation Dockerfiles declare Python
3.11. The final project quality environment is CPython `3.11.16`; the executing QC
cloud runtime reported CPython `3.11.14`.

Official source: [DockerfileLeanFoundation](https://github.com/QuantConnect/Lean/blob/185c691b89f28bd68e48d53c02147415134975f0/DockerfileLeanFoundation), [ARM Dockerfile](https://github.com/QuantConnect/Lean/blob/185c691b89f28bd68e48d53c02147415134975f0/DockerfileLeanFoundationARM), [LEAN overview](https://www.quantconnect.com/docs/v2/lean-engine/getting-started).

Source version/date: LEAN `185c691`, 2026-08-25; docs verified 2026-08-26.

Used in file: `pyproject.toml`, `docs/MAC_M4_QC_BOOTSTRAP.md`.

Status: `VERIFIED_LOCAL_AND_QC_CLOUD_PYTHON_3_11`.

### QuantBook

Requirement: QuantBook construction, project imports, and research behavior.

Verified symbol/API: `qb = QuantBook()` and `qb.set_time_zone("UTC")`.
The Research Environment is interactive and does not automatically restrict a
history request to an algorithm clock.

Official source: [Research engine](https://www.quantconnect.com/docs/v2/research-environment/key-concepts/research-engine), [Research initialization](https://www.quantconnect.com/docs/v2/research-environment/initialization), [QuantBook source](https://github.com/QuantConnect/Lean/blob/185c691b89f28bd68e48d53c02147415134975f0/Research/QuantBook.cs).

Source version/date: LEAN `185c691`; docs verified 2026-08-26.

Used in file: Notebook 1 and `systematic_futures/research_lib/quantbook_probe.py`.

Status: `VERIFIED`, with explicit user-code look-ahead responsibility.

Requirement: Bound the interactive QuantBook analysis clock.

Verified symbol/API: `qb.set_start_date(year, month, day)` and the Python
`set_start_date(datetime)` overload used by the adapter. History remains caller-driven;
the project sets this clock no earlier than the requested history end.

Official source: [Research initialization](https://www.quantconnect.com/docs/v2/research-environment/initialization), [QuantBook source](https://github.com/QuantConnect/Lean/blob/185c691b89f28bd68e48d53c02147415134975f0/Research/QuantBook.cs).

Source version/date: LEAN `185c691`; docs verified 2026-08-26.

Used in file: `systematic_futures/qc_adapters/futures_registration.py`, Notebook 1.

Status: `VERIFIED_CONTROL_NOT_A_COMPLETE_LOOK_AHEAD_GUARANTEE`.

### lean project-create

Requirement: Current `lean project-create` command.

Verified symbol/API: `lean project-create --language python "InstitutionalFuturesLift1"`.
`lean create-project` is a documented alias; `project-create` is canonical.

Official source: [lean project-create API](https://www.quantconnect.com/docs/v2/lean-cli/api-reference/lean-project-create), [lean-cli source](https://github.com/QuantConnect/lean-cli/blob/5277bb669507adb172b0a8ddabab728d1b0dab91/lean/commands/create_project.py).

Source version/date: lean-cli `1.0.228`, 2026-08-12; docs verified 2026-08-26.

Used in file: `docs/MAC_M4_QC_BOOTSTRAP.md`.

Status: `VERIFIED`.

### ES futures constant

Requirement: ES Python futures constant.

Verified symbol/API: `Futures.Indices.SP_500_E_MINI`.

Official source: [US Futures supported assets](https://www.quantconnect.com/docs/v2/writing-algorithms/datasets/algoseek/us-futures), [Futures.cs](https://github.com/QuantConnect/Lean/blob/185c691b89f28bd68e48d53c02147415134975f0/Common/Securities/Future/Futures.cs).

Source version/date: LEAN `185c691`; docs verified 2026-08-26.

Used in file: `systematic_futures/config/markets.py`, QC registration adapter.

Status: `VERIFIED`.

### ZN futures constant

Requirement: ZN Python futures constant.

Verified symbol/API: `Futures.Financials.Y_10_TREASURY_NOTE`.

Official source: [US Futures supported assets](https://www.quantconnect.com/docs/v2/writing-algorithms/datasets/algoseek/us-futures), [Futures.cs](https://github.com/QuantConnect/Lean/blob/185c691b89f28bd68e48d53c02147415134975f0/Common/Securities/Future/Futures.cs).

Source version/date: LEAN `185c691`; docs verified 2026-08-26.

Used in file: `systematic_futures/config/markets.py`, QC registration adapter.

Status: `VERIFIED`.

### 6E futures constant

Requirement: 6E Python futures constant.

Verified symbol/API: `Futures.Currencies.EUR`.

Official source: [US Futures supported assets](https://www.quantconnect.com/docs/v2/writing-algorithms/datasets/algoseek/us-futures), [Futures.cs](https://github.com/QuantConnect/Lean/blob/185c691b89f28bd68e48d53c02147415134975f0/Common/Securities/Future/Futures.cs).

Source version/date: LEAN `185c691`; docs verified 2026-08-26.

Used in file: `systematic_futures/config/markets.py`, QC registration adapter.

Status: `VERIFIED`.

### Remaining candidate constants

Requirement: Current Python constants for NQ, RTY, ZT, 6J, and 6B.

Verified symbol/API: `Futures.Indices.NASDAQ_100_E_MINI`,
`Futures.Indices.RUSSELL_2000_E_MINI`, `Futures.Financials.Y_2_TREASURY_NOTE`,
`Futures.Currencies.JPY`, and `Futures.Currencies.GBP`.

Official source: [US Futures supported assets](https://www.quantconnect.com/docs/v2/writing-algorithms/datasets/algoseek/us-futures), [Futures.cs](https://github.com/QuantConnect/Lean/blob/185c691b89f28bd68e48d53c02147415134975f0/Common/Securities/Future/Futures.cs).

Source version/date: LEAN `185c691`; docs verified 2026-08-26.

Used in file: `systematic_futures/config/markets.py` only; not registered by Lift 1.

Status: `VERIFIED`.

### add_future

Requirement: Futures subscription API and filter.

Verified symbol/API: `add_future(ticker, Resolution.MINUTE,
extended_market_hours=True, data_mapping_mode=..., data_normalization_mode=...,
contract_depth_offset=0)` followed by `future.set_filter(0, 182)`.
Documented parameter names are `ticker`, `resolution`, `market`, `fill_forward`,
`leverage`, `extended_market_hours`, `data_mapping_mode`,
`data_normalization_mode`, and `contract_depth_offset`.

Official source: [Futures universes](https://www.quantconnect.com/docs/v2/writing-algorithms/universes/futures), [AddFuture source](https://github.com/QuantConnect/Lean/blob/185c691b89f28bd68e48d53c02147415134975f0/Algorithm/QCAlgorithm.cs#L2207-L2221).

Source version/date: LEAN `185c691`; docs verified 2026-08-26.

Used in file: `systematic_futures/qc_adapters/futures_registration.py`.

Status: `VERIFIED`.

### Mapping mode

Requirement: Open Interest mapping.

Verified symbol/API: `DataMappingMode.OPEN_INTEREST`.

Official source: [Futures universes](https://www.quantconnect.com/docs/v2/writing-algorithms/universes/futures), [Global enum source](https://github.com/QuantConnect/Lean/blob/185c691b89f28bd68e48d53c02147415134975f0/Common/Global.cs#L921-L987).

Source version/date: LEAN `185c691`; docs verified 2026-08-26.

Used in file: QC registration adapter and market configuration name.

Status: `VERIFIED`.

### Normalization mode

Requirement: Backwards Ratio normalization.

Verified symbol/API: `DataNormalizationMode.BACKWARDS_RATIO`.

Official source: [Futures universes](https://www.quantconnect.com/docs/v2/writing-algorithms/universes/futures), [Global enum source](https://github.com/QuantConnect/Lean/blob/185c691b89f28bd68e48d53c02147415134975f0/Common/Global.cs#L921-L987).

Source version/date: LEAN `185c691`; docs verified 2026-08-26.

Used in file: QC registration adapter and market configuration name.

Status: `VERIFIED_FOR_IDENTITY_AND_COVERAGE_ONLY`. Official documentation states
that the entire futures history is used to adjust historical prices. The resulting
continuous adjusted values are not Lift 1 point-in-time-certified signal values.

### Extended-market-hours configuration

Requirement: Extended-market-hours subscription and history configuration.

Verified symbol/API: `extended_market_hours=True` for `add_future` and
`future_history`.

Official source: [Futures universes](https://www.quantconnect.com/docs/v2/writing-algorithms/universes/futures), [Research futures universes](https://www.quantconnect.com/docs/v2/research-environment/datasets/futures/universes).

Source version/date: docs verified 2026-08-26.

Used in file: QC registration adapter and QuantBook research helper.

Status: `VERIFIED`.

### Futures history and contract-chain retrieval

Requirement: Continuous and actual-contract history in research.

Verified symbol/API: `qb.future_history(future.symbol, start, end,
Resolution.MINUTE, fill_forward=False, extended_market_hours=True)`, then
`history.data_frame` and `history.get_expiry_dates()`; continuous history through
`qb.history(TradeBar, future.symbol, start, end, Resolution.MINUTE)`; daily contract
universe through `qb.history(FutureUniverse, future.symbol, start, end, flatten=True)`.

Official source: [Research futures universes](https://www.quantconnect.com/docs/v2/research-environment/datasets/futures/universes), [US Futures](https://www.quantconnect.com/docs/v2/writing-algorithms/datasets/algoseek/us-futures).

Source version/date: docs verified 2026-08-26.

Used in file: `systematic_futures/research_lib/quantbook_probe.py`, Notebook 1.

Status: `VERIFIED`. Python.NET acceptance of timezone-aware Python datetimes is
`NOT_VERIFIED`; the adapter explicitly validates aware UTC, sets QuantBook to UTC,
then removes `tzinfo` only at the documented QC boundary.

### Mapped contract property

Requirement: Continuous versus mapped contract identity.

Verified symbol/API: `future.symbol` is the continuous identity;
`future.mapped` is the current actual mapped contract.

Official source: [Futures universes](https://www.quantconnect.com/docs/v2/writing-algorithms/universes/futures).

Source version/date: docs verified 2026-08-26.

Used in file: QC probe algorithm, probe recorder, QuantBook helper.

Status: `VERIFIED`.

### Mapping-event callback

Requirement: Mapping-event callback and fields.

Verified symbol/API: `on_symbol_changed_events(self,
symbols_changed: SymbolChangedEvents)`; iterate `.items()` and read
`changed_event.old_symbol` and `.new_symbol`.

Official source: [Futures universes](https://www.quantconnect.com/docs/v2/writing-algorithms/universes/futures), [QCAlgorithm callback source](https://github.com/QuantConnect/Lean/blob/185c691b89f28bd68e48d53c02147415134975f0/Algorithm/QCAlgorithm.cs#L1137-L1144).

Source version/date: LEAN `185c691`; docs verified 2026-08-26.

Used in file: root `main.py`, probe recorder.

Status: `VERIFIED`. Documented backtest/live event times do not independently
certify vendor receive or platform delivery timestamps.

### Current Python naming style

Requirement: Current method/property/enum naming conventions.

Verified symbol/API: snake_case methods/properties and UPPER_SNAKE_CASE enum
members/constants in current official Python examples.

Official source: [Futures universes](https://www.quantconnect.com/docs/v2/writing-algorithms/universes/futures), [Futures handling data](https://www.quantconnect.com/docs/v2/writing-algorithms/securities/asset-classes/futures/handling-data).

Source version/date: docs verified 2026-08-26.

Used in file: all QC-facing Python files.

Status: `VERIFIED_FOR_EACH_RECORDED_NAME`; names not recorded here may not be
invented by conversion from C#.

### Cloud backtest command

Requirement: Current cloud backtest command.

Verified symbol/API: `lean cloud backtest PROJECT --push --name NAME`. The project
argument must be discovered from authenticated project state; this repository does
not invent a project name.

Official source: [lean cloud backtest API](https://www.quantconnect.com/docs/v2/lean-cli/api-reference/lean-cloud-backtest), [project workflows](https://www.quantconnect.com/docs/v2/lean-cli/projects/workflows).

Source version/date: lean-cli `1.0.228`; docs verified 2026-08-26.

Used in file: `docs/MAC_M4_QC_BOOTSTRAP.md` and closure execution documentation only.

Status: `VERIFIED_COMMAND_NOT_EXECUTED`.

## Additional APIs used by the read-only probe

Requirement: Algorithm lifecycle and UTC time configuration.

Verified symbol/API: `initialize`, `on_data(slice: Slice)`,
`on_symbol_changed_events(self, symbols_changed: SymbolChangedEvents)`,
`on_end_of_algorithm`, `set_start_date`,
`set_end_date`, `set_time_zone("UTC")`, and `log`.

Official source: [Algorithm engine](https://www.quantconnect.com/docs/v2/writing-algorithms/key-concepts/algorithm-engine), [time zones](https://www.quantconnect.com/docs/v2/writing-algorithms/key-concepts/time-modeling/time-zones), [Futures handling](https://www.quantconnect.com/docs/v2/writing-algorithms/securities/asset-classes/futures/handling-data).

Source version/date: docs verified 2026-08-26.

Used in file: root `main.py`.

Status: `VERIFIED`.

Requirement: Slice, bar, and symbol-property inspection used by the root probe;
chain, expiry, and open-interest inspection required by closure.

Verified symbol/API: `slice.futures_chains`, `slice.bars`, `contract.symbol`,
`contract.expiry`, `contract.open_interest`,
`future.symbol_properties.contract_multiplier`, and
`security.symbol_properties.minimum_price_variation`.

Official source: [US Futures](https://www.quantconnect.com/docs/v2/writing-algorithms/datasets/algoseek/us-futures), [Futures handling data](https://www.quantconnect.com/docs/v2/writing-algorithms/securities/asset-classes/futures/handling-data).

Source version/date: docs verified 2026-08-26.

Used in file: root `main.py` and the probe recorder. The recorder emits expiry,
daily contract/open-interest coverage, session IDs, mapped identities, roll states,
metadata, and raw datetime-boundary observations.

Status: `VERIFIED_AND_EXECUTED_QC_CLOUD`; empirical values are retained in
`artifacts/certification/qc_futures_runtime_probe.json`.

Requirement: Compact deterministic custom statistics.

Verified symbol/API: `self.set_summary_statistic(name, value)`.

Official source: [Statistics results](https://www.quantconnect.com/docs/v2/writing-algorithms/key-concepts/algorithm-engine#09-Statistics), [QCAlgorithm source](https://github.com/QuantConnect/Lean/blob/185c691b89f28bd68e48d53c02147415134975f0/Algorithm/QCAlgorithm.cs).

Source version/date: LEAN `185c691`; docs verified 2026-08-26.

Used in file: root `main.py` for compact per-market rows, mappings, mapping events,
open-interest, tick, multiplier, zero-action counts, and the probe hash.

Status: `VERIFIED_AND_EXECUTED_QC_CLOUD`; the statistics carried compact evidence
after the free-organization log quota was exhausted.

Requirement: Official programmatic cloud-backtest result retrieval.

Verified symbol/API: LEAN CLI API client methods `read_backtest`,
`list_backtests`, and `read_backtest_orders`.

Official source: [lean-cli API modules](https://github.com/QuantConnect/lean-cli/tree/5277bb669507adb172b0a8ddabab728d1b0dab91/lean/api).

Source version/date: lean-cli `1.0.228`, 2026-08-12.

Used in file: not used. Authenticated result retrieval used the official QC web result
surface; the listed CLI client methods remain an alternate verified path.

Status: `VERIFIED_API_NOT_EXECUTED`.

Requirement: CFTC Traders in Financial Futures reference-market constants.

Verified symbol/API: `CFTC.Markets.E_MINI_SP_500` (ES),
`CFTC.Markets.UST_10_Y_NOTE` (ZN), and `CFTC.Markets.EURO_FX` (6E), subscribed with
`add_data(CFTCFinancialFutures, market, Resolution.DAILY)`. The current stubs define
`CFTCFinancialFutures.end_time` as the report publication date/LEAN delivery date,
declare its data timezone Eastern, and expose nullable TFF position fields.

Official source: [CFTC dataset documentation](https://www.quantconnect.com/docs/v2/writing-algorithms/datasets/commodity-futures-trading-commission/commitments-of-traders), official QuantConnect
`quantconnect-stubs==18032` generated API surface.

Source version/date: stubs `18032`; living docs inspected 2026-08-26.

Used in file: `systematic_futures/qc_adapters/futures_registration.py`, CFTC branch
of the recorder, and parameterized read-only root probe.

Status: `VERIFIED_AND_EXECUTED_QC_CLOUD`; all three exact markets delivered real rows,
and their clocks/nullable-field observations are in
`artifacts/certification/cftc_release_delivery_audit.json`.

Requirement: Select the read-only certification probe without a second source tree.

Verified symbol/API: `self.get_parameter("lift1_probe_mode", "futures")`, with exact
allowed values `futures` and `cftc`.

Official source: [algorithm parameters](https://www.quantconnect.com/docs/v2/writing-algorithms/optimization/parameters).

Source version/date: living docs inspected 2026-08-26.

Used in file: root `main.py`.

Status: `VERIFIED_AND_EXECUTED_QC_CLOUD` for both exact parameter modes.

## Exchange time-zone evidence

Requirement: Current QC market-hours database zones for the eight registry roots.

Verified symbol/API: ES/NQ/RTY use `America/New_York`; ZT/ZN/6E/6J/6B use
`America/Chicago`; all eight have data time zone UTC.

Official source: [market-hours-database.json](https://github.com/QuantConnect/Lean/blob/185c691b89f28bd68e48d53c02147415134975f0/Data/market-hours/market-hours-database.json).

Source version/date: LEAN `185c691`, 2026-08-25.

Used in file: `systematic_futures/config/markets.py`.

Status: `VERIFIED`.

## Explicitly limited

- `quantconnect-stubs==18032` was verified and used in an isolated static-check
  environment. It is intentionally not a project dependency because it pulls Pandas,
  Matplotlib, and NumPy solely for editor support; the core remains standard-library
  only.
- Timezone-aware Python `datetime` passage through Python.NET history overloads is
  not verified. The research boundary uses explicit UTC validation and documented
  QuantBook time-zone interpretation instead.
- Ordinary/DST/holiday/early-close mechanics for ES, ZN, and 6E are pinned to the
  current official LEAN market-hours database and tested locally. The cloud probe
  observed semantic session IDs but did not separately serialize QC exchange objects.
- Python.NET runtime datetime types, `repr` values, and verified conversions were
  observed. The source timezone for `SymbolChangedEvent.time` was not established, so
  that single conversion remains withheld.
- CFTC is certified for context only. QC delivered no rows after 2026-05-29 inside the
  configured window, and revision/live-delivery semantics are not claimed.

## Lift 2 API resolution

Resolution date: **2026-08-27**. These entries are source-verified before Lift 2
implementation. Runtime qualification is added only after the exact source executes
in QC Cloud.

### Actual-contract tick subscription

Requirement: subscribe explicitly to the current mapped actual futures contract.

Verified symbol/API: `add_future_contract(symbol, Resolution.TICK,
fill_forward=False, extended_market_hours=True)`. The documented Python overload
accepts an actual `Symbol`; tick resolution provides trade and quote ticks and does
not fill forward.

Official source: [Individual futures contracts](https://www.quantconnect.com/docs/v2/writing-algorithms/securities/asset-classes/futures/requesting-data/individual-contracts),
[AddFutureContract source](https://github.com/QuantConnect/Lean/blob/07fb0182bfe229edd9445cf675ac6509d0069539/Algorithm/QCAlgorithm.cs).

Source version/date: LEAN `07fb018`; living docs inspected 2026-08-27.

Used in file: `systematic_futures/qc_adapters/lift2_runtime.py`.

Status: `VERIFIED_SOURCE_NOT_YET_EXECUTED`.

### Python package initialization in QC Cloud

Requirement: importing one concrete Lift 2 runtime module must not eagerly import
unrelated repository packages or re-enter a partially initialized domain module.

Observed behavior: fresh QC build `b77ac2-941e38` initialized `main.py` but failed
before data delivery with `DatasetCertificationStatus` reported from a partially
initialized `systematic_futures.domain.enums` module. Direct post-failure inspection
then proved that the cloud path held the bytes of `data/policies.py`, despite the
local path containing only enums. The cloud editor synchronization was therefore the
proximate failure; eager package exports remained an avoidable import-order risk.

Resolution: `config`, `domain`, `qc_adapters`, and `research_lib` package
initializers now declare no submodule imports. Callers import concrete symbols from
their defining modules, and a source-boundary regression test enforces the rule.
This changes package loading only; indicator formulas and state transitions are
unchanged.

Correction evidence: all 34 deployed runtime files were synchronized through isolated
editor sessions and independently reopened/read as byte-identical. Fresh build
`4dabc4-360f32` passed initialization on LEAN `2.5.0.0.18036`.

Status: `CLOUD_SOURCE_MISMATCH_RESOLVED`.

### Missing completed-bar buckets in real tick replay

Requirement: IAE formation uses exactly three consecutive completed five-minute bars;
missing buckets must not be treated as adjacent observations or silently filled.

Observed behavior: ES smoke backtest `69edd3f1bd02d166f9170c6223349be6`
reached real tick processing and stopped at 2024-03-04 23:05 UTC when the pure gap
geometry guard rejected a non-consecutive three-bar window.

Resolution: preserve the pure fail-closed guard and exact formation predicate. The
stateful IAE boundary clears its formation window and active gaps on a same-session
bar discontinuity, emits `IAE_BAR_GAP_RESET`, and restarts only from subsequently
completed bars. No synthetic or zero-volume bar is created.

Status: `LOCAL_RECERTIFIED_QC_REPLAY_PENDING`.

### Python project filename compatibility

Requirement: preserve the Lift 2 public module surface while compiling in QC Cloud.

Observed behavior: project `35697180` rejected nested files named `types.py` and
`profile.py` as Python-module conflicts. Replacing them with package directories was
also invalid because a `types` package shadowed the standard library and caused
`from types import GenericAlias` to fail during build `f68193`.

Resolution: the directive-named files remain thin local facades. Runtime
implementations live in `measurement/models.py` and
`measurement/volume_profile.py`, which are the files synchronized to QC Cloud.

Runtime evidence: failed backtest `Sleepy Red Koala`; failed build signature
`f68193`; LEAN `2.5.0.0.18036`.

Status: `VERIFIED_RUNTIME_CONSTRAINT`; the corrected source still requires a new
successful build and replay before certification.

### Tick collection and trade filtering

Requirement: admit traded price/quantity only for the mapped contract.

Verified symbol/API: `slice.ticks` is keyed by `Symbol`; each `Tick` exposes
`tick_type`, `price`, `quantity`, `time`, and `end_time`. `TickType.TRADE` identifies
trades; quote ticks are distinct and are excluded. Official documentation states
that backtests batch ticks in approximately one-millisecond groups, so callback order
is not represented as nanosecond exchange-event sequencing.

Official source: [Handling futures data](https://www.quantconnect.com/docs/v2/writing-algorithms/securities/asset-classes/futures/handling-data),
[Tick source](https://github.com/QuantConnect/Lean/blob/07fb0182bfe229edd9445cf675ac6509d0069539/Common/Data/Market/Tick.cs).

Source version/date: LEAN `07fb018`; living docs inspected 2026-08-27.

Used in file: `systematic_futures/qc_adapters/lift2_runtime.py`.

Status: `VERIFIED_SOURCE_NOT_YET_EXECUTED`; no queue, cancellation, replenishment,
MLOFI, or native exchange-sequence claim is authorized.

### Tick EndTime at the UTC algorithm boundary

Requirement: assign a causal UTC event time without reinterpreting LEAN's delivered
clock as an exchange-local wall clock.

Verified behavior: official time-model documentation states that LEAN uses each data
point's `EndTime` to advance the time frontier, that `Algorithm.Time` equals that
frontier, and that all data is synchronized in UTC before delivery. The Lift 2
algorithm explicitly sets its algorithm timezone to UTC. Tick `Time` and `EndTime`
are equal because ticks are point values.

Official source: [Timeslices](https://www.quantconnect.com/docs/v2/writing-algorithms/key-concepts/time-modeling/timeslices),
[Periods](https://www.quantconnect.com/docs/v2/writing-algorithms/key-concepts/time-modeling/periods),
[Initialization time zone](https://www.quantconnect.com/docs/v2/writing-algorithms/initialization#02-Set-Time-Zone).

Runtime evidence: backtest `58ceb00e5c5444d5dee37f85ffae0045` demonstrated
that treating the delivered naive `EndTime` as exchange-local moved it ahead of the
UTC algorithm frontier and correctly tripped `DataTimingInvariantError`.

Resolution: interpret naive delivered tick `EndTime` under the configured UTC
algorithm timezone. Do not clip, backdate, or silently coerce the time.

Status: `VERIFIED_SOURCE_AND_FAILURE_EVIDENCE`; corrected runtime replay pending.

### Contract metadata

Requirement: obtain the actual contract's minimum price variation.

Verified symbol/API: the `Security` returned by `add_future_contract` exposes
`symbol` and `symbol_properties.minimum_price_variation`.

Official source: [Futures key concepts](https://www.quantconnect.com/docs/v2/writing-algorithms/securities/asset-classes/futures/key-concepts),
[SymbolProperties source](https://github.com/QuantConnect/Lean/blob/07fb0182bfe229edd9445cf675ac6509d0069539/Common/Securities/SymbolProperties.cs).

Source version/date: LEAN `07fb018`; living docs inspected 2026-08-27.

Used in file: `systematic_futures/qc_adapters/lift2_runtime.py`.

Status: `VERIFIED_SOURCE_NOT_YET_EXECUTED`.

### Runtime parameter and version reporting

Requirement: run the same source separately by root when bounded tick replay is
needed.

Verified symbol/API: `get_parameter("lift2_root", "ES")`; algorithm date and UTC
methods, mapping callback, `set_summary_statistic`, continuous `mapped`, futures
chains, and zero-action evidence retain the previously resolved names above.

Official source: [Algorithm parameters](https://www.quantconnect.com/docs/v2/writing-algorithms/optimization/parameters),
[Algorithm statistics](https://www.quantconnect.com/docs/v2/writing-algorithms/key-concepts/algorithm-engine#09-Statistics).

Source version/date: living docs inspected 2026-08-27.

Used in file: `main.py`, `systematic_futures/qc_adapters/lift2_runtime.py`.

Status: `VERIFIED_SOURCE_NOT_YET_EXECUTED`.

### NumPy runtime

Requirement: use the numerical-library version supported by the certified QC Python
environment.

Verified package/version: `numpy==1.26.4` is listed in QuantConnect's current
supported Python libraries. It is the only Lift 2 numerical runtime dependency.

Official source: [Packages and libraries](https://www.quantconnect.com/docs/v2/local-platform/development-environment/packages-and-libraries).

Source version/date: living docs inspected 2026-08-27.

Used in file: `pyproject.toml`, `requirements.txt`, `measurement/imsi.py`, and
`measurement/icm.py`.

Status: `VERIFIED_SOURCE_NOT_YET_EXECUTED`.

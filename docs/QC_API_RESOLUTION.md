# Active QuantConnect API Resolution

Only APIs used by `main.py`, `qc_adapters/futures_registration.py`, and
`qc_adapters/runtime.py` belong here. The boundary fails closed when an expected API or
property is unavailable.

## Algorithm composition

- `QCAlgorithm`, `Slice`, and `SymbolChangedEvents` are imported from `AlgorithmImports`.
- `initialize`, `on_data`, `on_symbol_changed_events`, and `on_end_of_algorithm` delegate to
  `MeasurementRuntime`; they contain no measurement formula or trading call.
- `set_time_zone("UTC")`, `set_start_date`, `set_end_date`, and `get_parameter` configure the
  explicit replay boundary.

Status: source-verified and represented by the boundary tests.

## Continuous future registration

- `add_future` uses the verified constants for ES, NQ, RTY, ZT, ZN, 6E, 6J, and 6B.
- Resolution is `Resolution.MINUTE` with extended hours enabled.
- Mapping is `DataMappingMode.OPEN_INTEREST`.
- Signal-series normalization is `DataNormalizationMode.BACKWARDS_RATIO`.
- Contract depth offset is zero and `set_filter(0, contract_filter_days)` is explicit.

The continuous subscription is mapping identity only. Its adjusted price is not used for
actual-contract Profile or measurement state.

Status: source-verified; exact paths are enumerated in `config/markets.py` and resolved without
fallback in `futures_registration.py`.

## Actual-contract ticks and rolls

- `Security.mapped` identifies the currently mapped contract.
- `SymbolChangedEvents.items()` provides explicit mapping changes.
- `add_future_contract(mapped_symbol, resolution=Resolution.TICK, fill_forward=False,
  extended_market_hours=True)` subscribes the actual contract.
- Only `TickType.TRADE` is admitted. All non-trade ticks are counted and ignored.
- `Tick.end_time`, `price`, `quantity`, `suspicious`, and `sale_condition` are required at the
  boundary. Missing verified metadata raises.
- The pinned Tick surface provides no stable per-trade event identifier. Runtime observations
  therefore carry `PROVENANCE:DEDUPLICATION_UNVERIFIABLE`, which blocks research readiness;
  exactly-once delivery is not assumed.
- `symbol_properties.minimum_price_variation` must be positive and becomes the observed tick
  size for that actual-contract stream.
- Missing price/quantity fields raise, and pre-roll/transition/blackout ticks are counted and
  excluded before they can contaminate an eligible measurement bucket.

Status: source-verified and protected by `tests/test_runtime.py`.

## Pinned verification sources

Checked 2026-08-31 against QuantConnect's official [Futures universe and continuous-contract
documentation](https://www.quantconnect.com/docs/v2/writing-algorithms/universes/futures),
[individual-contract subscription documentation](https://www.quantconnect.com/docs/v2/writing-algorithms/securities/asset-classes/futures/requesting-data/individual-contracts),
and [Futures data-handling documentation](https://www.quantconnect.com/docs/v2/writing-algorithms/securities/asset-classes/futures/handling-data).
The pinned LEAN source is commit `b692bf4788e8b54fc23bdcb5659666bf055ce89f`:
[`Futures.cs`](https://github.com/QuantConnect/Lean/blob/b692bf4788e8b54fc23bdcb5659666bf055ce89f/Common/Securities/Future/Futures.cs)
and [`Tick.cs`](https://github.com/QuantConnect/Lean/blob/b692bf4788e8b54fc23bdcb5659666bf055ce89f/Common/Data/Market/Tick.cs).

Static source verification establishes API names and field semantics only. Equal-`EndTime`
OHLC follows the order delivered inside the QC Tick collection; stable tie ordering across
external QC replays is `NOT_VERIFIED`. A current external QC replay is also `NOT_VERIFIED` by
the local suite.

## Runtime outputs

- `set_summary_statistic` publishes deterministic measurement counts/hashes and explicit zero
  Orders, Insights, and PortfolioTargets.
- `log` emits one canonical `MEASUREMENT_RUNTIME` summary at finalization.

The runtime never calls an order, Insight, PortfolioTarget, holdings, or liquidation API.

## Reverification rule

Any new or changed QuantConnect symbol, enum, overload, property, or CLI operation remains
`NOT_VERIFIED` until checked against current official documentation or LEAN source and added to
this file. Local tests do not substitute for a current-source QuantConnect replay.

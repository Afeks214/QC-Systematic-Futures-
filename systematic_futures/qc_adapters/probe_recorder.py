from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from systematic_futures.data.rolls import MappingObservation, RollManager
from systematic_futures.data.sessions import SessionEngine, reference_session_policies
from systematic_futures.domain.enums import DataQualityStatus, RollState
from systematic_futures.domain.errors import (
    ContractBoundaryError,
    DataQualityError,
    DataTimingInvariantError,
    DuplicateIdentifierError,
    MarketConfigurationError,
    TimeSemanticsError,
    UnverifiedQuantConnectApiError,
)
from systematic_futures.domain.schemas import (
    DataProbeResult,
    MarketDefinition,
    validate_data_probe_result,
)
from systematic_futures.domain.serialization import canonical_json_bytes, sha256_hex
from systematic_futures.research_lib.certification import (
    RuntimeMarketProbeEvidence,
    validate_runtime_market_probe_evidence,
)

_MINUTE = timedelta(minutes=1)


@dataclass(slots=True)
class _ProbeState:
    root: str
    requested_start_utc: datetime
    requested_end_utc: datetime
    continuous_symbol: str
    exchange_timezone: str
    minimum_tick_observed: float | None
    multiplier_observed: float | None
    mapped_contracts: set[str] = field(default_factory=set)
    first_bar_utc: datetime | None = None
    last_bar_utc: datetime | None = None
    rows_received: int = 0
    missing_intervals: int = 0
    mapping_events: int = 0
    mapping_event_times_utc: list[datetime] = field(default_factory=list)
    open_interest_observation_keys: set[str] = field(default_factory=set)
    open_interest_non_null_keys: set[str] = field(default_factory=set)
    contract_expiries_utc: set[datetime] = field(default_factory=set)
    session_ids: set[str] = field(default_factory=set)
    roll_states: set[RollState] = field(default_factory=set)
    current_mapped_symbol: str | None = None
    roll_initialized: bool = False
    chain_observations: int = 0
    quality_flags: set[str] = field(default_factory=set)


def qc_datetime_to_utc(
    value: object,
    field_name: str,
    *,
    naive_source_timezone: str | None = None,
) -> datetime:
    """Normalize a QC boundary datetime using explicit source-zone provenance.

    Units: microsecond-resolution timestamp. Time semantics: aware values are converted
    to UTC; a naive QC/Python.NET value is localized only when the caller supplies the
    documented IANA source timezone for that exact boundary. Missingness: missing,
    non-datetime, naive-without-provenance, or unresolvable-zone values raise. Raises:
    ``TimeSemanticsError``.
    """

    if not isinstance(value, datetime):
        raise TimeSemanticsError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        if naive_source_timezone is None or not naive_source_timezone.strip():
            raise TimeSemanticsError(
                f"{field_name} is naive and requires an explicit source timezone"
            )
        try:
            source_zone = ZoneInfo(naive_source_timezone)
        except ZoneInfoNotFoundError as error:
            raise TimeSemanticsError(
                f"{field_name} source timezone is not resolvable: {naive_source_timezone}"
            ) from error
        return value.replace(tzinfo=source_zone).astimezone(UTC)
    return value.astimezone(UTC)


def qc_datetime_boundary_record(
    value: object,
    field_name: str,
    naive_source_timezone: str | None,
) -> Mapping[str, object]:
    if not isinstance(value, datetime):
        raise TimeSemanticsError(f"{field_name} must be a datetime")
    converted = qc_datetime_to_utc(
        value,
        field_name,
        naive_source_timezone=naive_source_timezone,
    )
    return {
        "python_type": f"{type(value).__module__}.{type(value).__qualname__}",
        "repr": repr(value),
        "tzinfo": None if value.tzinfo is None else str(value.tzinfo),
        "naive_source_timezone": naive_source_timezone,
        "converted_utc": converted,
    }


def _positive_observed_float(value: object, field_name: str) -> float | None:
    if value is None:
        return None
    observed = float(cast(Any, value))
    if not math.isfinite(observed) or observed <= 0:
        raise DataQualityError(f"{field_name} must be finite and positive when present")
    return observed


def qc_symbol_text(value: object, field_name: str, *, optional: bool = False) -> str | None:
    if value is None:
        if optional:
            return None
        raise ContractBoundaryError(f"{field_name} is missing")
    text = str(value)
    if not text.strip():
        if optional:
            return None
        raise ContractBoundaryError(f"{field_name} is blank")
    return text


def _subscription_values(subscription: object) -> tuple[str, float | None, float | None]:
    qc_subscription = cast(Any, subscription)
    continuous = qc_symbol_text(getattr(qc_subscription, "symbol", None), "continuous symbol")
    properties = getattr(qc_subscription, "symbol_properties", None)
    if continuous is None or properties is None:
        raise UnverifiedQuantConnectApiError("Future subscription lacks verified properties")
    minimum_tick = _positive_observed_float(
        getattr(properties, "minimum_price_variation", None), "minimum tick"
    )
    multiplier = _positive_observed_float(
        getattr(properties, "contract_multiplier", None), "contract multiplier"
    )
    return continuous, minimum_tick, multiplier


class FuturesProbeRecorder:
    """Collect small read-only futures coverage summaries from verified QC properties."""

    def __init__(
        self,
        markets: Sequence[MarketDefinition],
        requested_start_utc: datetime,
        requested_end_utc: datetime,
    ) -> None:
        """Create an empty recorder for explicit UTC probe bounds.

        Units: probe bounds have microsecond resolution. Time semantics: both bounds
        must be aware UTC and start must not follow end. Missingness: at least one unique
        market is required. Raises: ``TimeSemanticsError``,
        ``DataTimingInvariantError``, or ``MarketConfigurationError``.
        """

        start = qc_datetime_to_utc(requested_start_utc, "requested_start_utc")
        end = qc_datetime_to_utc(requested_end_utc, "requested_end_utc")
        if start > end:
            raise DataTimingInvariantError("requested probe start cannot follow end")
        roots = tuple(market.root for market in markets)
        if not roots or len(roots) != len(set(roots)):
            raise MarketConfigurationError("probe markets must be non-empty and unique")
        self._root_order = roots
        self._requested_start_utc = start
        self._requested_end_utc = end
        self._states: dict[str, _ProbeState] = {}
        self._root_by_continuous_symbol: dict[str, str] = {}
        self._market_by_root = {market.root: market for market in markets}
        self._session_engine = SessionEngine(reference_session_policies())
        self._roll_manager = RollManager()
        self._datetime_boundaries: dict[str, Mapping[str, object]] = {}

    def register_subscription(self, root: str, subscription: object) -> None:
        """Bind one verified continuous subscription to its immutable root.

        Units: tick is native price units; multiplier is quote value per price unit.
        Time semantics: metadata is observed at registration and is not backdated.
        Missingness: tick or multiplier may remain ``None``; missing identity raises.
        Raises: ``DuplicateIdentifierError``, ``MarketConfigurationError``,
        ``ContractBoundaryError``, ``DataQualityError``, or
        ``UnverifiedQuantConnectApiError``.
        """

        if root not in self._root_order:
            raise MarketConfigurationError(f"unexpected probe root: {root!r}")
        if root in self._states:
            raise DuplicateIdentifierError(f"subscription already registered for {root}")
        continuous, minimum_tick, multiplier = _subscription_values(subscription)
        if continuous in self._root_by_continuous_symbol:
            raise DuplicateIdentifierError(f"continuous symbol reused: {continuous}")
        state = _ProbeState(
            root=root,
            requested_start_utc=self._requested_start_utc,
            requested_end_utc=self._requested_end_utc,
            continuous_symbol=continuous,
            exchange_timezone=self._market_by_root[root].exchange_timezone,
            minimum_tick_observed=minimum_tick,
            multiplier_observed=multiplier,
        )
        self._states[root] = state
        self._root_by_continuous_symbol[continuous] = root
        self._observe_current_mapping(state, subscription, None)

    def _observe_current_mapping(
        self,
        state: _ProbeState,
        subscription: object,
        observed_at_utc: datetime | None,
    ) -> None:
        mapped = qc_symbol_text(
            getattr(cast(Any, subscription), "mapped", None),
            "mapped symbol",
            optional=True,
        )
        if mapped is not None:
            state.mapped_contracts.add(mapped)
        if mapped is None or observed_at_utc is None or state.roll_initialized:
            return
        self._roll_manager.observe_mapping(
            MappingObservation(
                root=state.root,
                old_mapped_symbol=None,
                new_mapped_symbol=mapped,
                observed_at_utc=observed_at_utc,
                effective_at_utc=observed_at_utc,
            )
        )
        state.current_mapped_symbol = mapped
        state.roll_initialized = True
        state.roll_states.add(RollState.NORMAL)

    def _observe_bar_time(self, state: _ProbeState, observed_at_utc: datetime) -> None:
        if state.last_bar_utc is not None:
            if observed_at_utc <= state.last_bar_utc:
                state.quality_flags.add("NON_MONOTONIC_BAR_TIME")
            elif observed_at_utc - state.last_bar_utc > _MINUTE:
                state.missing_intervals += 1
                state.quality_flags.add("UNADJUDICATED_MINUTE_GAP")
        if state.first_bar_utc is None or observed_at_utc < state.first_bar_utc:
            state.first_bar_utc = observed_at_utc
        if state.last_bar_utc is None or observed_at_utc > state.last_bar_utc:
            state.last_bar_utc = observed_at_utc
        state.rows_received += 1

    def _observe_chain(
        self,
        state: _ProbeState,
        slice_data: Any,
        continuous_symbol: object,
        observed_at_utc: datetime,
    ) -> None:
        chains = getattr(slice_data, "future_chains", None)
        if chains is None or not callable(getattr(chains, "get", None)):
            raise UnverifiedQuantConnectApiError("Slice lacks verified future_chains.get boundary")
        canonical = getattr(cast(Any, continuous_symbol), "canonical", continuous_symbol)
        chain = chains.get(canonical)
        if chain is None:
            return
        state.chain_observations += 1
        for contract in chain:
            contract_symbol = qc_symbol_text(
                getattr(contract, "symbol", None),
                "future-chain contract symbol",
            )
            if contract_symbol is None:
                raise ContractBoundaryError("future-chain contract symbol is missing")
            observation_key = f"{contract_symbol}|{observed_at_utc.date().isoformat()}"
            state.open_interest_observation_keys.add(observation_key)
            open_interest = getattr(contract, "open_interest", None)
            if open_interest is not None:
                numeric_open_interest = float(cast(Any, open_interest))
                if not math.isfinite(numeric_open_interest) or numeric_open_interest < 0:
                    raise DataQualityError("open interest must be finite and non-negative")
                state.open_interest_non_null_keys.add(observation_key)
            expiry_value = getattr(contract, "expiry", None)
            expiry_utc = qc_datetime_to_utc(
                expiry_value,
                f"{state.root} contract expiry",
                naive_source_timezone=state.exchange_timezone,
            )
            state.contract_expiries_utc.add(expiry_utc)
            self._record_datetime_boundary(
                f"{state.root}.contract_expiry",
                expiry_value,
                state.exchange_timezone,
            )

    def _record_datetime_boundary(
        self,
        name: str,
        value: object,
        naive_source_timezone: str | None,
    ) -> None:
        if name in self._datetime_boundaries:
            return
        self._datetime_boundaries[name] = qc_datetime_boundary_record(
            value,
            name,
            naive_source_timezone,
        )

    def observe_slice(
        self,
        slice_data: object,
        subscriptions: Mapping[str, object],
    ) -> None:
        """Observe continuous bars and current mapped identities in one QC Slice.

        Units: each observed continuous row is one minute bar. Time semantics: the Slice
        time is interpreted under the explicitly UTC algorithm clock; gaps are raw
        discontinuities and are not holiday/session adjudications. Missingness: absence of
        a bar is retained as absence and does not become a zero row.
        Raises: ``TimeSemanticsError``, ``MarketConfigurationError``,
        ``ContractBoundaryError``, or ``UnverifiedQuantConnectApiError``.
        """

        if set(subscriptions) != set(self._root_order):
            raise MarketConfigurationError("Slice subscriptions do not match probe markets")
        qc_slice = cast(Any, slice_data)
        observed_at = qc_datetime_to_utc(
            getattr(qc_slice, "time", None),
            "slice.time",
            naive_source_timezone="UTC",
        )
        self._record_datetime_boundary("slice.time", getattr(qc_slice, "time", None), "UTC")
        bars = getattr(qc_slice, "bars", None)
        if bars is None or not callable(getattr(bars, "get", None)):
            raise UnverifiedQuantConnectApiError("Slice lacks verified bars.get boundary")
        for root, subscription in subscriptions.items():
            state = self._states.get(root)
            if state is None:
                raise MarketConfigurationError(f"unregistered probe root: {root}")
            symbol = getattr(cast(Any, subscription), "symbol", None)
            if qc_symbol_text(symbol, "continuous symbol") != state.continuous_symbol:
                raise ContractBoundaryError(f"continuous identity changed for {root}")
            self._observe_current_mapping(state, subscription, observed_at)
            bar = cast(Any, bars).get(symbol)
            if bar is not None:
                self._observe_bar_time(state, observed_at)
                state.session_ids.add(self._session_engine.session_id(root, observed_at))
                if state.roll_initialized:
                    state.roll_states.add(self._roll_manager.current_roll_state(root, observed_at))
                self._record_datetime_boundary(
                    f"{root}.bar.time",
                    getattr(bar, "time", None),
                    state.exchange_timezone,
                )
                self._record_datetime_boundary(
                    f"{root}.bar.end_time",
                    getattr(bar, "end_time", None),
                    state.exchange_timezone,
                )
            self._observe_chain(state, qc_slice, symbol, observed_at)

    def observe_mapping_events(
        self,
        symbol_changed_events: object,
        observed_at_utc: object,
    ) -> None:
        """Record explicit continuous-to-actual mapping events without inference.

        Units: one count per delivered ``SymbolChangedEvent``. Time semantics: the
        supplied event-delivery time is normalized under the UTC algorithm clock; no
        effective time is moved backward. Missingness: old symbol may be absent, but new
        symbol and known continuous identity are mandatory.
        Raises: ``TimeSemanticsError``, ``ContractBoundaryError``, or
        ``UnverifiedQuantConnectApiError``.
        """

        qc_events = cast(Any, symbol_changed_events)
        items = getattr(qc_events, "items", None)
        if items is None or not callable(items):
            raise UnverifiedQuantConnectApiError("SymbolChangedEvents lacks items()")
        observed = qc_datetime_to_utc(
            observed_at_utc,
            "mapping observed_at_utc",
            naive_source_timezone="UTC",
        )
        for continuous, changed_event in cast(Any, items)():
            root = self._root_by_continuous_symbol.get(str(continuous))
            if root is None:
                raise ContractBoundaryError(f"unknown continuous mapping event: {continuous}")
            state = self._states[root]
            old_symbol = qc_symbol_text(
                getattr(changed_event, "old_symbol", None), "old mapped symbol", optional=True
            )
            new_symbol = qc_symbol_text(
                getattr(changed_event, "new_symbol", None), "new mapped symbol"
            )
            if old_symbol is not None:
                state.mapped_contracts.add(old_symbol)
            if new_symbol is None:
                raise ContractBoundaryError("mapping event has no new symbol")
            if not state.roll_initialized:
                raise ContractBoundaryError(
                    f"mapping event for {root} arrived before an initial mapped identity"
                )
            transition_state = self._roll_manager.observe_mapping(
                MappingObservation(
                    root=root,
                    old_mapped_symbol=old_symbol,
                    new_mapped_symbol=new_symbol,
                    observed_at_utc=observed,
                    effective_at_utc=observed,
                )
            )
            state.mapped_contracts.add(new_symbol)
            state.mapping_events += 1
            state.mapping_event_times_utc.append(observed)
            state.current_mapped_symbol = new_symbol
            state.roll_states.add(transition_state)
            event_time = getattr(changed_event, "time", None)
            if isinstance(event_time, datetime):
                self._datetime_boundaries.setdefault(
                    f"{root}.mapping_event.time",
                    {
                        "python_type": (
                            f"{type(event_time).__module__}.{type(event_time).__qualname__}"
                        ),
                        "repr": repr(event_time),
                        "tzinfo": (None if event_time.tzinfo is None else str(event_time.tzinfo)),
                        "naive_source_timezone": None,
                        "converted_utc": None,
                        "conversion_status": "WITHHELD_UNVERIFIED_SOURCE_TIMEZONE",
                    },
                )
            if state.last_bar_utc is not None and observed < state.last_bar_utc:
                state.quality_flags.add("MAPPING_EVENT_PRECEDES_LAST_OBSERVED_BAR")

    def _build_result(self, state: _ProbeState) -> DataProbeResult:
        flags = set(state.quality_flags)
        if state.rows_received == 0:
            flags.add("NO_ROWS_RECEIVED")
        if not state.mapped_contracts:
            flags.add("NO_MAPPED_CONTRACT_OBSERVED")
        if state.mapping_events == 0:
            flags.add("NO_MAPPING_EVENT_OBSERVED")
        if state.minimum_tick_observed is None:
            flags.add("MINIMUM_TICK_NOT_OBSERVED")
        if state.multiplier_observed is None:
            flags.add("MULTIPLIER_NOT_OBSERVED")
        quality_flags = tuple(sorted(flags))
        status = DataQualityStatus.VALID
        if state.rows_received == 0:
            status = DataQualityStatus.REJECTED
        elif quality_flags:
            status = DataQualityStatus.PARTIAL
        start = state.first_bar_utc or state.requested_start_utc
        end = state.last_bar_utc or state.requested_end_utc
        values: dict[str, object] = {
            "market": state.root,
            "continuous_symbol": state.continuous_symbol,
            "mapped_contracts_seen": tuple(sorted(state.mapped_contracts)),
            "start_time_utc": start,
            "end_time_utc": end,
            "rows_received": state.rows_received,
            "missing_intervals": state.missing_intervals,
            "mapping_events": state.mapping_events,
            "minimum_tick_observed": state.minimum_tick_observed,
            "multiplier_observed": state.multiplier_observed,
            "data_quality_status": status,
            "quality_flags": quality_flags,
        }
        result = DataProbeResult(
            market=state.root,
            continuous_symbol=state.continuous_symbol,
            mapped_contracts_seen=tuple(sorted(state.mapped_contracts)),
            start_time_utc=start,
            end_time_utc=end,
            rows_received=state.rows_received,
            missing_intervals=state.missing_intervals,
            mapping_events=state.mapping_events,
            minimum_tick_observed=state.minimum_tick_observed,
            multiplier_observed=state.multiplier_observed,
            data_quality_status=status,
            quality_flags=quality_flags,
            result_hash=sha256_hex(values),
        )
        validate_data_probe_result(result)
        return result

    def build_results(self, as_of_utc: object) -> tuple[DataProbeResult, ...]:
        """Build deterministic validated summaries as of an explicit QC clock value.

        Units: counts are observed rows, raw gap occurrences, and mapping events.
        Time semantics: ``as_of_utc`` must not precede any observed row or the requested start.
        Missingness: unobserved rows/metadata produce explicit flags and non-valid status.
        Raises: ``TimeSemanticsError``, ``DataTimingInvariantError``, or schema errors.
        """

        as_of = qc_datetime_to_utc(
            as_of_utc,
            "as_of_utc",
            naive_source_timezone="UTC",
        )
        if as_of < self._requested_start_utc:
            raise DataTimingInvariantError("probe result time precedes requested start")
        for state in self._states.values():
            if state.last_bar_utc is not None and as_of < state.last_bar_utc:
                raise DataTimingInvariantError("probe result time precedes an observed bar")
        if set(self._states) != set(self._root_order):
            raise MarketConfigurationError("not all probe subscriptions were registered")
        return tuple(self._build_result(self._states[root]) for root in self._root_order)

    def build_runtime_market_evidence(
        self,
        as_of_utc: object,
    ) -> tuple[RuntimeMarketProbeEvidence, ...]:
        """Build the detailed empirical evidence rows required by closure review.

        Units: counts, native price ticks, and quote-value multipliers. Time semantics:
        only observations delivered by ``as_of_utc`` are included and every stored clock
        is aware UTC. Missingness: absent chain/OI/session/metadata fields add explicit
        flags; no value is imputed. Raises: timing, QC-boundary, or evidence validation
        errors.
        """

        results = self.build_results(as_of_utc)
        evidence_rows: list[RuntimeMarketProbeEvidence] = []
        for result in results:
            state = self._states[result.market]
            flags = set(result.quality_flags)
            if state.chain_observations == 0:
                flags.add("NO_FUTURE_CHAIN_OBSERVED")
            if not state.open_interest_observation_keys:
                flags.add("NO_OPEN_INTEREST_OBSERVATION")
            if not state.contract_expiries_utc:
                flags.add("NO_CONTRACT_EXPIRY_OBSERVED")
            if not state.session_ids:
                flags.add("NO_SESSION_ID_OBSERVED")
            if not state.roll_states:
                flags.add("NO_ROLL_STATE_OBSERVED")
            mapping_times = tuple(state.mapping_event_times_utc)
            evidence = RuntimeMarketProbeEvidence(
                root=state.root,
                continuous_symbol=state.continuous_symbol,
                first_data_time_utc=result.start_time_utc,
                last_data_time_utc=result.end_time_utc,
                rows_received=state.rows_received,
                mapped_contracts_seen=tuple(sorted(state.mapped_contracts)),
                mapped_contract_count=len(state.mapped_contracts),
                mapping_event_count=state.mapping_events,
                first_mapping_event_time_utc=min(mapping_times) if mapping_times else None,
                last_mapping_event_time_utc=max(mapping_times) if mapping_times else None,
                open_interest_observations=len(state.open_interest_observation_keys),
                open_interest_non_null_observations=len(state.open_interest_non_null_keys),
                minimum_tick_observed=state.minimum_tick_observed,
                multiplier_observed=state.multiplier_observed,
                contract_expiries_seen=tuple(sorted(state.contract_expiries_utc)),
                missing_intervals_detected=state.missing_intervals,
                session_ids_seen=tuple(sorted(state.session_ids)),
                roll_states_seen=tuple(sorted(state.roll_states, key=lambda item: item.value)),
                quality_flags=tuple(sorted(flags)),
            )
            validate_runtime_market_probe_evidence(evidence)
            evidence_rows.append(evidence)
        return tuple(evidence_rows)

    def datetime_boundary_probe_json(self) -> str:
        """Return deterministic runtime datetime-boundary observations.

        Units: microsecond datetime precision. Time semantics: conversions occur only
        under the source-specific timezone recorded in each row; an unresolved mapping
        event clock remains unconverted. Missingness: unobserved boundaries are absent,
        never fabricated. Raises: canonical serialization errors.
        """

        return canonical_json_bytes(
            {
                "schema_version": "lift1-pythonnet-datetime-probe-v1",
                "observations": dict(sorted(self._datetime_boundaries.items())),
            }
        ).decode("utf-8")


def probe_result_json(result: DataProbeResult) -> str:
    """Return one validated probe result as compact canonical JSON.

    Units: inherited from ``DataProbeResult``.
    Time semantics: UTC datetimes use ISO-8601 ``Z``.
    Missingness: explicit ``None`` metadata becomes JSON ``null``.
    Raises: schema, time, or canonical-serialization errors.
    """

    validate_data_probe_result(result)
    return canonical_json_bytes(result).decode("utf-8")


def runtime_market_evidence_json(result: RuntimeMarketProbeEvidence) -> str:
    """Return one validated detailed market-evidence row as canonical JSON.

    Units, time semantics, and missingness are inherited from
    ``RuntimeMarketProbeEvidence``. Raises: evidence or serialization errors.
    """

    validate_runtime_market_probe_evidence(result)
    return canonical_json_bytes(result).decode("utf-8")


__all__ = (
    "FuturesProbeRecorder",
    "probe_result_json",
    "qc_datetime_boundary_record",
    "qc_datetime_to_utc",
    "qc_symbol_text",
    "runtime_market_evidence_json",
)

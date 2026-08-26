from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence, Sized
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from itertools import pairwise
from types import MappingProxyType
from typing import Any, cast
from zoneinfo import ZoneInfo

from systematic_futures.config.markets import get_market_definition
from systematic_futures.data.sessions import SessionEngine
from systematic_futures.domain.enums import DataQualityStatus
from systematic_futures.domain.errors import (
    DataQualityError,
    DataTimingInvariantError,
    TimeSemanticsError,
    UnverifiedQuantConnectApiError,
)
from systematic_futures.domain.schemas import DataProbeResult, validate_data_probe_result
from systematic_futures.domain.serialization import sha256_hex

_MINUTE = timedelta(minutes=1)


@dataclass(frozen=True, slots=True)
class _CoverageFacts:
    root: str
    continuous_symbol: str
    start_time_utc: datetime
    end_time_utc: datetime
    rows_received: int
    timestamps_utc: tuple[datetime, ...]
    missing_intervals: int
    mapping_events: int
    mapped_contracts: tuple[str, ...]
    expiry_coverage: tuple[str, ...]
    open_interest_available: bool
    minimum_tick_observed: float | None
    multiplier_observed: float | None
    duplicate_timestamps: bool


def _require_bundle(history: object) -> Mapping[str, object]:
    if not isinstance(history, Mapping):
        raise DataQualityError("contract history must be a per-market mapping bundle")
    raw_bundle = cast(Mapping[object, object], history)
    if not all(isinstance(key, str) for key in raw_bundle):
        raise DataQualityError("history bundle keys must be strings")
    return cast(Mapping[str, object], raw_bundle)


def _bundle_item(bundle: Mapping[str, object], key: str) -> object:
    if key not in bundle:
        raise DataQualityError(f"history bundle is missing {key!r}")
    return bundle[key]


def _history_frame(history: object) -> object:
    data_frame = getattr(cast(Any, history), "data_frame", None)
    return history if data_frame is None else cast(object, data_frame)


def history_row_count(history: object) -> int:
    """Return the explicit number of rows in a QC history object or DataFrame.

    Units: rows. Time semantics: no timestamp conversion is performed. Missingness:
    an empty history returns zero; an object with no length raises instead of becoming
    zero. Raises: ``DataQualityError``.
    """

    frame = _history_frame(history)
    if not isinstance(frame, Sized):
        raise DataQualityError("history object has no deterministic row count")
    return len(frame)


def _iterable_values(value: object, field_name: str) -> tuple[object, ...]:
    if isinstance(value, str | bytes) or not isinstance(value, Iterable):
        raise DataQualityError(f"{field_name} must be iterable")
    return tuple(cast(Iterable[object], value))


def _index_values(history: object) -> tuple[object, ...]:
    frame = _history_frame(history)
    if history_row_count(frame) == 0:
        return ()
    index = getattr(cast(Any, frame), "index", None)
    if index is None:
        raise DataQualityError("non-empty history lacks an index")
    level_getter = getattr(index, "get_level_values", None)
    values = cast(Any, level_getter)(-1) if callable(level_getter) else index
    return _iterable_values(values, "history index")


def _python_datetime(value: object, field_name: str) -> datetime:
    if isinstance(value, datetime):
        return value
    converter = getattr(cast(Any, value), "to_pydatetime", None)
    if converter is None or not callable(converter):
        raise TimeSemanticsError(f"{field_name} is not datetime-compatible")
    converted = cast(Any, converter)()
    if not isinstance(converted, datetime):
        raise TimeSemanticsError(f"{field_name} did not convert to datetime")
    return converted


def _exchange_timestamp_to_utc(value: object, timezone_name: str) -> datetime:
    timestamp = _python_datetime(value, "history timestamp")
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        timestamp = timestamp.replace(tzinfo=ZoneInfo(timezone_name))
    return timestamp.astimezone(UTC)


def history_timestamps_utc(root: str, history: object) -> tuple[datetime, ...]:
    """Return QC DataFrame index timestamps normalized from exchange time to UTC.

    Units: microsecond-resolution timestamps. Time semantics: official QuantBook docs
    define DataFrame indices in exchange time; naive index values are localized with the
    market registry IANA zone, while aware values are converted to UTC. Missingness: an
    empty history returns an empty tuple. Raises: ``TimeSemanticsError``,
    ``MarketConfigurationError``, or ``DataQualityError``.
    """

    timezone_name = get_market_definition(root).exchange_timezone
    converted = (
        _exchange_timestamp_to_utc(value, timezone_name) for value in _index_values(history)
    )
    return tuple(sorted(converted))


def count_unadjudicated_minute_gaps(timestamps_utc: Sequence[datetime]) -> int:
    """Count consecutive timestamp gaps greater than one minute.

    Units: gap occurrences, not missing-bar quantity. Time semantics: inputs must be
    aware UTC and are compared in ascending unique order; holiday, maintenance, and
    session closures are intentionally not adjudicated. Missingness: no timestamps
    returns zero. Raises: ``TimeSemanticsError``.
    """

    normalized: list[datetime] = []
    for timestamp in timestamps_utc:
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise TimeSemanticsError("gap timestamp must be timezone-aware")
        utc_timestamp = timestamp.astimezone(UTC)
        if utc_timestamp.utcoffset() != timedelta(0):
            raise TimeSemanticsError("gap timestamp must normalize to UTC")
        normalized.append(utc_timestamp)
    ordered = sorted(set(normalized))
    return sum(1 for left, right in pairwise(ordered) if right - left > _MINUTE)


def _column_name(history: object, expected_lower: str) -> object:
    frame = _history_frame(history)
    columns = getattr(cast(Any, frame), "columns", None)
    if columns is None:
        raise DataQualityError("history has no columns")
    for column in _iterable_values(columns, "history columns"):
        if str(column).lower() == expected_lower:
            return column
    raise DataQualityError(f"history lacks required {expected_lower!r} column")


def _column_values(history: object, expected_lower: str) -> tuple[object, ...]:
    if history_row_count(history) == 0:
        return ()
    frame = cast(Any, _history_frame(history))
    series = frame[_column_name(frame, expected_lower)]
    to_list = getattr(series, "tolist", None)
    values = cast(Any, to_list)() if callable(to_list) else series
    return _iterable_values(values, f"{expected_lower} column")


def _not_missing(value: object) -> bool:
    return value is not None and not (isinstance(value, float) and math.isnan(value))


def mapped_contracts_from_history(mapping_history: object) -> tuple[str, ...]:
    """Extract explicit old/new contracts from QC SymbolChangedEvent history.

    Units: symbol identities. Time semantics: only delivered historical mapping events
    are used; no future contract is inferred. Missingness: an empty event history returns
    an empty tuple; missing event columns or values raise.
    Raises: ``DataQualityError``.
    """

    values = _column_values(mapping_history, "oldsymbol") + _column_values(
        mapping_history, "newsymbol"
    )
    if any(not _not_missing(value) or not str(value).strip() for value in values):
        raise DataQualityError("mapping history contains a missing symbol identity")
    return tuple(sorted({str(value) for value in values}))


def expiry_coverage_from_history(chain_history: object) -> tuple[str, ...]:
    """Return explicit contract expiries exposed by ``FutureHistory``.

    Units: ISO-8601 calendar dates. Time semantics: expiry dates are identities, not
    availability timestamps. Missingness: no observed expiries returns an empty tuple;
    a missing verified API raises. Raises: ``UnverifiedQuantConnectApiError`` or
    ``DataQualityError``.
    """

    getter = getattr(cast(Any, chain_history), "get_expiry_dates", None)
    if getter is None or not callable(getter):
        raise UnverifiedQuantConnectApiError("FutureHistory lacks get_expiry_dates")
    values = _iterable_values(cast(Any, getter)(), "expiry dates")
    expiries: set[str] = set()
    for value in values:
        if isinstance(value, datetime):
            expiries.add(value.date().isoformat())
        elif isinstance(value, date):
            expiries.add(value.isoformat())
        else:
            raise DataQualityError("FutureHistory expiry is not a date")
    return tuple(sorted(expiries))


def open_interest_available(universe_history: object) -> bool:
    """Report whether daily FutureUniverse history contains any open-interest value.

    Units: availability boolean; values remain in native contract units. Time semantics:
    daily universe timestamps are not reinterpreted here. Missingness: empty history is
    explicitly unavailable; a non-empty history without the documented column raises.
    Raises: ``DataQualityError``.
    """

    if history_row_count(universe_history) == 0:
        return False
    return any(_not_missing(value) for value in _column_values(universe_history, "openinterest"))


def _required_datetime(bundle: Mapping[str, object], key: str) -> datetime:
    value = _bundle_item(bundle, key)
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise TimeSemanticsError(f"{key} must be a timezone-aware datetime")
    return value.astimezone(UTC)


def _optional_float(bundle: Mapping[str, object], key: str) -> float | None:
    value = _bundle_item(bundle, key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise DataQualityError(f"{key} must be numeric or None")
    observed = float(value)
    if not math.isfinite(observed) or observed <= 0:
        raise DataQualityError(f"{key} must be finite and positive")
    return observed


def _coverage_facts(root: str, history: object) -> _CoverageFacts:
    bundle = _require_bundle(history)
    continuous = _bundle_item(bundle, "continuous_symbol")
    if not isinstance(continuous, str) or not continuous.strip():
        raise DataQualityError("continuous_symbol must be non-blank")
    continuous_history = _bundle_item(bundle, "continuous_history")
    timestamps = history_timestamps_utc(root, continuous_history)
    requested_start = _required_datetime(bundle, "requested_start_utc")
    requested_end = _required_datetime(bundle, "requested_end_utc")
    if requested_start >= requested_end:
        raise DataTimingInvariantError("requested history start must precede end")
    start = timestamps[0] if timestamps else requested_start
    end = timestamps[-1] if timestamps else requested_end
    mapping_history = _bundle_item(bundle, "mapping_history")
    return _CoverageFacts(
        root=root,
        continuous_symbol=continuous,
        start_time_utc=start,
        end_time_utc=end,
        rows_received=history_row_count(continuous_history),
        timestamps_utc=timestamps,
        missing_intervals=count_unadjudicated_minute_gaps(timestamps),
        mapping_events=history_row_count(mapping_history),
        mapped_contracts=mapped_contracts_from_history(mapping_history),
        expiry_coverage=expiry_coverage_from_history(_bundle_item(bundle, "chain_history")),
        open_interest_available=open_interest_available(_bundle_item(bundle, "universe_history")),
        minimum_tick_observed=_optional_float(bundle, "minimum_tick_observed"),
        multiplier_observed=_optional_float(bundle, "multiplier_observed"),
        duplicate_timestamps=len(timestamps) != len(set(timestamps)),
    )


def _quality(facts: _CoverageFacts) -> tuple[DataQualityStatus, tuple[str, ...]]:
    flags: set[str] = set()
    if facts.rows_received == 0:
        flags.add("NO_ROWS_RECEIVED")
    if facts.mapping_events == 0:
        flags.add("NO_MAPPING_EVENT_OBSERVED")
    if not facts.mapped_contracts:
        flags.add("NO_MAPPED_CONTRACT_OBSERVED")
    if not facts.expiry_coverage:
        flags.add("NO_EXPIRY_OBSERVED")
    if not facts.open_interest_available:
        flags.add("OPEN_INTEREST_NOT_OBSERVED")
    if facts.missing_intervals:
        flags.add("UNADJUDICATED_MINUTE_GAP")
    if facts.duplicate_timestamps:
        flags.add("DUPLICATE_TIMESTAMPS")
    if facts.minimum_tick_observed is None:
        flags.add("MINIMUM_TICK_NOT_OBSERVED")
    if facts.multiplier_observed is None:
        flags.add("MULTIPLIER_NOT_OBSERVED")
    ordered = tuple(sorted(flags))
    if facts.rows_received == 0:
        return DataQualityStatus.REJECTED, ordered
    return (DataQualityStatus.PARTIAL if ordered else DataQualityStatus.VALID), ordered


def build_data_probe_result(root: str, history: object) -> DataProbeResult:
    """Build one deterministic DataProbeResult from a per-market history bundle.

    Units: rows, raw minute-gap occurrences, mapping-event counts, native tick, and
    quote-value multiplier. Time semantics: coverage indices are normalized from the
    configured exchange zone to UTC; requested UTC bounds are retained when no rows
    exist. Missingness: absent observations produce explicit flags and non-valid status.
    Raises: schema, quality, timing, market-configuration, or QC-boundary errors.
    """

    facts = _coverage_facts(root, history)
    status, flags = _quality(facts)
    hash_payload: dict[str, object] = {
        "market": root,
        "continuous_symbol": facts.continuous_symbol,
        "mapped_contracts_seen": facts.mapped_contracts,
        "start_time_utc": facts.start_time_utc,
        "end_time_utc": facts.end_time_utc,
        "rows_received": facts.rows_received,
        "missing_intervals": facts.missing_intervals,
        "mapping_events": facts.mapping_events,
        "minimum_tick_observed": facts.minimum_tick_observed,
        "multiplier_observed": facts.multiplier_observed,
        "data_quality_status": status,
        "quality_flags": flags,
    }
    result = DataProbeResult(
        market=root,
        continuous_symbol=facts.continuous_symbol,
        mapped_contracts_seen=facts.mapped_contracts,
        start_time_utc=facts.start_time_utc,
        end_time_utc=facts.end_time_utc,
        rows_received=facts.rows_received,
        missing_intervals=facts.missing_intervals,
        mapping_events=facts.mapping_events,
        minimum_tick_observed=facts.minimum_tick_observed,
        multiplier_observed=facts.multiplier_observed,
        data_quality_status=status,
        quality_flags=flags,
        result_hash=sha256_hex(hash_payload),
    )
    validate_data_probe_result(result)
    return result


def summarize_history_coverage(root: str, history: object) -> Mapping[str, object]:
    """Return display-ready coverage, expiry, mapping, and open-interest facts.

    Units: counts and metadata match ``DataProbeResult``; expiries are ISO dates.
    Time semantics: date coverage is aware UTC and gaps remain unadjudicated. Missingness:
    absent observations are represented by empty tuples, booleans, ``None`` metadata,
    and explicit quality flags. Raises: the same errors as ``build_data_probe_result``.
    """

    facts = _coverage_facts(root, history)
    result = build_data_probe_result(root, history)
    return MappingProxyType(
        {
            "market": root,
            "continuous_symbol": result.continuous_symbol,
            "rows_received": result.rows_received,
            "date_coverage_utc": (result.start_time_utc, result.end_time_utc),
            "expiry_coverage": facts.expiry_coverage,
            "mapped_contracts_observed": result.mapped_contracts_seen,
            "open_interest_available": facts.open_interest_available,
            "missing_intervals": result.missing_intervals,
            "mapping_events": result.mapping_events,
            "minimum_tick_observed": result.minimum_tick_observed,
            "multiplier_observed": result.multiplier_observed,
            "data_quality_status": result.data_quality_status,
            "quality_flags": result.quality_flags,
            "result_hash": result.result_hash,
        }
    )


def session_counts_for_history(
    root: str,
    history: object,
    engine: SessionEngine,
) -> Mapping[str, int]:
    """Count continuous-history rows by the versioned semantic session engine.

    Units: observed minute-row counts. Time semantics: QC exchange-local DataFrame
    timestamps are normalized to UTC before classification; the supplied engine's
    ordinary-day windows are used and do not certify holidays or early closes.
    Missingness: an empty continuous history returns an empty mapping; an unclassifiable
    timestamp raises through ``SessionEngine``. Raises: session, time, market, or raw
    history validation errors.
    """

    bundle = _require_bundle(history)
    timestamps = history_timestamps_utc(root, _bundle_item(bundle, "continuous_history"))
    counts: dict[str, int] = {}
    for timestamp in timestamps:
        session_name = engine.classify(root, timestamp).value
        counts[session_name] = counts.get(session_name, 0) + 1
    return MappingProxyType(dict(sorted(counts.items())))


__all__ = (
    "build_data_probe_result",
    "count_unadjudicated_minute_gaps",
    "expiry_coverage_from_history",
    "history_row_count",
    "history_timestamps_utc",
    "mapped_contracts_from_history",
    "open_interest_available",
    "session_counts_for_history",
    "summarize_history_coverage",
)

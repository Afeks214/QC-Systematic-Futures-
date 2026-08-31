# pyright: reportUnnecessaryIsInstance=false
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from types import MappingProxyType
from typing import cast
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from systematic_futures.domain.enums import DataQualityStatus, SessionType
from systematic_futures.domain.errors import (
    DataQualityError,
    DataTimingInvariantError,
    SessionBoundaryError,
    SystematicFuturesError,
    TimeSemanticsError,
)
from systematic_futures.domain.identifiers import make_lineage_hash
from systematic_futures.domain.serialization import canonical_json_bytes, canonicalize_for_json

_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True, slots=True)
class RawSourceRecord:
    dataset_id: str
    series_id: str
    market: str | None
    instrument_id: str | None
    observation_time_utc: datetime
    source_release_time_utc: datetime | None
    vendor_receive_time_utc: datetime | None
    platform_delivery_time_utc: datetime
    source_version: str
    schema_version: str
    payload: Mapping[str, object]
    revision_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", _immutable_payload(self.payload))


@dataclass(frozen=True, slots=True)
class PointInTimeDatum:
    dataset_id: str
    series_id: str
    market: str | None
    instrument_id: str | None
    observation_time_utc: datetime
    source_release_time_utc: datetime
    vendor_receive_time_utc: datetime | None
    platform_delivery_time_utc: datetime
    usable_from_utc: datetime
    revision_id: str | None
    source_version: str
    schema_version: str
    retrieved_at_utc: datetime
    value: object
    quality_status: DataQualityStatus
    quality_flags: tuple[str, ...]
    missing_reason: str | None
    lineage_hash: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _immutable_value(self.value))


@dataclass(frozen=True, slots=True)
class CertifiedMarketEvent:
    dataset_id: str
    series_id: str
    market: str | None
    instrument_id: str | None
    event_time_utc: datetime
    source_release_time_utc: datetime
    usable_from_utc: datetime
    released_at_utc: datetime
    revision_id: str | None
    source_version: str
    schema_version: str
    quality_status: DataQualityStatus
    quality_flags: tuple[str, ...]
    value: object
    lineage_hash: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _immutable_value(self.value))


@dataclass(frozen=True, slots=True)
class SessionWindow:
    session_name: str
    session_type: SessionType
    timezone_name: str
    start_local_time: time
    end_local_time: time
    crosses_midnight: bool
    policy_version: str


def _require_utc(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise TimeSemanticsError(f"{field_name} must be timezone-aware")
    if value.utcoffset() != timedelta(0):
        raise TimeSemanticsError(f"{field_name} must be normalized to UTC")


def _freeze_canonical_value(value: object) -> object:
    if isinstance(value, dict):
        mapping = cast(dict[str, object], value)
        return MappingProxyType(
            {key: _freeze_canonical_value(item) for key, item in mapping.items()}
        )
    if isinstance(value, list):
        sequence = cast(list[object], value)
        return tuple(_freeze_canonical_value(item) for item in sequence)
    return value


def _immutable_payload(payload: Mapping[str, object]) -> Mapping[str, object]:
    canonical = canonicalize_for_json(payload)
    if not isinstance(canonical, dict):
        raise DataQualityError("payload must canonicalize to a JSON object")
    frozen = _freeze_canonical_value(cast(dict[str, object], canonical))
    if not isinstance(frozen, Mapping):
        raise DataQualityError("payload must canonicalize to a JSON object")
    return cast(Mapping[str, object], frozen)


def _immutable_value(value: object) -> object:
    return _freeze_canonical_value(canonicalize_for_json(value))


def _require_text(
    value: str,
    field_name: str,
    error_type: type[SystematicFuturesError] = DataQualityError,
) -> None:
    if not isinstance(value, str) or not value.strip():
        raise error_type(f"{field_name} must be a non-blank string")


def _require_optional_text(
    value: str | None,
    field_name: str,
    error_type: type[SystematicFuturesError] = DataQualityError,
) -> None:
    if value is not None:
        _require_text(value, field_name, error_type)


def _require_hash(value: str, field_name: str) -> None:
    if not isinstance(value, str) or _SHA256_PATTERN.fullmatch(value) is None:
        raise DataQualityError(f"{field_name} must be a lowercase 64-character SHA-256 digest")


def _require_string_tuple(
    values: tuple[str, ...],
    field_name: str,
    *,
    sorted_unique: bool = False,
) -> None:
    if not isinstance(values, tuple):
        raise DataQualityError(f"{field_name} must be a tuple")
    for index, value in enumerate(values):
        _require_text(value, f"{field_name}[{index}]")
    if sorted_unique and values != tuple(sorted(set(values))):
        raise DataQualityError(f"{field_name} must be sorted and contain no duplicates")


def _require_quality_status(value: object, field_name: str) -> None:
    if not isinstance(value, DataQualityStatus):
        raise DataQualityError(f"{field_name} must be a DataQualityStatus")


def validate_raw_source_record(record: RawSourceRecord) -> None:
    """Validate source identity, UTC timestamps, versions, and raw payload."""

    _require_text(record.dataset_id, "dataset_id")
    _require_text(record.series_id, "series_id")
    _require_optional_text(record.market, "market")
    _require_optional_text(record.instrument_id, "instrument_id")
    _require_utc(record.observation_time_utc, "observation_time_utc")
    if record.source_release_time_utc is not None:
        _require_utc(record.source_release_time_utc, "source_release_time_utc")
        if record.observation_time_utc > record.source_release_time_utc:
            raise DataTimingInvariantError("observation time cannot follow source release")
    if record.vendor_receive_time_utc is not None:
        _require_utc(record.vendor_receive_time_utc, "vendor_receive_time_utc")
    _require_utc(record.platform_delivery_time_utc, "platform_delivery_time_utc")
    _require_text(record.source_version, "source_version")
    _require_text(record.schema_version, "schema_version")
    _require_optional_text(record.revision_id, "revision_id")
    if not isinstance(record.payload, Mapping):
        raise DataQualityError("payload must be a mapping")
    canonical_json_bytes(record.payload)


def validate_point_in_time_datum(datum: PointInTimeDatum) -> None:
    """Validate one datum and its point-in-time availability ordering."""

    _require_text(datum.dataset_id, "dataset_id")
    _require_text(datum.series_id, "series_id")
    _require_optional_text(datum.market, "market")
    _require_optional_text(datum.instrument_id, "instrument_id")
    _require_optional_text(datum.revision_id, "revision_id")
    _require_optional_text(datum.missing_reason, "missing_reason")
    for field_name, value in (
        ("observation_time_utc", datum.observation_time_utc),
        ("source_release_time_utc", datum.source_release_time_utc),
        ("platform_delivery_time_utc", datum.platform_delivery_time_utc),
        ("usable_from_utc", datum.usable_from_utc),
        ("retrieved_at_utc", datum.retrieved_at_utc),
    ):
        _require_utc(value, field_name)
    if datum.vendor_receive_time_utc is not None:
        _require_utc(datum.vendor_receive_time_utc, "vendor_receive_time_utc")
    if datum.observation_time_utc > datum.source_release_time_utc:
        raise DataTimingInvariantError("observation time cannot follow source release")
    if datum.platform_delivery_time_utc > datum.usable_from_utc:
        raise DataTimingInvariantError("platform delivery cannot follow usable-from time")
    if datum.vendor_receive_time_utc is not None and (
        datum.vendor_receive_time_utc > datum.usable_from_utc
    ):
        raise DataTimingInvariantError("vendor receipt cannot follow usable-from time")
    if datum.source_release_time_utc > datum.usable_from_utc:
        raise DataTimingInvariantError("source release cannot follow usable-from time")
    if datum.retrieved_at_utc < datum.platform_delivery_time_utc:
        raise DataTimingInvariantError("retrieval cannot precede platform delivery")
    _require_text(datum.source_version, "source_version")
    _require_text(datum.schema_version, "schema_version")
    _require_quality_status(datum.quality_status, "quality_status")
    _require_string_tuple(datum.quality_flags, "quality_flags", sorted_unique=True)
    _require_hash(datum.lineage_hash, "lineage_hash")
    canonical_json_bytes(datum.value)
    expected_lineage = make_lineage_hash(
        datum.dataset_id,
        datum.series_id,
        datum.observation_time_utc,
        datum.source_version,
        datum.value,
        market=datum.market,
        instrument_id=datum.instrument_id,
        schema_version=datum.schema_version,
        revision_id=datum.revision_id,
        source_release_time_utc=datum.source_release_time_utc,
    )
    if datum.lineage_hash != expected_lineage:
        raise DataQualityError("lineage_hash does not match point-in-time datum content")


def validate_certified_market_event(event: CertifiedMarketEvent) -> None:
    """Validate one availability-gated event without upgrading its quality."""

    _require_text(event.dataset_id, "dataset_id")
    _require_text(event.series_id, "series_id")
    _require_optional_text(event.market, "market")
    _require_optional_text(event.instrument_id, "instrument_id")
    _require_optional_text(event.revision_id, "revision_id")
    _require_utc(event.event_time_utc, "event_time_utc")
    _require_utc(event.source_release_time_utc, "source_release_time_utc")
    _require_utc(event.usable_from_utc, "usable_from_utc")
    _require_utc(event.released_at_utc, "released_at_utc")
    if event.event_time_utc > event.source_release_time_utc:
        raise DataTimingInvariantError("event time cannot follow source release")
    if event.source_release_time_utc > event.usable_from_utc:
        raise DataTimingInvariantError("source release cannot follow usable-from time")
    if event.released_at_utc < event.usable_from_utc:
        raise DataTimingInvariantError("an event cannot be released before usable-from time")
    _require_text(event.source_version, "source_version")
    _require_text(event.schema_version, "schema_version")
    _require_quality_status(event.quality_status, "quality_status")
    _require_string_tuple(event.quality_flags, "quality_flags", sorted_unique=True)
    _require_hash(event.lineage_hash, "lineage_hash")
    canonical_json_bytes(event.value)
    expected_lineage = make_lineage_hash(
        event.dataset_id,
        event.series_id,
        event.event_time_utc,
        event.source_version,
        event.value,
        market=event.market,
        instrument_id=event.instrument_id,
        schema_version=event.schema_version,
        revision_id=event.revision_id,
        source_release_time_utc=event.source_release_time_utc,
    )
    if event.lineage_hash != expected_lineage:
        raise DataQualityError("lineage_hash does not match certified event content")


def validate_session_window(window: SessionWindow) -> None:
    """Validate one versioned exchange-local session window."""

    _require_text(window.session_name, "session_name", SessionBoundaryError)
    _require_text(window.timezone_name, "timezone_name", SessionBoundaryError)
    _require_text(window.policy_version, "policy_version", SessionBoundaryError)
    if not isinstance(window.session_type, SessionType):
        raise SessionBoundaryError("session_type must be a SessionType")
    if not isinstance(window.start_local_time, time) or not isinstance(window.end_local_time, time):
        raise SessionBoundaryError("session boundaries must be datetime.time values")
    if not isinstance(window.crosses_midnight, bool):
        raise SessionBoundaryError("crosses_midnight must be boolean")
    if window.start_local_time == window.end_local_time:
        raise SessionBoundaryError("session start and end must differ")
    if window.crosses_midnight is not (window.start_local_time > window.end_local_time):
        raise SessionBoundaryError("crosses_midnight disagrees with local-time boundaries")
    try:
        ZoneInfo(window.timezone_name)
    except ZoneInfoNotFoundError as error:
        raise SessionBoundaryError(
            f"timezone_name is not resolvable: {window.timezone_name}"
        ) from error


__all__ = (
    "CertifiedMarketEvent",
    "PointInTimeDatum",
    "RawSourceRecord",
    "SessionWindow",
    "validate_certified_market_event",
    "validate_point_in_time_datum",
    "validate_raw_source_record",
    "validate_session_window",
)

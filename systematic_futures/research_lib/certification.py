from __future__ import annotations

# pyright: reportUnnecessaryIsInstance=false
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields
from datetime import UTC, datetime

from systematic_futures.data.rolls import MappingObservation, validate_mapping_observation
from systematic_futures.domain.enums import RollState
from systematic_futures.domain.errors import (
    DataQualityError,
    DataTimingInvariantError,
    TimeSemanticsError,
)
from systematic_futures.domain.serialization import sha256_hex

_REFERENCE_ROOTS = ("ES", "ZN", "6E")


@dataclass(frozen=True, slots=True)
class RuntimeMarketProbeEvidence:
    """One reference market's exact empirical runtime-evidence contract."""

    root: str
    continuous_symbol: str
    first_data_time_utc: datetime
    last_data_time_utc: datetime
    rows_received: int
    mapped_contracts_seen: tuple[str, ...]
    mapped_contract_count: int
    mapping_event_count: int
    first_mapping_event_time_utc: datetime | None
    last_mapping_event_time_utc: datetime | None
    open_interest_observations: int
    open_interest_non_null_observations: int
    minimum_tick_observed: float | None
    multiplier_observed: float | None
    contract_expiries_seen: tuple[datetime, ...]
    missing_intervals_detected: int
    session_ids_seen: tuple[str, ...]
    roll_states_seen: tuple[RollState, ...]
    quality_flags: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class QcFuturesRuntimeProbeArtifact:
    """Qualified read-only QC cloud-backtest evidence contract."""

    qc_project_id: str
    qc_cloud_backtest_id: str
    backtest_name: str
    lean_version: str
    compile_status: str
    backtest_status: str
    started_at_utc: datetime
    finished_at_utc: datetime
    markets: tuple[RuntimeMarketProbeEvidence, ...]
    orders_created: int
    insights_created: int
    portfolio_targets_created: int
    probe_hash: str


def validate_runtime_market_probe_evidence(evidence: RuntimeMarketProbeEvidence) -> None:
    """Validate one exact-market runtime evidence record.

    Units: rows/events/intervals are counts; tick is native price units and
    multiplier is quote value per price unit. Time semantics: all timestamps are
    aware UTC and chronologically ordered. Missingness: tick/multiplier and mapping
    event timestamps may be absent only when their observation counts permit it.
    Raises: ``TimeSemanticsError``, ``DataTimingInvariantError``, or
    ``DataQualityError``.
    """

    _require_text(evidence.root, "root")
    _require_text(evidence.continuous_symbol, "continuous_symbol")
    first_data = _require_utc(evidence.first_data_time_utc, "first_data_time_utc")
    last_data = _require_utc(evidence.last_data_time_utc, "last_data_time_utc")
    if first_data > last_data:
        raise DataTimingInvariantError("first data time cannot follow last data time")
    for field_name, value in (
        ("rows_received", evidence.rows_received),
        ("mapped_contract_count", evidence.mapped_contract_count),
        ("mapping_event_count", evidence.mapping_event_count),
        ("open_interest_observations", evidence.open_interest_observations),
        (
            "open_interest_non_null_observations",
            evidence.open_interest_non_null_observations,
        ),
        ("missing_intervals_detected", evidence.missing_intervals_detected),
    ):
        _require_nonnegative_int(value, field_name)
    _require_sorted_unique_text(evidence.mapped_contracts_seen, "mapped_contracts_seen")
    if evidence.mapped_contract_count != len(evidence.mapped_contracts_seen):
        raise DataQualityError("mapped_contract_count disagrees with mapped contracts")
    if evidence.open_interest_non_null_observations > evidence.open_interest_observations:
        raise DataQualityError("non-null open interest cannot exceed observed open interest")
    _validate_mapping_event_times(evidence)
    _require_optional_positive(evidence.minimum_tick_observed, "minimum_tick_observed")
    _require_optional_positive(evidence.multiplier_observed, "multiplier_observed")
    _require_sorted_unique_datetimes(evidence.contract_expiries_seen, "contract_expiries_seen")
    _require_sorted_unique_text(evidence.session_ids_seen, "session_ids_seen")
    expected_states = tuple(sorted(set(evidence.roll_states_seen), key=lambda state: state.value))
    if evidence.roll_states_seen != expected_states:
        raise DataQualityError("roll_states_seen must be sorted and unique")
    _require_sorted_unique_text(evidence.quality_flags, "quality_flags")


def validate_qc_futures_runtime_probe_artifact(
    artifact: QcFuturesRuntimeProbeArtifact,
) -> None:
    """Validate a completed zero-trading QC futures probe artifact.

    Units: order/Insight/target values are counts. Time semantics: start and finish
    are aware UTC and ordered; nested market clocks are independently validated.
    Missingness: identifiers, versions, statuses, all three reference markets, and
    the content hash are mandatory. Raises: ``TimeSemanticsError``,
    ``DataTimingInvariantError``, or ``DataQualityError``.
    """

    for field_name, value in (
        ("qc_project_id", artifact.qc_project_id),
        ("qc_cloud_backtest_id", artifact.qc_cloud_backtest_id),
        ("backtest_name", artifact.backtest_name),
        ("lean_version", artifact.lean_version),
        ("compile_status", artifact.compile_status),
        ("backtest_status", artifact.backtest_status),
    ):
        _require_text(value, field_name)
    started = _require_utc(artifact.started_at_utc, "started_at_utc")
    finished = _require_utc(artifact.finished_at_utc, "finished_at_utc")
    if started > finished:
        raise DataTimingInvariantError("probe start cannot follow finish")
    roots = tuple(market.root for market in artifact.markets)
    if roots != _REFERENCE_ROOTS:
        raise DataQualityError("runtime artifact must contain ES, ZN, and 6E in order")
    for market in artifact.markets:
        validate_runtime_market_probe_evidence(market)
    for field_name, value in (
        ("orders_created", artifact.orders_created),
        ("insights_created", artifact.insights_created),
        ("portfolio_targets_created", artifact.portfolio_targets_created),
    ):
        _require_nonnegative_int(value, field_name)
        if value != 0:
            raise DataQualityError(f"read-only probe requires {field_name}=0")
    _require_sha256(artifact.probe_hash, "probe_hash")
    if artifact.probe_hash != runtime_probe_content_hash(artifact):
        raise DataQualityError("probe_hash does not match canonical artifact content")


def runtime_probe_content_hash(artifact: QcFuturesRuntimeProbeArtifact) -> str:
    """Hash a runtime probe artifact excluding its self-referential hash field.

    Units: not applicable. Time semantics: nested aware UTC datetimes are serialized
    canonically. Missingness: the supplied ``probe_hash`` is deliberately excluded;
    all other values are preserved. Raises: canonical serialization domain errors.
    """

    content = {
        field.name: getattr(artifact, field.name)
        for field in fields(artifact)
        if field.name != "probe_hash"
    }
    return sha256_hex(content)


def parse_roll_evidence(
    rows: Sequence[Mapping[str, object]],
) -> tuple[MappingObservation, ...]:
    """Parse explicit JSON-like roll rows into validated causal observations.

    Units: timestamps have microsecond resolution. Time semantics: ISO-8601 inputs
    must include an offset and are normalized to UTC; no effective/observed time is
    inferred. Missingness: ``old_mapped_symbol`` alone may be null; every other field
    is mandatory. Raises: ``TimeSemanticsError``, ``DataQualityError``, or
    ``ContractBoundaryError`` from mapping validation.
    """

    observations: list[MappingObservation] = []
    for index, row in enumerate(rows):
        observation = MappingObservation(
            root=_mapping_text(row, "root", index),
            old_mapped_symbol=_mapping_optional_text(row, "old_mapped_symbol", index),
            new_mapped_symbol=_mapping_text(row, "new_mapped_symbol", index),
            observed_at_utc=_mapping_datetime(row, "observed_at_utc", index),
            effective_at_utc=_mapping_datetime(row, "effective_at_utc", index),
        )
        validate_mapping_observation(observation)
        observations.append(observation)
    ordered = tuple(sorted(observations, key=lambda item: (item.root, item.observed_at_utc)))
    if tuple(observations) != ordered:
        raise DataQualityError("roll evidence rows must already be in deterministic order")
    return ordered


def _validate_mapping_event_times(evidence: RuntimeMarketProbeEvidence) -> None:
    first = evidence.first_mapping_event_time_utc
    last = evidence.last_mapping_event_time_utc
    if evidence.mapping_event_count == 0:
        if first is not None or last is not None:
            raise DataQualityError("zero mapping events require null event timestamps")
        return
    if first is None or last is None:
        raise DataQualityError("mapping event timestamps are required when events exist")
    normalized_first = _require_utc(first, "first_mapping_event_time_utc")
    normalized_last = _require_utc(last, "last_mapping_event_time_utc")
    if normalized_first > normalized_last:
        raise DataTimingInvariantError("first mapping event cannot follow last mapping event")


def _mapping_text(row: Mapping[str, object], field_name: str, index: int) -> str:
    value = row.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise DataQualityError(f"roll row {index} {field_name} must be non-blank text")
    return value


def _mapping_optional_text(
    row: Mapping[str, object],
    field_name: str,
    index: int,
) -> str | None:
    value = row.get(field_name)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise DataQualityError(f"roll row {index} {field_name} must be null or text")
    return value


def _mapping_datetime(row: Mapping[str, object], field_name: str, index: int) -> datetime:
    value = row.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise TimeSemanticsError(f"roll row {index} {field_name} must be ISO-8601 text")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise TimeSemanticsError(f"roll row {index} {field_name} is not ISO-8601") from error
    return _require_utc(parsed, f"roll row {index} {field_name}")


def _require_utc(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise TimeSemanticsError(f"{field_name} must be timezone-aware")
    normalized = value.astimezone(UTC)
    if value.utcoffset() != UTC.utcoffset(value):
        raise TimeSemanticsError(f"{field_name} must be normalized to UTC")
    return normalized


def _require_text(value: str, field_name: str) -> None:
    if not value.strip():
        raise DataQualityError(f"{field_name} must be non-blank")


def _require_nonnegative_int(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise DataQualityError(f"{field_name} must be a non-negative integer")


def _require_optional_positive(value: float | None, field_name: str) -> None:
    if value is None:
        return
    if not math.isfinite(value) or value <= 0:
        raise DataQualityError(f"{field_name} must be finite and positive when present")


def _require_sorted_unique_text(values: tuple[str, ...], field_name: str) -> None:
    if any(not value.strip() for value in values):
        raise DataQualityError(f"{field_name} values must be non-blank")
    if values != tuple(sorted(set(values))):
        raise DataQualityError(f"{field_name} must be sorted and unique")


def _require_sorted_unique_datetimes(
    values: tuple[datetime, ...],
    field_name: str,
) -> None:
    normalized = tuple(_require_utc(value, field_name) for value in values)
    if normalized != tuple(sorted(set(normalized))):
        raise DataQualityError(f"{field_name} must be sorted and unique")


def _require_sha256(value: str, field_name: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise DataQualityError(f"{field_name} must be a lowercase SHA-256 digest")


__all__ = (
    "QcFuturesRuntimeProbeArtifact",
    "RuntimeMarketProbeEvidence",
    "parse_roll_evidence",
    "runtime_probe_content_hash",
    "validate_qc_futures_runtime_probe_artifact",
    "validate_runtime_market_probe_evidence",
)

# pyright: reportUnnecessaryIsInstance=false
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from types import MappingProxyType
from typing import cast
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from systematic_futures.domain.enums import (
    AssetClassGroup,
    DataQualityStatus,
    ExperimentDecision,
    ResearchEnvironment,
    RollState,
    SessionType,
)
from systematic_futures.domain.errors import (
    ContractBoundaryError,
    DataQualityError,
    DataTimingInvariantError,
    LedgerIntegrityError,
    MarketConfigurationError,
    SessionBoundaryError,
    SystematicFuturesError,
    TimeSemanticsError,
)
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


@dataclass(frozen=True, slots=True)
class CertifiedMarketEvent:
    dataset_id: str
    series_id: str
    market: str | None
    instrument_id: str | None
    event_time_utc: datetime
    usable_from_utc: datetime
    released_at_utc: datetime
    schema_version: str
    quality_status: DataQualityStatus
    quality_flags: tuple[str, ...]
    value: object
    lineage_hash: str


@dataclass(frozen=True, slots=True)
class MarketDefinition:
    root: str
    asset_class: AssetClassGroup
    qc_future_constant_path: str
    exchange_timezone: str
    session_policy_id: str
    mapping_mode_name: str
    normalization_mode_name: str
    extended_market_hours: bool
    contract_filter_days: int
    enabled_for_reference_probe: bool


@dataclass(frozen=True, slots=True)
class SessionWindow:
    session_name: str
    session_type: SessionType
    timezone_name: str
    start_local_time: time
    end_local_time: time
    crosses_midnight: bool
    policy_version: str


@dataclass(frozen=True, slots=True)
class ContractSnapshot:
    root: str
    continuous_symbol: str
    mapped_symbol: str
    expiry_utc: datetime
    multiplier: float
    minimum_tick: float
    mapping_mode: str
    normalization_mode: str
    roll_state: RollState
    tradable: bool
    as_of_utc: datetime
    metadata_version: str


@dataclass(frozen=True, slots=True)
class DatasetCertification:
    dataset_name: str
    source_name: str
    source_version: str
    schema_version: str
    markets: tuple[str, ...]
    certified_from_utc: datetime
    certified_to_utc: datetime
    availability_rule_id: str
    revision_policy_id: str
    tests_passed: tuple[str, ...]
    known_exceptions: tuple[str, ...]
    permitted_uses: tuple[str, ...]
    prohibited_uses: tuple[str, ...]
    owner: str
    approved_at_utc: datetime
    certification_hash: str


@dataclass(frozen=True, slots=True)
class ExperimentRecord:
    experiment_id: str
    parent_experiment_id: str | None
    hypothesis_name: str
    hypothesis_version: str
    registered_at_utc: datetime
    economic_rationale: str
    expected_direction: str
    target_definition: str
    horizons_minutes: tuple[int, ...]
    markets: tuple[str, ...]
    exclusions: tuple[str, ...]
    development_period: tuple[str, str]
    validation_period: tuple[str, str]
    final_holdout_period: tuple[str, str]
    planned_variants: int
    decision: ExperimentDecision
    decision_reason: str


@dataclass(frozen=True, slots=True)
class ResearchRunManifest:
    run_id: str
    created_at_utc: datetime
    environment: ResearchEnvironment
    python_version: str
    lean_version: str | None
    repository_revision: str | None
    configuration_hash: str
    source_document_hashes: Mapping[str, str]
    dependency_hash: str
    random_seed: int
    reference_markets: tuple[str, ...]
    probe_start_date: str
    probe_end_date: str
    manifest_hash: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_document_hashes",
            _immutable_source_hashes(self.source_document_hashes),
        )


@dataclass(frozen=True, slots=True)
class DataProbeResult:
    market: str
    continuous_symbol: str
    mapped_contracts_seen: tuple[str, ...]
    start_time_utc: datetime
    end_time_utc: datetime
    rows_received: int
    missing_intervals: int
    mapping_events: int
    minimum_tick_observed: float | None
    multiplier_observed: float | None
    data_quality_status: DataQualityStatus
    quality_flags: tuple[str, ...]
    result_hash: str


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
    canonical_mapping = cast(dict[str, object], canonical)
    frozen = _freeze_canonical_value(canonical_mapping)
    if not isinstance(frozen, Mapping):
        raise DataQualityError("payload must canonicalize to a JSON object")
    return cast(Mapping[str, object], frozen)


def _immutable_source_hashes(value: Mapping[str, str]) -> Mapping[str, str]:
    copied: dict[str, str] = {}
    for path, digest in value.items():
        if not isinstance(path, str) or not isinstance(digest, str):
            raise LedgerIntegrityError("source document hash keys and values must be strings")
        copied[path] = digest
    return MappingProxyType(dict(sorted(copied.items())))


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


def _require_hash(
    value: str,
    field_name: str,
    error_type: type[SystematicFuturesError] = DataQualityError,
) -> None:
    if not isinstance(value, str) or _SHA256_PATTERN.fullmatch(value) is None:
        raise error_type(f"{field_name} must be a lowercase 64-character SHA-256 digest")


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


def _parse_iso_date(value: str, field_name: str) -> date:
    _require_text(value, field_name)
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise DataQualityError(f"{field_name} must be an ISO-8601 calendar date") from exc


def _validate_period(value: tuple[str, str], field_name: str) -> None:
    if not isinstance(value, tuple) or len(value) != 2:
        raise DataQualityError(f"{field_name} must contain exactly two ISO date strings")
    start = _parse_iso_date(value[0], f"{field_name}[0]")
    end = _parse_iso_date(value[1], f"{field_name}[1]")
    if start > end:
        raise DataQualityError(f"{field_name} start must not follow its end")


def _require_nonnegative_integer(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise DataQualityError(f"{field_name} must be a non-negative integer")


def _require_positive_number(value: float, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise DataQualityError(f"{field_name} must be a finite positive number")
    if not math.isfinite(value) or value <= 0:
        raise DataQualityError(f"{field_name} must be a finite positive number")


def validate_raw_source_record(record: RawSourceRecord) -> None:
    """Validate the identity, UTC timestamps, versions, and raw payload of a source record.

    Units: payload units are unchanged. Time semantics: all present timestamps must be aware UTC;
    availability ordering is deferred to the dataset policy and normalizer. Missingness: market,
    instrument, source-release time, and vendor-receive time may be ``None``; blank present values
    are rejected. Raises ``TimeSemanticsError`` or ``DataQualityError``.
    """

    _require_text(record.dataset_id, "dataset_id")
    _require_text(record.series_id, "series_id")
    _require_optional_text(record.market, "market")
    _require_optional_text(record.instrument_id, "instrument_id")
    _require_utc(record.observation_time_utc, "observation_time_utc")
    if record.source_release_time_utc is not None:
        _require_utc(record.source_release_time_utc, "source_release_time_utc")
    if record.vendor_receive_time_utc is not None:
        _require_utc(record.vendor_receive_time_utc, "vendor_receive_time_utc")
    _require_utc(record.platform_delivery_time_utc, "platform_delivery_time_utc")
    _require_text(record.source_version, "source_version")
    _require_text(record.schema_version, "schema_version")
    if not isinstance(record.payload, Mapping):
        raise DataQualityError("payload must be a mapping")
    canonical_json_bytes(record.payload)


def validate_point_in_time_datum(datum: PointInTimeDatum) -> None:
    """Validate one normalized point-in-time datum and its availability ordering.

    Units: value units are preserved. Time semantics: timestamps must be UTC; source release,
    vendor receipt when present, and platform delivery may not follow ``usable_from_utc``;
    retrieval may not precede platform delivery. Missingness: optional identity/revision/reason
    fields may be ``None`` but present text may not be blank. Raises ``TimeSemanticsError``,
    ``DataTimingInvariantError``, or ``DataQualityError``.
    """

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
    if datum.platform_delivery_time_utc > datum.usable_from_utc:
        raise DataTimingInvariantError("platform delivery cannot follow usable-from time")
    if (
        datum.vendor_receive_time_utc is not None
        and datum.vendor_receive_time_utc > datum.usable_from_utc
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


def validate_certified_market_event(event: CertifiedMarketEvent) -> None:
    """Validate an availability-gated event without changing its quality state.

    Units: value units are preserved. Time semantics: timestamps must be UTC and gate release
    cannot precede usable-from time. Missingness: market and instrument may be ``None``; values may
    be
    ``None`` only as explicit JSON missingness. Raises ``TimeSemanticsError``,
    ``DataTimingInvariantError``, or ``DataQualityError``.
    """

    _require_text(event.dataset_id, "dataset_id")
    _require_text(event.series_id, "series_id")
    _require_optional_text(event.market, "market")
    _require_optional_text(event.instrument_id, "instrument_id")
    _require_utc(event.event_time_utc, "event_time_utc")
    _require_utc(event.usable_from_utc, "usable_from_utc")
    _require_utc(event.released_at_utc, "released_at_utc")
    if event.released_at_utc < event.usable_from_utc:
        raise DataTimingInvariantError("an event cannot be released before usable-from time")
    _require_text(event.schema_version, "schema_version")
    _require_quality_status(event.quality_status, "quality_status")
    _require_string_tuple(event.quality_flags, "quality_flags", sorted_unique=True)
    _require_hash(event.lineage_hash, "lineage_hash")
    canonical_json_bytes(event.value)


def validate_market_definition(market: MarketDefinition) -> None:
    """Validate a market registry entry without asserting product economics.

    Units: filter horizon is in calendar days. Time semantics: the exchange timezone must resolve
    through the Python timezone database. Missingness: no field may be blank or missing. Raises
    ``MarketConfigurationError`` for any invalid field.
    """

    for field_name, value in (
        ("root", market.root),
        ("qc_future_constant_path", market.qc_future_constant_path),
        ("exchange_timezone", market.exchange_timezone),
        ("session_policy_id", market.session_policy_id),
        ("mapping_mode_name", market.mapping_mode_name),
        ("normalization_mode_name", market.normalization_mode_name),
    ):
        _require_text(value, field_name, MarketConfigurationError)
    if not isinstance(market.asset_class, AssetClassGroup):
        raise MarketConfigurationError("asset_class must be an AssetClassGroup")
    if (
        isinstance(market.contract_filter_days, bool)
        or not isinstance(market.contract_filter_days, int)
        or market.contract_filter_days <= 0
    ):
        raise MarketConfigurationError("contract_filter_days must be a positive integer")
    if not isinstance(market.extended_market_hours, bool):
        raise MarketConfigurationError("extended_market_hours must be boolean")
    if not isinstance(market.enabled_for_reference_probe, bool):
        raise MarketConfigurationError("enabled_for_reference_probe must be boolean")
    try:
        ZoneInfo(market.exchange_timezone)
    except ZoneInfoNotFoundError as exc:
        raise MarketConfigurationError(
            f"exchange_timezone is not resolvable: {market.exchange_timezone}"
        ) from exc


def validate_session_window(window: SessionWindow) -> None:
    """Validate one versioned exchange-local session window.

    Units: local wall-clock times have microsecond precision. Time semantics: the named timezone
    must resolve; equal start/end boundaries are rejected; ``crosses_midnight`` must agree with
    boundary ordering. Missingness: names and policy version may not be blank. Raises
    ``SessionBoundaryError``.
    """

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
    expected_crossing = window.start_local_time > window.end_local_time
    if window.crosses_midnight is not expected_crossing:
        raise SessionBoundaryError("crosses_midnight disagrees with the local-time boundaries")
    try:
        ZoneInfo(window.timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise SessionBoundaryError(
            f"timezone_name is not resolvable: {window.timezone_name}"
        ) from exc


def validate_contract_snapshot(snapshot: ContractSnapshot) -> None:
    """Validate an observed continuous-to-mapped contract snapshot.

    Units: multiplier is quote-value per price unit and minimum tick is in native price units;
    both are observed metadata and must be finite and positive. Time semantics: expiry and as-of
    timestamps must be UTC. Missingness: all identity/metadata fields are mandatory. Raises
    ``TimeSemanticsError``, ``ContractBoundaryError``, or ``DataQualityError``.
    """

    for field_name, value in (
        ("root", snapshot.root),
        ("continuous_symbol", snapshot.continuous_symbol),
        ("mapped_symbol", snapshot.mapped_symbol),
        ("mapping_mode", snapshot.mapping_mode),
        ("normalization_mode", snapshot.normalization_mode),
        ("metadata_version", snapshot.metadata_version),
    ):
        _require_text(value, field_name, ContractBoundaryError)
    _require_utc(snapshot.expiry_utc, "expiry_utc")
    _require_utc(snapshot.as_of_utc, "as_of_utc")
    _require_positive_number(snapshot.multiplier, "multiplier")
    _require_positive_number(snapshot.minimum_tick, "minimum_tick")
    if not isinstance(snapshot.roll_state, RollState):
        raise ContractBoundaryError("roll_state must be a RollState")
    if not isinstance(snapshot.tradable, bool):
        raise ContractBoundaryError("tradable must be boolean")


def validate_dataset_certification(certification: DatasetCertification) -> None:
    """Validate the bounded evidence recorded for a dataset certification.

    Units: dataset-specific units are not altered. Time semantics: certification and approval
    timestamps must be UTC and the certified interval must be ordered. Missingness: required text,
    markets, permitted/prohibited uses, and the certification hash may not be missing. Raises
    ``TimeSemanticsError``, ``DataTimingInvariantError``, or ``DataQualityError``.
    """

    for field_name, value in (
        ("dataset_name", certification.dataset_name),
        ("source_name", certification.source_name),
        ("source_version", certification.source_version),
        ("schema_version", certification.schema_version),
        ("availability_rule_id", certification.availability_rule_id),
        ("revision_policy_id", certification.revision_policy_id),
        ("owner", certification.owner),
    ):
        _require_text(value, field_name)
    _require_string_tuple(certification.markets, "markets")
    if not certification.markets:
        raise DataQualityError("markets must not be empty")
    for field_name, values in (
        ("tests_passed", certification.tests_passed),
        ("known_exceptions", certification.known_exceptions),
        ("permitted_uses", certification.permitted_uses),
        ("prohibited_uses", certification.prohibited_uses),
    ):
        _require_string_tuple(values, field_name)
    if not certification.permitted_uses or not certification.prohibited_uses:
        raise DataQualityError("permitted_uses and prohibited_uses must not be empty")
    _require_utc(certification.certified_from_utc, "certified_from_utc")
    _require_utc(certification.certified_to_utc, "certified_to_utc")
    _require_utc(certification.approved_at_utc, "approved_at_utc")
    if certification.certified_from_utc > certification.certified_to_utc:
        raise DataTimingInvariantError("certification start cannot follow certification end")
    _require_hash(certification.certification_hash, "certification_hash")


def validate_experiment_record(record: ExperimentRecord) -> None:
    """Validate one human-readable, bounded experiment pre-registration.

    Units: any declared horizons are positive whole minutes. Time semantics: registration is UTC
    and each ISO date interval is internally ordered. Missingness: horizons may be empty for a
    non-forecast audit; rationale, target, direction, dates, markets, identifiers, and decision
    reason are mandatory; parent ID and exclusions may be absent/empty. Raises
    ``TimeSemanticsError`` or ``DataQualityError``.
    """

    for field_name, value in (
        ("experiment_id", record.experiment_id),
        ("hypothesis_name", record.hypothesis_name),
        ("hypothesis_version", record.hypothesis_version),
        ("economic_rationale", record.economic_rationale),
        ("expected_direction", record.expected_direction),
        ("target_definition", record.target_definition),
        ("decision_reason", record.decision_reason),
    ):
        _require_text(value, field_name)
    _require_optional_text(record.parent_experiment_id, "parent_experiment_id")
    if "_" in record.hypothesis_name and " " not in record.hypothesis_name:
        raise DataQualityError("hypothesis_name must be human-readable, not an opaque code")
    _require_utc(record.registered_at_utc, "registered_at_utc")
    if not isinstance(record.horizons_minutes, tuple):
        raise DataQualityError("horizons_minutes must be a tuple")
    if any(
        isinstance(horizon, bool) or not isinstance(horizon, int) or horizon <= 0
        for horizon in record.horizons_minutes
    ):
        raise DataQualityError("horizons_minutes must contain only positive integers")
    if record.horizons_minutes != tuple(sorted(set(record.horizons_minutes))):
        raise DataQualityError("horizons_minutes must be sorted and contain no duplicates")
    _require_string_tuple(record.markets, "markets")
    _require_string_tuple(record.exclusions, "exclusions")
    if not record.markets:
        raise DataQualityError("markets must not be empty")
    _validate_period(record.development_period, "development_period")
    _validate_period(record.validation_period, "validation_period")
    _validate_period(record.final_holdout_period, "final_holdout_period")
    if (
        isinstance(record.planned_variants, bool)
        or not isinstance(record.planned_variants, int)
        or record.planned_variants <= 0
    ):
        raise DataQualityError("planned_variants must be a positive integer")
    if not isinstance(record.decision, ExperimentDecision):
        raise DataQualityError("decision must be an ExperimentDecision")


def validate_research_run_manifest(manifest: ResearchRunManifest) -> None:
    """Validate a deterministic research-run manifest and its declared inputs.

    Units: random seed is a dimensionless integer and probe dates are calendar dates. Time
    semantics: creation time is UTC and probe dates are ordered. Missingness: LEAN version and Git
    revision may be ``None``; every other field and at least one source/reference market are
    required. Raises ``TimeSemanticsError``, ``LedgerIntegrityError``, or ``DataQualityError``.
    """

    for field_name, value in (
        ("run_id", manifest.run_id),
        ("python_version", manifest.python_version),
    ):
        _require_text(value, field_name, LedgerIntegrityError)
    _require_optional_text(manifest.lean_version, "lean_version", LedgerIntegrityError)
    _require_optional_text(
        manifest.repository_revision, "repository_revision", LedgerIntegrityError
    )
    _require_utc(manifest.created_at_utc, "created_at_utc")
    if not isinstance(manifest.environment, ResearchEnvironment):
        raise LedgerIntegrityError("environment must be a ResearchEnvironment")
    _require_hash(manifest.configuration_hash, "configuration_hash", LedgerIntegrityError)
    _require_hash(manifest.dependency_hash, "dependency_hash", LedgerIntegrityError)
    _require_hash(manifest.manifest_hash, "manifest_hash", LedgerIntegrityError)
    if not isinstance(manifest.source_document_hashes, Mapping):
        raise LedgerIntegrityError("source_document_hashes must be a mapping")
    if not manifest.source_document_hashes:
        raise LedgerIntegrityError("source_document_hashes must not be empty")
    for path, digest in manifest.source_document_hashes.items():
        _require_text(path, "source_document_hashes key", LedgerIntegrityError)
        _require_hash(digest, f"source_document_hashes[{path}]", LedgerIntegrityError)
    if isinstance(manifest.random_seed, bool) or not isinstance(manifest.random_seed, int):
        raise LedgerIntegrityError("random_seed must be an integer")
    try:
        _require_string_tuple(manifest.reference_markets, "reference_markets")
    except DataQualityError as exc:
        raise LedgerIntegrityError(str(exc)) from exc
    if not manifest.reference_markets:
        raise LedgerIntegrityError("reference_markets must not be empty")
    start = _parse_iso_date(manifest.probe_start_date, "probe_start_date")
    end = _parse_iso_date(manifest.probe_end_date, "probe_end_date")
    if start > end:
        raise LedgerIntegrityError("probe_start_date cannot follow probe_end_date")


def validate_data_probe_result(result: DataProbeResult) -> None:
    """Validate a small, lineage-bearing summary of observed QC futures data.

    Units: tick is native price units and multiplier is quote value per price unit. Time semantics:
    coverage timestamps must be UTC and ordered. Missingness: tick and multiplier may be ``None``
    when the probe did not observe them; all identities and hashes are required. Raises
    ``TimeSemanticsError``, ``DataTimingInvariantError``, or ``DataQualityError``.
    """

    _require_text(result.market, "market")
    _require_text(result.continuous_symbol, "continuous_symbol")
    _require_string_tuple(
        result.mapped_contracts_seen,
        "mapped_contracts_seen",
        sorted_unique=True,
    )
    _require_utc(result.start_time_utc, "start_time_utc")
    _require_utc(result.end_time_utc, "end_time_utc")
    if result.start_time_utc > result.end_time_utc:
        raise DataTimingInvariantError("probe start cannot follow probe end")
    _require_nonnegative_integer(result.rows_received, "rows_received")
    _require_nonnegative_integer(result.missing_intervals, "missing_intervals")
    _require_nonnegative_integer(result.mapping_events, "mapping_events")
    if result.minimum_tick_observed is not None:
        _require_positive_number(result.minimum_tick_observed, "minimum_tick_observed")
    if result.multiplier_observed is not None:
        _require_positive_number(result.multiplier_observed, "multiplier_observed")
    _require_quality_status(result.data_quality_status, "data_quality_status")
    _require_string_tuple(result.quality_flags, "quality_flags", sorted_unique=True)
    _require_hash(result.result_hash, "result_hash")


__all__ = (
    "CertifiedMarketEvent",
    "ContractSnapshot",
    "DataProbeResult",
    "DatasetCertification",
    "ExperimentRecord",
    "MarketDefinition",
    "PointInTimeDatum",
    "RawSourceRecord",
    "ResearchRunManifest",
    "SessionWindow",
    "validate_certified_market_event",
    "validate_contract_snapshot",
    "validate_data_probe_result",
    "validate_dataset_certification",
    "validate_experiment_record",
    "validate_market_definition",
    "validate_point_in_time_datum",
    "validate_raw_source_record",
    "validate_research_run_manifest",
    "validate_session_window",
)

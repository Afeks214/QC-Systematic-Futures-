from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from types import MappingProxyType
from typing import TYPE_CHECKING

from systematic_futures.data.policies import DatasetPolicy
from systematic_futures.data.quality import (
    normalize_quality_flags,
    quality_status_from_evidence,
)
from systematic_futures.domain.enums import RevisionMetadataPolicy
from systematic_futures.domain.errors import (
    DataQualityError,
    DataTimingInvariantError,
    DuplicateIdentifierError,
    TimeSemanticsError,
)
from systematic_futures.domain.identifiers import make_lineage_hash
from systematic_futures.domain.schemas import (
    PointInTimeDatum,
    RawSourceRecord,
    validate_point_in_time_datum,
    validate_raw_source_record,
)
from systematic_futures.domain.serialization import canonical_json_bytes
from systematic_futures.domain.time_semantics import ensure_aware_utc

if TYPE_CHECKING:
    from systematic_futures.data.availability_gate import AvailabilityGate
    from systematic_futures.domain.schemas import CertifiedMarketEvent


class PointInTimeNormalizer:
    """Convert raw observations under immutable, dataset-specific policies."""

    def __init__(self, policies: Mapping[str, DatasetPolicy]) -> None:
        """Copy a non-empty policy registry keyed by exact dataset ID.

        Units: not applicable. Time semantics: policy clocks are evaluated only
        when ``normalize`` is called. Missingness: an empty registry or blank
        key is invalid. Raises: ``DataQualityError`` for malformed registry
        entries.
        """
        copied: dict[str, DatasetPolicy] = {}
        for dataset_id, policy in policies.items():
            if not dataset_id.strip():
                raise DataQualityError("policy registry keys must be non-blank")
            if dataset_id != policy.dataset_id:
                raise DataQualityError(
                    f"policy key {dataset_id!r} does not match {policy.dataset_id!r}"
                )
            copied[dataset_id] = policy
        if not copied:
            raise DataQualityError("at least one dataset policy is required")
        self._policies: Mapping[str, DatasetPolicy] = MappingProxyType(copied)

    def normalize(
        self,
        record: RawSourceRecord,
        retrieved_at_utc: datetime,
    ) -> PointInTimeDatum:
        """Normalize one raw observation without releasing it.

        Units: payload units are preserved. Time semantics: all timestamps are
        normalized to UTC; usable time cannot precede release, vendor receipt,
        or platform delivery; retrieval cannot precede delivery. Missingness:
        a policy-normalized ``None`` is explicitly ``WITHHELD`` and never
        zero-filled. Raises: ``TimeSemanticsError``,
        ``DataTimingInvariantError``, or ``DataQualityError``.
        """
        policy = self._policies.get(record.dataset_id)
        if policy is None:
            raise DataQualityError(f"no policy registered for {record.dataset_id!r}")
        normalized_record = _normalize_raw_record(record)
        validate_raw_source_record(normalized_record)
        flags = normalize_quality_flags(
            (
                *policy.validate_record(normalized_record),
                *_revision_flags(normalized_record, policy),
            )
        )
        usable_from = ensure_aware_utc(
            policy.compute_usable_from(normalized_record),
            "usable_from_utc",
        )
        retrieved_at = ensure_aware_utc(retrieved_at_utc, "retrieved_at_utc")
        release = normalized_record.source_release_time_utc
        if release is None:
            raise TimeSemanticsError("source_release_time_utc is required after policy validation")
        _validate_timing_order(normalized_record, release, usable_from, retrieved_at)
        value = policy.normalize_value(normalized_record)
        canonical_json_bytes(value)
        missing_reason = "policy_normalized_value_missing" if value is None else None
        status = quality_status_from_evidence(flags, missing_reason)
        lineage_hash = make_lineage_hash(
            normalized_record.dataset_id,
            normalized_record.series_id,
            normalized_record.observation_time_utc,
            normalized_record.source_version,
            value,
            market=normalized_record.market,
            instrument_id=normalized_record.instrument_id,
            schema_version=normalized_record.schema_version,
            revision_id=normalized_record.revision_id,
            source_release_time_utc=release,
        )
        datum = PointInTimeDatum(
            dataset_id=normalized_record.dataset_id,
            series_id=normalized_record.series_id,
            market=normalized_record.market,
            instrument_id=normalized_record.instrument_id,
            observation_time_utc=normalized_record.observation_time_utc,
            source_release_time_utc=release,
            vendor_receive_time_utc=normalized_record.vendor_receive_time_utc,
            platform_delivery_time_utc=normalized_record.platform_delivery_time_utc,
            usable_from_utc=usable_from,
            revision_id=normalized_record.revision_id,
            source_version=normalized_record.source_version,
            schema_version=normalized_record.schema_version,
            retrieved_at_utc=retrieved_at,
            value=value,
            quality_status=status,
            quality_flags=flags,
            missing_reason=missing_reason,
            lineage_hash=lineage_hash,
        )
        validate_point_in_time_datum(datum)
        return datum


def _normalize_raw_record(record: RawSourceRecord) -> RawSourceRecord:
    release = (
        ensure_aware_utc(record.source_release_time_utc, "source_release_time_utc")
        if record.source_release_time_utc is not None
        else None
    )
    vendor = (
        ensure_aware_utc(record.vendor_receive_time_utc, "vendor_receive_time_utc")
        if record.vendor_receive_time_utc is not None
        else None
    )
    return RawSourceRecord(
        dataset_id=record.dataset_id,
        series_id=record.series_id,
        market=record.market,
        instrument_id=record.instrument_id,
        observation_time_utc=ensure_aware_utc(
            record.observation_time_utc,
            "observation_time_utc",
        ),
        source_release_time_utc=release,
        vendor_receive_time_utc=vendor,
        platform_delivery_time_utc=ensure_aware_utc(
            record.platform_delivery_time_utc,
            "platform_delivery_time_utc",
        ),
        source_version=record.source_version,
        schema_version=record.schema_version,
        payload=dict(record.payload),
        revision_id=record.revision_id,
    )


def _validate_timing_order(
    record: RawSourceRecord,
    release: datetime,
    usable_from: datetime,
    retrieved_at: datetime,
) -> None:
    if record.observation_time_utc > release:
        raise DataTimingInvariantError("observation time cannot follow source release")
    if record.platform_delivery_time_utc > usable_from:
        raise DataTimingInvariantError("platform delivery cannot follow usable_from")
    if record.vendor_receive_time_utc is not None:
        if record.vendor_receive_time_utc > usable_from:
            raise DataTimingInvariantError("vendor receipt cannot follow usable_from")
    if release > usable_from:
        raise DataTimingInvariantError("source release cannot follow usable_from")
    if retrieved_at < record.platform_delivery_time_utc:
        raise DataTimingInvariantError("retrieval cannot precede platform delivery")


def _revision_flags(record: RawSourceRecord, policy: DatasetPolicy) -> tuple[str, ...]:
    revision_id = record.revision_id
    revision_policy = policy.revision_policy
    if revision_policy is RevisionMetadataPolicy.REQUIRED:
        if revision_id is None or not revision_id.strip():
            raise DataQualityError("revision_id is required by dataset policy")
        return ("revision_metadata_required_and_present",)
    if revision_policy is RevisionMetadataPolicy.NOT_APPLICABLE:
        if revision_id is not None:
            raise DataQualityError("revision_id is prohibited for a non-revising dataset")
        return ("revision_metadata_not_applicable",)
    if revision_policy is RevisionMetadataPolicy.UNVERIFIED:
        if revision_id is None:
            return ("revision_metadata_unverified",)
        return ("revision_metadata_present_but_policy_unverified",)
    if revision_policy is RevisionMetadataPolicy.OPTIONAL:
        return ("revision_metadata_optional",)
    raise DataQualityError("dataset revision policy is invalid")


class PointInTimeEntryPath:
    """Single causal boundary for signal-bearing external observations."""

    def __init__(self, policies: Mapping[str, DatasetPolicy]) -> None:
        """Create a normalizer and availability gate from one policy registry.

        Units: inherited from source payloads. Time semantics: no wall clock is
        read; ingest and release receive explicit UTC instants. Missingness: an
        empty or malformed registry is rejected. Raises policy/normalizer errors.
        """

        from systematic_futures.data.availability_gate import AvailabilityGate

        self._normalizer = PointInTimeNormalizer(policies)
        self._gate: AvailabilityGate = AvailabilityGate()

    def ingest(self, record: RawSourceRecord, *, retrieved_at_utc: datetime) -> PointInTimeDatum:
        """Normalize and submit one datum without bypassing usable-from.

        Units: source units are unchanged. Time semantics: retrieval is explicit
        UTC and release remains gated. Missingness: policy behavior is retained;
        no value is filled. Raises normalization, policy, or duplicate errors.
        """

        datum = self._normalizer.normalize(record, retrieved_at_utc)
        self._gate.submit(datum)
        return datum

    def release(self, decision_time_utc: datetime) -> tuple[CertifiedMarketEvent, ...]:
        """Release only data usable at the supplied decision frontier.

        Units: source units are unchanged. Time semantics: equality is usable;
        future data remains withheld. Missingness and quality are preserved.
        Raises gate validation errors.
        """

        return self._gate.release(decision_time_utc)


class RevisionStore:
    """Append-only point-in-time store for explicitly versioned observations."""

    def __init__(self) -> None:
        """Create an empty revision archive with no implicit clock or values."""

        self._versions: dict[
            tuple[str, str, str | None, str | None, datetime],
            list[PointInTimeDatum],
        ] = {}
        self._revision_keys: set[tuple[str, str, str | None, str | None, datetime, str]] = set()

    def store(self, datum: PointInTimeDatum) -> None:
        """Append one revision without overwriting an existing revision identity.

        Units: values retain dataset units. Time semantics: all datum clocks are
        validated UTC and stored unchanged. Missingness: ``revision_id`` is
        mandatory because this store is only for revisable data. Raises schema,
        ``DataQualityError``, or ``DuplicateIdentifierError``.
        """

        validate_point_in_time_datum(datum)
        revision_id = datum.revision_id
        if revision_id is None or not revision_id.strip():
            raise DataQualityError("RevisionStore requires a non-blank revision_id")
        identity = (
            datum.dataset_id,
            datum.series_id,
            datum.market,
            datum.instrument_id,
            datum.observation_time_utc,
            revision_id,
        )
        if identity in self._revision_keys:
            raise DuplicateIdentifierError(f"revision already stored: {identity}")
        key = identity[:5]
        versions = self._versions.setdefault(key, [])
        if any(
            item.usable_from_utc == datum.usable_from_utc
            and item.source_release_time_utc == datum.source_release_time_utc
            for item in versions
        ):
            raise DataTimingInvariantError(
                "revision precedence is ambiguous at identical availability time"
            )
        versions.append(datum)
        versions.sort(
            key=lambda item: (
                item.usable_from_utc,
                item.source_release_time_utc,
                item.revision_id or "",
            )
        )
        self._revision_keys.add(identity)

    def value_as_known_at(
        self,
        *,
        dataset_id: str,
        series_id: str,
        observation_time_utc: datetime,
        decision_time_utc: datetime,
        market: str | None = None,
        instrument_id: str | None = None,
    ) -> PointInTimeDatum | None:
        """Return the latest revision causally known at one decision time.

        Units: stored values are unchanged. Time semantics: observation period
        and decision frontier are distinct aware UTC clocks; only
        ``usable_from_utc <= decision_time_utc`` is eligible. Missingness: returns
        ``None`` when no revision was yet known. Raises time or identity errors.
        """

        key = _revision_lookup_key(
            dataset_id,
            series_id,
            observation_time_utc,
            market=market,
            instrument_id=instrument_id,
        )
        decision_time = ensure_aware_utc(decision_time_utc, "decision_time_utc")
        eligible = tuple(
            datum for datum in self._versions.get(key, ()) if datum.usable_from_utc <= decision_time
        )
        if not eligible:
            return None
        return eligible[-1]

    def revision_as_known_at(
        self,
        *,
        dataset_id: str,
        series_id: str,
        observation_time_utc: datetime,
        revision_id: str,
        decision_time_utc: datetime,
        market: str | None = None,
        instrument_id: str | None = None,
    ) -> PointInTimeDatum:
        """Return one named revision only if it was known at the frontier.

        Units: stored values are unchanged. Time semantics: future revisions are
        rejected, not returned early. Missingness: unknown revision IDs raise.
        Raises ``DataQualityError`` or ``DataTimingInvariantError``.
        """

        key = _revision_lookup_key(
            dataset_id,
            series_id,
            observation_time_utc,
            market=market,
            instrument_id=instrument_id,
        )
        if not revision_id.strip():
            raise DataQualityError("revision_id must be non-blank")
        decision_time = ensure_aware_utc(decision_time_utc, "decision_time_utc")
        for datum in self._versions.get(key, ()):
            if datum.revision_id != revision_id:
                continue
            if datum.usable_from_utc > decision_time:
                raise DataTimingInvariantError("future revision is not available at decision time")
            return datum
        raise DataQualityError(f"unknown revision_id: {revision_id!r}")


def _revision_lookup_key(
    dataset_id: str,
    series_id: str,
    observation_time_utc: datetime,
    *,
    market: str | None,
    instrument_id: str | None,
) -> tuple[str, str, str | None, str | None, datetime]:
    if not dataset_id.strip() or not series_id.strip():
        raise DataQualityError("dataset_id and series_id must be non-blank")
    if market is not None and not market.strip():
        raise DataQualityError("market must be non-blank when supplied")
    if instrument_id is not None and not instrument_id.strip():
        raise DataQualityError("instrument_id must be non-blank when supplied")
    observation = ensure_aware_utc(observation_time_utc, "observation_time_utc")
    return dataset_id, series_id, market, instrument_id, observation


__all__ = (
    "PointInTimeEntryPath",
    "PointInTimeNormalizer",
    "RevisionStore",
)

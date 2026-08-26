from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from types import MappingProxyType

from systematic_futures.data.policies import DatasetPolicy
from systematic_futures.data.quality import (
    normalize_quality_flags,
    quality_status_from_evidence,
)
from systematic_futures.domain.errors import (
    DataQualityError,
    DataTimingInvariantError,
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


def ensure_aware_utc(value: datetime, field_name: str) -> datetime:
    """Normalize an aware timestamp to UTC.

    Units: UTC datetime. Time semantics: an aware instant is preserved while
    its representation becomes UTC. Missingness: neither the datetime nor a
    blank field name is accepted. Raises: ``TimeSemanticsError`` for naive
    timestamps or a blank field name.
    """
    if not field_name.strip():
        raise TimeSemanticsError("field_name must be non-blank")
    if value.tzinfo is None or value.utcoffset() is None:
        raise TimeSemanticsError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


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
        flags = normalize_quality_flags(policy.validate_record(normalized_record))
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
            revision_id=None,
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
    )


def _validate_timing_order(
    record: RawSourceRecord,
    release: datetime,
    usable_from: datetime,
    retrieved_at: datetime,
) -> None:
    if record.platform_delivery_time_utc > usable_from:
        raise DataTimingInvariantError("platform delivery cannot follow usable_from")
    if record.vendor_receive_time_utc is not None:
        if record.vendor_receive_time_utc > usable_from:
            raise DataTimingInvariantError("vendor receipt cannot follow usable_from")
    if release > usable_from:
        raise DataTimingInvariantError("source release cannot follow usable_from")
    if retrieved_at < record.platform_delivery_time_utc:
        raise DataTimingInvariantError("retrieval cannot precede platform delivery")

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from types import MappingProxyType
from typing import Protocol

from systematic_futures.domain.enums import DatasetCertificationStatus
from systematic_futures.domain.errors import (
    DataQualityError,
    DataTimingInvariantError,
    TimeSemanticsError,
)
from systematic_futures.domain.schemas import RawSourceRecord
from systematic_futures.domain.serialization import canonical_json_bytes


class DatasetPolicy(Protocol):
    """Structural contract for converting one explicitly identified raw dataset."""

    @property
    def dataset_id(self) -> str:
        """Return the immutable dataset identifier; it must never be missing."""
        ...

    @property
    def schema_version(self) -> str:
        """Return the immutable input schema version; it must never be missing."""
        ...

    @property
    def certification_status(self) -> DatasetCertificationStatus:
        """Return the explicit certification state; no fallback is permitted."""
        ...

    def compute_usable_from(self, record: RawSourceRecord) -> datetime:
        """Return the first usable UTC instant for ``record``.

        Units: UTC datetime. Time semantics: the result cannot precede any
        documented release, receipt, or delivery timestamp. Missingness: a
        missing required release timestamp is rejected. Raises:
        ``TimeSemanticsError``, ``DataTimingInvariantError``, or
        ``DataQualityError`` for invalid input.
        """
        ...

    def validate_record(self, record: RawSourceRecord) -> tuple[str, ...]:
        """Validate ``record`` and return deterministic quality flags.

        Units: not applicable. Time semantics: all inspected timestamps must
        be aware; ordering is checked by ``compute_usable_from``. Missingness:
        required identity and version fields are rejected rather than filled.
        Raises: ``TimeSemanticsError`` or ``DataQualityError``.
        """
        ...

    def normalize_value(self, record: RawSourceRecord) -> object:
        """Return a deterministic value without inventing vendor semantics.

        Units: unchanged from the raw payload. Time semantics: none.
        Missingness: an empty payload remains empty and is classified by the
        normalizer; it is never converted to zero. Raises: ``DataQualityError``
        when the payload cannot be represented safely.
        """
        ...


@dataclass(frozen=True, slots=True)
class UnderReviewDatasetPolicy:
    """Conservative policy for a dataset whose vendor semantics are unresolved."""

    dataset_id: str
    schema_version: str
    certification_status: DatasetCertificationStatus = DatasetCertificationStatus.UNDER_REVIEW
    additional_quality_flags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.dataset_id.strip():
            raise DataQualityError("dataset_id must be non-blank")
        if not self.schema_version.strip():
            raise DataQualityError("schema_version must be non-blank")
        if self.certification_status is not DatasetCertificationStatus.UNDER_REVIEW:
            raise DataQualityError("an unresolved policy must remain under review")
        normalized_flags = _normalize_flags(self.additional_quality_flags)
        object.__setattr__(self, "additional_quality_flags", normalized_flags)

    def compute_usable_from(self, record: RawSourceRecord) -> datetime:
        """Compute the maximum explicit release/receipt/delivery timestamp.

        Units: UTC datetime. Time semantics: every input is normalized to UTC;
        no unpublished vendor latency is inferred. Missingness: release time is
        mandatory because ``PointInTimeDatum`` requires it. Raises:
        ``TimeSemanticsError``, ``DataTimingInvariantError``, or
        ``DataQualityError``.
        """
        self._validate_identity(record)
        release = _aware_utc(record.source_release_time_utc, "source_release_time_utc")
        delivery = _aware_utc(
            record.platform_delivery_time_utc,
            "platform_delivery_time_utc",
        )
        candidates = [release, delivery]
        if record.vendor_receive_time_utc is not None:
            candidates.append(_aware_utc(record.vendor_receive_time_utc, "vendor_receive_time_utc"))
        usable_from = max(candidates)
        if delivery > usable_from:
            raise DataTimingInvariantError("delivery cannot follow usable_from")
        return usable_from

    def validate_record(self, record: RawSourceRecord) -> tuple[str, ...]:
        """Validate universal identity/timestamp facts and expose review status.

        Units: not applicable. Time semantics: timestamps must be aware;
        ordering is delegated to ``compute_usable_from``. Missingness: blank
        identities and release times are rejected. Raises:
        ``TimeSemanticsError``, ``DataTimingInvariantError``, or
        ``DataQualityError``.
        """
        self._validate_identity(record)
        _aware_utc(record.observation_time_utc, "observation_time_utc")
        self.compute_usable_from(record)
        flags = ("dataset_certification_under_review", *self.additional_quality_flags)
        return _normalize_flags(flags)

    def normalize_value(self, record: RawSourceRecord) -> object:
        """Copy and preserve the complete raw payload as the normalized value.

        Units: unchanged. Time semantics: none. Missingness: an empty mapping is
        returned empty, never zero-filled. Raises: ``DataQualityError`` when a
        payload key is not a string.
        """
        self._validate_identity(record)
        canonical_json_bytes(record.payload)
        return MappingProxyType(dict(record.payload))

    def _validate_identity(self, record: RawSourceRecord) -> None:
        if record.dataset_id != self.dataset_id:
            raise DataQualityError(
                f"policy {self.dataset_id!r} cannot process {record.dataset_id!r}"
            )
        if record.schema_version != self.schema_version:
            raise DataQualityError(
                f"expected schema {self.schema_version!r}, got {record.schema_version!r}"
            )
        if not record.series_id.strip():
            raise DataQualityError("series_id must be non-blank")
        if not record.source_version.strip():
            raise DataQualityError("source_version must be non-blank")


@dataclass(frozen=True, slots=True)
class SyntheticCftcTimingPolicy:
    """Synthetic Tuesday/Friday timing proof, not a QC CFTC certification."""

    dataset_id: str
    schema_version: str
    manual_exception_utc: datetime | None = None
    certification_status: DatasetCertificationStatus = DatasetCertificationStatus.UNDER_REVIEW

    def __post_init__(self) -> None:
        if not self.dataset_id.strip():
            raise DataQualityError("dataset_id must be non-blank")
        if not self.schema_version.strip():
            raise DataQualityError("schema_version must be non-blank")
        if self.certification_status is not DatasetCertificationStatus.UNDER_REVIEW:
            raise DataQualityError("synthetic CFTC timing must remain under review")
        if self.manual_exception_utc is not None:
            normalized = _aware_utc(self.manual_exception_utc, "manual_exception_utc")
            object.__setattr__(self, "manual_exception_utc", normalized)

    def compute_usable_from(self, record: RawSourceRecord) -> datetime:
        """Return max(Friday release, platform delivery, manual exception).

        Units: UTC datetime. Time semantics: observation must be Tuesday and
        explicit official release must be Friday after it. Vendor receipt, when
        present, is also respected. Missingness: absent official release is
        rejected. Raises: ``TimeSemanticsError``,
        ``DataTimingInvariantError``, or ``DataQualityError``.
        """
        self._validate_identity(record)
        observation = _aware_utc(record.observation_time_utc, "observation_time_utc")
        release = _aware_utc(record.source_release_time_utc, "source_release_time_utc")
        delivery = _aware_utc(
            record.platform_delivery_time_utc,
            "platform_delivery_time_utc",
        )
        if observation.weekday() != 1:
            raise DataTimingInvariantError("synthetic CFTC observation must be Tuesday")
        if release.weekday() != 4:
            raise DataTimingInvariantError("synthetic CFTC release must be Friday")
        if release < observation:
            raise DataTimingInvariantError("CFTC release cannot precede observation")
        candidates = [release, delivery]
        if record.vendor_receive_time_utc is not None:
            candidates.append(_aware_utc(record.vendor_receive_time_utc, "vendor_receive_time_utc"))
        if self.manual_exception_utc is not None:
            candidates.append(self.manual_exception_utc)
        return max(candidates)

    def validate_record(self, record: RawSourceRecord) -> tuple[str, ...]:
        """Validate the synthetic schedule and return explicit caveat flags.

        Units: not applicable. Time semantics: the explicit Tuesday/Friday rule
        is enforced in UTC for this proof policy only. Missingness: required
        identities and release are rejected. Raises: ``TimeSemanticsError``,
        ``DataTimingInvariantError``, or ``DataQualityError``.
        """
        self.compute_usable_from(record)
        return (
            "dataset_certification_under_review",
            "synthetic_cftc_timing_only",
        )

    def normalize_value(self, record: RawSourceRecord) -> object:
        """Copy the CFTC proof payload without interpreting its fields.

        Units: unchanged. Time semantics: none. Missingness: an empty payload
        remains empty. Raises: ``DataQualityError`` for non-string keys.
        """
        self._validate_identity(record)
        canonical_json_bytes(record.payload)
        return MappingProxyType(dict(record.payload))

    def _validate_identity(self, record: RawSourceRecord) -> None:
        if record.dataset_id != self.dataset_id:
            raise DataQualityError(
                f"policy {self.dataset_id!r} cannot process {record.dataset_id!r}"
            )
        if record.schema_version != self.schema_version:
            raise DataQualityError(
                f"expected schema {self.schema_version!r}, got {record.schema_version!r}"
            )
        if not record.series_id.strip():
            raise DataQualityError("series_id must be non-blank")
        if not record.source_version.strip():
            raise DataQualityError("source_version must be non-blank")


@dataclass(frozen=True, slots=True)
class CftcReleaseScheduleEntry:
    """One externally sourced CFTC observation-to-release schedule entry."""

    observation_date: date
    official_release_time_utc: datetime
    holiday_delayed: bool
    manual_exception_utc: datetime | None = None

    def __post_init__(self) -> None:
        validate_cftc_release_schedule_entry(self)
        release = _aware_utc(self.official_release_time_utc, "official_release_time_utc")
        object.__setattr__(self, "official_release_time_utc", release)
        if self.manual_exception_utc is not None:
            manual = _aware_utc(self.manual_exception_utc, "manual_exception_utc")
            object.__setattr__(self, "manual_exception_utc", manual)


def validate_cftc_release_schedule_entry(entry: CftcReleaseScheduleEntry) -> None:
    """Validate an explicit CFTC release schedule entry.

    Units: UTC datetime and report observation date. Time semantics: the
    official release must not precede the UTC start of the observation date; a
    manual exception, when supplied, must not precede the official release.
    Missingness: the official release is mandatory. Raises:
    ``TimeSemanticsError`` or ``DataTimingInvariantError``.
    """
    release = _aware_utc(entry.official_release_time_utc, "official_release_time_utc")
    observation_start = datetime.combine(entry.observation_date, time.min, tzinfo=UTC)
    if release < observation_start:
        raise DataTimingInvariantError("official CFTC release cannot precede observation date")
    if entry.manual_exception_utc is not None:
        manual = _aware_utc(entry.manual_exception_utc, "manual_exception_utc")
        if manual < release:
            raise DataTimingInvariantError("manual CFTC exception cannot precede official release")


@dataclass(frozen=True, slots=True)
class UnderReviewCftcReleaseTimingPolicy:
    """Apply an explicit CFTC schedule without certifying QC delivery semantics."""

    dataset_id: str
    schema_version: str
    release_schedule_version: str
    release_schedule: tuple[CftcReleaseScheduleEntry, ...]
    certification_status: DatasetCertificationStatus = DatasetCertificationStatus.UNDER_REVIEW

    def __post_init__(self) -> None:
        if not self.dataset_id.strip():
            raise DataQualityError("dataset_id must be non-blank")
        if not self.schema_version.strip():
            raise DataQualityError("schema_version must be non-blank")
        if not self.release_schedule_version.strip():
            raise DataQualityError("release_schedule_version must be non-blank")
        if self.certification_status is not DatasetCertificationStatus.UNDER_REVIEW:
            raise DataQualityError("unverified QC CFTC delivery must remain under review")
        if not self.release_schedule:
            raise DataQualityError("release_schedule must not be empty")
        entries_by_date: dict[date, CftcReleaseScheduleEntry] = {}
        for entry in self.release_schedule:
            validate_cftc_release_schedule_entry(entry)
            if entry.observation_date in entries_by_date:
                raise DataQualityError(
                    f"duplicate CFTC observation date: {entry.observation_date.isoformat()}"
                )
            entries_by_date[entry.observation_date] = entry
        ordered = tuple(entries_by_date[key] for key in sorted(entries_by_date))
        object.__setattr__(self, "release_schedule", ordered)

    def compute_usable_from(self, record: RawSourceRecord) -> datetime:
        """Return max(official release, receipt, delivery, manual exception).

        Units: UTC datetime. Time semantics: the record release must exactly
        match the explicit schedule entry for its observation date. Holiday
        delays are represented by a later explicit release, never inferred.
        Missingness: an unlisted observation date or absent release is rejected.
        Raises: ``TimeSemanticsError``, ``DataTimingInvariantError``, or
        ``DataQualityError``.
        """
        self._validate_identity(record)
        observation = _aware_utc(record.observation_time_utc, "observation_time_utc")
        entry = self._entry_for(observation.date())
        release = _aware_utc(record.source_release_time_utc, "source_release_time_utc")
        if release != entry.official_release_time_utc:
            raise DataTimingInvariantError(
                "record release does not match explicit CFTC release schedule"
            )
        delivery = _aware_utc(
            record.platform_delivery_time_utc,
            "platform_delivery_time_utc",
        )
        candidates = [release, delivery]
        if record.vendor_receive_time_utc is not None:
            candidates.append(_aware_utc(record.vendor_receive_time_utc, "vendor_receive_time_utc"))
        if entry.manual_exception_utc is not None:
            candidates.append(entry.manual_exception_utc)
        return max(candidates)

    def validate_record(self, record: RawSourceRecord) -> tuple[str, ...]:
        """Validate one scheduled CFTC record and return caveat flags.

        Units: not applicable. Time semantics: schedule identity and all
        availability clocks are checked by ``compute_usable_from``.
        Missingness: unscheduled observations are rejected without fallback.
        Raises: ``TimeSemanticsError``, ``DataTimingInvariantError``, or
        ``DataQualityError``.
        """
        observation = _aware_utc(record.observation_time_utc, "observation_time_utc")
        entry = self._entry_for(observation.date())
        self.compute_usable_from(record)
        flags = [
            "cftc_explicit_release_schedule_applied",
            "dataset_certification_under_review",
            "qc_cftc_delivery_not_certified",
        ]
        flags.append(
            "cftc_holiday_delayed_release" if entry.holiday_delayed else "cftc_ordinary_release"
        )
        if entry.manual_exception_utc is not None:
            flags.append("cftc_manual_exception_applied")
        return _normalize_flags(tuple(flags))

    def normalize_value(self, record: RawSourceRecord) -> object:
        """Copy a CFTC payload without interpreting fields or filling nulls.

        Units: unchanged from the raw payload. Time semantics: none.
        Missingness: empty mappings and explicit null values are preserved.
        Raises: ``DataQualityError`` when canonical serialization fails.
        """
        self._validate_identity(record)
        canonical_json_bytes(record.payload)
        return MappingProxyType(dict(record.payload))

    def _entry_for(self, observation_date: date) -> CftcReleaseScheduleEntry:
        for entry in self.release_schedule:
            if entry.observation_date == observation_date:
                return entry
        raise DataQualityError(f"no CFTC release schedule entry for {observation_date.isoformat()}")

    def _validate_identity(self, record: RawSourceRecord) -> None:
        if record.dataset_id != self.dataset_id:
            raise DataQualityError(
                f"policy {self.dataset_id!r} cannot process {record.dataset_id!r}"
            )
        if record.schema_version != self.schema_version:
            raise DataQualityError(
                f"expected schema {self.schema_version!r}, got {record.schema_version!r}"
            )
        if not record.series_id.strip():
            raise DataQualityError("series_id must be non-blank")
        if not record.source_version.strip():
            raise DataQualityError("source_version must be non-blank")


def _aware_utc(value: datetime | None, field_name: str) -> datetime:
    if value is None:
        raise TimeSemanticsError(f"{field_name} is required")
    if value.tzinfo is None or value.utcoffset() is None:
        raise TimeSemanticsError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _normalize_flags(flags: tuple[str, ...]) -> tuple[str, ...]:
    normalized: set[str] = set()
    for flag in flags:
        candidate = flag.strip()
        if not candidate:
            raise DataQualityError("quality flags must be non-blank")
        normalized.add(candidate)
    return tuple(sorted(normalized))

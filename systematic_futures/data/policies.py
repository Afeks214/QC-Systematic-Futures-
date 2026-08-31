# pyright: reportUnnecessaryIsInstance=false
from dataclasses import dataclass
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Protocol

from systematic_futures.domain.enums import RevisionMetadataPolicy
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
    def revision_policy(self) -> RevisionMetadataPolicy:
        """Return the explicit revision-identity requirement for this dataset."""
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
    revision_policy: RevisionMetadataPolicy = RevisionMetadataPolicy.UNVERIFIED
    additional_quality_flags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.dataset_id.strip():
            raise DataQualityError("dataset_id must be non-blank")
        if not self.schema_version.strip():
            raise DataQualityError("schema_version must be non-blank")
        if not isinstance(self.revision_policy, RevisionMetadataPolicy):
            raise DataQualityError("revision_policy must be explicit")
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

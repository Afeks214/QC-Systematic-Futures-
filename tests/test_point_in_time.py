from __future__ import annotations

from datetime import UTC, datetime

import pytest

from systematic_futures.data.point_in_time import PointInTimeNormalizer
from systematic_futures.domain.enums import RevisionMetadataPolicy
from systematic_futures.domain.errors import DataTimingInvariantError, TimeSemanticsError
from systematic_futures.domain.schemas import RawSourceRecord
from systematic_futures.domain.time_semantics import ensure_aware_utc


class _InvalidTimingPolicy:
    dataset_id = "synthetic.invalid_timing"
    schema_version = "1.0"
    revision_policy = RevisionMetadataPolicy.NOT_APPLICABLE

    def compute_usable_from(self, record: RawSourceRecord) -> datetime:
        return record.observation_time_utc

    def validate_record(self, record: RawSourceRecord) -> tuple[str, ...]:
        return ()

    def normalize_value(self, record: RawSourceRecord) -> object:
        return record.payload


def test_naive_datetime_raises_time_semantics_error() -> None:
    with pytest.raises(TimeSemanticsError):
        ensure_aware_utc(
            datetime(2024, 2, 15, 12, 0),  # noqa: DTZ001 - deliberately naive fixture
            "synthetic_timestamp",
        )


def test_normalizer_rejects_usable_time_before_platform_delivery() -> None:
    observation = datetime(2024, 2, 15, 12, 0, tzinfo=UTC)
    release = datetime(2024, 2, 15, 12, 1, tzinfo=UTC)
    delivery = datetime(2024, 2, 15, 12, 2, tzinfo=UTC)
    retrieved = datetime(2024, 2, 15, 12, 3, tzinfo=UTC)
    record = RawSourceRecord(
        dataset_id=_InvalidTimingPolicy.dataset_id,
        series_id="synthetic.series",
        market="ES",
        instrument_id="synthetic-contract",
        observation_time_utc=observation,
        source_release_time_utc=release,
        vendor_receive_time_utc=None,
        platform_delivery_time_utc=delivery,
        source_version="synthetic-v1",
        schema_version=_InvalidTimingPolicy.schema_version,
        payload={"value": 1.0},
    )
    normalizer = PointInTimeNormalizer({_InvalidTimingPolicy.dataset_id: _InvalidTimingPolicy()})

    with pytest.raises(DataTimingInvariantError):
        normalizer.normalize(record, retrieved)

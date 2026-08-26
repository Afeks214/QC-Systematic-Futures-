from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from systematic_futures.data.availability_gate import AvailabilityGate
from systematic_futures.domain.enums import DataQualityStatus
from systematic_futures.domain.errors import DuplicateIdentifierError
from systematic_futures.domain.identifiers import make_lineage_hash
from systematic_futures.domain.schemas import PointInTimeDatum

_OBSERVATION_TIME = datetime(2024, 2, 15, 12, 0, tzinfo=UTC)
_SOURCE_RELEASE_TIME = _OBSERVATION_TIME + timedelta(minutes=1)
_PLATFORM_DELIVERY_TIME = _OBSERVATION_TIME + timedelta(minutes=2)
_USABLE_FROM_TIME = _OBSERVATION_TIME + timedelta(minutes=3)
_RETRIEVED_TIME = _OBSERVATION_TIME + timedelta(minutes=4)


def _datum(series_id: str) -> PointInTimeDatum:
    value = {"synthetic_value": series_id}
    return PointInTimeDatum(
        dataset_id="synthetic.dataset",
        series_id=series_id,
        market="ES",
        instrument_id="synthetic-contract",
        observation_time_utc=_OBSERVATION_TIME,
        source_release_time_utc=_SOURCE_RELEASE_TIME,
        vendor_receive_time_utc=None,
        platform_delivery_time_utc=_PLATFORM_DELIVERY_TIME,
        usable_from_utc=_USABLE_FROM_TIME,
        revision_id=None,
        source_version="synthetic-v1",
        schema_version="1.0",
        retrieved_at_utc=_RETRIEVED_TIME,
        value=value,
        quality_status=DataQualityStatus.VALID,
        quality_flags=(),
        missing_reason=None,
        lineage_hash=make_lineage_hash(
            "synthetic.dataset",
            series_id,
            _OBSERVATION_TIME,
            "synthetic-v1",
            value,
        ),
    )


def test_gate_withholds_before_usable_from() -> None:
    gate = AvailabilityGate()
    gate.submit(_datum("series-a"))

    released = gate.release(_USABLE_FROM_TIME - timedelta(microseconds=1))

    assert released == ()
    assert gate.pending_count() == 1


def test_equal_usable_times_release_in_deterministic_order() -> None:
    gate = AvailabilityGate()
    gate.submit(_datum("series-z"))
    gate.submit(_datum("series-a"))

    released = gate.release(_USABLE_FROM_TIME)

    assert tuple(event.series_id for event in released) == ("series-a", "series-z")


def test_duplicate_lineage_hash_is_rejected() -> None:
    gate = AvailabilityGate()
    datum = _datum("series-a")
    gate.submit(datum)

    with pytest.raises(DuplicateIdentifierError):
        gate.submit(datum)

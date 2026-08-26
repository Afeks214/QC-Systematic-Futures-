from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from systematic_futures.data.availability_gate import AvailabilityGate
from systematic_futures.data.point_in_time import PointInTimeNormalizer
from systematic_futures.data.policies import (
    CftcReleaseScheduleEntry,
    UnderReviewCftcReleaseTimingPolicy,
)
from systematic_futures.domain.schemas import RawSourceRecord
from systematic_futures.domain.serialization import sha256_hex

_DATASET_ID = "synthetic_cftc_release_audit"
_SCHEMA_VERSION = "synthetic-test-v1"
_ORDINARY_OBSERVATION = datetime(2026, 1, 6, 0, 0, tzinfo=UTC)
_ORDINARY_RELEASE = datetime(2026, 1, 9, 20, 30, tzinfo=UTC)
_DELAYED_OBSERVATION = datetime(2026, 1, 13, 0, 0, tzinfo=UTC)
_DELAYED_RELEASE = datetime(2026, 1, 20, 20, 30, tzinfo=UTC)
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _policy() -> UnderReviewCftcReleaseTimingPolicy:
    return UnderReviewCftcReleaseTimingPolicy(
        dataset_id=_DATASET_ID,
        schema_version=_SCHEMA_VERSION,
        release_schedule_version="SYNTHETIC_TEST_SCHEDULE_NOT_CERTIFICATION",
        release_schedule=(
            CftcReleaseScheduleEntry(
                observation_date=date(2026, 1, 6),
                official_release_time_utc=_ORDINARY_RELEASE,
                holiday_delayed=False,
            ),
            CftcReleaseScheduleEntry(
                observation_date=date(2026, 1, 13),
                official_release_time_utc=_DELAYED_RELEASE,
                holiday_delayed=True,
            ),
        ),
    )


def _raw_record(observation: datetime, release: datetime) -> RawSourceRecord:
    return RawSourceRecord(
        dataset_id=_DATASET_ID,
        series_id=f"cftc-{observation.date().isoformat()}",
        market="ES",
        instrument_id="synthetic-cftc-symbol",
        observation_time_utc=observation,
        source_release_time_utc=release,
        vendor_receive_time_utc=release - timedelta(minutes=1),
        platform_delivery_time_utc=release - timedelta(minutes=2),
        source_version="synthetic-test-source-v1",
        schema_version=_SCHEMA_VERSION,
        payload={"synthetic_non_null_field": 1},
    )


def _normalize_and_submit(record: RawSourceRecord) -> AvailabilityGate:
    policy = _policy()
    normalizer = PointInTimeNormalizer({_DATASET_ID: policy})
    retrieved_at = record.platform_delivery_time_utc + timedelta(seconds=1)
    datum = normalizer.normalize(record, retrieved_at)
    gate = AvailabilityGate()
    gate.submit(datum)
    return gate


def test_cftc_ordinary_release_is_withheld_until_explicit_release_time() -> None:
    gate = _normalize_and_submit(_raw_record(_ORDINARY_OBSERVATION, _ORDINARY_RELEASE))

    assert gate.release(_ORDINARY_RELEASE - timedelta(microseconds=1)) == ()
    assert len(gate.release(_ORDINARY_RELEASE)) == 1


def test_cftc_holiday_delayed_release_is_not_released_on_ordinary_friday() -> None:
    gate = _normalize_and_submit(_raw_record(_DELAYED_OBSERVATION, _DELAYED_RELEASE))
    ordinary_friday = datetime(2026, 1, 16, 20, 30, tzinfo=UTC)

    assert gate.release(ordinary_friday) == ()
    assert gate.release(_DELAYED_RELEASE - timedelta(microseconds=1)) == ()
    assert len(gate.release(_DELAYED_RELEASE)) == 1


def test_official_2026_schedule_fixture_is_versioned_but_has_no_qc_delivery_claim() -> None:
    fixture = json.loads(
        (
            PROJECT_ROOT / "artifacts/certification/cftc_release_schedule_2026_reference.json"
        ).read_text(encoding="utf-8")
    )
    expected_hash = fixture.pop("normalized_fixture_sha256")

    assert sha256_hex(fixture) == expected_hash
    assert fixture["holiday_delayed_release_dates"] == [
        "2026-01-05",
        "2026-06-22",
        "2026-07-06",
    ]
    assert fixture["qc_delivery_audit_status"] == "NOT_EXECUTED"
    assert fixture["qc_delivery_observations"] == []

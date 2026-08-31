from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from systematic_futures.data.point_in_time import (
    PointInTimeEntryPath,
    RevisionStore,
)
from systematic_futures.data.policies import UnderReviewDatasetPolicy
from systematic_futures.domain.enums import RevisionMetadataPolicy
from systematic_futures.domain.errors import (
    DataQualityError,
    DataTimingInvariantError,
    DuplicateIdentifierError,
)
from systematic_futures.domain.schemas import RawSourceRecord

DATASET = "synthetic.revisable"
SCHEMA = "v2.synthetic.1"
OBSERVATION = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)


def _record(
    *,
    release: datetime,
    revision_id: str | None,
    value: float,
    market: str | None = None,
    instrument_id: str | None = None,
) -> RawSourceRecord:
    return RawSourceRecord(
        dataset_id=DATASET,
        series_id="series.one",
        market=market,
        instrument_id=instrument_id,
        observation_time_utc=OBSERVATION,
        source_release_time_utc=release,
        vendor_receive_time_utc=release,
        platform_delivery_time_utc=release,
        source_version="synthetic-source-v1",
        schema_version=SCHEMA,
        payload={"value": value},
        revision_id=revision_id,
    )


def _required_policy() -> UnderReviewDatasetPolicy:
    return UnderReviewDatasetPolicy(
        dataset_id=DATASET,
        schema_version=SCHEMA,
        revision_policy=RevisionMetadataPolicy.REQUIRED,
    )


def test_t001_entry_path_releases_exactly_at_usable_from() -> None:
    release = OBSERVATION + timedelta(days=1)
    path = PointInTimeEntryPath({DATASET: _required_policy()})
    datum = path.ingest(
        _record(release=release, revision_id="first", value=1.0),
        retrieved_at_utc=release,
    )

    assert path.release(release - timedelta(microseconds=1)) == ()
    released = path.release(release)
    assert len(released) == 1
    assert released[0].lineage_hash == datum.lineage_hash
    assert released[0].revision_id == "first"
    assert released[0].released_at_utc == release


def test_t002_future_revision_cannot_change_historical_as_known_result() -> None:
    first_release = OBSERVATION + timedelta(days=1)
    revised_release = OBSERVATION + timedelta(days=30)
    path = PointInTimeEntryPath({DATASET: _required_policy()})
    first = path.ingest(
        _record(release=first_release, revision_id="first", value=1.0),
        retrieved_at_utc=first_release,
    )
    revised = path.ingest(
        _record(release=revised_release, revision_id="revision-1", value=2.0),
        retrieved_at_utc=revised_release,
    )
    store = RevisionStore()
    store.store(first)
    before_future_insert = store.value_as_known_at(
        dataset_id=DATASET,
        series_id="series.one",
        observation_time_utc=OBSERVATION,
        decision_time_utc=first_release,
    )
    store.store(revised)
    after_future_insert = store.value_as_known_at(
        dataset_id=DATASET,
        series_id="series.one",
        observation_time_utc=OBSERVATION,
        decision_time_utc=first_release,
    )

    assert before_future_insert == after_future_insert == first
    assert (
        store.value_as_known_at(
            dataset_id=DATASET,
            series_id="series.one",
            observation_time_utc=OBSERVATION,
            decision_time_utc=revised_release,
        )
        == revised
    )
    with pytest.raises(DataTimingInvariantError, match="future revision"):
        store.revision_as_known_at(
            dataset_id=DATASET,
            series_id="series.one",
            observation_time_utc=OBSERVATION,
            revision_id="revision-1",
            decision_time_utc=first_release,
        )


def test_revision_store_is_append_only_and_preserves_lineage() -> None:
    release = OBSERVATION + timedelta(days=1)
    path = PointInTimeEntryPath({DATASET: _required_policy()})
    datum = path.ingest(
        _record(release=release, revision_id="first", value=1.0),
        retrieved_at_utc=release,
    )
    store = RevisionStore()
    store.store(datum)

    with pytest.raises(DuplicateIdentifierError):
        store.store(datum)
    assert (
        store.revision_as_known_at(
            dataset_id=DATASET,
            series_id="series.one",
            observation_time_utc=OBSERVATION,
            revision_id="first",
            decision_time_utc=release,
        ).lineage_hash
        == datum.lineage_hash
    )


def test_revision_store_rejects_ambiguous_simultaneous_revisions() -> None:
    release = OBSERVATION + timedelta(days=1)
    path = PointInTimeEntryPath({DATASET: _required_policy()})
    first = path.ingest(
        _record(release=release, revision_id="first", value=1.0),
        retrieved_at_utc=release,
    )
    simultaneous = path.ingest(
        _record(release=release, revision_id="simultaneous", value=2.0),
        retrieved_at_utc=release,
    )
    store = RevisionStore()
    store.store(first)

    with pytest.raises(DataTimingInvariantError, match="ambiguous"):
        store.store(simultaneous)
    assert (
        store.value_as_known_at(
            dataset_id=DATASET,
            series_id="series.one",
            observation_time_utc=OBSERVATION,
            decision_time_utc=release,
        )
        == first
    )


def test_lineage_and_revision_keys_isolate_market_and_instrument_identity() -> None:
    release = OBSERVATION + timedelta(days=1)
    path = PointInTimeEntryPath({DATASET: _required_policy()})
    es = path.ingest(
        _record(
            release=release,
            revision_id="first",
            value=1.0,
            market="ES",
            instrument_id="ESH24",
        ),
        retrieved_at_utc=release,
    )
    nq = path.ingest(
        _record(
            release=release,
            revision_id="first",
            value=1.0,
            market="NQ",
            instrument_id="NQH24",
        ),
        retrieved_at_utc=release,
    )
    assert es.lineage_hash != nq.lineage_hash

    store = RevisionStore()
    store.store(es)
    store.store(nq)
    assert (
        store.value_as_known_at(
            dataset_id=DATASET,
            series_id="series.one",
            market="ES",
            instrument_id="ESH24",
            observation_time_utc=OBSERVATION,
            decision_time_utc=release,
        )
        == es
    )
    assert (
        store.value_as_known_at(
            dataset_id=DATASET,
            series_id="series.one",
            market="NQ",
            instrument_id="NQH24",
            observation_time_utc=OBSERVATION,
            decision_time_utc=release,
        )
        == nq
    )


def test_missing_revision_metadata_follows_dataset_policy() -> None:
    release = OBSERVATION + timedelta(days=1)
    required_path = PointInTimeEntryPath({DATASET: _required_policy()})
    with pytest.raises(DataQualityError, match="revision_id"):
        required_path.ingest(
            _record(release=release, revision_id=None, value=1.0),
            retrieved_at_utc=release,
        )

    unverified = UnderReviewDatasetPolicy(
        dataset_id=DATASET,
        schema_version=SCHEMA,
        revision_policy=RevisionMetadataPolicy.UNVERIFIED,
    )
    datum = PointInTimeEntryPath({DATASET: unverified}).ingest(
        _record(release=release, revision_id=None, value=1.0),
        retrieved_at_utc=release,
    )
    assert "revision_metadata_unverified" in datum.quality_flags


def test_future_datum_injection_leaves_pre_frontier_release_unchanged() -> None:
    first_release = OBSERVATION + timedelta(days=1)
    future_release = OBSERVATION + timedelta(days=2)
    path = PointInTimeEntryPath({DATASET: _required_policy()})
    path.ingest(
        _record(release=first_release, revision_id="first", value=1.0),
        retrieved_at_utc=first_release,
    )
    first = path.release(first_release)
    path.ingest(
        _record(release=future_release, revision_id="revision-1", value=2.0),
        retrieved_at_utc=future_release,
    )

    assert path.release(first_release) == ()
    assert first[0].value == {"value": 1.0}


def test_impossible_observation_release_order_is_rejected() -> None:
    invalid_release = OBSERVATION - timedelta(seconds=1)
    path = PointInTimeEntryPath({DATASET: _required_policy()})

    with pytest.raises(DataTimingInvariantError, match="observation"):
        path.ingest(
            _record(release=invalid_release, revision_id="first", value=1.0),
            retrieved_at_utc=OBSERVATION,
        )


def test_revision_store_rejects_datum_without_revision_identity() -> None:
    release = OBSERVATION + timedelta(days=1)
    unverified = UnderReviewDatasetPolicy(
        dataset_id=DATASET,
        schema_version=SCHEMA,
        revision_policy=RevisionMetadataPolicy.UNVERIFIED,
    )
    datum = PointInTimeEntryPath({DATASET: unverified}).ingest(
        _record(release=release, revision_id=None, value=1.0),
        retrieved_at_utc=release,
    )

    with pytest.raises(DataQualityError, match="revision_id"):
        RevisionStore().store(replace(datum, revision_id=None))

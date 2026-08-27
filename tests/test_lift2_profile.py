from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import pytest

from systematic_futures.data.sessions import SessionEngine, reference_session_policies
from systematic_futures.domain.enums import ProfileKind, RollState
from systematic_futures.domain.errors import (
    ContractBoundaryError,
    DataTimingInvariantError,
    SessionBoundaryError,
)
from systematic_futures.measurement.profile import (
    DEFAULT_PROFILE_DEFINITION,
    VolumeProfileEngine,
    select_poc,
    select_value_area,
)
from systematic_futures.measurement.stream import MeasurementStream
from systematic_futures.measurement.types import TradeObservation


def _trade(
    timestamp: datetime,
    *,
    price: float = 100.0,
    quantity: float = 1.0,
    contract: str = "ESH24",
    session_id: str = "session-a",
) -> TradeObservation:
    return TradeObservation(
        root="ES",
        contract_symbol=contract,
        exchange_time_utc=timestamp,
        available_at_utc=timestamp,
        price=price,
        quantity=quantity,
        minimum_tick=0.25,
        session_id=session_id,
        roll_state=RollState.NORMAL,
    )


def test_profile_conserves_volume_and_freezes_poc_value_area_rules() -> None:
    engine = VolumeProfileEngine("ES", "ESH24", "session-a", 0.25)
    start = datetime(2024, 3, 4, 14, 30, tzinfo=UTC)
    trades = (
        _trade(start, price=100.0, quantity=40),
        _trade(start + timedelta(seconds=1), price=99.75, quantity=20),
        _trade(start + timedelta(seconds=2), price=100.25, quantity=30),
        _trade(start + timedelta(seconds=3), price=100.50, quantity=10),
    )
    for trade in trades:
        assert engine.ingest_trade(trade)
    snapshot = engine.snapshot(
        ProfileKind.DEVELOPING_SESSION, trades[-1].exchange_time_utc, trades[-1].available_at_utc
    )
    assert math.isclose(sum(volume for _, volume in snapshot.volume_by_tick), 100.0)
    assert snapshot.poc_tick == 400
    assert (snapshot.val_tick, snapshot.vah_tick) == (400, 401)
    selected = sum(
        volume
        for tick, volume in snapshot.volume_by_tick
        if snapshot.val_tick <= tick <= snapshot.vah_tick
    )
    assert selected >= DEFAULT_PROFILE_DEFINITION.value_area_fraction * snapshot.total_volume
    assert (
        selected - dict(snapshot.volume_by_tick)[snapshot.vah_tick] < 0.70 * snapshot.total_volume
    )

    tied = {100: 5.0, 104: 5.0}
    assert select_poc(tied) == 100
    val, vah = select_value_area({99: 20.0, 100: 40.0, 101: 30.0, 102: 10.0}, 100, 0.70)
    assert (val, vah) == (100, 101)
    assert tuple(range(val, vah + 1)) == (100, 101)


def test_profile_rejects_contract_session_contamination_and_backdated_snapshot() -> None:
    engine = VolumeProfileEngine("ES", "ESH24", "session-a", 0.25)
    timestamp = datetime(2024, 3, 4, 14, 30, tzinfo=UTC)
    assert engine.ingest_trade(_trade(timestamp))
    with pytest.raises(ContractBoundaryError):
        engine.ingest_trade(_trade(timestamp + timedelta(seconds=1), contract="ESM24"))
    with pytest.raises(SessionBoundaryError):
        engine.ingest_trade(_trade(timestamp + timedelta(seconds=1), session_id="session-b"))
    immutable = engine.snapshot(
        ProfileKind.DEVELOPING_SESSION,
        timestamp,
        timestamp,
    )
    assert engine.ingest_trade(_trade(timestamp + timedelta(seconds=1), price=100.25))
    assert immutable.total_volume == 1.0
    with pytest.raises(DataTimingInvariantError):
        engine.snapshot(ProfileKind.DEVELOPING_SESSION, timestamp, timestamp + timedelta(seconds=1))


def test_rolling_minutes_expire_without_raw_tick_reconstruction() -> None:
    engine = VolumeProfileEngine("ES", "ESH24", "session-a", 0.25)
    start = datetime(2024, 3, 4, 10, 0, 10, tzinfo=UTC)
    engine.ingest_trade(_trade(start, quantity=2))
    engine.finalize_minutes_through(datetime(2024, 3, 4, 10, 1, tzinfo=UTC))
    engine.finalize_minutes_through(datetime(2024, 3, 4, 12, 1, tzinfo=UTC))
    later = datetime(2024, 3, 4, 12, 1, 10, tzinfo=UTC)
    engine.ingest_trade(_trade(later, price=101.0, quantity=3))
    end = datetime(2024, 3, 4, 12, 2, tzinfo=UTC)
    engine.finalize_minutes_through(end)
    rolling = engine.snapshot(ProfileKind.ROLLING_120M, end, end)
    assert rolling.volume_by_tick == ((404, 3.0),)
    assert engine.minute_bucket_count <= 120


def test_stream_snapshot_excludes_boundary_later_tick_and_replays_deterministically() -> None:
    sessions = SessionEngine(reference_session_policies())
    start = datetime(2024, 3, 4, 14, 30, 10, tzinfo=UTC)

    def run() -> MeasurementStream:
        stream = MeasurementStream("ES", "ESH24", 0.25, sessions)
        for timestamp, price in (
            (start, 5000.0),
            (start + timedelta(minutes=4, seconds=40), 5000.25),
            (start + timedelta(minutes=5), 5000.50),
        ):
            session_id = sessions.session_id("ES", timestamp)
            stream.on_trade(
                TradeObservation(
                    root="ES",
                    contract_symbol="ESH24",
                    exchange_time_utc=timestamp,
                    available_at_utc=timestamp,
                    price=price,
                    quantity=1.0,
                    minimum_tick=0.25,
                    session_id=session_id,
                    roll_state=RollState.NORMAL,
                )
            )
        return stream

    first = run()
    second = run()
    developing = next(
        snapshot
        for snapshot in first.profile_snapshots
        if snapshot.profile_kind is ProfileKind.DEVELOPING_SESSION
    )
    assert developing.as_of_utc == datetime(2024, 3, 4, 14, 35, tzinfo=UTC)
    assert developing.total_volume == 2.0
    assert first.measurement_hash() == second.measurement_hash()

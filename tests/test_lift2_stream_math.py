from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from systematic_futures.data.sessions import SessionEngine, reference_session_policies
from systematic_futures.domain.enums import RollState
from systematic_futures.domain.errors import ContractBoundaryError
from systematic_futures.measurement.state_models import TradeObservation
from systematic_futures.measurement.stream import MeasurementStream, _TradeBarAggregator

SEED = 1729
PREFIX_CHECKPOINTS = (100, 250, 500, 1000, 1500)


def _trade(
    timestamp: datetime,
    price: float,
    quantity: float,
    *,
    session_id: str,
    contract: str = "ESH24",
    roll_state: RollState = RollState.NORMAL,
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
        roll_state=roll_state,
    )


@pytest.mark.parametrize("period", [5, 30])
@pytest.mark.analytic_math
@pytest.mark.differential_math
@pytest.mark.metamorphic_math
@pytest.mark.stress_math
def test_bar_aggregation_matches_independent_ohlcv_reference(period: int) -> None:
    sessions = SessionEngine(reference_session_policies())
    session_start = datetime(2024, 3, 4, 14, 30, tzinfo=UTC)
    _, session_end = sessions.session_bounds("ES", session_start)
    session_id = sessions.session_id("ES", session_start)
    aggregator = _TradeBarAggregator("ES", "ESH24", period)
    rng = np.random.default_rng(SEED + period)
    count = period * 3
    steps = rng.integers(-2, 3, size=count)
    prices = 5000.0 + 0.25 * np.cumsum(steps)
    quantities = rng.integers(1, 10, size=count).astype(float)
    for index, (price, quantity) in enumerate(zip(prices, quantities, strict=True)):
        timestamp = session_start + timedelta(seconds=20 * index)
        assert aggregator.ingest(
            _trade(timestamp, float(price), float(quantity), session_id=session_id),
            session_start,
            session_end,
        )
    close_time = session_start + timedelta(minutes=period)
    bar = aggregator.close_due(close_time, close_time)
    assert bar is not None
    assert bar.open == prices[0]
    assert bar.high == np.max(prices)
    assert bar.low == np.min(prices)
    assert bar.close == prices[-1]
    assert bar.volume == pytest.approx(float(np.sum(quantities)))
    with pytest.raises(ContractBoundaryError):
        aggregator.ingest(
            _trade(close_time, 5000.0, 1.0, session_id=session_id, contract="ESM24"),
            session_start,
            session_end,
        )


def _deterministic_stream() -> tuple[TradeObservation, ...]:
    sessions = SessionEngine(reference_session_policies())
    start = datetime(2024, 3, 4, 14, 30, 1, tzinfo=UTC)
    rng = np.random.default_rng(SEED)
    steps = rng.integers(-1, 2, size=2000)
    prices = 5000.0 + 0.25 * np.cumsum(steps)
    quantities = rng.integers(1, 6, size=2000)
    records = []
    for index, (price, quantity) in enumerate(zip(prices, quantities, strict=True)):
        timestamp = start + timedelta(seconds=index)
        records.append(
            _trade(
                timestamp,
                float(price),
                float(quantity),
                session_id=sessions.session_id("ES", timestamp),
            )
        )
    return tuple(records)


@pytest.mark.causality_math
def test_whole_engine_prefix_equivalence_at_frozen_checkpoints() -> None:
    records = _deterministic_stream()
    sessions = SessionEngine(reference_session_policies())
    full = MeasurementStream("ES", "ESH24", 0.25, sessions)
    full_hashes: dict[int, str] = {}
    for count, trade in enumerate(records, start=1):
        full.on_trade(trade)
        if count in PREFIX_CHECKPOINTS:
            full_hashes[count] = full.measurement_hash()

    truncated_hashes: dict[int, str] = {}
    for checkpoint in PREFIX_CHECKPOINTS:
        truncated = MeasurementStream(
            "ES",
            "ESH24",
            0.25,
            SessionEngine(reference_session_policies()),
        )
        for trade in records[:checkpoint]:
            truncated.on_trade(trade)
        truncated_hashes[checkpoint] = truncated.measurement_hash()
    assert truncated_hashes == full_hashes


def test_roll_transition_blocks_but_post_roll_recovers_without_cross_contract_state() -> None:
    def run_current_session(roll_state: RollState) -> MeasurementStream:
        sessions = SessionEngine(reference_session_policies())
        stream = MeasurementStream("ES", "ESH24", 0.25, sessions)
        prior_time = datetime(2024, 3, 4, 14, 30, 1, tzinfo=UTC)
        stream.on_trade(
            _trade(
                prior_time,
                5000.0,
                1.0,
                session_id=sessions.session_id("ES", prior_time),
            )
        )
        current_start = datetime(2024, 3, 5, 14, 30, 1, tzinfo=UTC)
        for index in range(26):
            timestamp = current_start + timedelta(minutes=5 * index)
            stream.on_trade(
                _trade(
                    timestamp,
                    5000.0 + 0.25 * (index % 3),
                    1.0,
                    session_id=sessions.session_id("ES", timestamp),
                    roll_state=roll_state,
                )
            )
        return stream

    transition = run_current_session(RollState.ROLL_TRANSITION)
    transition_snapshot = transition.auction_snapshots[-1]
    assert "ROLL:ROLL_TRANSITION" in transition_snapshot.quality_flags
    assert not transition_snapshot.measurement_ready

    post_roll = run_current_session(RollState.POST_ROLL)
    post_roll_snapshot = post_roll.auction_snapshots[-1]
    assert "ROLL:POST_ROLL" in post_roll_snapshot.quality_flags
    assert post_roll_snapshot.features.local_price_scale.warmup_complete
    assert post_roll_snapshot.references.prior_same_session_type_id is not None
    assert post_roll_snapshot.measurement_ready

    fresh_contract = MeasurementStream(
        "ES",
        "ESM24",
        0.25,
        SessionEngine(reference_session_policies()),
    )
    assert fresh_contract.completed_bars == []
    assert fresh_contract.profile_snapshots == []
    assert fresh_contract.imsi_snapshots == []
    assert fresh_contract.icm_snapshots == []
    assert fresh_contract.iae_snapshots == []

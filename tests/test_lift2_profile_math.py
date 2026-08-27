from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from systematic_futures.domain.enums import ProfileKind, RollState
from systematic_futures.domain.errors import (
    ContractBoundaryError,
    DataQualityError,
    DataTimingInvariantError,
    SessionBoundaryError,
)
from systematic_futures.measurement.models import (
    ATRMeasurement,
    AuctionTransitionMetrics,
    CompletedTradeBar,
    TradeObservation,
)
from systematic_futures.measurement.profile import (
    DEFAULT_PROFILE_DEFINITION,
    VolumeProfileEngine,
    auction_features,
    build_profile_snapshot,
    price_to_tick,
    select_poc,
    select_value_area,
)


def _profile(
    as_of: datetime,
    *,
    session_id: str,
    contract: str = "ESH24",
    current_tick: int = 100,
):  # type: ignore[no-untyped-def]
    return build_profile_snapshot(
        root="ES",
        contract_symbol=contract,
        session_id=session_id,
        profile_kind=(
            ProfileKind.DEVELOPING_SESSION if session_id == "current" else ProfileKind.FINAL_SESSION
        ),
        as_of_utc=as_of,
        available_at_utc=as_of,
        definition=DEFAULT_PROFILE_DEFINITION,
        tick_size=0.25,
        current_price_tick=current_tick,
        volume_by_tick={99: 10.0, 100: 80.0, 101: 10.0},
        expected_total_volume=100.0,
    )


def _bar(
    index: int,
    close_tick: int,
    *,
    as_of: datetime,
    session_id: str = "current",
    contract: str = "ESH24",
) -> CompletedTradeBar:
    end = as_of - timedelta(minutes=5 * (2 - index))
    close = close_tick * 0.25
    return CompletedTradeBar(
        root="ES",
        contract_symbol=contract,
        period_minutes=5,
        start_utc=end - timedelta(minutes=5),
        end_utc=end,
        available_at_utc=end,
        open=close,
        high=close + 0.25,
        low=close - 0.25,
        close=close,
        volume=10.0,
        session_id=session_id,
    )


@pytest.mark.analytic_math
@pytest.mark.stress_math
def test_price_lattice_uses_only_reconstruction_roundoff_tolerance() -> None:
    assert price_to_tick(100.0, 0.25) == 400
    assert price_to_tick(100.1, 0.1) == 1001
    assert price_to_tick(1_000_000.25, 0.25) == 4_000_001
    with pytest.raises(DataQualityError, match="reconstruct"):
        price_to_tick(100.125, 0.25)
    with pytest.raises(DataQualityError, match="reconstruct"):
        price_to_tick(1_000_000.125, 0.25)


@pytest.mark.analytic_math
@pytest.mark.stress_math
def test_poc_and_contiguous_value_area_cover_ties_sparse_bins_and_edges() -> None:
    assert select_poc({100: 5.0, 104: 5.0}) == 100
    assert select_poc({99: 1.0, 100: 5.0, 104: 5.0, 106: 10.0}) == 106
    assert select_value_area({99: 20.0, 100: 40.0, 101: 30.0, 102: 10.0}, 100, 0.70) == (
        100,
        101,
    )
    assert select_value_area({98: 10.0, 100: 80.0, 102: 10.0}, 100, 1.0) == (98, 102)
    assert select_value_area({100: 1.0}, 100, 0.70) == (100, 100)


@pytest.mark.analytic_math
@pytest.mark.causality_math
@pytest.mark.stress_math
def test_profile_identity_commits_asof_and_independent_volume_total() -> None:
    at = datetime(2024, 3, 4, 15, tzinfo=UTC)
    first = _profile(at, session_id="current")
    second = _profile(at + timedelta(minutes=5), session_id="current")
    assert first.snapshot_id != second.snapshot_id
    with pytest.raises(DataQualityError, match="admitted volume"):
        build_profile_snapshot(
            root="ES",
            contract_symbol="ESH24",
            session_id="current",
            profile_kind=ProfileKind.DEVELOPING_SESSION,
            as_of_utc=at,
            available_at_utc=at,
            definition=DEFAULT_PROFILE_DEFINITION,
            tick_size=0.25,
            current_price_tick=100,
            volume_by_tick={100: 2.0},
            expected_total_volume=3.0,
        )


@pytest.mark.differential_math
@pytest.mark.metamorphic_math
def test_online_profile_matches_slow_batch_histogram_for_every_admitted_trade() -> None:
    at = datetime(2024, 3, 4, 15, tzinfo=UTC)
    engine = VolumeProfileEngine("ES", "ESH24", "current", 0.25)
    batch: dict[int, float] = {}
    for index, (tick, quantity) in enumerate(((400, 2.0), (401, 3.0), (399, 5.0), (400, 7.0))):
        timestamp = at + timedelta(seconds=index)
        trade = TradeObservation(
            root="ES",
            contract_symbol="ESH24",
            exchange_time_utc=timestamp,
            available_at_utc=timestamp,
            price=tick * 0.25,
            quantity=quantity,
            minimum_tick=0.25,
            session_id="current",
            roll_state=RollState.NORMAL,
        )
        assert engine.ingest_trade(trade)
        batch[tick] = batch.get(tick, 0.0) + quantity
        snapshot = engine.snapshot(ProfileKind.DEVELOPING_SESSION, timestamp, timestamp)
        assert snapshot.volume_by_tick == tuple(sorted(batch.items()))
        assert snapshot.total_volume == pytest.approx(sum(batch.values()))


@pytest.mark.analytic_math
@pytest.mark.causality_math
@pytest.mark.stress_math
def test_auction_features_require_exact_bar_atr_and_transition_identity() -> None:
    at = datetime(2024, 3, 4, 15, tzinfo=UTC)
    current = _profile(at, session_id="current", current_tick=101)
    prior = _profile(at - timedelta(days=1), session_id="prior")
    bars = tuple(_bar(index, tick, as_of=at) for index, tick in enumerate((99, 100, 101)))
    atr = ATRMeasurement(
        root="ES",
        contract_symbol="ESH24",
        as_of_utc=at,
        available_at_utc=at,
        value=0.5,
        observation_count=24,
        warmup_complete=True,
        version="atr_5m_24_arithmetic_tr_v1",
    )
    transitions = AuctionTransitionMetrics(
        root="ES",
        contract_symbol="ESH24",
        session_id="current",
        as_of_utc=at,
        reentry_count=2,
        consecutive_outside_bars=3,
        version="auction_transition_metrics_v2",
    )
    features, _ = auction_features(current, prior, atr, bars, transitions)
    assert features.time_outside_value_ratio == pytest.approx(2.0 / 3.0)
    assert features.reentry_count == 2
    assert features.consecutive_minutes_outside == 15
    assert features.atr_5m_24 == 0.5

    with pytest.raises(SessionBoundaryError):
        auction_features(
            current,
            prior,
            atr,
            (*bars[:-1], _bar(2, 101, as_of=at, session_id="wrong")),
            transitions,
        )
    with pytest.raises(ContractBoundaryError):
        auction_features(
            current,
            prior,
            atr,
            (*bars[:-1], _bar(2, 101, as_of=at, contract="ESM24")),
            transitions,
        )
    future = replace(
        bars[-1],
        start_utc=at,
        end_utc=at + timedelta(minutes=5),
        available_at_utc=at + timedelta(minutes=5),
    )
    with pytest.raises(DataTimingInvariantError):
        auction_features(current, prior, atr, (*bars[:-1], future), transitions)

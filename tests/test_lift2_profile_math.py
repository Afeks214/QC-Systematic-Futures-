from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from systematic_futures.data.quality import (
    blocking_measurement_flags,
    measurement_quality_severity,
)
from systematic_futures.domain.enums import (
    AuctionLocationState,
    MeasurementQualitySeverity,
    ProfileKind,
    RollState,
)
from systematic_futures.domain.errors import (
    ContractBoundaryError,
    DataQualityError,
    DataTimingInvariantError,
    SessionBoundaryError,
)
from systematic_futures.measurement.events import AuctionTransitionEngine
from systematic_futures.measurement.profile import (
    DEFAULT_PROFILE_DEFINITION,
    VolumeProfileEngine,
    auction_features,
    build_profile_snapshot,
    price_to_tick,
    select_poc,
    select_value_area,
)
from systematic_futures.measurement.state_models import (
    ATRMeasurement,
    AuctionTransitionMetrics,
    CompletedTradeBar,
    TradeObservation,
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
            source_event_id=f"trade-{index}",
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
        version="atr_5m_24_arithmetic_tr_floor_1e-6_v2",
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
    assert features.bar_close_outside_value_ratio == pytest.approx(2.0 / 3.0)
    assert features.distance_to_current_poc_vol == pytest.approx(0.5)
    assert features.reentry_count == 2
    assert features.consecutive_minutes_outside == 15
    assert features.atr_5m_24 == 0.5
    assert features.local_price_scale.observation_count == 24

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


@pytest.mark.causality_math
@pytest.mark.stress_math
def test_trade_admission_uses_source_identity_and_quarantines_bad_ticks() -> None:
    at = datetime(2024, 3, 4, 15, tzinfo=UTC)
    engine = VolumeProfileEngine("ES", "ESH24", "current", 0.25)

    def trade(
        event_id: str | None,
        *,
        price: float = 100.0,
        quantity: float = 1.0,
        flags: tuple[str, ...] = (),
        sequence: int | None = None,
    ) -> TradeObservation:
        return TradeObservation(
            root="ES",
            contract_symbol="ESH24",
            exchange_time_utc=at,
            available_at_utc=at,
            price=price,
            quantity=quantity,
            minimum_tick=0.25,
            session_id="current",
            roll_state=RollState.NORMAL,
            source_event_id=event_id,
            source_sequence=sequence,
            source_quality_flags=flags,
        )

    assert engine.ingest_trade(trade("trade-a"))
    assert engine.ingest_trade(trade("trade-b"))
    assert not engine.ingest_trade(trade("trade-a"))
    assert engine.last_rejection_flags == ("DATA:DUPLICATE_SOURCE_ID_EXCLUDED",)
    assert not engine.ingest_trade(trade("suspicious", flags=("SOURCE_SUSPICIOUS",)))
    assert engine.last_rejection_flags == ("DATA:SOURCE_SUSPICIOUS_EXCLUDED",)
    assert not engine.ingest_trade(trade("off-grid", price=100.125))
    assert engine.last_rejection_flags == ("DATA:OFF_TICK_GRID_EXCLUDED",)
    assert not engine.ingest_trade(trade("bad-quantity", quantity=0.0))
    assert engine.last_rejection_flags == ("DATA:NON_POSITIVE_QUANTITY_EXCLUDED",)

    sequence_engine = VolumeProfileEngine("ES", "ESH24", "current", 0.25)
    assert sequence_engine.ingest_trade(trade(None, sequence=7))
    assert not sequence_engine.ingest_trade(trade(None, sequence=7))
    assert sequence_engine.last_rejection_flags == ("DATA:DUPLICATE_SOURCE_SEQUENCE_EXCLUDED",)

    unverifiable = VolumeProfileEngine("ES", "ESH24", "current", 0.25)
    assert unverifiable.ingest_trade(trade(None))
    assert unverifiable.ingest_trade(trade(None))
    snapshot = unverifiable.snapshot(ProfileKind.DEVELOPING_SESSION, at, at)
    assert snapshot.total_volume == 2
    assert "PROVENANCE:DEDUPLICATION_UNVERIFIABLE" in snapshot.quality_flags


def test_measurement_quality_severity_is_exact_and_dedup_provenance_is_nonblocking() -> None:
    assert (
        measurement_quality_severity("PROVENANCE:DEDUPLICATION_UNVERIFIABLE")
        is MeasurementQualitySeverity.INFORMATIONAL
    )
    assert measurement_quality_severity("DATA:LATE") is MeasurementQualitySeverity.BLOCKING
    assert measurement_quality_severity("DATA:OUT_OF_ORDER") is MeasurementQualitySeverity.BLOCKING
    assert blocking_measurement_flags(("PROVENANCE:DEDUPLICATION_UNVERIFIABLE",)) == ()


@pytest.mark.analytic_math
@pytest.mark.metamorphic_math
def test_current_poc_distance_is_dimensionally_invariant_across_tick_sizes() -> None:
    at = datetime(2024, 3, 4, 15, tzinfo=UTC)

    def features_for(
        root: str,
        contract: str,
        tick_size: float,
        base_tick: int,
        geometry_ticks: int,
        atr_value: float,
    ):  # type: ignore[no-untyped-def]
        prior = build_profile_snapshot(
            root=root,
            contract_symbol=contract,
            session_id="prior",
            profile_kind=ProfileKind.FINAL_SESSION,
            as_of_utc=at - timedelta(days=1),
            available_at_utc=at - timedelta(days=1),
            definition=DEFAULT_PROFILE_DEFINITION,
            tick_size=tick_size,
            current_price_tick=base_tick,
            volume_by_tick={
                base_tick - geometry_ticks: 20.0,
                base_tick: 60.0,
                base_tick + geometry_ticks: 20.0,
            },
            expected_total_volume=100.0,
        )
        current = build_profile_snapshot(
            root=root,
            contract_symbol=contract,
            session_id="current",
            profile_kind=ProfileKind.DEVELOPING_SESSION,
            as_of_utc=at,
            available_at_utc=at,
            definition=DEFAULT_PROFILE_DEFINITION,
            tick_size=tick_size,
            current_price_tick=base_tick + 2 * geometry_ticks,
            volume_by_tick={
                base_tick: 20.0,
                base_tick + geometry_ticks: 60.0,
                base_tick + 2 * geometry_ticks: 20.0,
            },
            expected_total_volume=100.0,
        )
        atr = ATRMeasurement(
            root=root,
            contract_symbol=contract,
            as_of_utc=at,
            available_at_utc=at,
            value=atr_value,
            observation_count=24,
            warmup_complete=True,
            version="atr_5m_24_arithmetic_tr_floor_1e-6_v2",
        )
        transitions = AuctionTransitionMetrics(
            root=root,
            contract_symbol=contract,
            session_id="current",
            as_of_utc=at,
            reentry_count=0,
            consecutive_outside_bars=0,
            version="auction_transition_metrics_v2",
        )
        bars = []
        for index, tick in enumerate(
            (base_tick, base_tick + geometry_ticks, base_tick + 2 * geometry_ticks)
        ):
            end = at - timedelta(minutes=10 - 5 * index)
            close = tick * tick_size
            bars.append(
                CompletedTradeBar(
                    root=root,
                    contract_symbol=contract,
                    period_minutes=5,
                    start_utc=end - timedelta(minutes=5),
                    end_utc=end,
                    available_at_utc=end,
                    open=close,
                    high=close + tick_size,
                    low=close - tick_size,
                    close=close,
                    volume=10.0,
                    session_id="current",
                )
            )
        transition = AuctionTransitionEngine(root, contract)
        transition.advance(
            session_id="current",
            location=AuctionLocationState.INSIDE_VALUE,
            developing_poc_tick=base_tick,
            prior_profile=prior,
            event_time_utc=at - timedelta(minutes=5),
            available_at_utc=at - timedelta(minutes=5),
        )
        triggers = transition.advance(
            session_id="current",
            location=AuctionLocationState.ABOVE_VALUE,
            developing_poc_tick=base_tick + geometry_ticks,
            prior_profile=prior,
            event_time_utc=at,
            available_at_utc=at,
        )
        features, _ = auction_features(current, prior, atr, bars, transitions)
        return features, tuple(trigger.event_type for trigger in triggers)

    es, es_transitions = features_for("ES", "ESH24", 0.25, 20_000, 4, 2.0)
    zn, zn_transitions = features_for("ZN", "ZNH24", 1.0 / 64.0, 7_040, 32, 1.0)
    assert es.distance_to_current_poc_ticks == 4
    assert zn.distance_to_current_poc_ticks == 32
    assert es.distance_to_current_poc_vol == pytest.approx(0.5)
    assert zn.distance_to_current_poc_vol == pytest.approx(0.5)
    for field_name in (
        "distance_to_prior_poc_vol",
        "distance_to_vah_vol",
        "distance_to_val_vol",
        "value_area_width_vol",
        "poc_migration_vol",
        "value_mid_migration_vol",
        "volume_above_poc_ratio",
        "volume_outside_value_ratio",
        "bar_close_outside_value_ratio",
        "profile_entropy",
        "profile_skew",
        "profile_kurtosis",
    ):
        assert getattr(es, field_name) == pytest.approx(getattr(zn, field_name))
    assert es_transitions == zn_transitions


@pytest.mark.analytic_math
@pytest.mark.metamorphic_math
def test_profile_volume_scale_tick_translation_and_mirror_metamorphics() -> None:
    at = datetime(2024, 3, 4, 15, tzinfo=UTC)
    histogram = {98: 10.0, 99: 20.0, 100: 40.0, 101: 20.0, 102: 10.0}

    def snapshot(values: dict[int, float]):  # type: ignore[no-untyped-def]
        return build_profile_snapshot(
            root="ES",
            contract_symbol="ESH24",
            session_id="current",
            profile_kind=ProfileKind.DEVELOPING_SESSION,
            as_of_utc=at,
            available_at_utc=at,
            definition=DEFAULT_PROFILE_DEFINITION,
            tick_size=0.25,
            current_price_tick=max(values),
            volume_by_tick=values,
            expected_total_volume=sum(values.values()),
        )

    base = snapshot(histogram)
    volume_scaled = snapshot({tick: 7.0 * volume for tick, volume in histogram.items()})
    translated = snapshot({tick + 13: volume for tick, volume in histogram.items()})
    assert (volume_scaled.poc_tick, volume_scaled.val_tick, volume_scaled.vah_tick) == (
        base.poc_tick,
        base.val_tick,
        base.vah_tick,
    )
    assert volume_scaled.total_volume == pytest.approx(7.0 * base.total_volume)
    assert (translated.poc_tick, translated.val_tick, translated.vah_tick) == (
        base.poc_tick + 13,
        base.val_tick + 13,
        base.vah_tick + 13,
    )

    def shape(profile):  # type: ignore[no-untyped-def]
        atr = ATRMeasurement(
            root="ES",
            contract_symbol="ESH24",
            as_of_utc=at,
            available_at_utc=at,
            value=1.0,
            observation_count=24,
            warmup_complete=True,
            version="atr_5m_24_arithmetic_tr_floor_1e-6_v2",
        )
        transitions = AuctionTransitionMetrics(
            root="ES",
            contract_symbol="ESH24",
            session_id="current",
            as_of_utc=at,
            reentry_count=0,
            consecutive_outside_bars=0,
            version="auction_transition_metrics_v2",
        )
        return auction_features(profile, None, atr, (), transitions)[0]

    base_shape = shape(base)
    scaled_shape = shape(volume_scaled)
    translated_shape = shape(translated)
    for field_name in (
        "volume_above_poc_ratio",
        "profile_entropy",
        "profile_skew",
        "profile_kurtosis",
    ):
        assert getattr(scaled_shape, field_name) == pytest.approx(getattr(base_shape, field_name))
        assert getattr(translated_shape, field_name) == pytest.approx(
            getattr(base_shape, field_name)
        )
    assert base_shape.profile_skew == pytest.approx(0.0, abs=1e-15)

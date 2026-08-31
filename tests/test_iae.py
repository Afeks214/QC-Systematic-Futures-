from __future__ import annotations

import math
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from systematic_futures.domain.enums import IAEGapDirection, IAEGapState, SessionType
from systematic_futures.domain.errors import DataQualityError, DataTimingInvariantError
from systematic_futures.measurement.iae import (
    IAEEngine,
    descriptive_reaction_score,
    detect_gap_geometry,
    formation_is_eligible,
    formation_quality,
)
from systematic_futures.measurement.state_models import ATRMeasurement, CompletedTradeBar
from systematic_futures.measurement.volatility import ATR5m24, true_range


def _bar(
    index: int,
    *,
    base: datetime,
    open_price: float,
    high: float,
    low: float,
    close: float,
    volume: float = 10.0,
    session_id: str = "session-a",
) -> CompletedTradeBar:
    start = base + timedelta(minutes=5 * index)
    return CompletedTradeBar(
        root="ES",
        contract_symbol="ESH24",
        period_minutes=5,
        start_utc=start,
        end_utc=start + timedelta(minutes=5),
        available_at_utc=start + timedelta(minutes=5),
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=volume,
        session_id=session_id,
    )


def _atr(bar: CompletedTradeBar, value: float = 1.0) -> ATRMeasurement:
    return ATRMeasurement(
        root=bar.root,
        contract_symbol=bar.contract_symbol,
        as_of_utc=bar.end_utc,
        available_at_utc=bar.available_at_utc,
        value=value,
        observation_count=24,
        warmup_complete=True,
        version="atr_5m_24_arithmetic_tr_floor_1e-6_v2",
    )


def _mirror(bar: CompletedTradeBar, center: float = 200.0) -> CompletedTradeBar:
    return CompletedTradeBar(
        root=bar.root,
        contract_symbol=bar.contract_symbol,
        period_minutes=bar.period_minutes,
        start_utc=bar.start_utc,
        end_utc=bar.end_utc,
        available_at_utc=bar.available_at_utc,
        open=center - bar.open,
        high=center - bar.low,
        low=center - bar.high,
        close=center - bar.close,
        volume=bar.volume,
        session_id=bar.session_id,
    )


@pytest.mark.analytic_math
@pytest.mark.metamorphic_math
@pytest.mark.stress_math
def test_shared_atr_true_range_analytic_warmup_scaling_and_stress() -> None:
    base = datetime(2024, 1, 1, tzinfo=UTC)
    first = _bar(
        0,
        base=base,
        open_price=100.0,
        high=101.0,
        low=99.0,
        close=100.0,
    )
    second = _bar(
        1,
        base=base,
        open_price=103.0,
        high=104.0,
        low=102.0,
        close=103.0,
    )
    assert true_range(second, first.close) == 4.0
    engine = ATR5m24("ES", "ESH24")
    state = engine.on_bar(first)
    assert state.observation_count == 0 and state.value is None
    for index in range(1, 25):
        bar = _bar(
            index,
            base=base,
            open_price=100.0,
            high=101.0,
            low=99.0,
            close=100.0,
        )
        state = engine.on_bar(bar)
    assert state.observation_count == 24
    assert state.value == pytest.approx(2.0)
    assert state.warmup_complete

    scaled_first = _mirror(first, center=300.0)
    scaled_second = _mirror(second, center=300.0)
    assert true_range(scaled_second, scaled_first.close) == pytest.approx(4.0)
    locked = ATR5m24("ES", "ESH24")
    locked.on_bar(first)
    for index in range(1, 25):
        locked_state = locked.on_bar(
            _bar(
                index,
                base=base,
                open_price=100.0,
                high=100.0,
                low=100.0,
                close=100.0,
            )
        )
    assert locked_state.observation_count == 24
    assert locked_state.warmup_complete
    assert locked_state.value == pytest.approx(1e-6)

    guarded = ATR5m24("ES", "ESH24")
    guarded.on_bar(replace(first, available_at_utc=first.available_at_utc + timedelta(days=3)))
    with pytest.raises(DataTimingInvariantError, match="frontier"):
        guarded.on_bar(second)


def test_iae_rejects_unsupported_atr_version_before_state_mutation() -> None:
    base = datetime(2024, 1, 1, 14, 30, tzinfo=UTC)
    bar = _bar(
        0,
        base=base,
        open_price=100.0,
        high=101.0,
        low=99.0,
        close=100.5,
    )
    engine = IAEEngine("ES", "ESH24", 0.25)

    with pytest.raises(DataQualityError, match="ATR version"):
        engine.on_bar(
            bar,
            replace(_atr(bar), version="unsupported-atr-semantics"),
            SessionType.RTH,
            base,
        )
    assert engine.active_gap_count == 0


@pytest.mark.analytic_math
@pytest.mark.differential_math
@pytest.mark.metamorphic_math
def test_formation_and_score_match_hand_calculation_and_decay_entire_bracket() -> None:
    assert formation_is_eligible(1.5000001, 0.3000001, 0.6000001)
    assert not formation_is_eligible(1.5, 0.4, 0.7)
    assert not formation_is_eligible(2.0, 0.3, 0.7)
    assert not formation_is_eligible(2.0, 0.4, 0.6)
    quality = formation_quality(2.0, 0.5, 0.8)
    assert quality == pytest.approx(2.0**0.4 * 0.5**0.4 * 0.8**0.2)
    expected_bracket = math.log1p(quality) + math.log1p(1.5) + math.log1p(2.0) + 0.5 * 0.75
    assert descriptive_reaction_score(quality, 1.5, 2.0, 0.75, 0) == pytest.approx(expected_bracket)
    assert descriptive_reaction_score(quality, 1.5, 2.0, 0.75, 14) == pytest.approx(
        expected_bracket * math.exp(-0.05 * 14)
    )
    assert descriptive_reaction_score(quality, 1.5, -3.0, 0.75, 0) == pytest.approx(
        math.log1p(quality) + math.log1p(1.5) - math.log1p(3.0) + 0.5 * 0.75
    )


@pytest.mark.analytic_math
@pytest.mark.metamorphic_math
def test_exact_three_bar_formation_predicate_and_directional_mirror() -> None:
    base = datetime(2024, 3, 4, 14, 30, tzinfo=UTC)
    first = _bar(
        0,
        base=base,
        open_price=99.5,
        high=100.0,
        low=99.0,
        close=99.75,
    )
    impulse = _bar(
        1,
        base=base,
        open_price=100.0,
        high=102.25,
        low=99.75,
        close=102.0,
    )
    current = _bar(
        2,
        base=base,
        open_price=101.0,
        high=103.0,
        low=100.5,
        close=102.0,
    )
    assert detect_gap_geometry(first, impulse, current, 0.25) == (
        IAEGapDirection.BULLISH,
        100.0,
        100.5,
    )
    mirrored = tuple(_mirror(bar) for bar in (first, impulse, current))
    assert detect_gap_geometry(*mirrored, 0.25) == (
        IAEGapDirection.BEARISH,
        99.5,
        100.0,
    )
    weak_impulse = _bar(
        1,
        base=base,
        open_price=99.5,
        high=100.25,
        low=99.25,
        close=100.0,
    )
    assert detect_gap_geometry(first, weak_impulse, current, 0.25) is None


def test_iae_snapshot_identity_commits_availability_time() -> None:
    base = datetime(2024, 3, 4, 14, 30, tzinfo=UTC)
    bars = (
        _bar(0, base=base, open_price=99.5, high=100.0, low=99.0, close=99.75),
        _bar(1, base=base, open_price=100.0, high=102.25, low=99.75, close=102.0),
        _bar(2, base=base, open_price=101.0, high=103.0, low=100.5, close=102.0),
    )
    baseline = IAEEngine("ES", "ESH24", 0.25)
    delayed = IAEEngine("ES", "ESH24", 0.25)
    baseline_snapshot = delayed_snapshot = None
    for index, bar in enumerate(bars):
        baseline_snapshot = baseline.on_bar(bar, _atr(bar), SessionType.RTH, base).bar_snapshot
        delayed_bar = (
            replace(bar, available_at_utc=bar.available_at_utc + timedelta(seconds=7))
            if index == 2
            else bar
        )
        delayed_snapshot = delayed.on_bar(
            delayed_bar,
            _atr(delayed_bar),
            SessionType.RTH,
            base,
        ).bar_snapshot
    assert baseline_snapshot is not None and delayed_snapshot is not None
    assert baseline_snapshot.as_of_utc == delayed_snapshot.as_of_utc
    assert baseline_snapshot.snapshot_id != delayed_snapshot.snapshot_id

    guarded = IAEEngine("ES", "ESH24", 0.25)
    future_available = replace(
        bars[0],
        available_at_utc=bars[0].available_at_utc + timedelta(days=3),
    )
    guarded.on_bar(
        future_available,
        _atr(future_available),
        SessionType.RTH,
        base,
    )
    with pytest.raises(DataTimingInvariantError, match="frontier"):
        guarded.on_bar(bars[1], _atr(bars[1]), SessionType.RTH, base)


@pytest.mark.causality_math
@pytest.mark.stress_math
def test_missing_five_minute_bar_resets_iae_formation_window() -> None:
    base = datetime(2024, 3, 4, 14, 30, tzinfo=UTC)
    engine = IAEEngine("ES", "ESH24", 0.25)
    first = _bar(
        0,
        base=base,
        open_price=99.5,
        high=100.0,
        low=99.0,
        close=99.75,
    )
    impulse = _bar(
        1,
        base=base,
        open_price=100.0,
        high=102.25,
        low=99.75,
        close=102.0,
    )
    after_gap = _bar(
        3,
        base=base,
        open_price=101.0,
        high=103.0,
        low=100.5,
        close=102.0,
    )
    engine.on_bar(first, _atr(first), SessionType.RTH, base)
    engine.on_bar(impulse, _atr(impulse), SessionType.RTH, base)
    update = engine.on_bar(after_gap, _atr(after_gap), SessionType.RTH, base)
    snapshot = update.bar_snapshot
    events = update.retests
    assert snapshot is not None
    assert snapshot.direction is None
    assert snapshot.active_gap_count == 0
    assert "IAE_BAR_GAP_RESET" in snapshot.quality_flags
    assert events == ()
    with pytest.raises(DataTimingInvariantError, match="three consecutive bars"):
        detect_gap_geometry(first, impulse, after_gap, 0.25)


@pytest.mark.causality_math
@pytest.mark.differential_math
@pytest.mark.metamorphic_math
@pytest.mark.stress_math
def test_full_iae_pipeline_is_price_reflection_symmetric_and_retests_once() -> None:
    bullish = IAEEngine("ES", "ESH24", 0.25)
    bearish = IAEEngine("ES", "ESH24", 0.25)

    for day in range(20):
        base = datetime(2024, 1, 1, 14, 30, tzinfo=UTC) + timedelta(days=day)
        session_id = f"history-{day:02d}"
        for index in range(4):
            bar = _bar(
                index,
                base=base,
                open_price=100.0,
                high=100.25,
                low=99.75,
                close=100.0,
                volume=10.0 + day + index,
                session_id=session_id,
            )
            bullish.on_bar(bar, _atr(bar), SessionType.RTH, base)
            mirror = _mirror(bar)
            bearish.on_bar(mirror, _atr(mirror), SessionType.RTH, base)

    base = datetime(2024, 2, 1, 14, 30, tzinfo=UTC)
    session_id = "formation"
    formation = (
        _bar(
            0,
            base=base,
            open_price=99.5,
            high=100.0,
            low=99.0,
            close=99.75,
            volume=30.0,
            session_id=session_id,
        ),
        _bar(
            1,
            base=base,
            open_price=100.0,
            high=102.25,
            low=99.75,
            close=102.0,
            volume=31.0,
            session_id=session_id,
        ),
        _bar(
            2,
            base=base,
            open_price=101.0,
            high=103.0,
            low=100.5,
            close=102.0,
            volume=32.0,
            session_id=session_id,
        ),
    )
    bull_snapshot = bear_snapshot = None
    for bar in formation:
        bull_update = bullish.on_bar(bar, _atr(bar), SessionType.RTH, base)
        bull_snapshot = bull_update.bar_snapshot
        bull_events = bull_update.retests
        mirrored = _mirror(bar)
        bear_update = bearish.on_bar(
            mirrored,
            _atr(mirrored),
            SessionType.RTH,
            base,
        )
        bear_snapshot = bear_update.bar_snapshot
        bear_events = bear_update.retests
        assert bull_events == bear_events == ()
    assert bull_snapshot is not None and bear_snapshot is not None
    assert bull_snapshot.direction is IAEGapDirection.BULLISH
    assert bear_snapshot.direction is IAEGapDirection.BEARISH
    assert bull_snapshot.measurement_ready and bear_snapshot.measurement_ready
    assert not bull_snapshot.score_ready and not bear_snapshot.score_ready
    assert bull_snapshot.formation_quality == pytest.approx(bear_snapshot.formation_quality)
    expected_quality = 2.0**0.4 * 0.5**0.4 * 0.8**0.2
    assert bull_snapshot.formation_quality == pytest.approx(expected_quality)

    retest = _bar(
        3,
        base=base,
        open_price=100.5,
        high=102.5,
        low=99.0,
        close=101.75,
        volume=1000.0,
        session_id=session_id,
    )
    bull_update = bullish.on_bar(
        retest,
        _atr(retest),
        SessionType.RTH,
        base,
    )
    bull_snapshot = bull_update.bar_snapshot
    bull_events = bull_update.retests
    mirrored_retest = _mirror(retest)
    bear_update = bearish.on_bar(
        mirrored_retest,
        _atr(mirrored_retest),
        SessionType.RTH,
        base,
    )
    bear_snapshot = bear_update.bar_snapshot
    bear_events = bear_update.retests
    assert bull_snapshot is not None and bear_snapshot is not None
    assert len(bull_events) == len(bear_events) == 1
    assert bull_snapshot.gap_state is IAEGapState.TESTED
    assert bear_snapshot.gap_state is IAEGapState.TESTED
    assert bull_snapshot.wick_rejection_ratio == pytest.approx(bear_snapshot.wick_rejection_ratio)
    assert bull_snapshot.close_position_raw == pytest.approx(bear_snapshot.close_position_raw)
    assert bull_snapshot.close_position_score == bear_snapshot.close_position_score == 1.0
    assert bull_snapshot.score_raw == pytest.approx(bear_snapshot.score_raw)
    assert bull_snapshot.score_effective == pytest.approx(bear_snapshot.score_effective)
    assert bull_snapshot.score_ready and bear_snapshot.score_ready
    prior_median = 22.5
    prior_mad = 5.0
    volume_z = (1000.0 - prior_median) / (1.4826 * prior_mad)
    wick = 1.5 / 3.5
    close_position_score = 1.0
    expected_score = (
        math.log1p(expected_quality)
        + math.log1p(wick)
        + math.log1p(volume_z)
        + 0.5 * close_position_score
    ) * math.exp(-0.05)
    assert bull_snapshot.score_raw == pytest.approx(expected_score)
    assert bull_snapshot.active_gap_count == bear_snapshot.active_gap_count == 1


@pytest.mark.analytic_math
@pytest.mark.causality_math
@pytest.mark.stress_math
def test_iae_close_invalidation_and_age_expiration_are_terminal() -> None:
    base = datetime(2024, 3, 4, 14, 30, tzinfo=UTC)

    def form(engine: IAEEngine) -> None:
        bars = (
            _bar(0, base=base, open_price=99.5, high=100.0, low=99.0, close=99.75),
            _bar(1, base=base, open_price=100.0, high=102.25, low=99.75, close=102.0),
            _bar(2, base=base, open_price=101.0, high=103.0, low=100.5, close=102.0),
        )
        for bar in bars:
            engine.on_bar(bar, _atr(bar), SessionType.RTH, base)

    invalidated = IAEEngine("ES", "ESH24", 0.25)
    form(invalidated)
    invalidating_bar = _bar(
        3,
        base=base,
        open_price=100.5,
        high=101.0,
        low=99.5,
        close=99.75,
    )
    invalidated_update = invalidated.on_bar(
        invalidating_bar,
        _atr(invalidating_bar),
        SessionType.RTH,
        base,
    )
    snapshot = invalidated_update.bar_snapshot
    assert snapshot is not None
    assert snapshot.gap_state is IAEGapState.INVALIDATED
    assert snapshot.active_gap_count == 0

    expired = IAEEngine("ES", "ESH24", 0.25)
    form(expired)
    for age in range(1, 50):
        bar = _bar(
            2 + age,
            base=base,
            open_price=102.0,
            high=102.25,
            low=101.75,
            close=102.0,
        )
        expired_update = expired.on_bar(bar, _atr(bar), SessionType.RTH, base)
        snapshot = expired_update.bar_snapshot
        assert snapshot is not None
    assert snapshot.gap_state is IAEGapState.EXPIRED
    assert snapshot.gap_age_bars == 49
    assert snapshot.active_gap_count == 0


@pytest.mark.causality_math
@pytest.mark.stress_math
def test_two_gaps_retested_on_one_bar_have_exact_distinct_snapshot_lineage() -> None:
    base = datetime(2024, 3, 4, 14, 30, tzinfo=UTC)
    engine = IAEEngine("ES", "ESH24", 0.25)
    formation = (
        _bar(0, base=base, open_price=99.5, high=100.0, low=99.0, close=99.75),
        _bar(1, base=base, open_price=100.0, high=102.5, low=99.75, close=102.0),
        _bar(2, base=base, open_price=101.0, high=103.5, low=100.5, close=103.0),
        _bar(3, base=base, open_price=103.0, high=105.0, low=103.0, close=104.5),
    )
    for bar in formation:
        engine.on_bar(bar, _atr(bar), SessionType.RTH, base)

    retest = _bar(
        4,
        base=base,
        open_price=102.0,
        high=104.0,
        low=99.5,
        close=103.25,
        volume=100.0,
    )
    update = engine.on_bar(retest, _atr(retest), SessionType.RTH, base)
    assert len(update.retests) == len(update.retest_snapshots) == 2
    assert len({item.gap_id for item in update.retests}) == 2
    assert len({item.iae_snapshot_id for item in update.retests}) == 2
    snapshots = {item.snapshot_id: item for item in update.retest_snapshots}
    assert {
        retest_observation.gap_id == snapshots[retest_observation.iae_snapshot_id].gap_id
        for retest_observation in update.retests
    } == {True}


@pytest.mark.causality_math
@pytest.mark.stress_math
def test_retest_and_same_bar_formation_have_collision_free_state_lineage() -> None:
    base = datetime(2024, 3, 4, 14, 30, tzinfo=UTC)
    engine = IAEEngine("ES", "ESH24", 0.25)
    bars = (
        _bar(0, base=base, open_price=99.5, high=100.0, low=99.0, close=99.75),
        _bar(1, base=base, open_price=100.0, high=102.5, low=99.75, close=102.0),
        _bar(2, base=base, open_price=101.0, high=103.0, low=101.0, close=102.5),
        _bar(3, base=base, open_price=104.0, high=106.0, low=104.0, close=105.0),
        _bar(4, base=base, open_price=105.0, high=105.0, low=101.5, close=102.0),
        _bar(5, base=base, open_price=100.5, high=100.75, low=99.5, close=100.5),
    )
    update = None
    for bar in bars:
        update = engine.on_bar(bar, _atr(bar), SessionType.RTH, base)

    assert update is not None and update.bar_snapshot is not None
    assert len(update.retest_snapshots) == 1
    retest_snapshot = update.retest_snapshots[0]
    assert retest_snapshot.gap_id == update.bar_snapshot.gap_id
    assert retest_snapshot.as_of_utc == update.bar_snapshot.as_of_utc
    assert retest_snapshot.active_gap_count == 1
    assert update.bar_snapshot.active_gap_count == 2
    assert retest_snapshot.snapshot_id != update.bar_snapshot.snapshot_id


@pytest.mark.analytic_math
@pytest.mark.stress_math
def test_doji_retest_uses_bounded_range_denominator_without_body_explosion() -> None:
    base = datetime(2024, 3, 4, 14, 30, tzinfo=UTC)
    engine = IAEEngine("ES", "ESH24", 0.25)
    formation = (
        _bar(0, base=base, open_price=99.5, high=100.0, low=99.0, close=99.75),
        _bar(1, base=base, open_price=100.0, high=102.25, low=99.75, close=102.0),
        _bar(2, base=base, open_price=101.0, high=103.0, low=100.5, close=102.0),
    )
    for bar in formation:
        engine.on_bar(bar, _atr(bar), SessionType.RTH, base)
    doji = _bar(
        3,
        base=base,
        open_price=100.25,
        high=101.0,
        low=99.75,
        close=100.25,
    )
    update = engine.on_bar(doji, _atr(doji), SessionType.RTH, base)
    assert len(update.retest_snapshots) == 1
    snapshot = update.retest_snapshots[0]
    assert snapshot.wick_rejection_ratio == pytest.approx(0.5 / 2.25)
    assert snapshot.rejection_length_raw == pytest.approx(0.5)
    assert snapshot.rejection_range_denominator == pytest.approx(2.25)
    assert snapshot.score_raw is None
    assert snapshot.score_effective is None
    assert snapshot.measurement_ready
    assert not snapshot.score_ready
    assert "IAE_SCORE_TOD_UNAVAILABLE" in snapshot.quality_flags

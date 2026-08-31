from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from systematic_futures.domain.enums import IAEGapState, SessionType
from systematic_futures.measurement.iae import (
    IAEEngine,
    bounded_rejection_ratio,
    descriptive_reaction_score,
    prior_volume_z,
)
from systematic_futures.measurement.state_models import ATRMeasurement, CompletedTradeBar

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _bar(
    index: int,
    *,
    base: datetime,
    open_price: float,
    high: float,
    low: float,
    close: float,
    volume: float,
    session_id: str,
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


def _atr(bar: CompletedTradeBar) -> ATRMeasurement:
    return ATRMeasurement(
        root=bar.root,
        contract_symbol=bar.contract_symbol,
        as_of_utc=bar.end_utc,
        available_at_utc=bar.available_at_utc,
        value=1.0,
        observation_count=24,
        warmup_complete=True,
        version="atr_5m_24_arithmetic_tr_floor_1e-6_v2",
    )


def test_tod_robust_median_mad_matches_hand_oracle_and_retains_negative_sign() -> None:
    prior = tuple(float(value) for value in range(1, 21))
    positive, positive_guard = prior_volume_z(25.0, prior)
    negative, negative_guard = prior_volume_z(1.0, prior)

    assert positive_guard is None and positive is not None
    assert negative_guard is None and negative is not None
    assert positive == pytest.approx((25.0 - 10.5) / (1.4826 * 5.0))
    assert negative == pytest.approx((1.0 - 10.5) / (1.4826 * 5.0))
    assert negative < 0


def test_tod_degenerate_mad_is_explicitly_not_ready() -> None:
    value, guard = prior_volume_z(11.0, (10.0,) * 20)
    assert value is None
    assert guard == "IAE_TOD_DEGENERATE_MAD"


def test_signed_descriptive_score_has_no_positive_volume_floor() -> None:
    negative = descriptive_reaction_score(1.0, 0.5, -2.0, 0.5, 1)
    zero = descriptive_reaction_score(1.0, 0.5, 0.0, 0.5, 1)
    positive = descriptive_reaction_score(1.0, 0.5, 2.0, 0.5, 1)
    assert negative < zero < positive


def test_rejection_ratio_is_true_range_normalized_bounded_and_tick_floored() -> None:
    base = datetime(2024, 3, 4, 14, 30, tzinfo=UTC)
    doji = _bar(
        0,
        base=base,
        open_price=100.0,
        high=100.5,
        low=99.5,
        close=100.0 + 1e-14,
        volume=10.0,
        session_id="doji",
    )
    raw, denominator, ratio = bounded_rejection_ratio(
        doji,
        side=1,
        previous_close=100.0,
        minimum_tick=0.25,
    )
    assert raw == pytest.approx(0.5)
    assert denominator == pytest.approx(1.0)
    assert ratio == pytest.approx(0.5)
    assert 0 <= ratio <= 1

    locked = _bar(
        1,
        base=base,
        open_price=100.0,
        high=100.0,
        low=100.0,
        close=100.0,
        volume=10.0,
        session_id="doji",
    )
    raw, denominator, ratio = bounded_rejection_ratio(
        locked,
        side=1,
        previous_close=100.0,
        minimum_tick=0.25,
    )
    assert raw == 0.0
    assert denominator == 0.25
    assert ratio == 0.0


def _prime_and_form(engine: IAEEngine, *, retest_volume: float):
    for day in range(20):
        base = datetime(2024, 1, 1, 14, 30, tzinfo=UTC) + timedelta(days=day)
        session = f"prior-{day:02d}"
        for index in range(4):
            bar = _bar(
                index,
                base=base,
                open_price=100.0,
                high=100.25,
                low=99.75,
                close=100.0,
                volume=10.0 + day + index,
                session_id=session,
            )
            engine.on_bar(bar, _atr(bar), SessionType.RTH, base)
    base = datetime(2024, 2, 1, 14, 30, tzinfo=UTC)
    formation = (
        _bar(
            0,
            base=base,
            open_price=99.5,
            high=100.0,
            low=99.0,
            close=99.75,
            volume=30.0,
            session_id="formation",
        ),
        _bar(
            1,
            base=base,
            open_price=100.0,
            high=102.25,
            low=99.75,
            close=102.0,
            volume=31.0,
            session_id="formation",
        ),
        _bar(
            2,
            base=base,
            open_price=101.0,
            high=103.0,
            low=100.5,
            close=102.0,
            volume=32.0,
            session_id="formation",
        ),
    )
    for bar in formation:
        engine.on_bar(bar, _atr(bar), SessionType.RTH, base)
    retest = _bar(
        3,
        base=base,
        open_price=100.5,
        high=102.5,
        low=99.0,
        close=101.75,
        volume=retest_volume,
        session_id="formation",
    )
    return engine.on_bar(retest, _atr(retest), SessionType.RTH, base)


def test_volume_surprise_changes_score_but_not_descriptive_structural_state() -> None:
    low = _prime_and_form(IAEEngine("ES", "ESH24", 0.25), retest_volume=1.0)
    high = _prime_and_form(IAEEngine("ES", "ESH24", 0.25), retest_volume=1000.0)
    assert low.retest_snapshots[0].gap_state is IAEGapState.TESTED
    assert high.retest_snapshots[0].gap_state is IAEGapState.TESTED
    assert low.retest_snapshots[0].score_effective != high.retest_snapshots[0].score_effective


def test_future_bars_do_not_repaint_prior_snapshot_and_current_session_is_excluded() -> None:
    engine = IAEEngine("ES", "ESH24", 0.25)
    update = _prime_and_form(engine, retest_volume=15.0)
    snapshot = update.retest_snapshots[0]
    expected, guard = prior_volume_z(15.0, tuple(float(13 + day) for day in range(20)))
    assert guard is None
    assert snapshot.tod_volume_z_raw == pytest.approx(expected)
    frozen_id = snapshot.snapshot_id
    future_base = datetime(2024, 2, 2, 14, 30, tzinfo=UTC)
    future = _bar(
        0,
        base=future_base,
        open_price=100.0,
        high=100.25,
        low=99.75,
        close=100.0,
        volume=9999.0,
        session_id="future",
    )
    engine.on_bar(future, _atr(future), SessionType.RTH, future_base)
    assert snapshot.snapshot_id == frozen_id
    assert snapshot.tod_volume_z_raw == pytest.approx(expected)


def test_active_iae_source_contains_no_legacy_threshold_or_positive_floor() -> None:
    source = (PROJECT_ROOT / "systematic_futures/measurement/iae.py").read_text(encoding="utf-8")
    assert "_SCORE_THRESHOLD" not in source
    assert "_VOLUME_Z_FLOOR" not in source
    assert "_MIN_WICK_ABSORPTION" not in source
    assert "max(volume_z" not in source

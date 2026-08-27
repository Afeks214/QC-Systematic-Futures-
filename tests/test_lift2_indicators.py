from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest

from systematic_futures.domain.enums import IAEGapDirection, IAEGapState, RollState, SessionType
from systematic_futures.domain.errors import ContractBoundaryError
from systematic_futures.measurement.iae import IAEEngine, detect_gap_geometry
from systematic_futures.measurement.icm import ICMEngine, fit_quadratic_geometry
from systematic_futures.measurement.imsi import IMSIEngine, stabilized_covariance
from systematic_futures.measurement.types import CompletedTradeBar, TradeObservation

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _bar(
    index: int,
    *,
    period: int = 30,
    open_price: float = 100.0,
    high: float = 101.0,
    low: float = 99.0,
    close: float = 100.0,
    volume: float = 10.0,
    contract: str = "ESH24",
    session_id: str = "session-a",
    base: datetime = datetime(2024, 1, 1, tzinfo=UTC),
) -> CompletedTradeBar:
    start = base + timedelta(minutes=index * period)
    end = start + timedelta(minutes=period)
    return CompletedTradeBar(
        root="ES",
        contract_symbol=contract,
        period_minutes=period,
        start_utc=start,
        end_utc=end,
        available_at_utc=end,
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=volume,
        session_id=session_id,
    )


def test_icm_exact_fit_translation_forward_only_and_contract_reset() -> None:
    tau = np.linspace(-1.0, 0.0, 70)
    exact = tuple(float(120.0 + 3.0 * value + 2.0 * value**2) for value in tau)
    beta0, beta1, beta2, sigma_ols, sigma_mad = fit_quadratic_geometry(exact)
    assert beta0 == pytest.approx(120.0, abs=1e-10)
    assert beta1 == pytest.approx(3.0, abs=1e-10)
    assert beta2 == pytest.approx(2.0, abs=1e-10)
    assert sigma_ols < 1e-10
    assert sigma_mad < 1e-10

    base_engine = ICMEngine("ES", "ESH24")
    shifted_engine = ICMEngine("ES", "ESH24")
    base_snapshot = None
    shifted_snapshot = None
    for index, value in enumerate(exact):
        noise = 0.01 * ((index % 3) - 1)
        price = value + noise
        base_snapshot = base_engine.on_bar(
            _bar(index, open_price=price, high=price + 0.25, low=price - 0.25, close=price)
        )
        shifted_snapshot = shifted_engine.on_bar(
            _bar(
                index,
                open_price=price + 10,
                high=price + 10.25,
                low=price + 9.75,
                close=price + 10,
            )
        )
    assert base_snapshot is not None and shifted_snapshot is not None
    assert isinstance(base_snapshot.fair_value, float)
    assert shifted_snapshot.fair_value - base_snapshot.fair_value == pytest.approx(10.0)
    assert shifted_snapshot.z_score == pytest.approx(base_snapshot.z_score, abs=1e-8)
    frozen_id = base_snapshot.snapshot_id
    base_engine.on_bar(_bar(70, open_price=130, high=131, low=129, close=130))
    assert base_snapshot.snapshot_id == frozen_id
    with pytest.raises(ContractBoundaryError):
        ICMEngine("ES", "ESM24").on_bar(_bar(0, contract="ESH24"))

    degenerate = ICMEngine("ES", "ESH24")
    for index in range(70):
        assert degenerate.on_bar(_bar(index)) is None
    assert degenerate.last_quality_flags == ("ICM_DEGENERATE_SCALE",)


def test_imsi_prior_only_tod_covariance_neighbors_rarity_and_vwap_reset() -> None:
    engine = IMSIEngine("ES", "ESH24")
    snapshots = []
    for day in range(85):
        session_id = f"session-{day:03d}"
        base = datetime(2024, 1, 1, 14, 30, tzinfo=UTC) + timedelta(days=day)
        close = 100.0 + math.sin(day / 3) + day * 0.01
        trade_price = close * (1.0 + 0.001 * math.cos(day / 5))
        trade_time = base + timedelta(minutes=29)
        engine.observe_trade(
            TradeObservation(
                root="ES",
                contract_symbol="ESH24",
                exchange_time_utc=trade_time,
                available_at_utc=trade_time,
                price=trade_price,
                quantity=10.0 + day % 5,
                minimum_tick=0.25,
                session_id=session_id,
                roll_state=RollState.NORMAL,
            )
        )
        bar = _bar(
            0,
            open_price=close,
            high=close + 0.5,
            low=close - 0.5,
            close=close,
            volume=100 + day,
            session_id=session_id,
            base=base,
        )
        snapshot = engine.on_bar(bar, SessionType.RTH, base)
        if snapshot is not None:
            snapshots.append(snapshot)
            assert snapshot.session_vwap == pytest.approx(trade_price)
    assert snapshots[8].vwrsi_tod_adjusted is None
    assert any(snapshot.vwrsi_tod_adjusted is not None for snapshot in snapshots[10:])
    final = snapshots[-1]
    assert final.mahalanobis_distance is not None and math.isfinite(final.mahalanobis_distance)
    assert final.neighbor_support == 15
    assert final.neighbor_distance_mean is not None
    assert final.neighbor_distance_p90 is not None
    assert final.state_rarity_percentile is not None
    assert final.warmup_complete
    frozen = snapshots[-2]
    assert frozen.snapshot_id == snapshots[-2].snapshot_id
    assert engine.prior_state_count <= 300

    collinear = np.asarray([[float(index), float(index * 2)] for index in range(40)])
    covariance, condition = stabilized_covariance(collinear)
    assert np.isfinite(covariance).all()
    assert math.isfinite(condition)
    assert np.linalg.eigvalsh(covariance).min() > 0


def test_iae_gap_symmetry_first_retest_and_close_only_invalidation() -> None:
    base = datetime(2024, 3, 4, 14, 30, tzinfo=UTC)
    bars = (
        _bar(0, period=5, open_price=99, high=100, low=98.5, close=99.5, base=base),
        _bar(1, period=5, open_price=100, high=102, low=99.5, close=101.5, base=base),
        _bar(2, period=5, open_price=101.5, high=103, low=101, close=102, base=base),
    )
    assert detect_gap_geometry(bars[0], bars[2], 0.25) == (
        IAEGapDirection.BULLISH,
        100,
        101,
    )
    mirrored_first = _bar(
        0,
        period=5,
        open_price=101,
        high=101.5,
        low=100,
        close=100.5,
        base=base,
    )
    mirrored_current = _bar(
        2,
        period=5,
        open_price=98.5,
        high=99,
        low=97,
        close=98,
        base=base,
    )
    assert detect_gap_geometry(mirrored_first, mirrored_current, 0.25) == (
        IAEGapDirection.BEARISH,
        99,
        100,
    )

    engine = IAEEngine("ES", "ESH24", 0.25)
    for bar in bars:
        snapshot, retests = engine.on_bar(bar, 1.0, SessionType.RTH, base)
        assert retests == ()
    assert snapshot.direction is IAEGapDirection.BULLISH
    assert snapshot.gap_width_atr == 1.0
    gap_id = snapshot.gap_id
    retest_bar = _bar(
        3,
        period=5,
        open_price=101.5,
        high=102,
        low=99.75,
        close=100.5,
        base=base,
    )
    snapshot, retests = engine.on_bar(retest_bar, 1.0, SessionType.RTH, base)
    assert len(retests) == 1 and retests[0].gap_id == gap_id
    assert snapshot.gap_state is IAEGapState.RETESTED
    assert snapshot.retest_depth_ratio == 1.0
    assert snapshot.close_position_ratio == 0.5
    repeated = _bar(
        4,
        period=5,
        open_price=101,
        high=101.5,
        low=99.5,
        close=100.25,
        base=base,
    )
    snapshot, retests = engine.on_bar(repeated, 1.0, SessionType.RTH, base)
    assert retests == ()
    assert snapshot.gap_state is IAEGapState.RETESTED
    invalidating = _bar(
        5,
        period=5,
        open_price=100.5,
        high=101,
        low=99.5,
        close=99.75,
        base=base,
    )
    snapshot, retests = engine.on_bar(invalidating, 1.0, SessionType.RTH, base)
    assert retests == ()
    assert snapshot.gap_state is IAEGapState.INVALIDATED


def test_indicator_sources_contain_no_prohibited_behavior() -> None:
    imsi = (PROJECT_ROOT / "systematic_futures/measurement/imsi.py").read_text(encoding="utf-8")
    icm = (PROJECT_ROOT / "systematic_futures/measurement/icm.py").read_text(encoding="utf-8")
    for token in ("forward_return", "label", "future_price", "profit"):
        assert token not in imsi
    for token in ("winsor", "clip(", "2.5", "4.5"):
        assert token not in icm

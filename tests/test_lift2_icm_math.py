from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from systematic_futures.domain.errors import ContractBoundaryError
from systematic_futures.measurement.icm import (
    ICMEngine,
    fit_quadratic_geometry,
    quadratic_design,
)
from systematic_futures.measurement.state_models import CompletedTradeBar, PriceScale

SEED = 1729


def _bar(index: int, close: float, *, contract: str = "ESH24") -> CompletedTradeBar:
    start = datetime(2024, 1, 1, tzinfo=UTC) + timedelta(minutes=30 * index)
    return CompletedTradeBar(
        root="ES",
        contract_symbol=contract,
        period_minutes=30,
        start_utc=start,
        end_utc=start + timedelta(minutes=30),
        available_at_utc=start + timedelta(minutes=30),
        open=close,
        high=close + 0.25,
        low=close - 0.25,
        close=close,
        volume=100.0,
        session_id="session-a",
    )


@pytest.mark.analytic_math
@pytest.mark.stress_math
def test_icm_exact_polynomial_time_coordinate_and_chain_rule_units() -> None:
    window = 70
    design = quadratic_design(window)
    assert design[0] == pytest.approx((1.0, -1.0, 1.0))
    assert design[-1] == pytest.approx((1.0, 0.0, 0.0))
    beta = np.asarray((120.0, 3.0, 2.0))
    prices = tuple(float(value) for value in design @ beta)
    beta0, beta1, beta2, sigma_ols, sigma_mad = fit_quadratic_geometry(prices)
    assert (beta0, beta1, beta2) == pytest.approx(beta, abs=1e-10)
    assert sigma_ols < 1e-10
    assert sigma_mad < 1e-10

    engine = ICMEngine("ES", "ESH24")
    snapshot = None
    for index, price in enumerate(prices):
        snapshot = engine.on_bar(_bar(index, price))
    assert snapshot is not None
    assert snapshot.fair_value == pytest.approx(120.0, abs=1e-10)
    assert snapshot.slope_per_bar == pytest.approx(3.0 / 69.0, abs=1e-12)
    assert snapshot.curvature_per_bar2 == pytest.approx(4.0 / 69.0**2, abs=1e-12)
    assert snapshot.z_effective is None
    assert "ICM_FLAT_SCALE_GUARD" in snapshot.quality_flags


@pytest.mark.differential_math
@pytest.mark.stress_math
def test_icm_pinv_matches_lstsq_seeded_differential_vectors() -> None:
    rng = np.random.default_rng(SEED)
    for window in (4, 10, 70, 140):
        design = quadratic_design(window)
        for _ in range(20):
            prices = 100.0 + rng.normal(0.0, 2.0, size=window)
            actual = fit_quadratic_geometry(tuple(float(value) for value in prices))
            reference_beta, *_ = np.linalg.lstsq(design, prices, rcond=None)
            residual = prices - design @ reference_beta
            reference_ols = np.sqrt(np.sum(residual**2) / (window - 3))
            reference_median = np.median(residual)
            reference_mad = 1.4826 * np.median(np.abs(residual - reference_median))
            assert actual[:3] == pytest.approx(reference_beta, abs=1e-10)
            assert actual[3] == pytest.approx(reference_ols, abs=1e-10)
            assert actual[4] == pytest.approx(reference_mad, abs=1e-10)


@pytest.mark.causality_math
@pytest.mark.metamorphic_math
def test_icm_translation_scaling_caps_guards_and_immutability() -> None:
    rng = np.random.default_rng(SEED)
    prices = 100.0 + np.linspace(0.0, 3.0, 70) + rng.normal(0.0, 0.05, 70)
    base = ICMEngine("ES", "ESH24")
    shifted = ICMEngine("ES", "ESH24")
    scaled = ICMEngine("ES", "ESH24")
    base_snapshot = shifted_snapshot = scaled_snapshot = None
    for index, price in enumerate(prices):
        base_snapshot = base.on_bar(_bar(index, float(price)))
        shifted_snapshot = shifted.on_bar(_bar(index, float(price + 10.0)))
        scaled_snapshot = scaled.on_bar(_bar(index, float(price * 2.0)))
    assert base_snapshot is not None
    assert shifted_snapshot is not None
    assert scaled_snapshot is not None
    assert shifted_snapshot.fair_value - base_snapshot.fair_value == pytest.approx(10.0)
    assert shifted_snapshot.z_raw == pytest.approx(base_snapshot.z_raw, abs=1e-8)
    assert scaled_snapshot.fair_value == pytest.approx(2.0 * base_snapshot.fair_value)
    assert scaled_snapshot.slope_per_bar == pytest.approx(2.0 * base_snapshot.slope_per_bar)
    assert scaled_snapshot.z_raw == pytest.approx(base_snapshot.z_raw, abs=1e-8)
    assert base_snapshot.z_capped is not None and -4.5 <= base_snapshot.z_capped <= 4.5
    frozen_id = base_snapshot.snapshot_id
    base.on_bar(_bar(70, 103.0))
    assert base_snapshot.snapshot_id == frozen_id
    with pytest.raises(ContractBoundaryError):
        ICMEngine("ES", "ESM24").on_bar(_bar(0, 100.0))


@pytest.mark.differential_math
@pytest.mark.causality_math
def test_icm_online_matches_batch_lstsq_at_every_warmed_observation() -> None:
    rng = np.random.default_rng(SEED)
    prices = 100.0 + np.cumsum(rng.normal(0.0, 0.2, 95))
    engine = ICMEngine("ES", "ESH24")
    design = quadratic_design(70)
    for index, price in enumerate(prices):
        snapshot = engine.on_bar(_bar(index, float(price)))
        if index < 69:
            assert snapshot is None
            continue
        window = prices[index - 69 : index + 1]
        beta, *_ = np.linalg.lstsq(design, window, rcond=None)
        residuals = window - design @ beta
        sigma_ols = float(np.sqrt(np.sum(residuals**2) / 67.0))
        median = float(np.median(residuals))
        sigma_mad = 1.4826 * float(np.median(np.abs(residuals - median)))
        sigma_blend = 0.5 * (sigma_ols + sigma_mad)
        assert snapshot is not None
        assert snapshot.fair_value == pytest.approx(beta[0], abs=1e-10)
        assert snapshot.slope_per_bar == pytest.approx(beta[1] / 69.0, abs=1e-10)
        assert snapshot.curvature_per_bar2 == pytest.approx(2.0 * beta[2] / 69.0**2, abs=1e-10)
        assert snapshot.sigma_ols == pytest.approx(sigma_ols, abs=1e-10)
        assert snapshot.sigma_mad == pytest.approx(sigma_mad, abs=1e-10)
        expected_z = (window[-1] - beta[0]) / (sigma_blend + 1e-12)
        assert snapshot.z_raw == pytest.approx(expected_z, abs=1e-9)


@pytest.mark.stress_math
def test_icm_regime_guard_preserves_raw_capped_and_effective_states() -> None:
    engine = ICMEngine("ES", "ESH24")
    snapshot = None
    prices = [100.0 + 0.01 * index for index in range(70)]
    prices[-1] += 5.0
    for index, price in enumerate(prices):
        snapshot = engine.on_bar(_bar(index, price))
    assert snapshot is not None
    assert snapshot.z_raw is not None
    assert snapshot.z_capped is not None
    if snapshot.r_ratio > 1.5:
        assert "ICM_REGIME_GUARD" in snapshot.quality_flags
        assert snapshot.z_effective is None
    else:
        assert snapshot.z_effective == snapshot.z_capped


@pytest.mark.analytic_math
@pytest.mark.causality_math
def test_icm_local_scale_distance_and_residual_autocorrelation_match_oracles() -> None:
    prices = 100.0 + np.linspace(0.0, 2.0, 70) + 0.08 * np.sin(np.arange(70) / 2.0)
    engine = ICMEngine("ES", "ESH24")
    scale = PriceScale(
        value=0.5,
        observation_count=24,
        warmup_complete=True,
        version="atr_5m_24_arithmetic_tr_floor_1e-6_v2",
    )
    snapshot = None
    for index, price in enumerate(prices):
        snapshot = engine.on_bar(_bar(index, float(price)), scale)
    assert snapshot is not None

    design = quadratic_design(70)
    beta, *_ = np.linalg.lstsq(design, prices, rcond=None)
    residuals = prices - design @ beta
    left = residuals[:-1] - np.mean(residuals[:-1])
    right = residuals[1:] - np.mean(residuals[1:])
    expected_autocorrelation = float(
        np.sum(left * right) / np.sqrt(np.sum(left**2) * np.sum(right**2))
    )
    assert snapshot.fair_value_distance_vol == pytest.approx(
        (prices[-1] - beta[0]) / 0.5,
        abs=1e-10,
    )
    assert snapshot.residual_autocorrelation == pytest.approx(
        expected_autocorrelation,
        abs=1e-10,
    )
    assert "ICM_LOCAL_SCALE_UNAVAILABLE" not in snapshot.quality_flags

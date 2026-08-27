from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest

from systematic_futures.domain.enums import SessionType
from systematic_futures.domain.errors import DataQualityError, DataTimingInvariantError
from systematic_futures.measurement.imsi import (
    IMSIStateCore,
    ewma_diagonal_shrinkage_spec_v1,
    mahalanobis_distance,
    neighbor_distance_summary,
    volume_weighted_rsi,
)
from systematic_futures.measurement.state_models import CompletedTradeBar

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SEED = 1729


def _bar(
    index: int,
    *,
    base: datetime,
    close: float,
    volume: float,
    session_id: str,
) -> CompletedTradeBar:
    start = base + timedelta(minutes=30 * index)
    return CompletedTradeBar(
        root="ES",
        contract_symbol="ESH24",
        period_minutes=30,
        start_utc=start,
        end_utc=start + timedelta(minutes=30),
        available_at_utc=start + timedelta(minutes=30),
        open=close,
        high=close + 0.25,
        low=close - 0.25,
        close=close,
        volume=volume,
        session_id=session_id,
    )


@pytest.mark.analytic_math
@pytest.mark.metamorphic_math
def test_vwrsi_zero_seed_recursion_and_scale_metamorphism() -> None:
    assert volume_weighted_rsi(0.0, 0.0) == 0.0
    up = 20.0 / 14.0
    down = 0.0
    expected = 100.0 - 100.0 / (1.0 + up / (down + 1e-12))
    assert volume_weighted_rsi(up, down) == pytest.approx(expected)
    mixed_up = (13.0 / 14.0) * up
    mixed_down = 14.0 / 14.0
    expected_mixed = 100.0 - 100.0 / (1.0 + mixed_up / (mixed_down + 1e-12))
    assert volume_weighted_rsi(mixed_up, mixed_down) == pytest.approx(expected_mixed)
    assert volume_weighted_rsi(7.0 * mixed_up, 7.0 * mixed_down) == pytest.approx(
        expected_mixed,
        abs=1e-10,
    )
    with pytest.raises(DataQualityError):
        volume_weighted_rsi(-1.0, 1.0)


@pytest.mark.analytic_math
@pytest.mark.metamorphic_math
def test_imsi_price_translation_and_positive_scaling_obey_declared_units() -> None:
    base = datetime(2024, 1, 1, 14, 30, tzinfo=UTC)
    original = IMSIStateCore("ES", "ESH24")
    translated = IMSIStateCore("ES", "ESH24")
    scaled = IMSIStateCore("ES", "ESH24")
    outputs = []
    for index, (price, volume) in enumerate(((100.0, 10.0), (101.0, 20.0), (99.5, 15.0))):
        original_snapshot = original.on_bar(
            _bar(index, base=base, close=price, volume=volume, session_id="session-a"),
            SessionType.RTH,
            base,
        )
        translated_snapshot = translated.on_bar(
            _bar(index, base=base, close=price + 50.0, volume=volume, session_id="session-a"),
            SessionType.RTH,
            base,
        )
        scaled_snapshot = scaled.on_bar(
            _bar(index, base=base, close=price * 3.0, volume=volume * 7.0, session_id="session-a"),
            SessionType.RTH,
            base,
        )
        outputs.append((original_snapshot, translated_snapshot, scaled_snapshot))

    for original_snapshot, translated_snapshot, scaled_snapshot in outputs[1:]:
        assert original_snapshot is not None
        assert translated_snapshot is not None
        assert scaled_snapshot is not None
        assert translated_snapshot.vwrsi_raw == pytest.approx(original_snapshot.vwrsi_raw)
        assert scaled_snapshot.vwrsi_raw == pytest.approx(original_snapshot.vwrsi_raw)
        assert translated_snapshot.session_vwap - original_snapshot.session_vwap == pytest.approx(
            50.0
        )
        assert scaled_snapshot.session_vwap == pytest.approx(3.0 * original_snapshot.session_vwap)
        assert scaled_snapshot.dist_vwap_pct == pytest.approx(original_snapshot.dist_vwap_pct)


@pytest.mark.analytic_math
@pytest.mark.causality_math
@pytest.mark.metamorphic_math
def test_bar_vwap_tod_covariance_neighbors_and_prefix_causality() -> None:
    engine = IMSIStateCore("ES", "ESH24")
    slot_one_snapshots = []
    all_ids: list[str] = []
    for day in range(115):
        session_id = f"session-{day:03d}"
        base = datetime(2024, 1, 1, 14, 30, tzinfo=UTC) + timedelta(days=day)
        first_close = 100.0 + 0.02 * day + math.sin(day / 5.0)
        second_close = first_close + 0.4 * math.cos(day / 3.0) + 0.1
        first_volume = 80.0 + day % 7
        second_volume = 110.0 + day % 11
        first = engine.on_bar(
            _bar(
                0,
                base=base,
                close=first_close,
                volume=first_volume,
                session_id=session_id,
            ),
            SessionType.RTH,
            base,
        )
        second = engine.on_bar(
            _bar(
                1,
                base=base,
                close=second_close,
                volume=second_volume,
                session_id=session_id,
            ),
            SessionType.RTH,
            base,
        )
        if first is not None:
            all_ids.append(first.snapshot_id)
        assert second is not None
        all_ids.append(second.snapshot_id)
        slot_one_snapshots.append(second)
        expected_vwap = (first_close * first_volume + second_close * second_volume) / (
            first_volume + second_volume
        )
        assert second.session_vwap == pytest.approx(expected_vwap)
        assert second.dist_vwap_pct == pytest.approx(
            100.0 * (second_close - expected_vwap) / expected_vwap
        )
        assert "IMSI_FULL_MODEL_DEFERRED_LIFT3" in second.quality_flags

    assert slot_one_snapshots[29].vwrsi_tod_adjusted is None
    assert slot_one_snapshots[30].vwrsi_tod_adjusted == pytest.approx(
        slot_one_snapshots[30].vwrsi_raw
        - float(np.median([item.vwrsi_raw for item in slot_one_snapshots[:30]]))
    )
    final = slot_one_snapshots[-1]
    assert final.mahalanobis_distance is not None
    assert final.state_rarity_percentile is not None
    assert final.neighbor_support == 15
    assert final.warmup_complete
    assert engine.prior_state_count <= 300
    frozen_prefix = tuple(all_ids)

    next_base = datetime(2024, 1, 1, 14, 30, tzinfo=UTC) + timedelta(days=116)
    engine.on_bar(
        _bar(0, base=next_base, close=104.0, volume=100.0, session_id="session-next"),
        SessionType.RTH,
        next_base,
    )
    assert tuple(all_ids) == frozen_prefix
    with pytest.raises(DataTimingInvariantError):
        engine.on_bar(
            _bar(0, base=next_base, close=104.0, volume=100.0, session_id="duplicate"),
            SessionType.RTH,
            next_base,
        )


@pytest.mark.differential_math
@pytest.mark.metamorphic_math
@pytest.mark.stress_math
def test_ewma_shrinkage_matches_independent_numpy_reference_and_stress() -> None:
    rng = np.random.default_rng(SEED)
    states = rng.normal(size=(200, 2)).astype(np.float64)
    states[:, 1] = 0.65 * states[:, 0] + 0.35 * states[:, 1]
    mean, inverse, delta, effective, condition = ewma_diagonal_shrinkage_spec_v1(states)

    powers = np.arange(len(states) - 1, -1, -1, dtype=np.float64)
    weights = 0.04 * np.power(0.96, powers)
    weights /= weights.sum()
    expected_mean = np.average(states, weights=weights, axis=0)
    centered = states - expected_mean
    raw = (centered * weights[:, None]).T @ centered
    rho = raw[0, 1] / math.sqrt(raw[0, 0] * raw[1, 1])
    expected_effective = 1.0 / np.sum(weights**2)
    expected_delta = float(
        np.clip((1.0 - rho**2) / (expected_effective * rho**2 + 1e-10), 0.05, 0.95)
    )
    target = np.diag(np.diag(raw))
    expected_covariance = (1.0 - expected_delta) * raw + expected_delta * target

    assert mean == pytest.approx(expected_mean, abs=1e-12)
    assert inverse == pytest.approx(np.linalg.inv(expected_covariance), abs=1e-10)
    assert delta == pytest.approx(expected_delta)
    assert effective == pytest.approx(expected_effective)
    assert condition >= 1.0

    shifted = states + np.asarray((13.0, -7.0))
    shifted_mean, shifted_inverse, *_ = ewma_diagonal_shrinkage_spec_v1(shifted)
    assert shifted_mean - mean == pytest.approx((13.0, -7.0), abs=1e-12)
    assert shifted_inverse == pytest.approx(inverse, abs=1e-10)

    collinear = np.asarray([[float(index), 2.0 * index] for index in range(40)])
    _, collinear_inverse, collinear_delta, _, collinear_condition = ewma_diagonal_shrinkage_spec_v1(
        collinear
    )
    assert collinear_delta == pytest.approx(0.05)
    assert np.linalg.eigvalsh(collinear_inverse).min() > 0
    assert collinear_condition == pytest.approx(39.0)
    with pytest.raises(DataQualityError, match="positive variance"):
        ewma_diagonal_shrinkage_spec_v1(np.asarray(((1.0, 2.0), (1.0, 3.0))))


@pytest.mark.differential_math
@pytest.mark.causality_math
def test_imsi_online_matches_slow_batch_reference_for_all_warmed_observations() -> None:
    engine = IMSIStateCore("ES", "ESH24")
    previous_close: float | None = None
    ema_up = 0.0
    ema_down = 0.0
    seasonal: dict[int, list[float]] = {0: [], 1: []}
    for day in range(45):
        base = datetime(2024, 1, 1, 14, 30, tzinfo=UTC) + timedelta(days=day)
        session_id = f"batch-{day:02d}"
        closes = (100.0 + math.sin(day / 4.0), 100.3 + math.cos(day / 6.0))
        volumes = (80.0 + day % 5, 120.0 + day % 9)
        cumulative_price_volume = 0.0
        cumulative_volume = 0.0
        for slot, (close, volume) in enumerate(zip(closes, volumes, strict=True)):
            cumulative_price_volume += close * volume
            cumulative_volume += volume
            snapshot = engine.on_bar(
                _bar(
                    slot,
                    base=base,
                    close=close,
                    volume=volume,
                    session_id=session_id,
                ),
                SessionType.RTH,
                base,
            )
            if previous_close is None:
                previous_close = close
                assert snapshot is None
                continue
            force = (close - previous_close) * volume
            previous_close = close
            ema_up = (1.0 / 14.0) * max(force, 0.0) + (13.0 / 14.0) * ema_up
            ema_down = (1.0 / 14.0) * max(-force, 0.0) + (13.0 / 14.0) * ema_down
            expected_raw = 100.0 - 100.0 / (1.0 + ema_up / (ema_down + 1e-12))
            expected_vwap = cumulative_price_volume / cumulative_volume
            prior_slot = seasonal[slot][-30:]
            expected_adjusted = (
                expected_raw - float(np.median(prior_slot)) if len(prior_slot) >= 30 else None
            )
            assert snapshot is not None
            assert snapshot.vwrsi_raw == pytest.approx(expected_raw)
            assert snapshot.session_vwap == pytest.approx(expected_vwap)
            assert snapshot.dist_vwap_pct == pytest.approx(
                100.0 * (close - expected_vwap) / expected_vwap
            )
            assert snapshot.vwrsi_tod_adjusted == pytest.approx(expected_adjusted)
            seasonal[slot].append(expected_raw)


@pytest.mark.analytic_math
@pytest.mark.stress_math
def test_mahalanobis_and_knn_exact_eligibility_boundary() -> None:
    current = np.asarray((0.0, 0.0), dtype=np.float64)
    mean = np.asarray((1.0, 2.0), dtype=np.float64)
    inverse = np.asarray(((2.0, 0.0), (0.0, 0.5)), dtype=np.float64)
    expected = math.sqrt((-1.0) ** 2 * 2.0 + (-2.0) ** 2 * 0.5)
    assert mahalanobis_distance(current, mean, inverse) == pytest.approx(expected)
    assert mahalanobis_distance(current, current, inverse) == 0.0
    with pytest.raises(DataQualityError, match="materially negative"):
        mahalanobis_distance(
            current + np.asarray((1.0, 0.0)),
            current,
            np.diag((-1.0, 1.0)),
        )

    prior = (
        (80, 10.0, 0.0),
        (92, 20.0, 0.0),
        (93, 0.0, 0.0),
        (94, 100.0, 0.0),
        (99, 100.0, 0.0),
    )
    neighbor_mean, p90, support = neighbor_distance_summary(
        prior,
        100,
        current,
        np.eye(2),
    )
    assert support == 3
    assert neighbor_mean == pytest.approx(10.0)
    assert p90 == pytest.approx(18.0)


@pytest.mark.stress_math
def test_imsi_scope_has_no_engine_alias_or_deferred_outputs() -> None:
    source = (PROJECT_ROOT / "systematic_futures/measurement/imsi.py").read_text(encoding="utf-8")
    assert "class IMSIEngine" not in source
    assert "stabilized_covariance" not in source
    for token in (
        "forward_return",
        "future_price",
        "profit",
        "imsi_raw_score",
        "predict_proba",
        "triple_barrier",
    ):
        assert token not in source

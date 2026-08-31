from dataclasses import fields, is_dataclass
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import numpy as np
import pytest

from systematic_futures.config.system import StructuralFeatureConfig
from systematic_futures.domain.enums import RollState
from systematic_futures.domain.errors import DataQualityError
from systematic_futures.domain.serialization import sha256_hex
from systematic_futures.measurement.structural import (
    ContinuousBarObservation,
    ContinuousSessionCloseBuilder,
    ContinuousSessionCloseObservation,
    ContractCurveObservation,
    QuoteObservation,
    StructuralStateEngine,
    StructuralStateSnapshot,
    TrendComponent,
    CarryComponent,
)
from systematic_futures.qc_adapters.data import (
    curve_observation_from_chain,
    latest_quote_from_ticks,
)


def _config() -> StructuralFeatureConfig:
    return StructuralFeatureConfig(
        trend_lookbacks_sessions=(2, 3),
        realized_volatility_window_sessions=3,
        volatility_percentile_window_sessions=4,
        volatility_percentile_minimum_history=2,
        carry_normalization_window_sessions=4,
        carry_minimum_history=3,
        annualization_sessions=252,
        feature_version="test_structural_v1",
    )


def _close(day: int, close: float, mapped: str = "ESH24") -> ContinuousSessionCloseObservation:
    end = datetime(2024, 1, day, 21, tzinfo=UTC)
    return ContinuousSessionCloseObservation(
        root="ES",
        continuous_symbol="ES-CONT",
        mapped_contract=mapped,
        session_id=f"ES-{day}",
        session_end_utc=end,
        available_at_utc=end,
        close=close,
        roll_state=RollState.NORMAL,
        source_lineage_hashes=(sha256_hex(("close", day, close)),),
        quality_flags=(),
    )


def _curve(
    day: int,
    mapped_price: float,
    next_price: float,
    mapped: str = "ESH24",
) -> ContractCurveObservation:
    timestamp = datetime(2024, 1, day, 20, tzinfo=UTC)
    return ContractCurveObservation(
        root="ES",
        continuous_symbol="ES-CONT",
        mapped_contract=mapped,
        next_contract="ESM24",
        mapped_expiry=date(2024, 3, 15),
        next_expiry=date(2024, 6, 21),
        mapped_price=mapped_price,
        next_price=next_price,
        mapped_open_interest=1000.0,
        next_open_interest=500.0,
        event_time_utc=timestamp,
        available_at_utc=timestamp,
        source_lineage_hash=sha256_hex(("curve", day, mapped_price, next_price)),
    )



def test_structural_contracts_are_frozen_slotted_dataclasses() -> None:
    for data_type in (
        ContinuousBarObservation,
        ContinuousSessionCloseObservation,
        ContractCurveObservation,
        QuoteObservation,
        TrendComponent,
        CarryComponent,
        StructuralStateSnapshot,
    ):
        assert is_dataclass(data_type)
        assert data_type.__dataclass_params__.frozen
        assert hasattr(data_type, "__slots__")
        assert tuple(field.name for field in fields(data_type))

def test_structural_config_rejects_unsorted_or_overstated_windows() -> None:
    with pytest.raises(DataQualityError, match="sorted and unique"):
        StructuralFeatureConfig(
            trend_lookbacks_sessions=(3, 2),
            realized_volatility_window_sessions=3,
            volatility_percentile_window_sessions=4,
            volatility_percentile_minimum_history=2,
            carry_normalization_window_sessions=4,
            carry_minimum_history=3,
            annualization_sessions=252,
            feature_version="x",
        )


def test_session_close_builder_emits_only_exact_completed_session() -> None:
    builder = ContinuousSessionCloseBuilder("ES", "ES-CONT")
    session_start = datetime(2024, 1, 2, 14, 30, tzinfo=UTC)
    session_end = session_start + timedelta(minutes=2)
    first = ContinuousBarObservation(
        root="ES",
        continuous_symbol="ES-CONT",
        mapped_contract="ESH24",
        session_id="s1",
        period_minutes=1,
        start_utc=session_start,
        end_utc=session_start + timedelta(minutes=1),
        available_at_utc=session_start + timedelta(minutes=1),
        session_start_utc=session_start,
        session_end_utc=session_end,
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.5,
        volume=10.0,
        roll_state=RollState.NORMAL,
        source_lineage_hash=sha256_hex("first"),
    )
    second = ContinuousBarObservation(
        root="ES",
        continuous_symbol="ES-CONT",
        mapped_contract="ESH24",
        session_id="s1",
        period_minutes=1,
        start_utc=session_start + timedelta(minutes=1),
        end_utc=session_end,
        available_at_utc=session_end,
        session_start_utc=session_start,
        session_end_utc=session_end,
        open=100.5,
        high=102.0,
        low=100.0,
        close=101.5,
        volume=11.0,
        roll_state=RollState.NORMAL,
        source_lineage_hash=sha256_hex("second"),
    )
    assert builder.update(first) is None
    assert builder.update(second) is None
    close = builder.finalize(session_end)
    assert close is not None
    assert close.close == 101.5
    assert close.source_lineage_hashes == (sha256_hex("first"), sha256_hex("second"))


def test_session_close_builder_withholds_incomplete_session() -> None:
    builder = ContinuousSessionCloseBuilder("ES", "ES-CONT")
    start = datetime(2024, 1, 2, 14, 30, tzinfo=UTC)
    bar = ContinuousBarObservation(
        root="ES",
        continuous_symbol="ES-CONT",
        mapped_contract="ESH24",
        session_id="s1",
        period_minutes=1,
        start_utc=start,
        end_utc=start + timedelta(minutes=1),
        available_at_utc=start + timedelta(minutes=1),
        session_start_utc=start,
        session_end_utc=start + timedelta(minutes=2),
        open=100.0,
        high=100.0,
        low=100.0,
        close=100.0,
        volume=0.0,
        roll_state=RollState.NORMAL,
        source_lineage_hash=sha256_hex("incomplete"),
    )
    builder.update(bar)
    assert builder.finalize(start + timedelta(minutes=2)) is None
    assert builder.incomplete_session_count == 1


def test_structural_trend_math_matches_direct_oracle() -> None:
    engine = StructuralStateEngine("ES", "ES-CONT", _config())
    closes = (100.0, 101.0, 99.0, 102.0)
    snapshots = [
        engine.update_session_close(_close(index + 1, value))
        for index, value in enumerate(closes)
    ]
    snapshot = snapshots[-1]
    returns = np.diff(np.log(np.asarray(closes, dtype=np.float64)))
    expected_vol = float(np.std(returns, ddof=1) * np.sqrt(252.0))
    expected_two = np.log(102.0 / 101.0) / (expected_vol * np.sqrt(2.0 / 252.0))
    expected_three = np.log(102.0 / 100.0) / (expected_vol * np.sqrt(3.0 / 252.0))
    assert snapshot.realized_volatility == pytest.approx(expected_vol)
    assert snapshot.trend_components[0].volatility_normalized_return == pytest.approx(expected_two)
    assert snapshot.trend_components[1].volatility_normalized_return == pytest.approx(
        expected_three
    )
    assert snapshot.trend_score == pytest.approx((expected_two + expected_three) / 2.0)
    assert snapshot.measurement_ready


def test_future_closes_do_not_repaint_prior_structural_snapshot() -> None:
    engine = StructuralStateEngine("ES", "ES-CONT", _config())
    for index, value in enumerate((100.0, 101.0, 99.0, 102.0), start=1):
        snapshot = engine.update_session_close(_close(index, value))
    frozen = snapshot
    engine.update_session_close(_close(5, 104.0))
    assert frozen == snapshot


def test_carry_normalization_is_prior_only_and_contract_bound() -> None:
    engine = StructuralStateEngine("ES", "ES-CONT", _config())
    for day, pair in enumerate(((100.0, 101.0), (100.0, 100.5), (100.0, 99.5)), start=1):
        engine.update_curve(_curve(day, *pair))
        engine.update_session_close(_close(day, 100.0 + day))
    current_curve = _curve(4, 100.0, 98.5)
    prior_raw = np.asarray(
        [
            _curve(1, 100.0, 101.0).annualized_curve_carry,
            _curve(2, 100.0, 100.5).annualized_curve_carry,
            _curve(3, 100.0, 99.5).annualized_curve_carry,
        ]
    )
    center = float(np.median(prior_raw))
    mad = float(np.median(np.abs(prior_raw - center)))
    expected = (current_curve.annualized_curve_carry - center) / (1.4826 * mad)
    engine.update_curve(current_curve)
    snapshot = engine.update_session_close(_close(4, 104.0))
    assert snapshot.carry is not None
    assert snapshot.carry.normalized_carry == pytest.approx(expected)
    assert snapshot.carry.open_interest_ratio == pytest.approx(2.0)


def test_curve_contract_mismatch_is_explicit_and_not_imputed() -> None:
    engine = StructuralStateEngine("ES", "ES-CONT", _config())
    engine.update_curve(_curve(1, 100.0, 101.0, mapped="ESH24"))
    snapshot = engine.update_session_close(_close(1, 101.0, mapped="ESM24"))
    assert snapshot.carry is None
    assert "CARRY_CONTRACT_MISMATCH" in snapshot.quality_flags


def test_qc_chain_adapter_uses_mapped_and_nearest_later_expiry() -> None:
    chain = SimpleNamespace(
        contracts={
            "old": SimpleNamespace(
                symbol="ESZ23",
                expiry=date(2023, 12, 15),
                last_price=99.0,
                open_interest=1,
            ),
            "mapped": SimpleNamespace(
                symbol="ESH24",
                expiry=date(2024, 3, 15),
                last_price=100.0,
                open_interest=1000,
            ),
            "next": SimpleNamespace(
                symbol="ESM24",
                expiry=date(2024, 6, 21),
                last_price=101.0,
                open_interest=500,
            ),
            "far": SimpleNamespace(
                symbol="ESU24",
                expiry=date(2024, 9, 20),
                last_price=102.0,
                open_interest=100,
            ),
        }
    )
    observed = datetime(2024, 1, 2, 15, tzinfo=UTC)
    curve = curve_observation_from_chain(
        root="ES",
        continuous_symbol="ES-CONT",
        mapped_contract="ESH24",
        future_chain=chain,
        observed_at_utc=observed,
    )
    assert curve is not None
    assert curve.mapped_contract == "ESH24"
    assert curve.next_contract == "ESM24"
    assert curve.mapped_open_interest == 1000.0


def test_qc_quote_adapter_preserves_latest_two_sided_quote() -> None:
    observed = datetime(2024, 1, 2, 15, 0, 1, tzinfo=UTC)
    ticks = [
        SimpleNamespace(
            tick_type="quote",
            end_time=datetime(2024, 1, 2, 15, tzinfo=UTC),
            bid_price=100.0,
            ask_price=100.25,
            bid_size=10,
            ask_size=5,
        ),
        SimpleNamespace(
            tick_type="quote",
            end_time=datetime(2024, 1, 2, 15, 0, 0, 500000, tzinfo=UTC),
            bid_price=100.25,
            ask_price=100.5,
            bid_size=4,
            ask_size=12,
        ),
    ]
    quote = latest_quote_from_ticks(
        root="ES",
        actual_contract="ESH24",
        ticks=ticks,
        quote_tick_type="quote",
        observed_at_utc=observed,
        minimum_tick=0.25,
    )
    assert quote is not None
    assert quote.bid_price == 100.25
    assert quote.ask_price == 100.5
    assert quote.spread_ticks == pytest.approx(1.0)
    assert quote.top_depth_imbalance == pytest.approx(-0.5)

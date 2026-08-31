from datetime import UTC, datetime, timedelta

import pytest

from systematic_futures.config.system import StructuralFeatureConfig
from systematic_futures.data.rolls import make_mapping_observation
from systematic_futures.data.sessions import SessionEngine, reference_session_policies
from systematic_futures.domain.enums import RollState
from systematic_futures.domain.errors import ContractBoundaryError
from systematic_futures.domain.serialization import sha256_hex
from systematic_futures.measurement.market_pipeline import (
    ActualContractActivation,
    MarketInputBatch,
    MarketPipeline,
)
from systematic_futures.measurement.structural_inputs import ContinuousBarObservation


def _config() -> StructuralFeatureConfig:
    return StructuralFeatureConfig(
        trend_lookbacks_sessions=(1,),
        realized_volatility_window_sessions=1,
        volatility_percentile_window_sessions=2,
        volatility_percentile_minimum_history=1,
        carry_normalization_window_sessions=2,
        carry_minimum_history=1,
        annualization_sessions=252,
        feature_version="pipeline_test_v1",
    )


def _activation(
    root: str,
    continuous: str,
    actual: str,
    timestamp: datetime,
    old: str | None = None,
) -> ActualContractActivation:
    mapping = make_mapping_observation(
        root=root,
        continuous_symbol=continuous,
        old_mapped_contract=old,
        new_mapped_contract=actual,
        actual_contract=actual,
        event_time_utc=timestamp,
        available_time_utc=timestamp,
        mapping_mode="OPEN_INTEREST",
        source="test",
        roll_state=RollState.NORMAL if old is None else RollState.ROLL_TRANSITION,
    )
    return ActualContractActivation(mapping, 0.25)


def _closing_bar(
    *,
    root: str,
    continuous: str,
    actual: str,
    timestamp: datetime,
    sessions: SessionEngine,
    price: float,
) -> ContinuousBarObservation:
    _, session_end = sessions.session_bounds(root, timestamp)
    session_start, _ = sessions.session_bounds(root, timestamp)
    return ContinuousBarObservation(
        root=root,
        continuous_symbol=continuous,
        mapped_contract=actual,
        session_id=sessions.session_id(root, timestamp),
        period_minutes=1,
        start_utc=session_end - timedelta(minutes=1),
        end_utc=session_end,
        available_at_utc=session_end,
        session_start_utc=session_start,
        session_end_utc=session_end,
        open=price,
        high=price + 0.25,
        low=price - 0.25,
        close=price,
        volume=10.0,
        roll_state=RollState.NORMAL,
        source_lineage_hash=sha256_hex((root, timestamp, price)),
    )


def _batch(
    *,
    root: str,
    timestamp: datetime,
    activation: ActualContractActivation | None = None,
    bar: ContinuousBarObservation | None = None,
) -> MarketInputBatch:
    return MarketInputBatch(
        root=root,
        observed_at_utc=timestamp,
        activation=activation,
        continuous_bar=bar,
        curve_observation=None,
        quote_observation=None,
        trades=(),
        quality_flags=(),
        lineage_hash=sha256_hex((root, timestamp, activation, bar)),
    )


def test_market_pipelines_are_root_isolated_and_publish_only_completed_sessions() -> None:
    sessions = SessionEngine(reference_session_policies())
    es = MarketPipeline(
        root="ES",
        continuous_symbol="ES-CONT",
        session_engine=sessions,
        structural_config=_config(),
    )
    zn = MarketPipeline(
        root="ZN",
        continuous_symbol="ZN-CONT",
        session_engine=sessions,
        structural_config=_config(),
    )
    es_time = datetime(2024, 3, 4, 15, tzinfo=UTC)
    zn_time = datetime(2024, 3, 4, 15, tzinfo=UTC)
    es_bar = _closing_bar(
        root="ES",
        continuous="ES-CONT",
        actual="ESH24",
        timestamp=es_time,
        sessions=sessions,
        price=5000.0,
    )
    zn_bar = _closing_bar(
        root="ZN",
        continuous="ZN-CONT",
        actual="ZNH24",
        timestamp=zn_time,
        sessions=sessions,
        price=110.0,
    )
    es_update = es.on_batch(
        _batch(
            root="ES",
            timestamp=es_bar.end_utc,
            activation=_activation("ES", "ES-CONT", "ESH24", es_bar.end_utc),
            bar=es_bar,
        )
    )
    zn_update = zn.on_batch(
        _batch(
            root="ZN",
            timestamp=zn_bar.end_utc,
            activation=_activation("ZN", "ZN-CONT", "ZNH24", zn_bar.end_utc),
            bar=zn_bar,
        )
    )
    assert es_update.structural_snapshot is not None
    assert zn_update.structural_snapshot is not None
    assert es_update.structural_snapshot.root == "ES"
    assert zn_update.structural_snapshot.root == "ZN"
    assert es.latest_structural != zn.latest_structural


def test_market_pipeline_rejects_cross_root_batch() -> None:
    sessions = SessionEngine(reference_session_policies())
    pipeline = MarketPipeline(
        root="ES",
        continuous_symbol="ES-CONT",
        session_engine=sessions,
        structural_config=_config(),
    )
    timestamp = datetime(2024, 3, 4, 15, tzinfo=UTC)
    with pytest.raises(ContractBoundaryError, match="batch root"):
        pipeline.on_batch(_batch(root="ZN", timestamp=timestamp))


def test_market_pipeline_archives_rolls_without_retaining_completed_stream_objects() -> None:
    sessions = SessionEngine(reference_session_policies())
    pipeline = MarketPipeline(
        root="ES",
        continuous_symbol="ES-CONT",
        session_engine=sessions,
        structural_config=_config(),
    )
    first = datetime(2024, 3, 4, 15, tzinfo=UTC)
    pipeline.on_batch(
        _batch(
            root="ES",
            timestamp=first,
            activation=_activation("ES", "ES-CONT", "ESH24", first),
        )
    )
    second = first + timedelta(days=1)
    pipeline.on_batch(
        _batch(
            root="ES",
            timestamp=second,
            activation=_activation("ES", "ES-CONT", "ESM24", second, old="ESH24"),
        )
    )
    summary = pipeline.summary()
    assert summary["contract_count"] == 2
    assert summary["roll_count"] == 1
    assert summary["bounded_state"]["completed_stream_objects"] == 0
    assert summary["bounded_state"]["active_stream_objects"] == 1

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from systematic_futures.config.dataset_uses import (
    CONTINUOUS_BACKWARDS_RATIO_ID,
    dataset_use_policies,
    get_dataset_use_policy,
)
from systematic_futures.config.feature_semantics import feature_semantics_v1
from systematic_futures.domain.enums import DatasetCertificationStatus
from systematic_futures.domain.errors import DataQualityError, DataTimingInvariantError
from systematic_futures.domain.research_contracts import (
    CostScenario,
    ExpectedCostComponents,
    FeatureImplementationStatus,
    ForecastPacket,
    SafetyBlockingReason,
    lift1_cost_scenario_contracts,
    lift1_hard_safety_policy,
    validate_cost_scenario_contract,
    validate_forecast_packet,
)
from systematic_futures.domain.serialization import canonicalize_for_json

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _synthetic_forecast_contract() -> ForecastPacket:
    generated = datetime(2024, 2, 15, 12, 0, tzinfo=UTC)
    return ForecastPacket(
        forecast_id="synthetic-schema-validation-only",
        hypothesis_name="Synthetic Contract Validation Only",
        hypothesis_version="not-implemented",
        model_name="not-implemented",
        model_version="not-implemented",
        market="ES",
        contract_symbol="synthetic-contract",
        generated_at_utc=generated,
        horizon_minutes=60,
        expires_at_utc=generated + timedelta(minutes=60),
        expected_gross_return=0.0,
        expected_cost_return=0.0,
        expected_net_return=0.0,
        expected_volatility=0.0,
        probability_positive_net=None,
        downside_quantile_05=0.0,
        median_return=0.0,
        upside_quantile_95=0.0,
        prediction_uncertainty=0.0,
        expected_mae=None,
        expected_mfe=None,
        expected_holding_minutes=None,
        capacity_contracts=0,
        expected_turnover=0.0,
        structural_state_id="not-implemented",
        market_state_id="not-implemented",
        auction_state_id="not-implemented",
        event_id=None,
        invalidation_rule_id="not-implemented",
        data_snapshot_id="synthetic-schema-validation-only",
        feature_set_version="not-implemented",
        cost_model_version="not-implemented",
        status="not-generated",
        missing_optional_features=(),
        quality_flags=("synthetic_schema_fixture",),
    )


def test_forecast_packet_is_schema_only_and_enforces_timing() -> None:
    packet = _synthetic_forecast_contract()
    validate_forecast_packet(packet)

    with pytest.raises(DataTimingInvariantError):
        validate_forecast_packet(replace(packet, expires_at_utc=packet.generated_at_utc))


def test_feature_semantics_are_frozen_and_unimplemented() -> None:
    features = feature_semantics_v1()
    names = {feature.feature_name for feature in features}

    assert {
        "acceptance_score",
        "distance_to_vah_vol",
        "distance_to_val_vol",
        "poc_migration_vol",
        "profile_entropy",
        "rejection_score",
        "time_outside_value_ratio",
        "value_area_width_vol",
        "volume_outside_value_ratio",
    }.issubset(names)
    assert all(
        feature.implementation_status is FeatureImplementationStatus.NOT_IMPLEMENTED
        for feature in features
    )

    artifact = json.loads(
        (PROJECT_ROOT / "artifacts/contracts/feature_semantics_v1.json").read_text(encoding="utf-8")
    )
    assert artifact == {
        "schema_version": "feature-semantics-v1",
        "features": canonicalize_for_json(features),
    }


def test_cost_scenarios_have_no_invented_numbers() -> None:
    contracts = lift1_cost_scenario_contracts()

    assert tuple(contract.scenario for contract in contracts) == tuple(CostScenario)
    assert all(contract.components == ExpectedCostComponents() for contract in contracts)
    with pytest.raises(DataQualityError):
        validate_cost_scenario_contract(
            replace(
                contracts[0],
                components=ExpectedCostComponents(total_expected_cost=1.0),
            )
        )


def test_hard_safety_contract_remains_observe_only() -> None:
    policy = lift1_hard_safety_policy()

    assert policy.allow_new_capital is False
    assert set(policy.blocking_reasons) == set(SafetyBlockingReason)


def test_dataset_uses_remain_under_review_and_backwards_ratio_is_non_executable() -> None:
    policies = dataset_use_policies()
    backwards_ratio = get_dataset_use_policy(CONTINUOUS_BACKWARDS_RATIO_ID)

    assert len(policies) == 5
    assert all(
        policy.certification_status is DatasetCertificationStatus.UNDER_REVIEW
        for policy in policies
    )
    assert "continuity_research" in backwards_ratio.permitted_uses
    assert {
        "actual_execution_price",
        "actual_fill_simulation",
        "actual_realized_pnl",
        "actual_volume_profile_price_bins",
    }.issubset(backwards_ratio.prohibited_uses)

    matrix = json.loads(
        (
            PROJECT_ROOT / "artifacts/certification/lift1_dataset_certification_matrix.json"
        ).read_text(encoding="utf-8")
    )
    rows = (*matrix["normalization_policies"], *matrix["use_policies"])
    assert matrix["evidence_basis"] == "STATIC_POLICY_ONLY_NO_QC_RUNTIME"
    assert all(row["certification_status"] == "under_review" for row in rows)

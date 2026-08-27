from __future__ import annotations

# pyright: reportUnnecessaryIsInstance=false
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from systematic_futures.domain.errors import (
    DataQualityError,
    DataTimingInvariantError,
    TimeSemanticsError,
)


class FeatureImplementationStatus(str, Enum):
    NOT_IMPLEMENTED = "not_implemented"
    RESEARCH_MEASUREMENT = "research_measurement"


class CostScenario(str, Enum):
    BASE = "base"
    STRESS = "stress"
    SEVERE = "severe"


class SafetyBlockingReason(str, Enum):
    POINT_IN_TIME_INVALID = "point_in_time_invalid"
    CRITICAL_DATA_STALE = "critical_data_stale"
    CONTRACT_IDENTITY_AMBIGUOUS = "contract_identity_ambiguous"
    SESSION_INVALID = "session_invalid"
    ROLL_STATE_UNSAFE = "roll_state_unsafe"
    DATASET_QUARANTINED = "dataset_quarantined"


class Lift1OperatingMode(str, Enum):
    OBSERVE_ONLY = "observe_only"


@dataclass(frozen=True, slots=True)
class FeatureSemantic:
    feature_name: str
    human_definition: str
    unit: str
    normalization_family: str
    source_family: str
    point_in_time_requirement: str
    missingness_policy: str
    implementation_status: FeatureImplementationStatus


@dataclass(frozen=True, slots=True)
class ForecastPacket:
    """Immutable future forecast contract; Lift 1 creates no real instances."""

    forecast_id: str
    hypothesis_name: str
    hypothesis_version: str
    model_name: str
    model_version: str
    market: str
    contract_symbol: str
    generated_at_utc: datetime
    horizon_minutes: int
    expires_at_utc: datetime
    expected_gross_return: float
    expected_cost_return: float
    expected_net_return: float
    expected_volatility: float
    probability_positive_net: float | None
    downside_quantile_05: float
    median_return: float
    upside_quantile_95: float
    prediction_uncertainty: float
    expected_mae: float | None
    expected_mfe: float | None
    expected_holding_minutes: float | None
    capacity_contracts: int
    expected_turnover: float
    structural_state_id: str
    market_state_id: str
    auction_state_id: str
    event_id: str | None
    invalidation_rule_id: str
    data_snapshot_id: str
    feature_set_version: str
    cost_model_version: str
    status: str
    missing_optional_features: tuple[str, ...]
    quality_flags: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ExpectedCostComponents:
    commission: float | None = None
    exchange_fees: float | None = None
    spread: float | None = None
    slippage: float | None = None
    impact: float | None = None
    roll_cost: float | None = None
    total_expected_cost: float | None = None


@dataclass(frozen=True, slots=True)
class CostScenarioContract:
    scenario: CostScenario
    components: ExpectedCostComponents
    implementation_status: FeatureImplementationStatus
    schema_version: str


@dataclass(frozen=True, slots=True)
class HardSafetyPolicy:
    operating_mode: Lift1OperatingMode
    blocking_reasons: tuple[SafetyBlockingReason, ...]
    allow_new_capital: bool
    policy_version: str


def _require_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise DataQualityError(f"{field_name} must be a non-blank string")


def _require_utc(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise TimeSemanticsError(f"{field_name} must be timezone-aware")
    if value.utcoffset() != timedelta(0):
        raise TimeSemanticsError(f"{field_name} must be normalized to UTC")


def _require_finite(value: float, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise DataQualityError(f"{field_name} must be a finite number")
    if not math.isfinite(value):
        raise DataQualityError(f"{field_name} must be a finite number")


def _require_sorted_unique_text(values: tuple[str, ...], field_name: str) -> None:
    if not isinstance(values, tuple):
        raise DataQualityError(f"{field_name} must be a tuple")
    for index, value in enumerate(values):
        _require_text(value, f"{field_name}[{index}]")
    if values != tuple(sorted(set(values))):
        raise DataQualityError(f"{field_name} must be sorted and contain no duplicates")


def validate_feature_semantic(feature: FeatureSemantic) -> None:
    """Validate metadata for one registered feature.

    Units: ``unit`` names the future value unit; no value is calculated or converted.
    Time semantics: ``point_in_time_requirement`` must state the availability rule in text.
    Missingness: ``missingness_policy`` is mandatory and no fallback is inferred.
    Raises: ``DataQualityError`` for blank metadata or an unknown status.
    """

    for field_name, value in (
        ("feature_name", feature.feature_name),
        ("human_definition", feature.human_definition),
        ("unit", feature.unit),
        ("normalization_family", feature.normalization_family),
        ("source_family", feature.source_family),
        ("point_in_time_requirement", feature.point_in_time_requirement),
        ("missingness_policy", feature.missingness_policy),
    ):
        _require_text(value, field_name)
    if feature.feature_name.strip() != feature.feature_name:
        raise DataQualityError("feature_name may not contain surrounding whitespace")
    if feature.feature_name.lower() != feature.feature_name or " " in feature.feature_name:
        raise DataQualityError("feature_name must use lowercase snake_case")
    if not isinstance(feature.implementation_status, FeatureImplementationStatus):
        raise DataQualityError("implementation_status must be a FeatureImplementationStatus")


def validate_forecast_packet(packet: ForecastPacket) -> None:
    """Validate the Master-Spec forecast contract without generating a forecast.

    Units: returns, costs, volatility, and quantiles are decimal-return units; turnover is a
    non-negative dimensionless ratio; holding and horizon values are minutes; capacity is whole
    contracts. Time semantics: generation and expiry must be aware UTC and expiry must be later.
    Missingness: probability, event identity, MAE/MFE, and expected holding time may be ``None``;
    optional-feature names and quality flags explicitly record other missingness. Raises:
    ``TimeSemanticsError``, ``DataTimingInvariantError``, or ``DataQualityError``.
    """

    for field_name, value in (
        ("forecast_id", packet.forecast_id),
        ("hypothesis_name", packet.hypothesis_name),
        ("hypothesis_version", packet.hypothesis_version),
        ("model_name", packet.model_name),
        ("model_version", packet.model_version),
        ("market", packet.market),
        ("contract_symbol", packet.contract_symbol),
        ("structural_state_id", packet.structural_state_id),
        ("market_state_id", packet.market_state_id),
        ("auction_state_id", packet.auction_state_id),
        ("invalidation_rule_id", packet.invalidation_rule_id),
        ("data_snapshot_id", packet.data_snapshot_id),
        ("feature_set_version", packet.feature_set_version),
        ("cost_model_version", packet.cost_model_version),
        ("status", packet.status),
    ):
        _require_text(value, field_name)
    if packet.event_id is not None:
        _require_text(packet.event_id, "event_id")
    _require_utc(packet.generated_at_utc, "generated_at_utc")
    _require_utc(packet.expires_at_utc, "expires_at_utc")
    if packet.generated_at_utc >= packet.expires_at_utc:
        raise DataTimingInvariantError("generated_at_utc must precede expires_at_utc")
    if isinstance(packet.horizon_minutes, bool) or not isinstance(packet.horizon_minutes, int):
        raise DataQualityError("horizon_minutes must be a positive integer")
    if packet.horizon_minutes <= 0:
        raise DataQualityError("horizon_minutes must be a positive integer")
    _validate_forecast_numbers(packet)
    _require_sorted_unique_text(packet.missing_optional_features, "missing_optional_features")
    _require_sorted_unique_text(packet.quality_flags, "quality_flags")


def _validate_forecast_numbers(packet: ForecastPacket) -> None:
    values = (
        ("expected_gross_return", packet.expected_gross_return),
        ("expected_cost_return", packet.expected_cost_return),
        ("expected_net_return", packet.expected_net_return),
        ("expected_volatility", packet.expected_volatility),
        ("downside_quantile_05", packet.downside_quantile_05),
        ("median_return", packet.median_return),
        ("upside_quantile_95", packet.upside_quantile_95),
        ("prediction_uncertainty", packet.prediction_uncertainty),
        ("expected_turnover", packet.expected_turnover),
    )
    for field_name, value in values:
        _require_finite(value, field_name)
    for field_name, value in (
        ("expected_mae", packet.expected_mae),
        ("expected_mfe", packet.expected_mfe),
        ("expected_holding_minutes", packet.expected_holding_minutes),
    ):
        if value is not None:
            _require_finite(value, field_name)
    if packet.probability_positive_net is not None:
        _require_finite(packet.probability_positive_net, "probability_positive_net")
        if not 0.0 <= packet.probability_positive_net <= 1.0:
            raise DataQualityError("probability_positive_net must be between zero and one")
    if not packet.downside_quantile_05 <= packet.median_return <= packet.upside_quantile_95:
        raise DataQualityError("forecast quantiles must be ordered")
    if packet.expected_cost_return < 0 or packet.expected_volatility < 0:
        raise DataQualityError("expected_cost_return and expected_volatility must be non-negative")
    if packet.prediction_uncertainty < 0 or packet.expected_turnover < 0:
        raise DataQualityError("prediction_uncertainty and expected_turnover must be non-negative")
    if packet.expected_holding_minutes is not None and packet.expected_holding_minutes <= 0:
        raise DataQualityError("expected_holding_minutes must be positive when present")
    if isinstance(packet.capacity_contracts, bool) or not isinstance(
        packet.capacity_contracts, int
    ):
        raise DataQualityError("capacity_contracts must be a non-negative integer")
    if packet.capacity_contracts < 0:
        raise DataQualityError("capacity_contracts must be a non-negative integer")


def validate_expected_cost_components(components: ExpectedCostComponents) -> None:
    """Enforce that Lift 1 freezes cost fields without inventing numerical costs.

    Units: future component values will use one explicitly declared common cost unit.
    Time semantics: this schema has no clock and performs no estimation.
    Missingness: every numerical component must remain ``None`` in Lift 1.
    Raises: ``DataQualityError`` if any numerical implementation is supplied.
    """

    values = (
        components.commission,
        components.exchange_fees,
        components.spread,
        components.slippage,
        components.impact,
        components.roll_cost,
        components.total_expected_cost,
    )
    if any(value is not None for value in values):
        raise DataQualityError("Lift 1 cost component values must remain NOT_IMPLEMENTED")


def validate_cost_scenario_contract(contract: CostScenarioContract) -> None:
    """Validate one schema-only base, stress, or severe cost scenario.

    Units: future component units are deliberately unresolved until a cost model is certified.
    Time semantics: scenarios do not estimate time-dependent costs in Lift 1.
    Missingness: all numerical components are explicitly ``None``.
    Raises: ``DataQualityError`` for an invalid scenario, status, version, or numerical value.
    """

    if not isinstance(contract.scenario, CostScenario):
        raise DataQualityError("scenario must be a CostScenario")
    if contract.implementation_status is not FeatureImplementationStatus.NOT_IMPLEMENTED:
        raise DataQualityError("Lift 1 cost scenarios must remain NOT_IMPLEMENTED")
    _require_text(contract.schema_version, "schema_version")
    validate_expected_cost_components(contract.components)


def lift1_cost_scenario_contracts() -> tuple[CostScenarioContract, ...]:
    """Return the three deterministic, number-free Lift 1 cost interfaces.

    Units: unresolved; no numerical fields are populated. Time semantics: not applicable.
    Missingness: all component numbers are explicit ``None``. Raises: ``DataQualityError`` if a
    static contract violates the schema-only boundary.
    """

    contracts = tuple(
        CostScenarioContract(
            scenario=scenario,
            components=ExpectedCostComponents(),
            implementation_status=FeatureImplementationStatus.NOT_IMPLEMENTED,
            schema_version="lift1.cost-interface.v1",
        )
        for scenario in CostScenario
    )
    for contract in contracts:
        validate_cost_scenario_contract(contract)
    return contracts


def validate_hard_safety_policy(policy: HardSafetyPolicy) -> None:
    """Validate the Lift 1 observe-only, no-new-capital safety contract.

    Units: not applicable. Time semantics: the policy contains no runtime clock or state change.
    Missingness: all six required blocking reasons must be present exactly once.
    Raises: ``DataQualityError`` if observe-only mode, required reasons, or the capital block is
    weakened.
    """

    if policy.operating_mode is not Lift1OperatingMode.OBSERVE_ONLY:
        raise DataQualityError("Lift 1 operating mode must be OBSERVE_ONLY")
    expected = tuple(sorted(SafetyBlockingReason, key=lambda reason: reason.value))
    if policy.blocking_reasons != expected:
        raise DataQualityError("blocking_reasons must contain the six exact reasons in order")
    if policy.allow_new_capital is not False:
        raise DataQualityError("Lift 1 safety policy must prohibit new capital")
    _require_text(policy.policy_version, "policy_version")


def lift1_hard_safety_policy() -> HardSafetyPolicy:
    """Return the immutable Lift 1 observe-only safety policy.

    Units: not applicable. Time semantics: this is a static pre-capital contract.
    Missingness: all mandatory block reasons are populated. Raises: ``DataQualityError`` if the
    embedded policy violates its safety invariant.
    """

    policy = HardSafetyPolicy(
        operating_mode=Lift1OperatingMode.OBSERVE_ONLY,
        blocking_reasons=tuple(sorted(SafetyBlockingReason, key=lambda reason: reason.value)),
        allow_new_capital=False,
        policy_version="lift1.hard-safety.v1",
    )
    validate_hard_safety_policy(policy)
    return policy


__all__ = (
    "CostScenario",
    "CostScenarioContract",
    "ExpectedCostComponents",
    "FeatureImplementationStatus",
    "FeatureSemantic",
    "ForecastPacket",
    "HardSafetyPolicy",
    "Lift1OperatingMode",
    "SafetyBlockingReason",
    "lift1_cost_scenario_contracts",
    "lift1_hard_safety_policy",
    "validate_cost_scenario_contract",
    "validate_expected_cost_components",
    "validate_feature_semantic",
    "validate_forecast_packet",
    "validate_hard_safety_policy",
)

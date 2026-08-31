# pyright: reportPrivateUsage=false
import math
from dataclasses import dataclass
from datetime import date, datetime

from systematic_futures.domain.enums import RollState
from systematic_futures.domain.errors import (
    ContractBoundaryError,
    DataQualityError,
    DataTimingInvariantError,
)
from systematic_futures.measurement.structural_inputs import (
    _require_flags,
    _require_hash,
    _require_non_negative_optional,
    _require_text,
    _require_utc,
)


@dataclass(frozen=True, slots=True)
class TrendComponent:
    """One transparent trend horizon in completed-session units."""

    lookback_sessions: int
    log_return: float | None
    expected_horizon_volatility: float | None
    volatility_normalized_return: float | None

    def __post_init__(self) -> None:
        if type(self.lookback_sessions) is not int or self.lookback_sessions <= 0:
            raise DataQualityError("lookback_sessions must be a positive integer")
        values = (
            self.log_return,
            self.expected_horizon_volatility,
            self.volatility_normalized_return,
        )
        if any(value is None for value in values) and not all(value is None for value in values):
            raise DataQualityError("trend component values must be jointly present or absent")
        for field_name, value in (
            ("log_return", self.log_return),
            ("expected_horizon_volatility", self.expected_horizon_volatility),
            ("volatility_normalized_return", self.volatility_normalized_return),
        ):
            if value is not None and not math.isfinite(value):
                raise DataQualityError(f"{field_name} must be finite when present")
        if self.expected_horizon_volatility is not None and self.expected_horizon_volatility <= 0:
            raise DataQualityError("expected_horizon_volatility must be positive")


@dataclass(frozen=True, slots=True)
class CarryComponent:
    """Transparent mapped/next actual-contract curve state."""

    mapped_contract: str
    next_contract: str
    mapped_expiry: date
    next_expiry: date
    annualized_curve_carry: float
    front_next_log_spread: float
    normalized_carry: float | None
    mapped_open_interest: float | None
    next_open_interest: float | None
    open_interest_ratio: float | None
    observation_time_utc: datetime
    available_at_utc: datetime
    source_lineage_hash: str

    def __post_init__(self) -> None:
        _require_text(self.mapped_contract, "mapped_contract")
        _require_text(self.next_contract, "next_contract")
        if self.next_expiry <= self.mapped_expiry:
            raise ContractBoundaryError("carry expiry ordering is invalid")
        for field_name, value in (
            ("annualized_curve_carry", self.annualized_curve_carry),
            ("front_next_log_spread", self.front_next_log_spread),
        ):
            if not math.isfinite(value):
                raise DataQualityError(f"{field_name} must be finite")
        if self.normalized_carry is not None and not math.isfinite(self.normalized_carry):
            raise DataQualityError("normalized_carry must be finite when present")
        _require_non_negative_optional(self.mapped_open_interest, "mapped_open_interest")
        _require_non_negative_optional(self.next_open_interest, "next_open_interest")
        _require_non_negative_optional(self.open_interest_ratio, "open_interest_ratio")
        _require_utc(self.observation_time_utc, "observation_time_utc")
        _require_utc(self.available_at_utc, "available_at_utc")
        if self.observation_time_utc > self.available_at_utc:
            raise DataTimingInvariantError("carry observation cannot precede availability")
        _require_hash(self.source_lineage_hash, "source_lineage_hash")


@dataclass(frozen=True, slots=True)
class StructuralStateSnapshot:
    """Point-in-time structural state with separate trend, volatility, and carry dimensions."""

    snapshot_id: str
    root: str
    continuous_symbol: str
    mapped_contract: str
    session_id: str
    as_of_utc: datetime
    available_at_utc: datetime
    trend_components: tuple[TrendComponent, ...]
    trend_score: float | None
    trend_consistency: float | None
    realized_volatility: float | None
    volatility_percentile: float | None
    carry: CarryComponent | None
    roll_state: RollState
    measurement_ready: bool
    quality_flags: tuple[str, ...]
    feature_version: str
    lineage_hash: str

    def __post_init__(self) -> None:
        _require_text(self.snapshot_id, "snapshot_id")
        for field_name, value in (
            ("root", self.root),
            ("continuous_symbol", self.continuous_symbol),
            ("mapped_contract", self.mapped_contract),
            ("session_id", self.session_id),
            ("feature_version", self.feature_version),
        ):
            _require_text(value, field_name)
        _require_utc(self.as_of_utc, "as_of_utc")
        _require_utc(self.available_at_utc, "available_at_utc")
        if self.as_of_utc > self.available_at_utc:
            raise DataTimingInvariantError("state as_of cannot exceed availability")
        if not self.trend_components:
            raise DataQualityError("trend_components must not be empty")
        if tuple(component.lookback_sessions for component in self.trend_components) != tuple(
            sorted(component.lookback_sessions for component in self.trend_components)
        ):
            raise DataQualityError("trend_components must be sorted by lookback")
        for field_name, value in (
            ("trend_score", self.trend_score),
            ("trend_consistency", self.trend_consistency),
            ("realized_volatility", self.realized_volatility),
            ("volatility_percentile", self.volatility_percentile),
        ):
            if value is not None and not math.isfinite(value):
                raise DataQualityError(f"{field_name} must be finite when present")
        if self.trend_consistency is not None and not 0 <= self.trend_consistency <= 1:
            raise DataQualityError("trend_consistency must be in [0, 1]")
        if self.realized_volatility is not None and self.realized_volatility <= 0:
            raise DataQualityError("realized_volatility must be positive when present")
        if self.volatility_percentile is not None and not 0 <= self.volatility_percentile <= 1:
            raise DataQualityError("volatility_percentile must be in [0, 1]")
        if not isinstance(self.roll_state, RollState):
            raise DataQualityError("roll_state must be a RollState")
        if self.measurement_ready != (
            self.trend_score is not None
            and self.realized_volatility is not None
            and all(
                component.volatility_normalized_return is not None
                for component in self.trend_components
            )
        ):
            raise DataQualityError("measurement_ready disagrees with trend readiness")
        _require_flags(self.quality_flags)
        _require_hash(self.lineage_hash, "lineage_hash")


__all__ = (
    "CarryComponent",
    "StructuralStateSnapshot",
    "TrendComponent",
)

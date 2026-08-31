from __future__ import annotations

import math
from collections import deque
from statistics import median

import numpy as np

from systematic_futures.config.system import StructuralFeatureConfig
from systematic_futures.domain.errors import (
    ContractBoundaryError,
    DataTimingInvariantError,
)
from systematic_futures.domain.serialization import sha256_hex
from systematic_futures.measurement.structural_inputs import (
    ContinuousBarObservation,
    ContinuousSessionCloseObservation,
    ContractCurveObservation,
    QuoteObservation,
    _require_text,
)
from systematic_futures.measurement.structural_sessions import ContinuousSessionCloseBuilder
from systematic_futures.measurement.structural_state import (
    CarryComponent,
    StructuralStateSnapshot,
    TrendComponent,
)

_ROBUST_SCALE_CONSTANT = 1.4826
_EPSILON = 1e-12

class StructuralStateEngine:
    """Build transparent structural state from continuous closes and explicit curve pairs."""

    def __init__(
        self,
        root: str,
        continuous_symbol: str,
        config: StructuralFeatureConfig,
    ) -> None:
        _require_text(root, "root")
        _require_text(continuous_symbol, "continuous_symbol")
        self.root = root
        self.continuous_symbol = continuous_symbol
        self.config = config
        self._closes: deque[float] = deque(maxlen=config.maximum_trend_lookback + 1)
        self._realized_volatility_history: deque[float] = deque(
            maxlen=config.volatility_percentile_window_sessions
        )
        self._carry_history: deque[float] = deque(
            maxlen=config.carry_normalization_window_sessions
        )
        self._latest_curve: ContractCurveObservation | None = None
        self._last_curve_time_utc: datetime | None = None
        self._last_session_end_utc: datetime | None = None
        self._last_snapshot: StructuralStateSnapshot | None = None

    @property
    def last_snapshot(self) -> StructuralStateSnapshot | None:
        """Return the latest immutable structural state, if one has been produced."""

        return self._last_snapshot

    def update_curve(self, observation: ContractCurveObservation) -> None:
        """Store the latest point-in-time curve pair without creating a state snapshot."""

        if observation.root != self.root or observation.continuous_symbol != self.continuous_symbol:
            raise ContractBoundaryError(
                "curve observation identity does not match structural engine"
            )
        if (
            self._last_curve_time_utc is not None
            and observation.event_time_utc <= self._last_curve_time_utc
        ):
            raise DataTimingInvariantError("curve observations must be strictly time ordered")
        self._latest_curve = observation
        self._last_curve_time_utc = observation.event_time_utc

    def update_session_close(
        self,
        observation: ContinuousSessionCloseObservation,
    ) -> StructuralStateSnapshot:
        """Update state at one completed semantic-session close.

        Trend and volatility use the continuous normalized series. Carry uses only the
        latest explicit mapped/next actual-contract pair available no later than this close.
        """

        if observation.root != self.root or observation.continuous_symbol != self.continuous_symbol:
            raise ContractBoundaryError("session close identity does not match structural engine")
        if (
            self._last_session_end_utc is not None
            and observation.session_end_utc <= self._last_session_end_utc
        ):
            raise DataTimingInvariantError("session closes must be strictly time ordered")
        self._last_session_end_utc = observation.session_end_utc
        self._closes.append(observation.close)
        realized_volatility = self._realized_volatility()
        volatility_percentile = self._prior_only_percentile(
            realized_volatility,
            self._realized_volatility_history,
            self.config.volatility_percentile_minimum_history,
        )
        trend_components = self._trend_components(realized_volatility)
        normalized_returns = tuple(
            component.volatility_normalized_return
            for component in trend_components
            if component.volatility_normalized_return is not None
        )
        trend_score = float(math.fsum(normalized_returns) / len(normalized_returns)) if (
            len(normalized_returns) == len(trend_components)
        ) else None
        trend_consistency = self._trend_consistency(normalized_returns, trend_score)
        quality_flags = set(observation.quality_flags)
        if realized_volatility is None:
            quality_flags.add("REALIZED_VOLATILITY_NOT_READY")
        if any(component.volatility_normalized_return is None for component in trend_components):
            quality_flags.add("TREND_NOT_READY")
        if volatility_percentile is None:
            quality_flags.add("VOLATILITY_PERCENTILE_NOT_READY")
        carry = self._carry_component(observation, quality_flags)
        if realized_volatility is not None:
            self._realized_volatility_history.append(realized_volatility)
        lineage_hash = sha256_hex(
            {
                "close_sources": observation.source_lineage_hashes,
                "curve_source": None if carry is None else carry.source_lineage_hash,
                "feature_version": self.config.feature_version,
            }
        )
        snapshot_payload = {
            "root": self.root,
            "continuous_symbol": self.continuous_symbol,
            "mapped_contract": observation.mapped_contract,
            "session_id": observation.session_id,
            "as_of_utc": observation.session_end_utc,
            "available_at_utc": observation.available_at_utc,
            "trend_components": trend_components,
            "trend_score": trend_score,
            "trend_consistency": trend_consistency,
            "realized_volatility": realized_volatility,
            "volatility_percentile": volatility_percentile,
            "carry": carry,
            "roll_state": observation.roll_state,
            "quality_flags": tuple(sorted(quality_flags)),
            "feature_version": self.config.feature_version,
            "lineage_hash": lineage_hash,
        }
        snapshot = StructuralStateSnapshot(
            snapshot_id=f"structural_{sha256_hex(snapshot_payload)}",
            root=self.root,
            continuous_symbol=self.continuous_symbol,
            mapped_contract=observation.mapped_contract,
            session_id=observation.session_id,
            as_of_utc=observation.session_end_utc,
            available_at_utc=observation.available_at_utc,
            trend_components=trend_components,
            trend_score=trend_score,
            trend_consistency=trend_consistency,
            realized_volatility=realized_volatility,
            volatility_percentile=volatility_percentile,
            carry=carry,
            roll_state=observation.roll_state,
            measurement_ready=(
                trend_score is not None
                and realized_volatility is not None
                and all(
                    component.volatility_normalized_return is not None
                    for component in trend_components
                )
            ),
            quality_flags=tuple(sorted(quality_flags)),
            feature_version=self.config.feature_version,
            lineage_hash=lineage_hash,
        )
        self._last_snapshot = snapshot
        return snapshot

    def _realized_volatility(self) -> float | None:
        window = self.config.realized_volatility_window_sessions
        if len(self._closes) < window + 1:
            return None
        values = np.asarray(tuple(self._closes)[-(window + 1) :], dtype=np.float64)
        returns = np.diff(np.log(values))
        volatility = float(np.std(returns, ddof=1) * math.sqrt(self.config.annualization_sessions))
        if not math.isfinite(volatility) or volatility <= _EPSILON:
            return None
        return volatility

    def _trend_components(
        self,
        realized_volatility: float | None,
    ) -> tuple[TrendComponent, ...]:
        closes = tuple(self._closes)
        components: list[TrendComponent] = []
        for lookback in self.config.trend_lookbacks_sessions:
            if len(closes) < lookback + 1 or realized_volatility is None:
                components.append(TrendComponent(lookback, None, None, None))
                continue
            log_return = math.log(closes[-1] / closes[-(lookback + 1)])
            expected_horizon_volatility = realized_volatility * math.sqrt(
                lookback / self.config.annualization_sessions
            )
            if expected_horizon_volatility <= _EPSILON:
                components.append(TrendComponent(lookback, None, None, None))
                continue
            components.append(
                TrendComponent(
                    lookback_sessions=lookback,
                    log_return=log_return,
                    expected_horizon_volatility=expected_horizon_volatility,
                    volatility_normalized_return=log_return / expected_horizon_volatility,
                )
            )
        return tuple(components)

    @staticmethod
    def _trend_consistency(
        normalized_returns: tuple[float, ...],
        trend_score: float | None,
    ) -> float | None:
        if trend_score is None or abs(trend_score) <= _EPSILON or not normalized_returns:
            return None
        direction = 1 if trend_score > 0 else -1
        agreements = sum(
            1
            for value in normalized_returns
            if (1 if value > 0 else -1 if value < 0 else 0) == direction
        )
        return agreements / len(normalized_returns)

    def _carry_component(
        self,
        session_close: ContinuousSessionCloseObservation,
        quality_flags: set[str],
    ) -> CarryComponent | None:
        observation = self._latest_curve
        if observation is None:
            quality_flags.add("CARRY_OBSERVATION_MISSING")
            return None
        if (
            observation.event_time_utc > session_close.session_end_utc
            or observation.available_at_utc > session_close.available_at_utc
        ):
            quality_flags.add("CARRY_OBSERVATION_AFTER_DECISION")
            return None
        if observation.mapped_contract != session_close.mapped_contract:
            quality_flags.add("CARRY_CONTRACT_MISMATCH")
            return None
        raw_carry = observation.annualized_curve_carry
        normalized = self._prior_only_robust_z(
            raw_carry,
            self._carry_history,
            self.config.carry_minimum_history,
        )
        if normalized is None:
            quality_flags.add("CARRY_NORMALIZATION_NOT_READY")
        oi_ratio = None
        if (
            observation.mapped_open_interest is not None
            and observation.next_open_interest is not None
            and observation.next_open_interest > 0
        ):
            oi_ratio = observation.mapped_open_interest / observation.next_open_interest
        component = CarryComponent(
            mapped_contract=observation.mapped_contract,
            next_contract=observation.next_contract,
            mapped_expiry=observation.mapped_expiry,
            next_expiry=observation.next_expiry,
            annualized_curve_carry=raw_carry,
            front_next_log_spread=observation.front_next_log_spread,
            normalized_carry=normalized,
            mapped_open_interest=observation.mapped_open_interest,
            next_open_interest=observation.next_open_interest,
            open_interest_ratio=oi_ratio,
            observation_time_utc=observation.event_time_utc,
            available_at_utc=observation.available_at_utc,
            source_lineage_hash=observation.source_lineage_hash,
        )
        self._carry_history.append(raw_carry)
        return component

    @staticmethod
    def _prior_only_robust_z(
        value: float,
        history: deque[float],
        minimum_history: int,
    ) -> float | None:
        if len(history) < minimum_history:
            return None
        past = tuple(history)
        center = median(past)
        mad = median(abs(item - center) for item in past)
        scale = _ROBUST_SCALE_CONSTANT * mad
        if not math.isfinite(scale) or scale <= _EPSILON:
            return None
        return (value - center) / scale

    @staticmethod
    def _prior_only_percentile(
        value: float | None,
        history: deque[float],
        minimum_history: int,
    ) -> float | None:
        if value is None or len(history) < minimum_history:
            return None
        return sum(item <= value for item in history) / len(history)




__all__ = (
    "CarryComponent",
    "ContinuousBarObservation",
    "ContinuousSessionCloseBuilder",
    "ContinuousSessionCloseObservation",
    "ContractCurveObservation",
    "QuoteObservation",
    "StructuralStateEngine",
    "StructuralStateSnapshot",
    "TrendComponent",
)

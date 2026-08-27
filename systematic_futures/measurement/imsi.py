# pyright: reportUnnecessaryIsInstance=false
import math
from collections import defaultdict, deque
from datetime import datetime

import numpy as np
import numpy.typing as npt

from systematic_futures.config.research import MEASUREMENT_CLOCK_POLICY
from systematic_futures.domain.enums import SessionType
from systematic_futures.domain.errors import (
    ContractBoundaryError,
    DataQualityError,
    DataTimingInvariantError,
)
from systematic_futures.domain.serialization import sha256_hex
from systematic_futures.measurement.state_models import CompletedTradeBar, IMSIStateSnapshot

_VERSION = "imsi_state_core_math_v3|ewma_diagonal_shrinkage_spec_v1"
_ALPHA = 1.0 / 14.0
_EWMA_DECAY = 0.96
_SHRINKAGE_MINIMUM = 0.05
_SHRINKAGE_MAXIMUM = 0.95
_MAX_PRIOR_STATES = 300
_MIN_COVARIANCE_STATES = 30
_MIN_RARITY_DISTANCES = 30
_MAX_NEIGHBORS = 15
_NEIGHBOR_EMBARGO_BARS = 7
_MIN_TOD_OBSERVATIONS = 30
_MAX_TOD_SESSIONS = 30
_MAX_CORRELATION_CONDITION = 1000.0
_EPSILON = 1e-12
_ROUND_OFF_TOLERANCE = 1e-12


class IMSIStateCore:
    """Bounded prior-only VW-RSI, bar-VWAP displacement, and state geometry."""

    def __init__(self, root: str, contract_symbol: str) -> None:
        """Create empty state for one actual contract.

        Units: prices and completed-bar volume remain native until ratios are formed.
        Time semantics: 30-minute bars must be strictly chronological. Missingness:
        the first delta and under-warmed baselines withhold dependent fields. Raises:
        ``DataQualityError`` for blank identity.
        """

        if not root.strip() or not contract_symbol.strip():
            raise DataQualityError("IMSI StateCore identity must be non-blank")
        self.root = root
        self.contract_symbol = contract_symbol
        self._session_id: str | None = None
        self._session_price_volume = 0.0
        self._session_volume = 0.0
        self._previous_close: float | None = None
        self._ema_up = 0.0
        self._ema_down = 0.0
        self._last_bar_end: datetime | None = None
        self._bar_sequence = 0
        self._seasonal: dict[tuple[SessionType, int], deque[tuple[str, float]]] = defaultdict(
            lambda: deque(maxlen=_MAX_TOD_SESSIONS)
        )
        self._states: deque[tuple[int, float, float]] = deque(maxlen=_MAX_PRIOR_STATES)
        self._distances: deque[float] = deque(maxlen=_MAX_PRIOR_STATES)

    @property
    def prior_state_count(self) -> int:
        """Return the bounded count of prior valid two-dimensional states."""

        return len(self._states)

    def on_bar(
        self,
        bar: CompletedTradeBar,
        session_type: SessionType,
        session_start_utc: datetime,
    ) -> IMSIStateSnapshot | None:
        """Measure one completed 30-minute bar from prior-only baselines.

        VW-RSI is in oscillator points, session VWAP is native price, VWAP distance
        is in percentage points, and state geometry is dimensionless. The current bar
        enters seasonal and state memories only after its snapshot is calculated.
        """

        self._validate_bar(bar, session_type, session_start_utc)
        self._last_bar_end = bar.end_utc
        self._bar_sequence += 1
        if bar.session_id != self._session_id:
            self._session_id = bar.session_id
            self._session_price_volume = 0.0
            self._session_volume = 0.0
        self._session_price_volume += bar.close * bar.volume
        self._session_volume += bar.volume
        session_vwap = self._session_price_volume / self._session_volume
        if self._previous_close is None:
            self._previous_close = bar.close
            return None

        force = (bar.close - self._previous_close) * bar.volume
        self._previous_close = bar.close
        upward = max(force, 0.0)
        downward = max(-force, 0.0)
        self._ema_up = _ALPHA * upward + (1.0 - _ALPHA) * self._ema_up
        self._ema_down = _ALPHA * downward + (1.0 - _ALPHA) * self._ema_down
        vwrsi = volume_weighted_rsi(self._ema_up, self._ema_down)
        dist_vwap = (bar.close - session_vwap) / session_vwap * 100.0

        elapsed = bar.start_utc - session_start_utc
        slot = int(
            elapsed.total_seconds() // (MEASUREMENT_CLOCK_POLICY.medium_state_bar_minutes * 60)
        )
        seasonal_key = (session_type, slot)
        prior_bucket = self._seasonal[seasonal_key]
        if any(session_id == bar.session_id for session_id, _ in prior_bucket):
            raise DataQualityError("IMSI TOD bucket already contains the current session")
        prior_tod = tuple(value for _, value in prior_bucket)[-_MAX_TOD_SESSIONS:]
        adjusted = (
            vwrsi - float(np.median(prior_tod)) if len(prior_tod) >= _MIN_TOD_OBSERVATIONS else None
        )

        flags: set[str] = {"IMSI_FULL_MODEL_DEFERRED_LIFT3"}
        if adjusted is None:
            flags.add("IMSI_TOD_WARMUP")
        distance: float | None = None
        rarity: float | None = None
        neighbor_mean: float | None = None
        neighbor_p90: float | None = None
        neighbor_support = 0
        condition: float | None = None
        shrinkage_delta: float | None = None
        effective_sample_size: float | None = None

        if adjusted is not None:
            current = np.asarray((adjusted, dist_vwap), dtype=np.float64)
            if len(self._states) >= _MIN_COVARIANCE_STATES:
                prior = np.asarray(
                    [(first, second) for _, first, second in self._states],
                    dtype=np.float64,
                )
                try:
                    (
                        mean,
                        inverse,
                        shrinkage_delta,
                        effective_sample_size,
                        condition,
                    ) = ewma_diagonal_shrinkage_spec_v1(prior)
                except DataQualityError:
                    flags.add("IMSI_COVARIANCE_DEGENERATE")
                else:
                    if condition > _MAX_CORRELATION_CONDITION:
                        flags.add("IMSI_COVARIANCE_UNSTABLE")
                    else:
                        distance = mahalanobis_distance(current, mean, inverse)
                        neighbor_mean, neighbor_p90, neighbor_support = neighbor_distance_summary(
                            tuple(self._states),
                            self._bar_sequence,
                            current,
                            inverse,
                        )
                        if len(self._distances) >= _MIN_RARITY_DISTANCES:
                            rarity = sum(value <= distance for value in self._distances) / len(
                                self._distances
                            )
                        else:
                            flags.add("IMSI_RARITY_WARMUP")
                        self._distances.append(distance)
            else:
                flags.add("IMSI_COVARIANCE_WARMUP")
            self._states.append((self._bar_sequence, float(current[0]), float(current[1])))

        prior_bucket.append((bar.session_id, vwrsi))
        warmup_complete = distance is not None and rarity is not None
        identity = {
            "as_of_utc": bar.end_utc,
            "contract_symbol": self.contract_symbol,
            "covariance_condition_number": condition,
            "covariance_effective_sample_size": effective_sample_size,
            "covariance_shrinkage_delta": shrinkage_delta,
            "dist_vwap_pct": dist_vwap,
            "mahalanobis_distance": distance,
            "neighbor_distance_mean": neighbor_mean,
            "neighbor_distance_p90": neighbor_p90,
            "neighbor_support": neighbor_support,
            "root": self.root,
            "session_id": bar.session_id,
            "session_vwap": session_vwap,
            "state_rarity_percentile": rarity,
            "version": _VERSION,
            "vwrsi_raw": vwrsi,
            "vwrsi_tod_adjusted": adjusted,
        }
        return IMSIStateSnapshot(
            snapshot_id=f"imsi_{sha256_hex(identity)}",
            root=self.root,
            contract_symbol=self.contract_symbol,
            session_id=bar.session_id,
            as_of_utc=bar.end_utc,
            available_at_utc=bar.available_at_utc,
            vwrsi_raw=vwrsi,
            vwrsi_tod_adjusted=adjusted,
            session_vwap=session_vwap,
            dist_vwap_pct=dist_vwap,
            mahalanobis_distance=distance,
            state_rarity_percentile=rarity,
            neighbor_distance_mean=neighbor_mean,
            neighbor_distance_p90=neighbor_p90,
            neighbor_support=neighbor_support,
            covariance_shrinkage_delta=shrinkage_delta,
            covariance_effective_sample_size=effective_sample_size,
            covariance_condition_number=condition,
            warmup_complete=warmup_complete,
            measurement_ready=warmup_complete,
            quality_flags=tuple(sorted(flags)),
            version=_VERSION,
        )

    def _validate_bar(
        self,
        bar: CompletedTradeBar,
        session_type: SessionType,
        session_start_utc: datetime,
    ) -> None:
        if bar.root != self.root or bar.contract_symbol != self.contract_symbol:
            raise ContractBoundaryError("IMSI StateCore cannot cross actual-contract identity")
        if bar.period_minutes != MEASUREMENT_CLOCK_POLICY.medium_state_bar_minutes:
            raise DataQualityError("IMSI StateCore requires completed medium-state bars")
        if not isinstance(session_type, SessionType):
            raise DataQualityError("session_type must be a SessionType")
        if self._last_bar_end is not None and bar.end_utc <= self._last_bar_end:
            raise DataTimingInvariantError("IMSI bars must arrive in increasing end-time order")
        if bar.start_utc < session_start_utc:
            raise DataTimingInvariantError("IMSI bar starts before its semantic session")


def volume_weighted_rsi(ema_up: float, ema_down: float) -> float:
    """Return the exact specified zero-seed VW-RSI transform in oscillator points."""

    if not all(math.isfinite(value) and value >= 0 for value in (ema_up, ema_down)):
        raise DataQualityError("VW-RSI EMA inputs must be finite and non-negative")
    relative_strength = ema_up / (ema_down + _EPSILON)
    value = 100.0 - 100.0 / (1.0 + relative_strength)
    if not math.isfinite(value) or not 0.0 <= value <= 100.0:
        raise DataQualityError("VW-RSI calculation produced an invalid value")
    return value


def ewma_diagonal_shrinkage_spec_v1(
    prior_states: npt.NDArray[np.float64],
    decay: float = _EWMA_DECAY,
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64], float, float, float]:
    """Return the exact prior-only project EWMA diagonal-shrinkage estimator.

    Rows are oldest to newest. The estimator preserves both weighted variances and
    shrinks only the weighted correlation using the specification's bounded delta.
    """

    if prior_states.ndim != 2 or prior_states.shape[1] != 2 or prior_states.shape[0] < 2:
        raise DataQualityError("EWMA covariance requires at least two two-dimensional states")
    if not np.isfinite(prior_states).all():
        raise DataQualityError("EWMA covariance states must be finite")
    if not math.isfinite(decay) or not 0.0 < decay < 1.0:
        raise DataQualityError("EWMA covariance decay must be in (0, 1)")
    count = len(prior_states)
    powers = np.arange(count - 1, -1, -1, dtype=np.float64)
    weights = (1.0 - decay) * np.power(decay, powers)
    weights /= np.sum(weights)
    mean = np.asarray(np.average(prior_states, weights=weights, axis=0), dtype=np.float64)
    centered = prior_states - mean
    covariance = np.asarray((centered * weights[:, None]).T @ centered, dtype=np.float64)
    variance_first = float(covariance[0, 0])
    variance_second = float(covariance[1, 1])
    if variance_first <= _EPSILON or variance_second <= _EPSILON:
        raise DataQualityError("EWMA covariance requires positive variance in both dimensions")
    correlation = float(covariance[0, 1]) / math.sqrt(variance_first * variance_second)
    if abs(correlation) > 1.0 + _ROUND_OFF_TOLERANCE:
        raise DataQualityError("EWMA correlation exceeds its mathematical bounds")
    if abs(correlation) > 1.0:
        correlation = math.copysign(1.0, correlation)
    effective_sample_size = float(1.0 / np.sum(weights**2))
    correlation_squared = correlation**2
    raw_delta = (1.0 - correlation_squared) / (effective_sample_size * correlation_squared + 1e-10)
    shrinkage_delta = float(min(_SHRINKAGE_MAXIMUM, max(_SHRINKAGE_MINIMUM, raw_delta)))
    shrunk_correlation = (1.0 - shrinkage_delta) * correlation
    determinant = 1.0 - shrunk_correlation**2
    if determinant <= _EPSILON:
        raise DataQualityError("shrunk EWMA correlation is not positive definite")
    inverse_correlation = (
        np.asarray(
            ((1.0, -shrunk_correlation), (-shrunk_correlation, 1.0)),
            dtype=np.float64,
        )
        / determinant
    )
    inverse_scale = np.diag((1.0 / math.sqrt(variance_first), 1.0 / math.sqrt(variance_second)))
    inverse_covariance = np.asarray(
        inverse_scale @ inverse_correlation @ inverse_scale,
        dtype=np.float64,
    )
    condition = (1.0 + abs(shrunk_correlation)) / (1.0 - abs(shrunk_correlation))
    if not np.isfinite(inverse_covariance).all() or not math.isfinite(condition):
        raise DataQualityError("EWMA covariance calculation produced a non-finite value")
    return mean, inverse_covariance, shrinkage_delta, effective_sample_size, condition


def mahalanobis_distance(
    current: npt.NDArray[np.float64],
    mean: npt.NDArray[np.float64],
    inverse_covariance: npt.NDArray[np.float64],
) -> float:
    """Return a two-dimensional Mahalanobis distance with fail-closed roundoff handling."""

    if current.shape != (2,) or mean.shape != (2,) or inverse_covariance.shape != (2, 2):
        raise DataQualityError("Mahalanobis inputs must use the two-dimensional state shape")
    if not all(np.isfinite(value).all() for value in (current, mean, inverse_covariance)):
        raise DataQualityError("Mahalanobis inputs must be finite")
    if not np.allclose(inverse_covariance, inverse_covariance.T, rtol=1e-12, atol=1e-12):
        raise DataQualityError("Mahalanobis inverse covariance must be symmetric")
    delta = current - mean
    squared = float(delta.T @ inverse_covariance @ delta)
    tolerance = (
        64.0
        * np.finfo(np.float64).eps
        * max(
            1.0,
            float(np.linalg.norm(delta) ** 2 * np.linalg.norm(inverse_covariance, ord=2)),
        )
    )
    if squared < -tolerance:
        raise DataQualityError("Mahalanobis quadratic form is materially negative")
    return math.sqrt(0.0 if squared < 0.0 else squared)


def neighbor_distance_summary(
    prior_states: tuple[tuple[int, float, float], ...],
    current_sequence: int,
    current: npt.NDArray[np.float64],
    inverse_covariance: npt.NDArray[np.float64],
) -> tuple[float | None, float | None, int]:
    """Summarize at most 15 nearest prior states after the exact seven-bar embargo."""

    eligible = np.asarray(
        [
            (first, second)
            for sequence, first, second in prior_states
            if sequence < current_sequence and sequence <= current_sequence - _NEIGHBOR_EMBARGO_BARS
        ],
        dtype=np.float64,
    )
    if len(eligible) == 0:
        return None, None, 0
    distances = np.asarray(
        [mahalanobis_distance(row, current, inverse_covariance) for row in eligible],
        dtype=np.float64,
    )
    support = min(_MAX_NEIGHBORS, len(distances))
    nearest = np.sort(distances)[:support]
    return float(np.mean(nearest)), float(np.percentile(nearest, 90)), support


__all__ = (
    "IMSIStateCore",
    "ewma_diagonal_shrinkage_spec_v1",
    "mahalanobis_distance",
    "neighbor_distance_summary",
    "volume_weighted_rsi",
)

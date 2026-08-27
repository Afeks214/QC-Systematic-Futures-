from __future__ import annotations

# pyright: reportUnnecessaryIsInstance=false
import math
from collections import defaultdict, deque
from datetime import datetime

import numpy as np
import numpy.typing as npt

from systematic_futures.domain.enums import SessionType
from systematic_futures.domain.errors import (
    ContractBoundaryError,
    DataQualityError,
    DataTimingInvariantError,
)
from systematic_futures.domain.serialization import sha256_hex
from systematic_futures.measurement.types import (
    CompletedTradeBar,
    IMSIStateSnapshot,
    TradeObservation,
)

_VERSION = "imsi_state_v1|eigen_floor_covariance_v1"
_ALPHA = 1.0 / 14.0
_MAX_PRIOR_STATES = 300
_MIN_COVARIANCE_STATES = 30
_MIN_RARITY_DISTANCES = 30
_MAX_NEIGHBORS = 15
_MIN_TOD_OBSERVATIONS = 10
_MAX_TOD_SESSIONS = 30


class IMSIEngine:
    """Bounded prior-only momentum, VWAP displacement, and state-distance engine."""

    def __init__(self, root: str, contract_symbol: str) -> None:
        """Create empty contract-local state.

        Units: prices/quantities remain native until ratios are calculated. Time
        semantics: bars and trades must arrive chronologically. Missingness: root and
        actual contract are mandatory. Raises: ``DataQualityError`` for blank identity.
        """

        if not root.strip() or not contract_symbol.strip():
            raise DataQualityError("IMSI identity must be non-blank")
        self.root = root
        self.contract_symbol = contract_symbol
        self._session_id: str | None = None
        self._session_price_volume = 0.0
        self._session_volume = 0.0
        self._previous_close: float | None = None
        self._ema_up: float | None = None
        self._ema_down: float | None = None
        self._last_bar_end: datetime | None = None
        self._seasonal: dict[tuple[SessionType, int], deque[tuple[str, float]]] = defaultdict(
            lambda: deque(maxlen=_MAX_TOD_SESSIONS)
        )
        self._states: deque[tuple[float, float]] = deque(maxlen=_MAX_PRIOR_STATES)
        self._distances: deque[float] = deque(maxlen=_MAX_PRIOR_STATES)

    @property
    def prior_state_count(self) -> int:
        """Return the bounded number of prior valid two-dimensional states."""

        return len(self._states)

    def observe_trade(self, trade: TradeObservation) -> None:
        """Update actual-trade session VWAP state.

        Units: native price times traded quantity. Time semantics: a semantic session
        change resets cumulative VWAP before the new trade is added. Missingness: none.
        Raises: ``ContractBoundaryError`` for an identity mismatch.
        """

        self._validate_identity(trade.root, trade.contract_symbol)
        if trade.session_id != self._session_id:
            self._session_id = trade.session_id
            self._session_price_volume = 0.0
            self._session_volume = 0.0
        self._session_price_volume += trade.price * trade.quantity
        self._session_volume += trade.quantity

    def on_bar(
        self,
        bar: CompletedTradeBar,
        session_type: SessionType,
        session_start_utc: datetime,
    ) -> IMSIStateSnapshot | None:
        """Measure one completed 30m bar using only previously stored baselines.

        Units: VW-RSI is 0-100, VWAP displacement is a decimal ratio, and state
        geometry is dimensionless. Time semantics: seasonal, covariance, neighbor,
        and rarity calculations exclude the current observation until after emission.
        Missingness: the first delta or absent session trades returns ``None``;
        insufficient baselines produce optional fields and quality flags. Raises:
        boundary, session, or ordering errors for invalid input.
        """

        self._validate_identity(bar.root, bar.contract_symbol)
        if bar.period_minutes != 30:
            raise DataQualityError("IMSI requires completed 30m bars")
        if not isinstance(session_type, SessionType):
            raise DataQualityError("session_type must be a SessionType")
        if self._last_bar_end is not None and bar.end_utc <= self._last_bar_end:
            raise DataTimingInvariantError("IMSI bars must arrive in increasing end-time order")
        self._last_bar_end = bar.end_utc
        if self._previous_close is None:
            self._previous_close = bar.close
            return None
        delta = (bar.close - self._previous_close) * bar.volume
        self._previous_close = bar.close
        up = max(delta, 0.0)
        down = max(-delta, 0.0)
        self._ema_up = up if self._ema_up is None else _ALPHA * up + (1 - _ALPHA) * self._ema_up
        self._ema_down = (
            down if self._ema_down is None else _ALPHA * down + (1 - _ALPHA) * self._ema_down
        )
        vwrsi = _vwrsi(self._ema_up, self._ema_down)
        if self._session_id != bar.session_id or self._session_volume <= 0:
            return None
        session_vwap = self._session_price_volume / self._session_volume
        dist_vwap = (bar.close - session_vwap) / session_vwap
        elapsed = bar.start_utc - session_start_utc
        if elapsed.total_seconds() < 0:
            raise DataTimingInvariantError("IMSI bar starts before its semantic session")
        slot = int(elapsed.total_seconds() // (30 * 60))
        seasonal_key = (session_type, slot)
        prior_tod = tuple(
            value
            for session_id, value in self._seasonal[seasonal_key]
            if session_id != bar.session_id
        )[-_MAX_TOD_SESSIONS:]
        adjusted = (
            vwrsi - float(np.median(prior_tod)) if len(prior_tod) >= _MIN_TOD_OBSERVATIONS else None
        )
        flags: set[str] = set()
        if adjusted is None:
            flags.add("IMSI_TOD_WARMUP")
        distance: float | None = None
        rarity: float | None = None
        neighbor_mean: float | None = None
        neighbor_p90: float | None = None
        neighbor_support = 0
        condition: float | None = None
        if adjusted is not None:
            current = np.asarray((adjusted, dist_vwap), dtype=np.float64)
            if len(self._states) >= _MIN_COVARIANCE_STATES:
                prior = np.asarray(self._states, dtype=np.float64)
                covariance, condition = stabilized_covariance(prior)
                inverse = np.linalg.inv(covariance)
                mean = np.mean(prior, axis=0)
                distance = _mahalanobis(current, mean, inverse)
                all_distances = np.asarray(
                    [_mahalanobis(row, current, inverse) for row in prior],
                    dtype=np.float64,
                )
                neighbor_support = min(_MAX_NEIGHBORS, len(all_distances))
                nearest = np.sort(all_distances)[:neighbor_support]
                neighbor_mean = float(np.mean(nearest))
                neighbor_p90 = float(np.percentile(nearest, 90))
                if len(self._distances) >= _MIN_RARITY_DISTANCES:
                    rarity = sum(value <= distance for value in self._distances) / len(
                        self._distances
                    )
                else:
                    flags.add("IMSI_RARITY_WARMUP")
                self._distances.append(distance)
            else:
                flags.add("IMSI_COVARIANCE_WARMUP")
            self._states.append((float(current[0]), float(current[1])))
        self._seasonal[seasonal_key].append((bar.session_id, vwrsi))
        warmup_complete = distance is not None and rarity is not None
        identity = {
            "as_of_utc": bar.end_utc,
            "contract_symbol": self.contract_symbol,
            "dist_vwap_pct": dist_vwap,
            "mahalanobis_distance": distance,
            "root": self.root,
            "session_id": bar.session_id,
            "version": _VERSION,
            "vwrsi_raw": vwrsi,
            "vwrsi_tod_adjusted": adjusted,
        }
        return IMSIStateSnapshot(
            snapshot_id=f"imsi_{sha256_hex(identity)}",
            root=self.root,
            contract_symbol=self.contract_symbol,
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
            covariance_condition_number=condition,
            warmup_complete=warmup_complete,
            quality_flags=tuple(sorted(flags)),
            version=_VERSION,
        )

    def _validate_identity(self, root: str, contract_symbol: str) -> None:
        if root != self.root or contract_symbol != self.contract_symbol:
            raise ContractBoundaryError("IMSI cannot cross actual-contract identity")


def stabilized_covariance(
    prior_states: npt.NDArray[np.float64],
) -> tuple[npt.NDArray[np.float64], float]:
    """Return empirical 2x2 covariance after the frozen eigenvalue floor.

    Units: inherited squared state units; condition number is dimensionless. Time
    semantics: callers supply prior rows only. Missingness: at least two finite 2D
    rows are required. Raises: ``DataQualityError`` for invalid shape or values.
    """

    if prior_states.ndim != 2 or prior_states.shape[1] != 2 or prior_states.shape[0] < 2:
        raise DataQualityError("covariance requires at least two two-dimensional states")
    if not np.isfinite(prior_states).all():
        raise DataQualityError("covariance states must be finite")
    empirical = np.asarray(np.cov(prior_states, rowvar=False, ddof=1), dtype=np.float64)
    eigenvalues, eigenvectors = np.linalg.eigh(empirical)
    largest = max(float(np.max(eigenvalues)), 0.0)
    floor = max(largest * 1e-8, 1e-12)
    stabilized_values = np.maximum(eigenvalues, floor)
    covariance = np.asarray(
        eigenvectors @ np.diag(stabilized_values) @ eigenvectors.T,
        dtype=np.float64,
    )
    condition = float(np.max(stabilized_values) / np.min(stabilized_values))
    return covariance, condition


def _vwrsi(ema_up: float, ema_down: float) -> float:
    if ema_up == 0 and ema_down == 0:
        return 50.0
    if ema_down == 0:
        return 100.0
    relative_strength = ema_up / ema_down
    value = 100.0 - 100.0 / (1.0 + relative_strength)
    if not math.isfinite(value):
        raise DataQualityError("VW-RSI calculation produced a non-finite value")
    return value


def _mahalanobis(
    current: npt.NDArray[np.float64],
    mean: npt.NDArray[np.float64],
    inverse_covariance: npt.NDArray[np.float64],
) -> float:
    delta = current - mean
    squared = float(delta.T @ inverse_covariance @ delta)
    return math.sqrt(max(squared, 0.0))


__all__ = ("IMSIEngine", "stabilized_covariance")

from __future__ import annotations

# pyright: reportUnnecessaryIsInstance=false
import math
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime

from systematic_futures.domain.enums import (
    CandidateEventType,
    IAEGapDirection,
    IAEGapState,
    SessionType,
)
from systematic_futures.domain.errors import (
    ContractBoundaryError,
    DataQualityError,
    DataTimingInvariantError,
)
from systematic_futures.domain.serialization import sha256_hex
from systematic_futures.measurement.types import CompletedTradeBar, IAEStateSnapshot

_VERSION = "iae_l1_gap_geometry_v1"
_MAX_GAP_AGE_BARS = 48
_MAX_TOD_SESSIONS = 30
_MIN_TOD_OBSERVATIONS = 20
_EPSILON = 1e-12


@dataclass(frozen=True, slots=True)
class IAERetestObservation:
    """One first-retest description handed to the candidate-event generator."""

    gap_id: str
    event_type: CandidateEventType
    direction: int
    event_time_utc: datetime
    available_at_utc: datetime
    session_id: str


@dataclass(slots=True)
class _Gap:
    gap_id: str
    direction: IAEGapDirection
    created_at_utc: datetime
    session_id: str
    gap_bot: float
    gap_top: float
    gap_width_atr: float | None
    impulse_body_atr: float | None
    displacement_efficiency: float
    age: int = 0
    retest_count: int = 0
    state: IAEGapState = IAEGapState.OPEN


class IAEEngine:
    """Bounded symmetric completed-bar gap and first-retest measurement engine."""

    def __init__(self, root: str, contract_symbol: str, minimum_tick: float) -> None:
        """Create empty contract-local IAE-L1 state.

        Units: native price and one verified minimum tick. Time semantics: completed
        5m bars must arrive chronologically. Missingness: identity and tick size are
        mandatory. Raises: ``DataQualityError`` for invalid configuration.
        """

        if not root.strip() or not contract_symbol.strip():
            raise DataQualityError("IAE identity must be non-blank")
        if not math.isfinite(minimum_tick) or minimum_tick <= 0:
            raise DataQualityError("IAE minimum_tick must be finite and positive")
        self.root = root
        self.contract_symbol = contract_symbol
        self.minimum_tick = minimum_tick
        self._bars: deque[CompletedTradeBar] = deque(maxlen=3)
        self._gaps: list[_Gap] = []
        self._last_bar_end: datetime | None = None
        self._session_id: str | None = None
        self._seasonal: dict[tuple[SessionType, int], deque[tuple[str, float]]] = defaultdict(
            lambda: deque(maxlen=_MAX_TOD_SESSIONS)
        )

    @property
    def active_gap_count(self) -> int:
        """Return the number of open or retested gaps still inside their lifetime."""

        return sum(gap.state in {IAEGapState.OPEN, IAEGapState.RETESTED} for gap in self._gaps)

    def on_bar(
        self,
        bar: CompletedTradeBar,
        local_scale: float | None,
        session_type: SessionType,
        session_start_utc: datetime,
    ) -> tuple[IAEStateSnapshot, tuple[IAERetestObservation, ...]]:
        """Measure one completed 5m bar and emit only first-retest observations.

        Units: gap/body widths use local-range units when available; other geometry is
        dimensionless. Time semantics: the current session is excluded from its own
        time-of-day baseline. Missingness: scale/TOD shortfalls remain ``None`` with
        flags. Raises: boundary, order, or configuration errors.
        """

        self._validate_bar(bar)
        if bar.session_id != self._session_id:
            self._session_id = bar.session_id
            self._bars.clear()
            self._gaps.clear()
        if local_scale is not None and (not math.isfinite(local_scale) or local_scale <= 0):
            raise DataQualityError("IAE local scale must be positive when present")
        if not isinstance(session_type, SessionType):
            raise DataQualityError("session_type must be a SessionType")
        elapsed = bar.start_utc - session_start_utc
        if elapsed.total_seconds() < 0:
            raise DataTimingInvariantError("IAE bar starts before its semantic session")
        slot = int(elapsed.total_seconds() // (5 * 60))
        seasonal_key = (session_type, slot)
        prior_volumes = tuple(
            value
            for session_id, value in self._seasonal[seasonal_key]
            if session_id != bar.session_id
        )[-_MAX_TOD_SESSIONS:]
        volume_z, tod_flag = _prior_volume_z(bar.volume, prior_volumes)
        flags: set[str] = set()
        if tod_flag is not None:
            flags.add(tod_flag)
        retests: list[IAERetestObservation] = []
        selected: _Gap | None = None
        retest_metrics: tuple[float, float, float] | None = None
        for gap in self._gaps:
            if gap.state not in {IAEGapState.OPEN, IAEGapState.RETESTED}:
                continue
            gap.age += 1
            if gap.age > _MAX_GAP_AGE_BARS:
                gap.state = IAEGapState.EXPIRED
                selected = gap
                continue
            invalidated = (
                gap.direction is IAEGapDirection.BULLISH and bar.close < gap.gap_bot
            ) or (gap.direction is IAEGapDirection.BEARISH and bar.close > gap.gap_top)
            if invalidated:
                gap.state = IAEGapState.INVALIDATED
                selected = gap
                continue
            if bar.low <= gap.gap_top and bar.high >= gap.gap_bot:
                gap.retest_count += 1
                gap.state = IAEGapState.RETESTED
                selected = gap
                retest_metrics = _retest_geometry(gap, bar)
                if gap.retest_count == 1:
                    event_type = (
                        CandidateEventType.IAE_RETEST_BULL
                        if gap.direction is IAEGapDirection.BULLISH
                        else CandidateEventType.IAE_RETEST_BEAR
                    )
                    retests.append(
                        IAERetestObservation(
                            gap_id=gap.gap_id,
                            event_type=event_type,
                            direction=1 if gap.direction is IAEGapDirection.BULLISH else -1,
                            event_time_utc=bar.end_utc,
                            available_at_utc=bar.available_at_utc,
                            session_id=bar.session_id,
                        )
                    )
        self._bars.append(bar)
        formed = self._detect_gap(local_scale)
        if formed is not None:
            self._gaps.append(formed)
            selected = formed
            retest_metrics = None
        active = [
            gap for gap in self._gaps if gap.state in {IAEGapState.OPEN, IAEGapState.RETESTED}
        ]
        self._gaps = active
        if selected is None and active:
            selected = active[-1]
        self._seasonal[seasonal_key].append((bar.session_id, bar.volume))
        snapshot = self._snapshot(bar, selected, retest_metrics, volume_z, flags)
        return snapshot, tuple(retests)

    def _detect_gap(self, local_scale: float | None) -> _Gap | None:
        if len(self._bars) < 3:
            return None
        first, impulse, current = self._bars
        geometry = detect_gap_geometry(first, current, self.minimum_tick)
        if geometry is None:
            return None
        direction, gap_bot, gap_top = geometry
        width = gap_top - gap_bot
        body = abs(impulse.close - impulse.open)
        bar_range = impulse.high - impulse.low
        identity = {
            "contract_symbol": self.contract_symbol,
            "created_at_utc": current.end_utc,
            "direction": direction,
            "gap_bot": gap_bot,
            "gap_top": gap_top,
            "root": self.root,
            "version": _VERSION,
        }
        return _Gap(
            gap_id=f"gap_{sha256_hex(identity)}",
            direction=direction,
            created_at_utc=current.end_utc,
            session_id=current.session_id,
            gap_bot=gap_bot,
            gap_top=gap_top,
            gap_width_atr=width / local_scale if local_scale is not None else None,
            impulse_body_atr=body / local_scale if local_scale is not None else None,
            displacement_efficiency=body / max(bar_range, _EPSILON),
        )

    def _snapshot(
        self,
        bar: CompletedTradeBar,
        gap: _Gap | None,
        retest_metrics: tuple[float, float, float] | None,
        volume_z: float | None,
        flags: set[str],
    ) -> IAEStateSnapshot:
        if gap is None:
            values = (None, None, None)
        else:
            values = retest_metrics or (None, None, None)
        retest_depth, wick_ratio, close_position = values
        identity = {
            "as_of_utc": bar.end_utc,
            "contract_symbol": self.contract_symbol,
            "gap_id": gap.gap_id if gap is not None else None,
            "gap_state": gap.state if gap is not None else None,
            "root": self.root,
            "version": _VERSION,
        }
        return IAEStateSnapshot(
            snapshot_id=f"iae_{sha256_hex(identity)}",
            root=self.root,
            contract_symbol=self.contract_symbol,
            as_of_utc=bar.end_utc,
            available_at_utc=bar.available_at_utc,
            gap_id=gap.gap_id if gap is not None else None,
            direction=gap.direction if gap is not None else None,
            gap_state=gap.state if gap is not None else None,
            gap_width_atr=gap.gap_width_atr if gap is not None else None,
            impulse_body_atr=gap.impulse_body_atr if gap is not None else None,
            displacement_efficiency=(gap.displacement_efficiency if gap is not None else None),
            gap_age_bars=gap.age if gap is not None else None,
            retest_depth_ratio=retest_depth,
            wick_absorption_ratio=wick_ratio,
            close_position_ratio=close_position,
            tod_volume_z=volume_z,
            active_gap_count=self.active_gap_count,
            quality_flags=tuple(sorted(flags)),
            version=_VERSION,
        )

    def _validate_bar(self, bar: CompletedTradeBar) -> None:
        if bar.root != self.root or bar.contract_symbol != self.contract_symbol:
            raise ContractBoundaryError("IAE cannot cross actual-contract identity")
        if bar.period_minutes != 5:
            raise DataQualityError("IAE requires completed 5m bars")
        if self._last_bar_end is not None and bar.end_utc <= self._last_bar_end:
            raise DataTimingInvariantError("IAE bars must arrive in increasing end-time order")
        self._last_bar_end = bar.end_utc


def _prior_volume_z(current: float, prior: tuple[float, ...]) -> tuple[float | None, str | None]:
    if len(prior) < _MIN_TOD_OBSERVATIONS:
        return None, "IAE_TOD_WARMUP"
    mean = sum(prior) / len(prior)
    variance = sum((value - mean) ** 2 for value in prior) / len(prior)
    if variance <= 0:
        return None, "IAE_TOD_DEGENERATE"
    return (current - mean) / math.sqrt(variance), None


def detect_gap_geometry(
    first: CompletedTradeBar,
    current: CompletedTradeBar,
    minimum_tick: float,
) -> tuple[IAEGapDirection, float, float] | None:
    """Return exact symmetric structural-gap direction and native-price boundaries.

    Units: native bar price and minimum tick. Time semantics: `first` is t-2 and
    `current` is t; both must be completed same-contract 5m bars. Missingness: no gap
    returns ``None``. Raises: boundary/data errors for incompatible inputs.
    """

    if first.root != current.root or first.contract_symbol != current.contract_symbol:
        raise ContractBoundaryError("gap geometry cannot cross actual contracts")
    if first.session_id != current.session_id:
        raise DataQualityError("gap geometry cannot cross semantic sessions")
    if first.period_minutes != 5 or current.period_minutes != 5:
        raise DataQualityError("gap geometry requires completed 5m bars")
    if not math.isfinite(minimum_tick) or minimum_tick <= 0:
        raise DataQualityError("gap geometry minimum_tick must be positive")
    if current.low > first.high and current.low - first.high >= minimum_tick:
        return IAEGapDirection.BULLISH, first.high, current.low
    if current.high < first.low and first.low - current.high >= minimum_tick:
        return IAEGapDirection.BEARISH, current.high, first.low
    return None


def _retest_geometry(gap: _Gap, bar: CompletedTradeBar) -> tuple[float, float, float]:
    width = gap.gap_top - gap.gap_bot
    overlap = max(0.0, min(bar.high, gap.gap_top) - max(bar.low, gap.gap_bot))
    depth = overlap / width
    body = abs(bar.close - bar.open)
    if gap.direction is IAEGapDirection.BULLISH:
        wick = min(bar.open, bar.close) - bar.low
        close_position = (bar.close - gap.gap_bot) / width
    else:
        wick = bar.high - max(bar.open, bar.close)
        close_position = (gap.gap_top - bar.close) / width
    return depth, wick / max(body, _EPSILON), close_position


__all__ = ("IAEEngine", "IAERetestObservation", "detect_gap_geometry")

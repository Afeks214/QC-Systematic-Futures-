from __future__ import annotations

# pyright: reportUnnecessaryIsInstance=false
import math
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime

from systematic_futures.config.research import MEASUREMENT_CLOCK_POLICY
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
from systematic_futures.measurement.state_models import (
    ATRMeasurement,
    CompletedTradeBar,
    IAEStateSnapshot,
)

_VERSION = "iae_l1_absorption_math_v2"
_MAX_GAP_AGE_BARS = 48
_MAX_TOD_SESSIONS = 30
_MIN_TOD_OBSERVATIONS = 20
_MIN_Z_DISPLACEMENT = 1.5
_MIN_DISPLACEMENT_EFFICIENCY = 0.6
_MIN_Z_GAP = 0.3
_MIN_WICK_ABSORPTION = 0.5
_SCORE_THRESHOLD = 2.1
_TIME_DECAY = 0.05
_VOLUME_Z_FLOOR = 0.1
_WEIGHT_DISPLACEMENT = 0.4
_WEIGHT_GAP = 0.4
_WEIGHT_EFFICIENCY = 0.2
_WEIGHT_WICK = 1.0
_WEIGHT_VOLUME = 1.0
_WEIGHT_CLOSE = 0.5
_EPSILON = 1e-12


@dataclass(frozen=True, slots=True)
class IAERetestObservation:
    """One first-test description handed to the candidate-event generator."""

    gap_id: str
    event_type: CandidateEventType
    direction: int
    event_time_utc: datetime
    available_at_utc: datetime
    session_id: str
    iae_snapshot_id: str


@dataclass(frozen=True, slots=True)
class IAEUpdate:
    """One bar state plus exact per-gap snapshots for every first retest."""

    bar_snapshot: IAEStateSnapshot | None
    retests: tuple[IAERetestObservation, ...]
    retest_snapshots: tuple[IAEStateSnapshot, ...]

    def __post_init__(self) -> None:
        by_id = {snapshot.snapshot_id: snapshot for snapshot in self.retest_snapshots}
        if len(by_id) != len(self.retest_snapshots):
            raise DataQualityError("IAE retest snapshot IDs must be unique")
        referenced_ids = {retest.iae_snapshot_id for retest in self.retests}
        if len(self.retests) != len(self.retest_snapshots) or referenced_ids != set(by_id):
            raise DataQualityError("IAE first retests and exact snapshots must be one-to-one")
        for retest in self.retests:
            snapshot = by_id.get(retest.iae_snapshot_id)
            if snapshot is None or snapshot.gap_id != retest.gap_id:
                raise DataQualityError("IAE retest lineage does not resolve to its exact gap")


@dataclass(slots=True)
class _Gap:
    gap_id: str
    direction: IAEGapDirection
    created_at_utc: datetime
    session_id: str
    gap_bot: float
    gap_top: float
    z_gap: float
    z_displacement: float
    displacement_efficiency: float
    formation_quality: float
    age: int = 0
    retest_count: int = 0
    state: IAEGapState = IAEGapState.OPEN


@dataclass(frozen=True, slots=True)
class _RetestMetrics:
    depth: float
    wick: float | None
    close_position_raw: float
    close_position_score: float
    time_decay: float
    score_raw: float | None
    score_effective: float | None
    guard: str | None


class IAEEngine:
    """Symmetric L1 structural-gap formation, test, and absorption measurement."""

    def __init__(self, root: str, contract_symbol: str, minimum_tick: float) -> None:
        """Create empty contract-local IAE state.

        Units: native prices and a verified minimum tick. Time semantics: completed
        five-minute bars must be strictly chronological. This L1 geometry is a proxy;
        it does not establish hidden order-book state or institutional participation.
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
        """Return open or tested gaps still eligible for later bars."""

        return sum(gap.state in {IAEGapState.OPEN, IAEGapState.TESTED} for gap in self._gaps)

    def on_bar(
        self,
        bar: CompletedTradeBar,
        atr: ATRMeasurement,
        session_type: SessionType,
        session_start_utc: datetime,
    ) -> IAEUpdate:
        """Advance one completed five-minute bar using only prior baseline data.

        Formation requires the exact three-bar structural predicate, a fully warmed
        shared ATR, and all three quality gates. Retest volume is standardized only
        against prior completed sessions at the same semantic slot.
        """

        previous_bar_end = self._last_bar_end
        self._validate_inputs(bar, atr, session_type, session_start_utc)
        continuity_reset = False
        if bar.session_id != self._session_id:
            self._session_id = bar.session_id
            self._bars.clear()
            self._gaps.clear()
        elif previous_bar_end is not None and previous_bar_end != bar.start_utc:
            self._bars.clear()
            self._gaps.clear()
            continuity_reset = True
        elapsed = bar.start_utc - session_start_utc
        slot = int(elapsed.total_seconds() // (MEASUREMENT_CLOCK_POLICY.fast_bar_minutes * 60))
        seasonal_key = (session_type, slot)
        prior_bucket = self._seasonal[seasonal_key]
        if any(session_id == bar.session_id for session_id, _ in prior_bucket):
            raise DataQualityError("IAE TOD bucket already contains the current session")
        prior_volumes = tuple(value for _, value in prior_bucket)[-_MAX_TOD_SESSIONS:]
        volume_z, tod_guard = prior_volume_z(bar.volume, prior_volumes)

        flags: set[str] = set()
        if continuity_reset:
            flags.add("IAE_BAR_GAP_RESET")
        if tod_guard is not None:
            flags.add(tod_guard)
        if not atr.warmup_complete:
            flags.add("IAE_ATR_WARMUP")
        retests: list[IAERetestObservation] = []
        retest_snapshots: list[IAEStateSnapshot] = []
        selected: _Gap | None = None
        selected_metrics: _RetestMetrics | None = None

        for gap in self._gaps:
            if gap.state not in {IAEGapState.OPEN, IAEGapState.TESTED}:
                continue
            gap.age += 1
            if gap.age > _MAX_GAP_AGE_BARS:
                gap.state = IAEGapState.EXPIRED
                selected = gap
                selected_metrics = None
                continue
            invalidated = (
                gap.direction is IAEGapDirection.BULLISH and bar.close < gap.gap_bot
            ) or (gap.direction is IAEGapDirection.BEARISH and bar.close > gap.gap_top)
            if invalidated:
                gap.state = IAEGapState.INVALIDATED
                selected = gap
                selected_metrics = None
                continue
            if not _is_retest(gap, bar):
                continue
            gap.retest_count += 1
            gap.state = IAEGapState.TESTED
            metrics = retest_geometry(gap, bar, volume_z)
            retest_flags = set(flags)
            if metrics.guard is not None:
                flags.add(metrics.guard)
                retest_flags.add(metrics.guard)
            directional_confirmation = (
                gap.direction is IAEGapDirection.BULLISH and bar.close > bar.open
            ) or (gap.direction is IAEGapDirection.BEARISH and bar.close < bar.open)
            if (
                metrics.score_effective is not None
                and metrics.score_effective > _SCORE_THRESHOLD
                and metrics.wick is not None
                and metrics.wick > _MIN_WICK_ABSORPTION
                and directional_confirmation
            ):
                gap.state = IAEGapState.ABSORBED
            selected = gap
            selected_metrics = metrics
            if gap.retest_count == 1:
                retest_snapshot = self._snapshot(
                    bar,
                    gap,
                    metrics,
                    volume_z,
                    retest_flags,
                    normalization_ready=atr.warmup_complete,
                )
                retest_snapshots.append(retest_snapshot)
                retests.append(
                    IAERetestObservation(
                        gap_id=gap.gap_id,
                        event_type=(
                            CandidateEventType.IAE_RETEST_BULL
                            if gap.direction is IAEGapDirection.BULLISH
                            else CandidateEventType.IAE_RETEST_BEAR
                        ),
                        direction=1 if gap.direction is IAEGapDirection.BULLISH else -1,
                        event_time_utc=bar.end_utc,
                        available_at_utc=bar.available_at_utc,
                        session_id=bar.session_id,
                        iae_snapshot_id=retest_snapshot.snapshot_id,
                    )
                )

        self._bars.append(bar)
        formed, formation_guard = self._detect_gap(atr)
        if formation_guard is not None:
            flags.add(formation_guard)
        if formed is not None:
            self._gaps.append(formed)
            if selected is None:
                selected = formed
                selected_metrics = None
        self._gaps = [
            gap for gap in self._gaps if gap.state in {IAEGapState.OPEN, IAEGapState.TESTED}
        ]
        if selected is None and self._gaps:
            selected = self._gaps[-1]
        prior_bucket.append((bar.session_id, bar.volume))
        return IAEUpdate(
            bar_snapshot=self._snapshot(
                bar,
                selected,
                selected_metrics,
                volume_z,
                flags,
                normalization_ready=atr.warmup_complete,
            ),
            retests=tuple(retests),
            retest_snapshots=tuple(retest_snapshots),
        )

    def _detect_gap(self, atr: ATRMeasurement) -> tuple[_Gap | None, str | None]:
        if len(self._bars) < 3 or not atr.warmup_complete or atr.value is None:
            return None, None
        first, impulse, current = self._bars
        geometry = detect_gap_geometry(first, impulse, current, self.minimum_tick)
        if geometry is None:
            return None, None
        direction, gap_bot, gap_top = geometry
        impulse_range = impulse.high - impulse.low
        if impulse_range <= 0:
            return None, "IAE_FORMATION_DEGENERATE"
        body = abs(impulse.close - impulse.open)
        z_displacement = body / (atr.value + _EPSILON)
        z_gap = (gap_top - gap_bot) / (atr.value + _EPSILON)
        efficiency = body / (impulse_range + _EPSILON)
        if not formation_is_eligible(z_displacement, z_gap, efficiency):
            return None, "IAE_FORMATION_GATED"
        quality = formation_quality(z_displacement, z_gap, efficiency)
        identity = {
            "contract_symbol": self.contract_symbol,
            "created_at_utc": current.end_utc,
            "direction": direction,
            "displacement_efficiency": efficiency,
            "formation_quality": quality,
            "gap_bot": gap_bot,
            "gap_top": gap_top,
            "root": self.root,
            "session_id": current.session_id,
            "version": _VERSION,
            "z_displacement": z_displacement,
            "z_gap": z_gap,
        }
        return (
            _Gap(
                gap_id=f"gap_{sha256_hex(identity)}",
                direction=direction,
                created_at_utc=current.end_utc,
                session_id=current.session_id,
                gap_bot=gap_bot,
                gap_top=gap_top,
                z_gap=z_gap,
                z_displacement=z_displacement,
                displacement_efficiency=efficiency,
                formation_quality=quality,
            ),
            None,
        )

    def _snapshot(
        self,
        bar: CompletedTradeBar,
        gap: _Gap | None,
        metrics: _RetestMetrics | None,
        volume_z: float | None,
        flags: set[str],
        *,
        normalization_ready: bool,
    ) -> IAEStateSnapshot:
        volume_score_input = max(volume_z, _VOLUME_Z_FLOOR) if volume_z is not None else None
        active_gap_count = self.active_gap_count
        identity = {
            "active_gap_count": active_gap_count,
            "as_of_utc": bar.end_utc,
            "contract_symbol": self.contract_symbol,
            "gap_id": gap.gap_id if gap is not None else None,
            "gap_state": gap.state if gap is not None else None,
            "quality_flags": tuple(sorted(flags)),
            "root": self.root,
            "session_id": bar.session_id,
            "score_effective": metrics.score_effective if metrics is not None else None,
            "version": _VERSION,
        }
        return IAEStateSnapshot(
            snapshot_id=f"iae_{sha256_hex(identity)}",
            root=self.root,
            contract_symbol=self.contract_symbol,
            session_id=bar.session_id,
            as_of_utc=bar.end_utc,
            available_at_utc=bar.available_at_utc,
            gap_id=gap.gap_id if gap is not None else None,
            direction=gap.direction if gap is not None else None,
            gap_state=gap.state if gap is not None else None,
            gap_width_atr=gap.z_gap if gap is not None else None,
            impulse_body_atr=gap.z_displacement if gap is not None else None,
            displacement_efficiency=(gap.displacement_efficiency if gap is not None else None),
            formation_quality=gap.formation_quality if gap is not None else None,
            gap_age_bars=gap.age if gap is not None else None,
            time_decay=metrics.time_decay if metrics is not None else None,
            retest_depth_ratio=metrics.depth if metrics is not None else None,
            wick_rejection_ratio=metrics.wick if metrics is not None else None,
            close_position_raw=(metrics.close_position_raw if metrics is not None else None),
            close_position_score=(metrics.close_position_score if metrics is not None else None),
            tod_volume_z_raw=volume_z,
            tod_volume_score_input=volume_score_input,
            score_raw=metrics.score_raw if metrics is not None else None,
            score_effective=metrics.score_effective if metrics is not None else None,
            absorption_confirmed=gap is not None and gap.state is IAEGapState.ABSORBED,
            active_gap_count=active_gap_count,
            measurement_ready=gap is not None and normalization_ready,
            quality_flags=tuple(sorted(flags)),
            version=_VERSION,
        )

    def _validate_inputs(
        self,
        bar: CompletedTradeBar,
        atr: ATRMeasurement,
        session_type: SessionType,
        session_start_utc: datetime,
    ) -> None:
        if bar.root != self.root or bar.contract_symbol != self.contract_symbol:
            raise ContractBoundaryError("IAE cannot cross actual-contract identity")
        if bar.period_minutes != MEASUREMENT_CLOCK_POLICY.fast_bar_minutes:
            raise DataQualityError("IAE requires completed fast-clock bars")
        if self._last_bar_end is not None and bar.end_utc <= self._last_bar_end:
            raise DataTimingInvariantError("IAE bars must arrive in increasing end-time order")
        if atr.root != self.root or atr.contract_symbol != self.contract_symbol:
            raise ContractBoundaryError("IAE ATR identity differs")
        if atr.as_of_utc != bar.end_utc or atr.available_at_utc > bar.available_at_utc:
            raise DataTimingInvariantError("IAE ATR clock is not aligned with the bar")
        if not isinstance(session_type, SessionType):
            raise DataQualityError("session_type must be a SessionType")
        if bar.start_utc < session_start_utc:
            raise DataTimingInvariantError("IAE bar starts before its semantic session")
        self._last_bar_end = bar.end_utc


def prior_volume_z(current: float, prior: tuple[float, ...]) -> tuple[float | None, str | None]:
    """Return a prior-only population Z-score for one time-of-day volume slot."""

    if not math.isfinite(current) or current <= 0:
        raise DataQualityError("IAE current volume must be finite and positive")
    if len(prior) < _MIN_TOD_OBSERVATIONS:
        return None, "IAE_TOD_WARMUP"
    if any(not math.isfinite(value) or value <= 0 for value in prior):
        raise DataQualityError("IAE prior TOD volumes must be finite and positive")
    mean = sum(prior) / len(prior)
    variance = sum((value - mean) ** 2 for value in prior) / len(prior)
    if variance <= _EPSILON:
        return None, "IAE_TOD_DEGENERATE"
    return (current - mean) / (math.sqrt(variance) + _EPSILON), None


def formation_quality(z_displacement: float, z_gap: float, efficiency: float) -> float:
    """Return the specified multiplicative formation quality."""

    values = (z_displacement, z_gap, efficiency)
    if any(not math.isfinite(value) or value < 0 for value in values):
        raise DataQualityError("IAE formation inputs must be finite and non-negative")
    return (
        z_displacement**_WEIGHT_DISPLACEMENT * z_gap**_WEIGHT_GAP * efficiency**_WEIGHT_EFFICIENCY
    )


def formation_is_eligible(z_displacement: float, z_gap: float, efficiency: float) -> bool:
    """Return the exact strict formation-gate conjunction."""

    values = (z_displacement, z_gap, efficiency)
    if any(not math.isfinite(value) or value < 0 for value in values):
        raise DataQualityError("IAE formation inputs must be finite and non-negative")
    return (
        z_displacement > _MIN_Z_DISPLACEMENT
        and efficiency > _MIN_DISPLACEMENT_EFFICIENCY
        and z_gap > _MIN_Z_GAP
    )


def absorption_score(
    quality: float,
    wick: float,
    volume_z: float,
    close_position: float,
    age: int,
) -> float:
    """Return the exact full-bracket IAE score after exponential age decay."""

    if any(not math.isfinite(value) for value in (quality, wick, volume_z, close_position)):
        raise DataQualityError("IAE score inputs must be finite")
    if quality < 0 or wick < 0 or close_position < 0:
        raise DataQualityError("IAE quality, wick, and close position must be non-negative")
    if isinstance(age, bool) or not isinstance(age, int) or age < 0:
        raise DataQualityError("IAE score age must be a non-negative integer")
    volume_contribution = max(volume_z, _VOLUME_Z_FLOOR)
    bracket = (
        math.log1p(quality)
        + _WEIGHT_WICK * math.log1p(wick)
        + _WEIGHT_VOLUME * math.log1p(volume_contribution)
        + _WEIGHT_CLOSE * close_position
    )
    score = bracket * math.exp(-_TIME_DECAY * age)
    if not math.isfinite(score):
        raise DataQualityError("IAE score produced a non-finite value")
    return score


def detect_gap_geometry(
    first: CompletedTradeBar,
    impulse: CompletedTradeBar,
    current: CompletedTradeBar,
    minimum_tick: float,
) -> tuple[IAEGapDirection, float, float] | None:
    """Return the exact three-bar bullish predicate or its price-reflected mirror."""

    identities = {
        (bar.root, bar.contract_symbol, bar.session_id) for bar in (first, impulse, current)
    }
    if len({(root, contract) for root, contract, _ in identities}) != 1:
        raise ContractBoundaryError("gap geometry cannot cross actual contracts")
    if len({session for _, _, session in identities}) != 1:
        raise DataQualityError("gap geometry cannot cross semantic sessions")
    if any(
        bar.period_minutes != MEASUREMENT_CLOCK_POLICY.fast_bar_minutes
        for bar in (first, impulse, current)
    ):
        raise DataQualityError("gap geometry requires completed fast-clock bars")
    if first.end_utc != impulse.start_utc or impulse.end_utc != current.start_utc:
        raise DataTimingInvariantError("gap geometry requires three consecutive bars")
    if not math.isfinite(minimum_tick) or minimum_tick <= 0:
        raise DataQualityError("gap geometry minimum_tick must be positive")
    if (
        current.low > first.high
        and impulse.close > first.high
        and current.low - first.high >= minimum_tick
    ):
        return IAEGapDirection.BULLISH, first.high, current.low
    if (
        current.high < first.low
        and impulse.close < first.low
        and first.low - current.high >= minimum_tick
    ):
        return IAEGapDirection.BEARISH, current.high, first.low
    return None


def retest_geometry(
    gap: _Gap,
    bar: CompletedTradeBar,
    volume_z: float | None,
) -> _RetestMetrics:
    """Return exact direction-normalized retest geometry and full-bracket score."""

    width = gap.gap_top - gap.gap_bot
    if width <= 0:
        raise DataQualityError("IAE gap width must be positive")
    overlap = max(0.0, min(bar.high, gap.gap_top) - max(bar.low, gap.gap_bot))
    depth = overlap / width
    body = abs(bar.close - bar.open)
    decay = math.exp(-_TIME_DECAY * gap.age)
    if gap.direction is IAEGapDirection.BULLISH:
        wick_length = min(bar.open, bar.close) - bar.low
        close_position_raw = (bar.close - gap.gap_bot) / (width + _EPSILON)
    else:
        wick_length = bar.high - max(bar.open, bar.close)
        close_position_raw = (gap.gap_top - bar.close) / (width + _EPSILON)
    close_position_score = min(1.0, max(0.0, close_position_raw))
    if body <= 0:
        return _RetestMetrics(
            depth,
            None,
            close_position_raw,
            close_position_score,
            decay,
            None,
            None,
            "IAE_DEGENERATE_BODY",
        )
    wick = wick_length / (body + _EPSILON)
    if volume_z is None:
        return _RetestMetrics(
            depth,
            wick,
            close_position_raw,
            close_position_score,
            decay,
            None,
            None,
            "IAE_SCORE_TOD_UNAVAILABLE",
        )
    score = absorption_score(
        gap.formation_quality,
        wick,
        volume_z,
        close_position_score,
        gap.age,
    )
    return _RetestMetrics(
        depth,
        wick,
        close_position_raw,
        close_position_score,
        decay,
        score,
        score,
        None,
    )


def _is_retest(gap: _Gap, bar: CompletedTradeBar) -> bool:
    if gap.direction is IAEGapDirection.BULLISH:
        return bar.low <= gap.gap_top and bar.close >= gap.gap_bot
    return bar.high >= gap.gap_bot and bar.close <= gap.gap_top


__all__ = (
    "IAEEngine",
    "IAERetestObservation",
    "IAEUpdate",
    "absorption_score",
    "detect_gap_geometry",
    "formation_is_eligible",
    "formation_quality",
    "prior_volume_z",
    "retest_geometry",
)

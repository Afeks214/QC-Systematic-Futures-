from __future__ import annotations

# pyright: reportUnnecessaryIsInstance=false
import math
from collections import Counter, defaultdict, deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from itertools import pairwise

from systematic_futures.config.research import MEASUREMENT_CLOCK_POLICY
from systematic_futures.domain.enums import AuctionLocationState, ProfileKind
from systematic_futures.domain.errors import (
    ContractBoundaryError,
    DataQualityError,
    DataTimingInvariantError,
    SessionBoundaryError,
)
from systematic_futures.domain.serialization import sha256_hex
from systematic_futures.measurement.models import (
    ATRMeasurement,
    AuctionFeatureVector,
    AuctionTransitionMetrics,
    CompletedTradeBar,
    ProfileDefinition,
    TradeObservation,
    VolumeProfileSnapshot,
)
from systematic_futures.measurement.volatility import ATR_5M_24_VERSION

DEFAULT_PROFILE_DEFINITION = ProfileDefinition(
    price_bin_ticks=1,
    value_area_fraction=0.70,
    snapshot_interval_minutes=MEASUREMENT_CLOCK_POLICY.profile_snapshot_minutes,
    rolling_windows_minutes=(30, 60, 120),
    version="volume_profile_math_v2",
)
ATR_NORMALIZATION_VERSION = ATR_5M_24_VERSION


@dataclass(frozen=True, slots=True)
class MinuteVolumeBucket:
    """One completed UTC minute's sorted tick-volume histogram."""

    minute_end_utc: datetime
    volume_by_tick: tuple[tuple[int, float], ...]
    total_volume: float


def price_to_tick(price: float, minimum_tick: float) -> int:
    """Convert positive native price to an integer tick with reconstruction validation.

    Units: ``price`` and ``minimum_tick`` share native price units; output is ticks.
    Time semantics: none. Missingness: no fallback tick size exists. Raises:
    ``DataQualityError`` for non-positive/non-finite values or an off-grid price.
    """

    if not math.isfinite(price) or price <= 0:
        raise DataQualityError("price must be finite and positive")
    if not math.isfinite(minimum_tick) or minimum_tick <= 0:
        raise DataQualityError("minimum_tick must be finite and positive")
    tick = round(price / minimum_tick)
    reconstructed = tick * minimum_tick
    tolerance = max(
        8.0 * math.ulp(price),
        8.0 * math.ulp(reconstructed),
        8.0 * abs(tick) * math.ulp(minimum_tick),
        minimum_tick * 1e-12,
    )
    if abs(reconstructed - price) > tolerance:
        raise DataQualityError("trade price does not reconstruct from the minimum tick")
    return int(tick)


def select_poc(volume_by_tick: Mapping[int, float]) -> int:
    """Select the deterministic POC using volume, weighted-mean distance, then lower tick.

    Units: integer ticks and positive traded quantity. Time semantics: none.
    Missingness: an empty profile is invalid. Raises: ``DataQualityError`` for empty,
    non-integer, non-positive, or non-finite bins.
    """

    histogram = _validated_histogram(volume_by_tick)
    maximum = max(histogram.values())
    candidates = tuple(tick for tick, volume in histogram.items() if volume == maximum)
    total = sum(histogram.values())
    weighted_mean = sum(tick * volume for tick, volume in histogram.items()) / total
    return min(candidates, key=lambda tick: (abs(tick - weighted_mean), tick))


def select_value_area(
    volume_by_tick: Mapping[int, float],
    poc_tick: int,
    fraction: float,
) -> tuple[int, int]:
    """Expand contiguously from POC until the target observed-volume fraction is met.

    Units: ticks and traded quantity; ``fraction`` is dimensionless. Time semantics:
    none. Missing intermediate ticks contribute zero. Missingness: empty histograms or
    absent POC are invalid. Raises: ``DataQualityError`` for invalid inputs.
    """

    histogram = _validated_histogram(volume_by_tick)
    if poc_tick not in histogram:
        raise DataQualityError("poc_tick must be occupied")
    if not math.isfinite(fraction) or not 0 < fraction <= 1:
        raise DataQualityError("value-area fraction must be in (0, 1]")
    target = fraction * sum(histogram.values())
    cumulative = histogram[poc_tick]
    lower = poc_tick
    upper = poc_tick
    minimum = min(histogram)
    maximum = max(histogram)
    while cumulative < target and (lower > minimum or upper < maximum):
        next_lower = lower - 1 if lower > minimum else None
        next_upper = upper + 1 if upper < maximum else None
        lower_volume = histogram.get(next_lower, 0.0) if next_lower is not None else -1.0
        upper_volume = histogram.get(next_upper, 0.0) if next_upper is not None else -1.0
        if next_lower is None:
            if next_upper is None:
                raise DataQualityError("Value Area expansion has no remaining side")
            upper = next_upper
            cumulative += max(upper_volume, 0.0)
        elif next_upper is None:
            lower = next_lower
            cumulative += max(lower_volume, 0.0)
        elif lower_volume == upper_volume:
            lower = next_lower
            upper = next_upper
            cumulative += lower_volume + upper_volume
        elif lower_volume > upper_volume:
            lower = next_lower
            cumulative += lower_volume
        else:
            upper = next_upper
            cumulative += upper_volume
    return lower, upper


class VolumeProfileEngine:
    """Bounded actual-contract Profile accumulator for one semantic session."""

    def __init__(
        self,
        root: str,
        contract_symbol: str,
        session_id: str,
        tick_size: float,
        definition: ProfileDefinition = DEFAULT_PROFILE_DEFINITION,
    ) -> None:
        """Create an empty session-bound profile.

        Units: ``tick_size`` is native price per tick. Time semantics: the first trade
        establishes the first minute; callers finalize elapsed minutes before ingesting
        a later trade. Missingness: identities and tick size are mandatory. Raises:
        ``DataQualityError`` for invalid policy or identity.
        """

        if not root.strip() or not contract_symbol.strip() or not session_id.strip():
            raise DataQualityError("Profile identity fields must be non-blank")
        if not math.isfinite(tick_size) or tick_size <= 0:
            raise DataQualityError("tick_size must be finite and positive")
        if definition != DEFAULT_PROFILE_DEFINITION:
            raise DataQualityError("Lift 2 requires the frozen mathematical Profile definition")
        self.root = root
        self.contract_symbol = contract_symbol
        self.session_id = session_id
        self.tick_size = tick_size
        self.definition = definition
        self._session_histogram: dict[int, float] = defaultdict(float)
        self._minute_histogram: dict[int, float] = defaultdict(float)
        self._minute_end_utc: datetime | None = None
        self._minute_buckets: deque[MinuteVolumeBucket] = deque()
        self._last_trade_time_utc: datetime | None = None
        self._last_available_at_utc: datetime | None = None
        self._last_price_tick: int | None = None
        self._last_finalized_minute_end: datetime | None = None
        self._final_snapshot: VolumeProfileSnapshot | None = None
        self._quality_flags: set[str] = set()
        self._last_rejection_flags: tuple[str, ...] = ()
        self._seen_source_event_ids: set[str] = set()
        self._seen_source_sequences: set[int] = set()
        self.rejection_counts: Counter[str] = Counter()
        self._admitted_volume = 0.0
        self.late_trade_count = 0

    @property
    def minute_bucket_count(self) -> int:
        """Return the bounded count of completed non-empty minute buckets."""

        return len(self._minute_buckets)

    @property
    def last_rejection_flags(self) -> tuple[str, ...]:
        """Return the explicit reasons the immediately preceding trade was rejected."""

        return self._last_rejection_flags

    def ingest_trade(self, trade: TradeObservation) -> bool:
        """Add one on-time actual-contract trade and return whether it was admitted.

        Units and clocks are inherited from ``TradeObservation``. Time semantics:
        callers must finalize due minutes/snapshots first; late data is not backdated
        and returns ``False`` with an explicit quality incident. Missingness: none.
        Raises: contract/session/data-quality errors for boundary contamination.
        """

        self._validate_trade_identity(trade)
        self._last_rejection_flags = ()
        source_flags = {f"DATA:{flag}" for flag in trade.source_quality_flags}
        self._quality_flags.update(source_flags)
        if "SOURCE_SUSPICIOUS" in trade.source_quality_flags:
            return self._reject_trade("DATA:SOURCE_SUSPICIOUS")
        if trade.price <= 0:
            return self._reject_trade("DATA:NON_POSITIVE_PRICE")
        if trade.quantity <= 0:
            return self._reject_trade("DATA:NON_POSITIVE_QUANTITY")
        if (
            trade.source_event_id is not None
            and trade.source_event_id in self._seen_source_event_ids
        ):
            return self._reject_trade("DATA:DUPLICATE_SOURCE_ID")
        if (
            trade.source_sequence is not None
            and trade.source_sequence in self._seen_source_sequences
        ):
            return self._reject_trade("DATA:DUPLICATE_SOURCE_SEQUENCE")
        if trade.source_event_id is None and trade.source_sequence is None:
            self._quality_flags.add("DATA:DEDUPLICATION_UNVERIFIABLE")
        if self._final_snapshot is not None:
            self._quality_flags.add("DATA:LATE_TRADE_AFTER_FINAL_PROFILE")
            self.late_trade_count += 1
            return self._reject_trade("DATA:LATE")
        if (
            self._last_finalized_minute_end is not None
            and trade.exchange_time_utc < self._last_finalized_minute_end
        ):
            self._quality_flags.add("DATA:LATE_TRADE_IGNORED")
            self.late_trade_count += 1
            return self._reject_trade("DATA:LATE")
        if (
            self._last_trade_time_utc is not None
            and trade.exchange_time_utc < self._last_trade_time_utc
        ):
            self._quality_flags.add("DATA:OUT_OF_ORDER_TRADE_IGNORED")
            self.late_trade_count += 1
            return self._reject_trade("DATA:OUT_OF_ORDER")
        try:
            tick = price_to_tick(trade.price, trade.minimum_tick)
        except DataQualityError:
            return self._reject_trade("DATA:OFF_TICK_GRID")
        minute_end = trade.exchange_time_utc.replace(second=0, microsecond=0) + timedelta(minutes=1)
        if self._minute_end_utc is None:
            self._minute_end_utc = minute_end
        elif minute_end != self._minute_end_utc:
            raise DataTimingInvariantError(
                "elapsed minute must be finalized before trade ingestion"
            )
        self._session_histogram[tick] += trade.quantity
        self._minute_histogram[tick] += trade.quantity
        self._admitted_volume += trade.quantity
        self._last_trade_time_utc = trade.exchange_time_utc
        self._last_available_at_utc = trade.available_at_utc
        self._last_price_tick = tick
        if trade.source_event_id is not None:
            self._seen_source_event_ids.add(trade.source_event_id)
        if trade.source_sequence is not None:
            self._seen_source_sequences.add(trade.source_sequence)
        return True

    def _reject_trade(self, *flags: str) -> bool:
        normalized = tuple(sorted(set(flags)))
        self._last_rejection_flags = normalized
        self._quality_flags.update(normalized)
        self.rejection_counts.update(normalized)
        return False

    def finalize_minutes_through(self, as_of_utc: datetime) -> tuple[MinuteVolumeBucket, ...]:
        """Finalize non-empty minute buckets whose end is no later than ``as_of_utc``.

        Units: UTC instant. Time semantics: finalization never rewrites a prior bucket;
        empty elapsed minutes are not fabricated. Missingness: no current minute
        returns an empty tuple. Raises: ``DataTimingInvariantError`` for a backward
        clock.
        """

        if (
            self._last_finalized_minute_end is not None
            and as_of_utc < self._last_finalized_minute_end
        ):
            raise DataTimingInvariantError("minute finalization clock cannot move backward")
        finalized: list[MinuteVolumeBucket] = []
        if self._minute_end_utc is not None and self._minute_end_utc <= as_of_utc:
            pairs = tuple(sorted(self._minute_histogram.items()))
            total = sum(volume for _, volume in pairs)
            bucket = MinuteVolumeBucket(self._minute_end_utc, pairs, total)
            self._minute_buckets.append(bucket)
            finalized.append(bucket)
            self._last_finalized_minute_end = self._minute_end_utc
            self._minute_histogram = defaultdict(float)
            self._minute_end_utc = None
        horizon_start = as_of_utc - timedelta(minutes=max(self.definition.rolling_windows_minutes))
        while self._minute_buckets and self._minute_buckets[0].minute_end_utc <= horizon_start:
            self._minute_buckets.popleft()
        if len(self._minute_buckets) > max(self.definition.rolling_windows_minutes):
            raise DataQualityError("rolling minute profile memory exceeded its bound")
        return tuple(finalized)

    def snapshot(
        self,
        profile_kind: ProfileKind,
        as_of_utc: datetime,
        available_at_utc: datetime,
    ) -> VolumeProfileSnapshot:
        """Build one deterministic developing, final, or rolling Profile snapshot.

        Units: native trade quantity and integer ticks. Time semantics: callers first
        finalize elapsed minutes; only buckets ending by ``as_of_utc`` enter a rolling
        snapshot. Missingness: an empty selected histogram is invalid. Raises:
        ``DataQualityError`` or timing errors for invalid state.
        """

        if as_of_utc > available_at_utc:
            raise DataTimingInvariantError("Profile as-of time must not exceed availability")
        if self._last_trade_time_utc is not None and self._last_trade_time_utc > as_of_utc:
            raise DataTimingInvariantError(
                "Profile snapshot cannot be backdated before admitted data"
            )
        if self._last_price_tick is None:
            raise DataQualityError("cannot snapshot an empty Profile")
        if profile_kind is ProfileKind.FINAL_SESSION and self._final_snapshot is not None:
            return self._final_snapshot
        if profile_kind in {ProfileKind.DEVELOPING_SESSION, ProfileKind.FINAL_SESSION}:
            histogram = dict(self._session_histogram)
            expected_total_volume = self._admitted_volume
        else:
            minutes = _rolling_minutes(profile_kind)
            histogram, expected_total_volume = self._rolling_histogram(minutes, as_of_utc)
        snapshot = build_profile_snapshot(
            root=self.root,
            contract_symbol=self.contract_symbol,
            session_id=self.session_id,
            profile_kind=profile_kind,
            as_of_utc=as_of_utc,
            available_at_utc=available_at_utc,
            definition=self.definition,
            tick_size=self.tick_size,
            current_price_tick=self._last_price_tick,
            volume_by_tick=histogram,
            expected_total_volume=expected_total_volume,
            quality_flags=tuple(sorted(self._quality_flags)),
        )
        if profile_kind is ProfileKind.FINAL_SESSION:
            self._final_snapshot = snapshot
        return snapshot

    def _rolling_histogram(
        self,
        minutes: int,
        as_of_utc: datetime,
    ) -> tuple[dict[int, float], float]:
        start = as_of_utc - timedelta(minutes=minutes)
        histogram: dict[int, float] = defaultdict(float)
        admitted_volume = 0.0
        for bucket in self._minute_buckets:
            if start < bucket.minute_end_utc <= as_of_utc:
                admitted_volume += bucket.total_volume
                for tick, volume in bucket.volume_by_tick:
                    histogram[tick] += volume
        return dict(histogram), admitted_volume

    def _validate_trade_identity(self, trade: TradeObservation) -> None:
        if trade.root != self.root:
            raise ContractBoundaryError("Profile root does not match trade root")
        if trade.contract_symbol != self.contract_symbol:
            raise ContractBoundaryError("Profile cannot mix actual contracts")
        if trade.session_id != self.session_id:
            raise SessionBoundaryError("Profile cannot mix semantic sessions")
        if not math.isclose(trade.minimum_tick, self.tick_size, rel_tol=0, abs_tol=1e-15):
            raise DataQualityError("minimum tick changed inside a Profile")


def build_profile_snapshot(
    *,
    root: str,
    contract_symbol: str,
    session_id: str,
    profile_kind: ProfileKind,
    as_of_utc: datetime,
    available_at_utc: datetime,
    definition: ProfileDefinition,
    tick_size: float,
    current_price_tick: int,
    volume_by_tick: Mapping[int, float],
    expected_total_volume: float,
    quality_flags: tuple[str, ...] = (),
) -> VolumeProfileSnapshot:
    """Create a validated immutable Profile and content-derived identifier.

    Units: integer ticks and traded quantity. Time semantics: as-of cannot exceed
    availability. Missingness: the histogram must be non-empty. Raises:
    ``DataQualityError`` or timing errors for invalid content.
    """

    histogram = _validated_histogram(volume_by_tick)
    histogram_total = sum(histogram.values())
    if not math.isfinite(expected_total_volume) or expected_total_volume <= 0:
        raise DataQualityError("expected_total_volume must be finite and positive")
    if not math.isclose(
        histogram_total,
        expected_total_volume,
        rel_tol=1e-12,
        abs_tol=1e-12,
    ):
        raise DataQualityError("Profile admitted volume does not equal histogram volume")
    poc = select_poc(histogram)
    val, vah = select_value_area(histogram, poc, definition.value_area_fraction)
    pairs = tuple(sorted(histogram.items()))
    identity = {
        "as_of_utc": as_of_utc,
        "available_at_utc": available_at_utc,
        "contract_symbol": contract_symbol,
        "current_price_tick": current_price_tick,
        "definition_version": definition.version,
        "profile_kind": profile_kind,
        "root": root,
        "session_id": session_id,
        "tick_size": tick_size,
        "value_area": (val, vah),
        "volume_by_tick": pairs,
    }
    return VolumeProfileSnapshot(
        snapshot_id=f"profile_{sha256_hex(identity)}",
        root=root,
        contract_symbol=contract_symbol,
        session_id=session_id,
        profile_kind=profile_kind,
        as_of_utc=as_of_utc,
        available_at_utc=available_at_utc,
        definition_version=definition.version,
        tick_size=tick_size,
        total_volume=histogram_total,
        occupied_bins=len(histogram),
        poc_tick=poc,
        vah_tick=vah,
        val_tick=val,
        current_price_tick=current_price_tick,
        volume_by_tick=pairs,
        quality_flags=tuple(sorted(set(quality_flags))),
    )


def auction_location(
    close_price: float,
    minimum_tick: float,
    prior_profile: VolumeProfileSnapshot | None,
) -> AuctionLocationState:
    """Classify a completed close against the prior finalized Value Area.

    Units: native price converted to integer ticks. Time semantics: the reference must
    be supplied causally by the caller. Missingness: no prior profile returns
    ``NO_REFERENCE``. Raises: ``DataQualityError`` for an off-grid close.
    """

    if prior_profile is None:
        return AuctionLocationState.NO_REFERENCE
    close_tick = price_to_tick(close_price, minimum_tick)
    if close_tick > prior_profile.vah_tick:
        return AuctionLocationState.ABOVE_VALUE
    if close_tick < prior_profile.val_tick:
        return AuctionLocationState.BELOW_VALUE
    return AuctionLocationState.INSIDE_VALUE


def auction_features(
    current: VolumeProfileSnapshot,
    prior: VolumeProfileSnapshot | None,
    atr: ATRMeasurement,
    completed_five_minute_bars: Sequence[CompletedTradeBar],
    transitions: AuctionTransitionMetrics,
) -> tuple[AuctionFeatureVector, tuple[str, ...]]:
    """Compute primitive Profile/Auction measurements without a composite score.

    Units: ticks, native-price scale units, elapsed ratios, and dimensionless moments.
    Time semantics: current/prior snapshots and bars must already be causal.
    Missingness: prior/scale-dependent values are ``None``. Raises: identity or data
    errors for incompatible snapshots.
    """

    if prior is not None:
        if prior.root != current.root or prior.contract_symbol != current.contract_symbol:
            raise ContractBoundaryError("prior Profile identity differs from current Profile")
        if not math.isclose(prior.tick_size, current.tick_size, rel_tol=0, abs_tol=1e-15):
            raise DataQualityError("prior Profile tick size differs from current Profile")
        if prior.as_of_utc >= current.as_of_utc:
            raise DataTimingInvariantError("prior Profile must precede current Profile")
    if atr.root != current.root or atr.contract_symbol != current.contract_symbol:
        raise ContractBoundaryError("ATR identity differs from current Profile")
    if atr.as_of_utc != current.as_of_utc or atr.available_at_utc > current.available_at_utc:
        raise DataTimingInvariantError("ATR clock is not aligned with current Profile")
    if transitions.root != current.root or transitions.contract_symbol != current.contract_symbol:
        raise ContractBoundaryError("Auction transition identity differs from current Profile")
    if transitions.session_id != current.session_id:
        raise SessionBoundaryError("Auction transition session differs from current Profile")
    if transitions.as_of_utc != current.as_of_utc:
        raise DataTimingInvariantError("Auction transition clock is not aligned")
    bars = tuple(completed_five_minute_bars)
    for bar in bars:
        if bar.root != current.root or bar.contract_symbol != current.contract_symbol:
            raise ContractBoundaryError("Auction bars cannot cross actual-contract identity")
        if bar.session_id != current.session_id:
            raise SessionBoundaryError("Auction bars cannot cross semantic sessions")
        if bar.period_minutes != MEASUREMENT_CLOCK_POLICY.fast_bar_minutes:
            raise DataQualityError("Auction features require completed fast-clock bars")
        if bar.end_utc > current.as_of_utc or bar.available_at_utc > current.available_at_utc:
            raise DataTimingInvariantError("Auction bar is unavailable at current Profile time")
    if any(left.end_utc >= right.end_utc for left, right in pairwise(bars)):
        raise DataTimingInvariantError("Auction bars must be strictly chronological")
    scale = atr.value if atr.warmup_complete else None
    price_scale = atr.as_price_scale()
    histogram = dict(current.volume_by_tick)
    total = current.total_volume
    above = sum(volume for tick, volume in histogram.items() if tick > current.poc_tick) / total
    entropy, skew, kurtosis, moment_flags = _profile_moments(histogram)
    prior_poc = _scaled_distance(
        current.current_price_tick,
        prior.poc_tick if prior is not None else None,
        scale,
        current.tick_size,
    )
    current_poc = _scaled_distance(
        current.current_price_tick,
        current.poc_tick,
        scale,
        current.tick_size,
    )
    distance_vah = _scaled_distance(
        current.current_price_tick,
        prior.vah_tick if prior is not None else None,
        scale,
        current.tick_size,
    )
    distance_val = _scaled_distance(
        current.current_price_tick,
        prior.val_tick if prior is not None else None,
        scale,
        current.tick_size,
    )
    if prior is None or scale is None:
        width = None
        poc_migration = None
        mid_migration = None
    else:
        width = (current.vah_tick - current.val_tick) * current.tick_size / scale
        poc_migration = (current.poc_tick - prior.poc_tick) * current.tick_size / scale
        current_mid = (current.vah_tick + current.val_tick) / 2
        prior_mid = (prior.vah_tick + prior.val_tick) / 2
        mid_migration = (current_mid - prior_mid) * current.tick_size / scale
    if prior is None:
        volume_outside = None
        bar_close_outside = None
        overlap = None
    else:
        volume_outside = (
            sum(
                volume
                for tick, volume in histogram.items()
                if tick < prior.val_tick or tick > prior.vah_tick
            )
            / total
        )
        eligible = bars
        bar_close_outside = (
            sum(
                price_to_tick(bar.close, current.tick_size) < prior.val_tick
                or price_to_tick(bar.close, current.tick_size) > prior.vah_tick
                for bar in eligible
            )
            / len(eligible)
            if eligible
            else None
        )
        intersection = max(
            0, min(current.vah_tick, prior.vah_tick) - max(current.val_tick, prior.val_tick) + 1
        )
        union = max(current.vah_tick, prior.vah_tick) - min(current.val_tick, prior.val_tick) + 1
        overlap = intersection / union
    vector = AuctionFeatureVector(
        distance_to_current_poc_ticks=float(current.current_price_tick - current.poc_tick),
        distance_to_current_poc_vol=current_poc,
        distance_to_prior_poc_vol=prior_poc,
        distance_to_vah_vol=distance_vah,
        distance_to_val_vol=distance_val,
        value_area_width_vol=width,
        poc_migration_vol=poc_migration,
        value_mid_migration_vol=mid_migration,
        volume_above_poc_ratio=above,
        volume_outside_value_ratio=volume_outside,
        bar_close_outside_value_ratio=bar_close_outside,
        profile_entropy=entropy,
        profile_skew=skew,
        profile_kurtosis=kurtosis,
        profile_overlap_ratio=overlap,
        reentry_count=transitions.reentry_count,
        consecutive_minutes_outside=transitions.consecutive_minutes_outside,
        local_price_scale=price_scale,
    )
    return vector, moment_flags


def _validated_histogram(volume_by_tick: Mapping[int, float]) -> dict[int, float]:
    if not volume_by_tick:
        raise DataQualityError("Volume Profile histogram must not be empty")
    histogram: dict[int, float] = {}
    for tick, volume in volume_by_tick.items():
        if isinstance(tick, bool) or not isinstance(tick, int):
            raise DataQualityError("Volume Profile keys must be integer ticks")
        if not math.isfinite(volume) or volume <= 0:
            raise DataQualityError("Volume Profile bins must contain positive finite volume")
        histogram[tick] = float(volume)
    return histogram


def _rolling_minutes(profile_kind: ProfileKind) -> int:
    mapping = {
        ProfileKind.ROLLING_30M: 30,
        ProfileKind.ROLLING_60M: 60,
        ProfileKind.ROLLING_120M: 120,
    }
    try:
        return mapping[profile_kind]
    except KeyError as error:
        raise DataQualityError(f"{profile_kind.value} is not a rolling Profile") from error


def _scaled_distance(
    current_tick: int,
    reference_tick: int | None,
    scale: float | None,
    tick_size: float,
) -> float | None:
    if reference_tick is None or scale is None:
        return None
    return (current_tick - reference_tick) * tick_size / scale


def _profile_moments(
    histogram: Mapping[int, float],
) -> tuple[float, float | None, float | None, tuple[str, ...]]:
    total = sum(histogram.values())
    probabilities = tuple(volume / total for volume in histogram.values())
    entropy = (
        0.0
        if len(probabilities) == 1
        else -sum(value * math.log(value) for value in probabilities) / math.log(len(probabilities))
    )
    mean = sum(tick * volume for tick, volume in histogram.items()) / total
    variance = sum(volume * (tick - mean) ** 2 for tick, volume in histogram.items()) / total
    if variance == 0:
        return entropy, None, None, ("DEGENERATE_PROFILE",)
    deviation = math.sqrt(variance)
    skew = (
        sum(volume * ((tick - mean) / deviation) ** 3 for tick, volume in histogram.items()) / total
    )
    # Weighted Pearson kurtosis: a Gaussian reference has value 3, not zero.
    kurtosis = (
        sum(volume * ((tick - mean) / deviation) ** 4 for tick, volume in histogram.items()) / total
    )
    return entropy, skew, kurtosis, ()


__all__ = (
    "ATR_NORMALIZATION_VERSION",
    "DEFAULT_PROFILE_DEFINITION",
    "MinuteVolumeBucket",
    "VolumeProfileEngine",
    "auction_features",
    "auction_location",
    "build_profile_snapshot",
    "price_to_tick",
    "select_poc",
    "select_value_area",
)

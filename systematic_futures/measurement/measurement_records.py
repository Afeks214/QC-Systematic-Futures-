"""Immutable Lift 2 measurement records and validation invariants."""

# pyright: reportUnnecessaryIsInstance=false
import math
from dataclasses import dataclass
from datetime import datetime, timedelta

from systematic_futures.config.research import MEASUREMENT_CLOCK_POLICY
from systematic_futures.domain.enums import (
    ProfileKind,
    RollState,
)
from systematic_futures.domain.errors import (
    DataQualityError,
    DataTimingInvariantError,
    TimeSemanticsError,
)


def _require_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise DataQualityError(f"{field_name} must be a non-blank string")


def _require_utc(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise TimeSemanticsError(f"{field_name} must be timezone-aware")
    if value.utcoffset() != timedelta(0):
        raise TimeSemanticsError(f"{field_name} must be normalized to UTC")


def _require_finite(value: float, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise DataQualityError(f"{field_name} must be a finite number")


def _require_positive(value: float, field_name: str) -> None:
    _require_finite(value, field_name)
    if value <= 0:
        raise DataQualityError(f"{field_name} must be positive")


def _require_optional_finite(value: float | None, field_name: str) -> None:
    if value is not None:
        _require_finite(value, field_name)


def _require_flags(flags: tuple[str, ...]) -> None:
    if not isinstance(flags, tuple):
        raise DataQualityError("quality_flags must be a tuple")
    if flags != tuple(sorted(set(flags))):
        raise DataQualityError("quality_flags must be sorted and unique")
    for flag in flags:
        _require_text(flag, "quality_flag")


def _require_snapshot_clock(as_of_utc: datetime, available_at_utc: datetime) -> None:
    _require_utc(as_of_utc, "as_of_utc")
    _require_utc(available_at_utc, "available_at_utc")
    if as_of_utc > available_at_utc:
        raise DataTimingInvariantError("as_of_utc must not exceed available_at_utc")


@dataclass(frozen=True, slots=True)
class TradeObservation:
    """One raw actual-contract trade plus source provenance metadata."""

    root: str
    contract_symbol: str
    exchange_time_utc: datetime
    available_at_utc: datetime
    price: float
    quantity: float
    minimum_tick: float
    session_id: str
    roll_state: RollState
    source_event_id: str | None = None
    source_sequence: int | None = None
    trade_condition: str | None = None
    source_quality_flags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.root, "root")
        _require_text(self.contract_symbol, "contract_symbol")
        _require_text(self.session_id, "session_id")
        _require_utc(self.exchange_time_utc, "exchange_time_utc")
        _require_utc(self.available_at_utc, "available_at_utc")
        if self.exchange_time_utc > self.available_at_utc:
            raise DataTimingInvariantError("exchange_time_utc must not exceed available_at_utc")
        _require_finite(self.price, "price")
        _require_finite(self.quantity, "quantity")
        _require_positive(self.minimum_tick, "minimum_tick")
        if not isinstance(self.roll_state, RollState):
            raise DataQualityError("roll_state must be a RollState")
        for field_name, value in (
            ("source_event_id", self.source_event_id),
            ("trade_condition", self.trade_condition),
        ):
            if value is not None:
                _require_text(value, field_name)
        if self.source_sequence is not None and (
            isinstance(self.source_sequence, bool)
            or not isinstance(self.source_sequence, int)
            or self.source_sequence < 0
        ):
            raise DataQualityError("source_sequence must be a non-negative integer")
        _require_flags(self.source_quality_flags)


@dataclass(frozen=True, slots=True)
class CompletedTradeBar:
    """One completed actual-contract bar; prices are native and volume is traded quantity."""

    root: str
    contract_symbol: str
    period_minutes: int
    start_utc: datetime
    end_utc: datetime
    available_at_utc: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    session_id: str

    def __post_init__(self) -> None:
        _require_text(self.root, "root")
        _require_text(self.contract_symbol, "contract_symbol")
        _require_text(self.session_id, "session_id")
        if (
            isinstance(self.period_minutes, bool)
            or not isinstance(self.period_minutes, int)
            or self.period_minutes <= 0
        ):
            raise DataQualityError("period_minutes must be a positive integer")
        for field_name, value in (
            ("start_utc", self.start_utc),
            ("end_utc", self.end_utc),
            ("available_at_utc", self.available_at_utc),
        ):
            _require_utc(value, field_name)
        if not self.start_utc < self.end_utc <= self.available_at_utc:
            raise DataTimingInvariantError("bar clocks must satisfy start < end <= available")
        if self.end_utc - self.start_utc != timedelta(minutes=self.period_minutes):
            raise DataTimingInvariantError("completed bar duration must equal period_minutes")
        for field_name, value in (
            ("open", self.open),
            ("high", self.high),
            ("low", self.low),
            ("close", self.close),
        ):
            _require_positive(value, field_name)
        _require_positive(self.volume, "volume")
        if self.low > self.high or not self.low <= self.open <= self.high:
            raise DataQualityError("bar open/high/low are inconsistent")
        if not self.low <= self.close <= self.high:
            raise DataQualityError("bar close/high/low are inconsistent")


@dataclass(frozen=True, slots=True)
class ProfileDefinition:
    """Frozen Volume Profile representation parameters."""

    price_bin_ticks: int
    value_area_fraction: float
    snapshot_interval_minutes: int
    rolling_windows_minutes: tuple[int, ...]
    version: str

    def __post_init__(self) -> None:
        if self.price_bin_ticks <= 0:
            raise DataQualityError("price_bin_ticks must be positive")
        _require_finite(self.value_area_fraction, "value_area_fraction")
        if not 0 < self.value_area_fraction <= 1:
            raise DataQualityError("value_area_fraction must be in (0, 1]")
        if self.snapshot_interval_minutes <= 0:
            raise DataQualityError("snapshot_interval_minutes must be positive")
        if not self.rolling_windows_minutes or any(
            value <= 0 for value in self.rolling_windows_minutes
        ):
            raise DataQualityError("rolling_windows_minutes must contain positive values")
        if self.rolling_windows_minutes != tuple(sorted(set(self.rolling_windows_minutes))):
            raise DataQualityError("rolling_windows_minutes must be sorted and unique")
        _require_text(self.version, "version")


@dataclass(frozen=True, slots=True)
class VolumeProfileSnapshot:
    """Immutable sorted integer-tick Volume Profile snapshot."""

    snapshot_id: str
    root: str
    contract_symbol: str
    session_id: str
    profile_kind: ProfileKind
    as_of_utc: datetime
    available_at_utc: datetime
    definition_version: str
    tick_size: float
    total_volume: float
    occupied_bins: int
    poc_tick: int
    vah_tick: int
    val_tick: int
    current_price_tick: int
    volume_by_tick: tuple[tuple[int, float], ...]
    quality_flags: tuple[str, ...]

    def __post_init__(self) -> None:
        for field_name, value in (
            ("snapshot_id", self.snapshot_id),
            ("root", self.root),
            ("contract_symbol", self.contract_symbol),
            ("session_id", self.session_id),
            ("definition_version", self.definition_version),
        ):
            _require_text(value, field_name)
        if not isinstance(self.profile_kind, ProfileKind):
            raise DataQualityError("profile_kind must be a ProfileKind")
        _require_snapshot_clock(self.as_of_utc, self.available_at_utc)
        _require_positive(self.tick_size, "tick_size")
        _require_positive(self.total_volume, "total_volume")
        if self.occupied_bins <= 0 or self.occupied_bins != len(self.volume_by_tick):
            raise DataQualityError("occupied_bins must equal positive histogram size")
        ticks = tuple(tick for tick, _ in self.volume_by_tick)
        if ticks != tuple(sorted(set(ticks))):
            raise DataQualityError("volume_by_tick must be sorted with unique integer ticks")
        for tick, volume in self.volume_by_tick:
            if isinstance(tick, bool) or not isinstance(tick, int):
                raise DataQualityError("profile tick keys must be integers")
            _require_positive(volume, "bin volume")
        if not math.isclose(
            sum(volume for _, volume in self.volume_by_tick),
            self.total_volume,
            rel_tol=1e-12,
            abs_tol=1e-12,
        ):
            raise DataQualityError("profile volume is not conserved")
        if self.poc_tick not in set(ticks):
            raise DataQualityError("poc_tick must be occupied")
        if not self.val_tick <= self.poc_tick <= self.vah_tick:
            raise DataQualityError("Value Area must contain POC")
        _require_flags(self.quality_flags)


@dataclass(frozen=True, slots=True)
class AuctionFeatureVector:
    """Descriptive Auction measurements with explicit optional normalization."""

    distance_to_current_poc_ticks: float
    distance_to_current_poc_vol: float | None
    distance_to_prior_poc_vol: float | None
    distance_to_vah_vol: float | None
    distance_to_val_vol: float | None
    value_area_width_vol: float | None
    poc_migration_vol: float | None
    value_mid_migration_vol: float | None
    volume_above_poc_ratio: float
    volume_outside_value_ratio: float | None
    bar_close_outside_value_ratio: float | None
    profile_entropy: float
    profile_skew: float | None
    profile_kurtosis: float | None
    profile_overlap_ratio: float | None
    reentry_count: int
    consecutive_minutes_outside: int
    local_price_scale: "PriceScale"

    def __post_init__(self) -> None:
        for field_name, value in (
            ("distance_to_current_poc_ticks", self.distance_to_current_poc_ticks),
            ("volume_above_poc_ratio", self.volume_above_poc_ratio),
            ("profile_entropy", self.profile_entropy),
        ):
            _require_finite(value, field_name)
        for field_name, value in (
            ("distance_to_prior_poc_vol", self.distance_to_prior_poc_vol),
            ("distance_to_current_poc_vol", self.distance_to_current_poc_vol),
            ("distance_to_vah_vol", self.distance_to_vah_vol),
            ("distance_to_val_vol", self.distance_to_val_vol),
            ("value_area_width_vol", self.value_area_width_vol),
            ("poc_migration_vol", self.poc_migration_vol),
            ("value_mid_migration_vol", self.value_mid_migration_vol),
            ("volume_outside_value_ratio", self.volume_outside_value_ratio),
            ("bar_close_outside_value_ratio", self.bar_close_outside_value_ratio),
            ("profile_skew", self.profile_skew),
            ("profile_kurtosis", self.profile_kurtosis),
            ("profile_overlap_ratio", self.profile_overlap_ratio),
        ):
            _require_optional_finite(value, field_name)
        for field_name, value in (
            ("volume_above_poc_ratio", self.volume_above_poc_ratio),
            ("volume_outside_value_ratio", self.volume_outside_value_ratio),
            ("bar_close_outside_value_ratio", self.bar_close_outside_value_ratio),
            ("profile_overlap_ratio", self.profile_overlap_ratio),
        ):
            if value is not None and not 0 <= value <= 1:
                raise DataQualityError(f"{field_name} must be in [0, 1]")
        if not 0 <= self.profile_entropy <= 1:
            raise DataQualityError("profile_entropy must be in [0, 1]")
        if self.reentry_count < 0 or self.consecutive_minutes_outside < 0:
            raise DataQualityError("Auction counts must be non-negative")
        if not isinstance(self.local_price_scale, PriceScale):
            raise DataQualityError("local_price_scale must be a PriceScale")

    @property
    def atr_5m_24(self) -> float | None:
        """Return the explicitly versioned local range value, if fully warmed."""

        return self.local_price_scale.value


@dataclass(frozen=True, slots=True)
class AuctionTransitionMetrics:
    """State-machine-derived Auction counters for one completed five-minute bar."""

    root: str
    contract_symbol: str
    session_id: str
    as_of_utc: datetime
    reentry_count: int
    consecutive_outside_bars: int
    version: str

    def __post_init__(self) -> None:
        for field_name, value in (
            ("root", self.root),
            ("contract_symbol", self.contract_symbol),
            ("session_id", self.session_id),
            ("version", self.version),
        ):
            _require_text(value, field_name)
        _require_utc(self.as_of_utc, "as_of_utc")
        if self.reentry_count < 0 or self.consecutive_outside_bars < 0:
            raise DataQualityError("Auction transition counters must be non-negative")

    @property
    def consecutive_minutes_outside(self) -> int:
        """Return exact elapsed minutes from completed fast-clock bars."""

        return self.consecutive_outside_bars * MEASUREMENT_CLOCK_POLICY.fast_bar_minutes


@dataclass(frozen=True, slots=True)
class PriceScale:
    """Auditable local price scale with warmup and version lineage."""

    value: float | None
    observation_count: int
    warmup_complete: bool
    version: str

    def __post_init__(self) -> None:
        _require_optional_finite(self.value, "value")
        if self.value is not None and self.value <= 0:
            raise DataQualityError("PriceScale value must be positive when present")
        if not 0 <= self.observation_count <= 24:
            raise DataQualityError("PriceScale observation_count must be in [0, 24]")
        if self.warmup_complete != (self.observation_count == 24 and self.value is not None):
            raise DataQualityError("PriceScale warmup state disagrees with count/value")
        _require_text(self.version, "version")


@dataclass(frozen=True, slots=True)
class ProfileReferenceSet:
    """Typed point-in-time references used by one Auction snapshot."""

    prior_same_session_type_id: str | None
    prior_rth_id: str | None
    prior_eth_id: str | None
    rolling_30m_id: str | None
    rolling_60m_id: str | None
    rolling_120m_id: str | None

    def __post_init__(self) -> None:
        for field_name, value in (
            ("prior_same_session_type_id", self.prior_same_session_type_id),
            ("prior_rth_id", self.prior_rth_id),
            ("prior_eth_id", self.prior_eth_id),
            ("rolling_30m_id", self.rolling_30m_id),
            ("rolling_60m_id", self.rolling_60m_id),
            ("rolling_120m_id", self.rolling_120m_id),
        ):
            if value is not None:
                _require_text(value, field_name)


@dataclass(frozen=True, slots=True)
class ATRMeasurement:
    """Contract-local arithmetic mean of the last 24 completed five-minute true ranges."""

    root: str
    contract_symbol: str
    as_of_utc: datetime
    available_at_utc: datetime
    value: float | None
    observation_count: int
    warmup_complete: bool
    version: str

    def __post_init__(self) -> None:
        for field_name, value in (
            ("root", self.root),
            ("contract_symbol", self.contract_symbol),
            ("version", self.version),
        ):
            _require_text(value, field_name)
        _require_snapshot_clock(self.as_of_utc, self.available_at_utc)
        _require_optional_finite(self.value, "value")
        if self.value is not None and self.value <= 0:
            raise DataQualityError("ATR value must be positive when present")
        if not 0 <= self.observation_count <= 24:
            raise DataQualityError("ATR observation_count must be in [0, 24]")
        if self.warmup_complete != (self.observation_count == 24 and self.value is not None):
            raise DataQualityError("ATR warmup state disagrees with count/value")

    def as_price_scale(self) -> PriceScale:
        """Return the immutable local-range representation used by Auction and ICM."""

        return PriceScale(
            value=self.value,
            observation_count=self.observation_count,
            warmup_complete=self.warmup_complete,
            version=self.version,
        )


__all__ = (
    "ATRMeasurement",
    "AuctionFeatureVector",
    "AuctionTransitionMetrics",
    "CompletedTradeBar",
    "PriceScale",
    "ProfileDefinition",
    "ProfileReferenceSet",
    "TradeObservation",
    "VolumeProfileSnapshot",
)

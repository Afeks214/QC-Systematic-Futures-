from __future__ import annotations

# pyright: reportUnnecessaryIsInstance=false
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from systematic_futures.domain.enums import (
    AuctionLocationState,
    CandidateEventType,
    IAEGapDirection,
    IAEGapState,
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
    """One positive actual-contract trade in native price and quantity units."""

    root: str
    contract_symbol: str
    exchange_time_utc: datetime
    available_at_utc: datetime
    price: float
    quantity: float
    minimum_tick: float
    session_id: str
    roll_state: RollState

    def __post_init__(self) -> None:
        _require_text(self.root, "root")
        _require_text(self.contract_symbol, "contract_symbol")
        _require_text(self.session_id, "session_id")
        _require_utc(self.exchange_time_utc, "exchange_time_utc")
        _require_utc(self.available_at_utc, "available_at_utc")
        if self.exchange_time_utc > self.available_at_utc:
            raise DataTimingInvariantError("exchange_time_utc must not exceed available_at_utc")
        _require_positive(self.price, "price")
        _require_positive(self.quantity, "quantity")
        _require_positive(self.minimum_tick, "minimum_tick")
        if not isinstance(self.roll_state, RollState):
            raise DataQualityError("roll_state must be a RollState")


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
        if self.period_minutes not in {5, 30}:
            raise DataQualityError("period_minutes must be 5 or 30")
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
    distance_to_prior_poc_vol: float | None
    distance_to_vah_vol: float | None
    distance_to_val_vol: float | None
    value_area_width_vol: float | None
    poc_migration_vol: float | None
    value_mid_migration_vol: float | None
    volume_above_poc_ratio: float
    volume_outside_value_ratio: float | None
    time_outside_value_ratio: float | None
    profile_entropy: float
    profile_skew: float | None
    profile_kurtosis: float | None
    profile_overlap_ratio: float | None
    reentry_count: int
    consecutive_minutes_outside: int
    atr_5m_24: float | None
    normalization_version: str

    def __post_init__(self) -> None:
        for field_name, value in (
            ("distance_to_current_poc_ticks", self.distance_to_current_poc_ticks),
            ("volume_above_poc_ratio", self.volume_above_poc_ratio),
            ("profile_entropy", self.profile_entropy),
        ):
            _require_finite(value, field_name)
        for field_name, value in (
            ("distance_to_prior_poc_vol", self.distance_to_prior_poc_vol),
            ("distance_to_vah_vol", self.distance_to_vah_vol),
            ("distance_to_val_vol", self.distance_to_val_vol),
            ("value_area_width_vol", self.value_area_width_vol),
            ("poc_migration_vol", self.poc_migration_vol),
            ("value_mid_migration_vol", self.value_mid_migration_vol),
            ("volume_outside_value_ratio", self.volume_outside_value_ratio),
            ("time_outside_value_ratio", self.time_outside_value_ratio),
            ("profile_skew", self.profile_skew),
            ("profile_kurtosis", self.profile_kurtosis),
            ("profile_overlap_ratio", self.profile_overlap_ratio),
            ("atr_5m_24", self.atr_5m_24),
        ):
            _require_optional_finite(value, field_name)
        for field_name, value in (
            ("volume_above_poc_ratio", self.volume_above_poc_ratio),
            ("volume_outside_value_ratio", self.volume_outside_value_ratio),
            ("time_outside_value_ratio", self.time_outside_value_ratio),
            ("profile_overlap_ratio", self.profile_overlap_ratio),
        ):
            if value is not None and not 0 <= value <= 1:
                raise DataQualityError(f"{field_name} must be in [0, 1]")
        if not 0 <= self.profile_entropy <= 1:
            raise DataQualityError("profile_entropy must be in [0, 1]")
        if self.reentry_count < 0 or self.consecutive_minutes_outside < 0:
            raise DataQualityError("Auction counts must be non-negative")
        if self.atr_5m_24 is not None and self.atr_5m_24 <= 0:
            raise DataQualityError("atr_5m_24 must be positive when present")
        _require_text(self.normalization_version, "normalization_version")


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
        """Return exact elapsed minutes from completed five-minute bars."""

        return self.consecutive_outside_bars * 5


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


@dataclass(frozen=True, slots=True)
class AuctionStateSnapshot:
    """Point-in-time Auction location and primitive measurements."""

    snapshot_id: str
    root: str
    contract_symbol: str
    session_id: str
    as_of_utc: datetime
    available_at_utc: datetime
    location_state: AuctionLocationState
    developing_profile_id: str
    prior_profile_id: str | None
    features: AuctionFeatureVector
    active_excursion_id: str | None
    quality_flags: tuple[str, ...]
    feature_version: str

    def __post_init__(self) -> None:
        for field_name, value in (
            ("snapshot_id", self.snapshot_id),
            ("root", self.root),
            ("contract_symbol", self.contract_symbol),
            ("session_id", self.session_id),
            ("developing_profile_id", self.developing_profile_id),
            ("feature_version", self.feature_version),
        ):
            _require_text(value, field_name)
        _require_snapshot_clock(self.as_of_utc, self.available_at_utc)
        if not isinstance(self.location_state, AuctionLocationState):
            raise DataQualityError("location_state must be an AuctionLocationState")
        for field_name, value in (
            ("prior_profile_id", self.prior_profile_id),
            ("active_excursion_id", self.active_excursion_id),
        ):
            if value is not None:
                _require_text(value, field_name)
        _require_flags(self.quality_flags)


@dataclass(frozen=True, slots=True)
class IMSIStateSnapshot:
    """Prior-only momentum and two-dimensional state geometry."""

    snapshot_id: str
    root: str
    contract_symbol: str
    as_of_utc: datetime
    available_at_utc: datetime
    vwrsi_raw: float
    vwrsi_tod_adjusted: float | None
    session_vwap: float
    dist_vwap_pct: float
    mahalanobis_distance: float | None
    state_rarity_percentile: float | None
    neighbor_distance_mean: float | None
    neighbor_distance_p90: float | None
    neighbor_support: int
    covariance_shrinkage_delta: float | None
    covariance_effective_sample_size: float | None
    covariance_condition_number: float | None
    warmup_complete: bool
    quality_flags: tuple[str, ...]
    version: str

    def __post_init__(self) -> None:
        _validate_indicator_identity(self)
        _require_finite(self.vwrsi_raw, "vwrsi_raw")
        if not 0 <= self.vwrsi_raw <= 100:
            raise DataQualityError("vwrsi_raw must be in [0, 100]")
        _require_positive(self.session_vwap, "session_vwap")
        _require_finite(self.dist_vwap_pct, "dist_vwap_pct")
        for field_name, value in (
            ("vwrsi_tod_adjusted", self.vwrsi_tod_adjusted),
            ("mahalanobis_distance", self.mahalanobis_distance),
            ("state_rarity_percentile", self.state_rarity_percentile),
            ("neighbor_distance_mean", self.neighbor_distance_mean),
            ("neighbor_distance_p90", self.neighbor_distance_p90),
            ("covariance_shrinkage_delta", self.covariance_shrinkage_delta),
            ("covariance_effective_sample_size", self.covariance_effective_sample_size),
            ("covariance_condition_number", self.covariance_condition_number),
        ):
            _require_optional_finite(value, field_name)
        if self.state_rarity_percentile is not None and not 0 <= self.state_rarity_percentile <= 1:
            raise DataQualityError("state_rarity_percentile must be in [0, 1]")
        if (
            self.covariance_shrinkage_delta is not None
            and not 0 <= self.covariance_shrinkage_delta <= 1
        ):
            raise DataQualityError("covariance_shrinkage_delta must be in [0, 1]")
        if (
            self.covariance_effective_sample_size is not None
            and self.covariance_effective_sample_size <= 0
        ):
            raise DataQualityError("covariance_effective_sample_size must be positive")
        covariance_diagnostics = (
            self.covariance_shrinkage_delta,
            self.covariance_effective_sample_size,
            self.covariance_condition_number,
        )
        if any(value is None for value in covariance_diagnostics) and not all(
            value is None for value in covariance_diagnostics
        ):
            raise DataQualityError("IMSI covariance diagnostics must be jointly present or absent")
        neighbor_metrics = (self.neighbor_distance_mean, self.neighbor_distance_p90)
        if (self.neighbor_support == 0) != all(value is None for value in neighbor_metrics):
            raise DataQualityError("IMSI neighbor metrics must agree with neighbor_support")
        if self.mahalanobis_distance is not None and all(
            value is None for value in covariance_diagnostics
        ):
            raise DataQualityError("IMSI distance requires covariance diagnostics")
        if self.warmup_complete != (
            self.mahalanobis_distance is not None and self.state_rarity_percentile is not None
        ):
            raise DataQualityError("IMSI warmup_complete disagrees with distance and rarity")
        if not 0 <= self.neighbor_support <= 15:
            raise DataQualityError("neighbor_support must be in [0, 15]")
        _require_flags(self.quality_flags)


@dataclass(frozen=True, slots=True)
class ICMStateSnapshot:
    """Causal quadratic price-geometry measurement over one contract window."""

    snapshot_id: str
    root: str
    contract_symbol: str
    as_of_utc: datetime
    available_at_utc: datetime
    fair_value: float
    z_raw: float | None
    z_capped: float | None
    z_effective: float | None
    slope_per_bar: float
    slope_normalized: float | None
    curvature_per_bar2: float
    curvature_normalized: float | None
    sigma_ols: float
    sigma_mad: float
    sigma_blend: float
    r_ratio: float
    window_size: int
    warmup_complete: bool
    quality_flags: tuple[str, ...]
    version: str

    def __post_init__(self) -> None:
        _validate_indicator_identity(self)
        for field_name, value in (
            ("fair_value", self.fair_value),
            ("slope_per_bar", self.slope_per_bar),
            ("curvature_per_bar2", self.curvature_per_bar2),
            ("sigma_ols", self.sigma_ols),
            ("sigma_mad", self.sigma_mad),
            ("sigma_blend", self.sigma_blend),
            ("r_ratio", self.r_ratio),
        ):
            _require_finite(value, field_name)
        for field_name, value in (
            ("z_raw", self.z_raw),
            ("z_capped", self.z_capped),
            ("z_effective", self.z_effective),
            ("slope_normalized", self.slope_normalized),
            ("curvature_normalized", self.curvature_normalized),
        ):
            _require_optional_finite(value, field_name)
        if self.sigma_ols < 0 or self.sigma_mad < 0 or self.sigma_blend < 0:
            raise DataQualityError("ICM residual scales must be non-negative")
        if (self.z_raw is None) != (self.z_capped is None):
            raise DataQualityError("ICM raw and capped Z must be jointly present or absent")
        if self.z_capped is not None and not -4.5 <= self.z_capped <= 4.5:
            raise DataQualityError("ICM capped Z must be in [-4.5, 4.5]")
        if self.z_effective is not None and self.z_capped != self.z_effective:
            raise DataQualityError("ICM effective Z must equal capped Z when unguarded")
        normalized = (self.slope_normalized, self.curvature_normalized)
        if (self.sigma_blend > 0) != all(value is not None for value in normalized):
            raise DataQualityError("ICM normalized geometry disagrees with residual scale")
        if self.window_size <= 3:
            raise DataQualityError("window_size must exceed three")
        _require_flags(self.quality_flags)


@dataclass(frozen=True, slots=True)
class IAEStateSnapshot:
    """Symmetric structural gap/retest geometry with no order-book inference."""

    snapshot_id: str
    root: str
    contract_symbol: str
    as_of_utc: datetime
    available_at_utc: datetime
    gap_id: str | None
    direction: IAEGapDirection | None
    gap_state: IAEGapState | None
    gap_width_atr: float | None
    impulse_body_atr: float | None
    displacement_efficiency: float | None
    formation_quality: float | None
    gap_age_bars: int | None
    time_decay: float | None
    retest_depth_ratio: float | None
    wick_absorption_ratio: float | None
    close_position_ratio: float | None
    tod_volume_z: float | None
    score_raw: float | None
    score_effective: float | None
    absorption_confirmed: bool
    active_gap_count: int
    quality_flags: tuple[str, ...]
    version: str

    def __post_init__(self) -> None:
        _validate_indicator_identity(self)
        if self.gap_id is not None:
            _require_text(self.gap_id, "gap_id")
        if (self.direction is None) != (self.gap_state is None):
            raise DataQualityError("IAE direction and state must be jointly present or absent")
        for field_name, value in (
            ("gap_width_atr", self.gap_width_atr),
            ("impulse_body_atr", self.impulse_body_atr),
            ("displacement_efficiency", self.displacement_efficiency),
            ("formation_quality", self.formation_quality),
            ("time_decay", self.time_decay),
            ("retest_depth_ratio", self.retest_depth_ratio),
            ("wick_absorption_ratio", self.wick_absorption_ratio),
            ("close_position_ratio", self.close_position_ratio),
            ("tod_volume_z", self.tod_volume_z),
            ("score_raw", self.score_raw),
            ("score_effective", self.score_effective),
        ):
            _require_optional_finite(value, field_name)
        if self.gap_age_bars is not None and self.gap_age_bars < 0:
            raise DataQualityError("gap_age_bars must be non-negative")
        if self.active_gap_count < 0:
            raise DataQualityError("active_gap_count must be non-negative")
        if self.time_decay is not None and not 0 < self.time_decay <= 1:
            raise DataQualityError("time_decay must be in (0, 1]")
        if self.score_effective is not None and self.score_raw != self.score_effective:
            raise DataQualityError("effective IAE score must equal raw score when unguarded")
        if self.absorption_confirmed != (self.gap_state is IAEGapState.ABSORBED):
            raise DataQualityError("IAE absorption flag disagrees with gap state")
        _require_flags(self.quality_flags)


@dataclass(frozen=True, slots=True)
class IndicatorSynergySnapshot:
    """As-of references to available measurements; no score or vote is calculated."""

    snapshot_id: str
    root: str
    contract_symbol: str
    as_of_utc: datetime
    available_at_utc: datetime
    auction_snapshot_id: str
    imsi_snapshot_id: str | None
    icm_snapshot_id: str | None
    iae_snapshot_id: str | None
    all_required_inputs_available: bool
    quality_flags: tuple[str, ...]
    version: str

    def __post_init__(self) -> None:
        _validate_indicator_identity(self)
        _require_text(self.auction_snapshot_id, "auction_snapshot_id")
        for field_name, value in (
            ("imsi_snapshot_id", self.imsi_snapshot_id),
            ("icm_snapshot_id", self.icm_snapshot_id),
            ("iae_snapshot_id", self.iae_snapshot_id),
        ):
            if value is not None:
                _require_text(value, field_name)
        expected = all(
            value is not None
            for value in (self.imsi_snapshot_id, self.icm_snapshot_id, self.iae_snapshot_id)
        )
        if self.all_required_inputs_available is not expected:
            raise DataQualityError("all_required_inputs_available disagrees with references")
        _require_flags(self.quality_flags)


@dataclass(frozen=True, slots=True)
class CandidateEventObservation:
    """Immutable descriptive research event recorded before any outcome exists."""

    event_id: str
    parent_event_id: str | None
    event_type: CandidateEventType
    root: str
    contract_symbol: str
    event_time_utc: datetime
    available_at_utc: datetime
    session_id: str
    direction: int
    auction_snapshot_id: str
    synergy_snapshot_id: str
    data_snapshot_hash: str
    feature_version: str
    quality_flags: tuple[str, ...]

    def __post_init__(self) -> None:
        for field_name, value in (
            ("event_id", self.event_id),
            ("root", self.root),
            ("contract_symbol", self.contract_symbol),
            ("session_id", self.session_id),
            ("auction_snapshot_id", self.auction_snapshot_id),
            ("synergy_snapshot_id", self.synergy_snapshot_id),
            ("data_snapshot_hash", self.data_snapshot_hash),
            ("feature_version", self.feature_version),
        ):
            _require_text(value, field_name)
        if self.parent_event_id is not None:
            _require_text(self.parent_event_id, "parent_event_id")
        if not isinstance(self.event_type, CandidateEventType):
            raise DataQualityError("event_type must be a CandidateEventType")
        _require_utc(self.event_time_utc, "event_time_utc")
        _require_utc(self.available_at_utc, "available_at_utc")
        if self.event_time_utc > self.available_at_utc:
            raise DataTimingInvariantError("event_time_utc must not exceed available_at_utc")
        if self.direction not in {-1, 1}:
            raise DataQualityError("direction must be +1 or -1")
        _require_flags(self.quality_flags)


class _IndicatorIdentity(Protocol):
    @property
    def snapshot_id(self) -> str: ...

    @property
    def root(self) -> str: ...

    @property
    def contract_symbol(self) -> str: ...

    @property
    def version(self) -> str: ...

    @property
    def as_of_utc(self) -> datetime: ...

    @property
    def available_at_utc(self) -> datetime: ...


def _validate_indicator_identity(snapshot: _IndicatorIdentity) -> None:
    for field_name, value in (
        ("snapshot_id", snapshot.snapshot_id),
        ("root", snapshot.root),
        ("contract_symbol", snapshot.contract_symbol),
        ("version", snapshot.version),
    ):
        _require_text(value, field_name)
    _require_snapshot_clock(snapshot.as_of_utc, snapshot.available_at_utc)


__all__ = (
    "ATRMeasurement",
    "AuctionFeatureVector",
    "AuctionStateSnapshot",
    "AuctionTransitionMetrics",
    "CandidateEventObservation",
    "CompletedTradeBar",
    "IAEStateSnapshot",
    "ICMStateSnapshot",
    "IMSIStateSnapshot",
    "IndicatorSynergySnapshot",
    "ProfileDefinition",
    "TradeObservation",
    "VolumeProfileSnapshot",
)

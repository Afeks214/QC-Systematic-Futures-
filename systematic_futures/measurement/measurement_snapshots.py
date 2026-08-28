"""Immutable Lift 2 state snapshots and candidate-event records."""

# pyright: reportPrivateUsage=false, reportUnnecessaryIsInstance=false
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from systematic_futures.domain.enums import (
    AuctionLocationState,
    CandidateEventType,
    IAEGapDirection,
    IAEGapState,
)
from systematic_futures.domain.errors import DataQualityError, DataTimingInvariantError
from systematic_futures.measurement.measurement_records import (
    AuctionFeatureVector,
    CandidateResearchReadiness,
    ProfileReferenceSet,
    _require_finite,
    _require_flags,
    _require_optional_finite,
    _require_positive,
    _require_snapshot_clock,
    _require_text,
    _require_utc,
)


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
    references: ProfileReferenceSet
    migration_reference_profile_id: str | None
    features: AuctionFeatureVector
    active_excursion_id: str | None
    measurement_ready: bool
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
        if not isinstance(self.references, ProfileReferenceSet):
            raise DataQualityError("references must be a ProfileReferenceSet")
        for field_name, value in (
            ("migration_reference_profile_id", self.migration_reference_profile_id),
            ("active_excursion_id", self.active_excursion_id),
        ):
            if value is not None:
                _require_text(value, field_name)
        if self.migration_reference_profile_id != self.references.prior_same_session_type_id:
            raise DataQualityError(
                "Auction migration reference must be the prior same-session type"
            )
        has_reference = self.references.prior_same_session_type_id is not None
        if (self.location_state is AuctionLocationState.NO_REFERENCE) == has_reference:
            raise DataQualityError("Auction location state disagrees with its reference profile")
        if self.measurement_ready and not (
            has_reference and self.features.local_price_scale.warmup_complete
        ):
            raise DataQualityError("ready Auction requires a reference and warmed local scale")
        _require_flags(self.quality_flags)


@dataclass(frozen=True, slots=True)
class IMSIStateSnapshot:
    """Prior-only momentum and two-dimensional state geometry."""

    snapshot_id: str
    root: str
    contract_symbol: str
    session_id: str
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
    measurement_ready: bool
    quality_flags: tuple[str, ...]
    version: str

    def __post_init__(self) -> None:
        _validate_indicator_identity(self)
        _require_text(self.session_id, "session_id")
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
        if self.measurement_ready != self.warmup_complete:
            raise DataQualityError("IMSI measurement_ready disagrees with StateCore warmup")
        if not 0 <= self.neighbor_support <= 15:
            raise DataQualityError("neighbor_support must be in [0, 15]")
        _require_flags(self.quality_flags)


@dataclass(frozen=True, slots=True)
class ICMStateSnapshot:
    """Causal quadratic price-geometry measurement over one contract window."""

    snapshot_id: str
    root: str
    contract_symbol: str
    session_id: str
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
    fair_value_distance_vol: float | None
    residual_autocorrelation: float | None
    window_size: int
    warmup_complete: bool
    measurement_ready: bool
    quality_flags: tuple[str, ...]
    version: str

    def __post_init__(self) -> None:
        _validate_indicator_identity(self)
        _require_text(self.session_id, "session_id")
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
            ("fair_value_distance_vol", self.fair_value_distance_vol),
            ("residual_autocorrelation", self.residual_autocorrelation),
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
        if (
            self.residual_autocorrelation is not None
            and not -1 <= self.residual_autocorrelation <= 1
        ):
            raise DataQualityError("residual_autocorrelation must be in [-1, 1]")
        if self.measurement_ready != (self.z_effective is not None):
            raise DataQualityError("ICM measurement_ready disagrees with effective Z")
        _require_flags(self.quality_flags)


@dataclass(frozen=True, slots=True)
class IAEStateSnapshot:
    """Symmetric structural gap/retest geometry with no order-book inference."""

    snapshot_id: str
    root: str
    contract_symbol: str
    session_id: str
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
    wick_rejection_ratio: float | None
    close_position_raw: float | None
    close_position_score: float | None
    tod_volume_z_raw: float | None
    tod_volume_score_input: float | None
    score_raw: float | None
    score_effective: float | None
    absorption_confirmed: bool
    active_gap_count: int
    measurement_ready: bool
    score_ready: bool
    quality_flags: tuple[str, ...]
    version: str

    def __post_init__(self) -> None:
        _validate_indicator_identity(self)
        _require_text(self.session_id, "session_id")
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
            ("wick_rejection_ratio", self.wick_rejection_ratio),
            ("close_position_raw", self.close_position_raw),
            ("close_position_score", self.close_position_score),
            ("tod_volume_z_raw", self.tod_volume_z_raw),
            ("tod_volume_score_input", self.tod_volume_score_input),
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
        if self.close_position_score is not None and not 0 <= self.close_position_score <= 1:
            raise DataQualityError("close_position_score must be in [0, 1]")
        if self.tod_volume_score_input is not None and self.tod_volume_score_input < 0:
            raise DataQualityError("tod_volume_score_input must be non-negative")
        if self.score_effective is not None and self.score_raw != self.score_effective:
            raise DataQualityError("effective IAE score must equal raw score when unguarded")
        if self.absorption_confirmed != (self.gap_state is IAEGapState.ABSORBED):
            raise DataQualityError("IAE absorption flag disagrees with gap state")
        if self.measurement_ready and self.gap_id is None:
            raise DataQualityError("IAE measurement_ready requires a gap state")
        expected_score_ready = (
            self.measurement_ready
            and self.retest_depth_ratio is not None
            and self.wick_rejection_ratio is not None
            and self.tod_volume_z_raw is not None
            and self.score_effective is not None
        )
        if self.score_ready is not expected_score_ready:
            raise DataQualityError("IAE score_ready disagrees with exact score inputs")
        _require_flags(self.quality_flags)


@dataclass(frozen=True, slots=True)
class IndicatorSynergySnapshot:
    """As-of references to available measurements; no score or vote is calculated."""

    snapshot_id: str
    root: str
    contract_symbol: str
    session_id: str
    as_of_utc: datetime
    available_at_utc: datetime
    auction_snapshot_id: str
    imsi_snapshot_id: str | None
    icm_snapshot_id: str | None
    iae_snapshot_id: str | None
    all_required_inputs_present: bool
    all_required_inputs_fresh: bool
    all_required_inputs_ready: bool
    imsi_ready: bool
    icm_ready: bool
    iae_structural_ready: bool
    iae_score_ready: bool
    component_quality_flags: tuple[str, ...]
    blocking_quality_flags: tuple[str, ...]
    quality_flags: tuple[str, ...]
    version: str

    def __post_init__(self) -> None:
        _validate_indicator_identity(self)
        _require_text(self.session_id, "session_id")
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
        if self.all_required_inputs_present is not expected:
            raise DataQualityError("all_required_inputs_present disagrees with references")
        if self.all_required_inputs_ready and not (
            self.all_required_inputs_present and self.all_required_inputs_fresh
        ):
            raise DataQualityError("ready synergy inputs must also be present and fresh")
        if self.all_required_inputs_ready and not (
            self.imsi_ready and self.icm_ready and self.iae_structural_ready
        ):
            raise DataQualityError("ready synergy disagrees with component readiness")
        if self.iae_score_ready and not self.iae_structural_ready:
            raise DataQualityError("IAE score readiness requires structural readiness")
        _require_flags(self.component_quality_flags)
        _require_flags(self.blocking_quality_flags)
        if self.quality_flags != tuple(
            sorted(set(self.component_quality_flags) | set(self.blocking_quality_flags))
        ):
            raise DataQualityError("synergy quality_flags must be the complete quality union")
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
    readiness: CandidateResearchReadiness
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
        if not isinstance(self.readiness, CandidateResearchReadiness):
            raise DataQualityError("readiness must be CandidateResearchReadiness")
        _require_flags(self.quality_flags)

    @property
    def research_ready(self) -> bool:
        """Return backward-compatible base-event eligibility without duplicate state."""

        return self.readiness.base_event_ready


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
    "AuctionStateSnapshot",
    "CandidateEventObservation",
    "IAEStateSnapshot",
    "ICMStateSnapshot",
    "IMSIStateSnapshot",
    "IndicatorSynergySnapshot",
)

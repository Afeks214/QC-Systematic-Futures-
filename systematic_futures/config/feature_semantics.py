from __future__ import annotations

from collections.abc import Sequence

from systematic_futures.domain.errors import DataQualityError
from systematic_futures.domain.research_contracts import (
    FeatureImplementationStatus,
    FeatureSemantic,
    validate_feature_semantic,
)

_NOT_IMPLEMENTED = FeatureImplementationStatus.NOT_IMPLEMENTED
_RESEARCH_MEASUREMENT = FeatureImplementationStatus.RESEARCH_MEASUREMENT
_PROFILE_PIT = "Use only observations available at the snapshot time from one actual contract."
_MISSING_WITHHOLD = "Withhold the feature; never coerce missing input to zero."

_FEATURES_V1 = (
    FeatureSemantic(
        feature_name="acceptance_score",
        human_definition="Future composite evidence that participation is forming new value.",
        unit="dimensionless_score",
        normalization_family="component_preserving_composite",
        source_family="auction_profile",
        point_in_time_requirement=_PROFILE_PIT,
        missingness_policy=_MISSING_WITHHOLD,
        implementation_status=_NOT_IMPLEMENTED,
    ),
    FeatureSemantic(
        feature_name="distance_to_current_poc_ticks",
        human_definition="Future signed price distance from the current point of control.",
        unit="raw_ticks",
        normalization_family="raw_ticks",
        source_family="auction_profile",
        point_in_time_requirement=_PROFILE_PIT,
        missingness_policy=_MISSING_WITHHOLD,
        implementation_status=_NOT_IMPLEMENTED,
    ),
    FeatureSemantic(
        feature_name="distance_to_vah_vol",
        human_definition="Future signed price distance from value-area high in volatility units.",
        unit="volatility_units",
        normalization_family="realized_volatility_units",
        source_family="auction_profile",
        point_in_time_requirement=_PROFILE_PIT,
        missingness_policy=_MISSING_WITHHOLD,
        implementation_status=_NOT_IMPLEMENTED,
    ),
    FeatureSemantic(
        feature_name="distance_to_val_vol",
        human_definition="Future signed price distance from value-area low in volatility units.",
        unit="volatility_units",
        normalization_family="realized_volatility_units",
        source_family="auction_profile",
        point_in_time_requirement=_PROFILE_PIT,
        missingness_policy=_MISSING_WITHHOLD,
        implementation_status=_NOT_IMPLEMENTED,
    ),
    FeatureSemantic(
        feature_name="expected_shortfall_fraction_nav",
        human_definition="Future expected-shortfall exposure expressed as a fraction of NAV.",
        unit="fraction_of_nav",
        normalization_family="risk_nav_units",
        source_family="future_risk_contract",
        point_in_time_requirement="Use only risk inputs available at the declared snapshot time.",
        missingness_policy=_MISSING_WITHHOLD,
        implementation_status=_NOT_IMPLEMENTED,
    ),
    FeatureSemantic(
        feature_name="poc_migration_vol",
        human_definition="Future point-of-control migration relative to an explicit prior window.",
        unit="volatility_units",
        normalization_family="realized_volatility_units",
        source_family="auction_profile",
        point_in_time_requirement=_PROFILE_PIT,
        missingness_policy=_MISSING_WITHHOLD,
        implementation_status=_NOT_IMPLEMENTED,
    ),
    FeatureSemantic(
        feature_name="profile_entropy",
        human_definition="Future normalized entropy of the observed volume-at-price distribution.",
        unit="dimensionless_ratio",
        normalization_family="normalized_distribution",
        source_family="auction_profile",
        point_in_time_requirement=_PROFILE_PIT,
        missingness_policy=_MISSING_WITHHOLD,
        implementation_status=_NOT_IMPLEMENTED,
    ),
    FeatureSemantic(
        feature_name="rejection_score",
        human_definition="Future composite evidence of excursion failure and value re-entry.",
        unit="dimensionless_score",
        normalization_family="component_preserving_composite",
        source_family="auction_profile",
        point_in_time_requirement=_PROFILE_PIT,
        missingness_policy=_MISSING_WITHHOLD,
        implementation_status=_NOT_IMPLEMENTED,
    ),
    FeatureSemantic(
        feature_name="return_h",
        human_definition="Future horizon-explicit price return using completed observations.",
        unit="decimal_return",
        normalization_family="returns",
        source_family="market_state",
        point_in_time_requirement="Both price observations must be usable by the snapshot time.",
        missingness_policy=_MISSING_WITHHOLD,
        implementation_status=_NOT_IMPLEMENTED,
    ),
    FeatureSemantic(
        feature_name="time_outside_value_ratio",
        human_definition="Future elapsed eligible time outside an explicit value area ratio.",
        unit="session_normalized_ratio",
        normalization_family="session_normalized_ratios",
        source_family="auction_profile",
        point_in_time_requirement=_PROFILE_PIT,
        missingness_policy=_MISSING_WITHHOLD,
        implementation_status=_NOT_IMPLEMENTED,
    ),
    FeatureSemantic(
        feature_name="value_area_width_vol",
        human_definition="Future value-area width expressed in volatility units.",
        unit="volatility_units",
        normalization_family="realized_volatility_units",
        source_family="auction_profile",
        point_in_time_requirement=_PROFILE_PIT,
        missingness_policy=_MISSING_WITHHOLD,
        implementation_status=_NOT_IMPLEMENTED,
    ),
    FeatureSemantic(
        feature_name="volatility_percentile",
        human_definition="Future point-in-time rolling percentile of realized volatility.",
        unit="percentile_0_1",
        normalization_family="rolling_percentiles",
        source_family="market_state",
        point_in_time_requirement="Rank only against history usable before the snapshot time.",
        missingness_policy=_MISSING_WITHHOLD,
        implementation_status=_NOT_IMPLEMENTED,
    ),
    FeatureSemantic(
        feature_name="volume_outside_value_ratio",
        human_definition="Future observed volume outside value divided by eligible elapsed volume.",
        unit="session_normalized_ratio",
        normalization_family="session_normalized_ratios",
        source_family="auction_profile",
        point_in_time_requirement=_PROFILE_PIT,
        missingness_policy=_MISSING_WITHHOLD,
        implementation_status=_NOT_IMPLEMENTED,
    ),
)

_REQUIRED_NAMES = frozenset(
    {
        "acceptance_score",
        "distance_to_vah_vol",
        "distance_to_val_vol",
        "poc_migration_vol",
        "profile_entropy",
        "rejection_score",
        "time_outside_value_ratio",
        "value_area_width_vol",
        "volume_outside_value_ratio",
    }
)
_REQUIRED_NORMALIZATION_FAMILIES = frozenset(
    {
        "raw_ticks",
        "realized_volatility_units",
        "session_normalized_ratios",
        "rolling_percentiles",
        "returns",
        "risk_nav_units",
    }
)

_MEASUREMENT_VOCABULARY: dict[str, tuple[str, str, str]] = {
    "consecutive_minutes_outside": ("minutes", "elapsed_session", "auction_profile"),
    "distance_to_current_poc_ticks": ("raw_ticks", "raw_ticks", "auction_profile"),
    "distance_to_prior_poc_vol": ("local_range_units", "local_price_scale", "auction_profile"),
    "distance_to_vah_vol": ("local_range_units", "local_price_scale", "auction_profile"),
    "distance_to_val_vol": ("local_range_units", "local_price_scale", "auction_profile"),
    "iae_close_position_ratio": ("dimensionless_ratio", "gap_geometry", "iae_l1"),
    "iae_displacement_efficiency": ("dimensionless_ratio", "bar_geometry", "iae_l1"),
    "iae_gap_age_bars": ("completed_5m_bars", "elapsed_bars", "iae_l1"),
    "iae_gap_width_atr": ("local_range_units", "local_price_scale", "iae_l1"),
    "iae_impulse_body_atr": ("local_range_units", "local_price_scale", "iae_l1"),
    "iae_retest_depth_ratio": ("dimensionless_ratio", "gap_geometry", "iae_l1"),
    "iae_tod_volume_z": ("z_score", "prior_session_slot", "iae_l1"),
    "iae_wick_absorption_ratio": ("dimensionless_ratio", "bar_geometry", "iae_l1"),
    "icm_curvature_norm": ("residual_scale_units", "quadratic_residual_scale", "icm"),
    "icm_fair_value": ("native_price", "quadratic_window", "icm"),
    "icm_r_ratio": ("dimensionless_ratio", "residual_scale_ratio", "icm"),
    "icm_sigma_blend": ("native_price", "quadratic_residual_scale", "icm"),
    "icm_sigma_mad": ("native_price", "quadratic_residual_scale", "icm"),
    "icm_sigma_ols": ("native_price", "quadratic_residual_scale", "icm"),
    "icm_slope_norm": ("residual_scale_units", "quadratic_residual_scale", "icm"),
    "icm_z_score": ("z_score", "quadratic_residual_scale", "icm"),
    "imsi_dist_vwap_pct": ("decimal_ratio", "session_vwap", "imsi"),
    "imsi_mahalanobis_distance": ("distance", "prior_state_covariance", "imsi"),
    "imsi_neighbor_distance_mean": ("distance", "prior_state_covariance", "imsi"),
    "imsi_neighbor_distance_p90": ("distance", "prior_state_covariance", "imsi"),
    "imsi_neighbor_support": ("count", "prior_state_count", "imsi"),
    "imsi_state_rarity_percentile": ("percentile_0_1", "prior_distance_rank", "imsi"),
    "imsi_vwrsi_raw": ("oscillator_0_100", "volume_weighted_rsi", "imsi"),
    "imsi_vwrsi_tod_adjusted": ("oscillator_points", "prior_session_slot", "imsi"),
    "poc_migration_vol": ("local_range_units", "local_price_scale", "auction_profile"),
    "profile_entropy": ("dimensionless_ratio", "normalized_distribution", "auction_profile"),
    "profile_kurtosis": ("standardized_moment", "volume_weighted_moment", "auction_profile"),
    "profile_overlap_ratio": ("dimensionless_ratio", "value_area_overlap", "auction_profile"),
    "profile_skew": ("standardized_moment", "volume_weighted_moment", "auction_profile"),
    "reentry_count": ("count", "elapsed_session", "auction_profile"),
    "time_outside_value_ratio": ("session_normalized_ratio", "elapsed_session", "auction_profile"),
    "value_area_width_vol": ("local_range_units", "local_price_scale", "auction_profile"),
    "value_mid_migration_vol": ("local_range_units", "local_price_scale", "auction_profile"),
    "volume_above_poc_ratio": ("dimensionless_ratio", "elapsed_volume", "auction_profile"),
    "volume_outside_value_ratio": ("session_normalized_ratio", "elapsed_volume", "auction_profile"),
}

_UNIMPLEMENTED_V2_NAMES = frozenset(
    {
        "acceptance_score",
        "expected_shortfall_fraction_nav",
        "rejection_score",
        "return_h",
        "volatility_percentile",
    }
)


def _measurement_feature(name: str, metadata: tuple[str, str, str]) -> FeatureSemantic:
    unit, normalization_family, source_family = metadata
    return FeatureSemantic(
        feature_name=name,
        human_definition=f"Lift 2 point-in-time descriptive measurement: {name}.",
        unit=unit,
        normalization_family=normalization_family,
        source_family=source_family,
        point_in_time_requirement=(
            "Use only completed observations whose availability is no later than the snapshot."
        ),
        missingness_policy=_MISSING_WITHHOLD,
        implementation_status=_RESEARCH_MEASUREMENT,
    )


_FEATURES_V2 = tuple(
    sorted(
        (
            *(
                feature
                for feature in _FEATURES_V1
                if feature.feature_name in _UNIMPLEMENTED_V2_NAMES
            ),
            *(
                _measurement_feature(name, metadata)
                for name, metadata in _MEASUREMENT_VOCABULARY.items()
            ),
        ),
        key=lambda feature: feature.feature_name,
    )
)


def validate_feature_semantics_registry(features: Sequence[FeatureSemantic]) -> tuple[str, ...]:
    """Validate the frozen semantic names and unit families without calculating features.

    Units: required families cover ticks, volatility, session ratios, percentiles, returns, and
    risk/NAV representations. Time semantics: each entry declares a non-blank point-in-time rule.
    Missingness: each entry declares withholding explicitly. Raises: ``DataQualityError`` for a
    duplicate, unsorted, missing, or implemented feature. Returns the validated feature names.
    """

    records = tuple(features)
    if not records:
        raise DataQualityError("feature semantics registry must not be empty")
    for feature in records:
        validate_feature_semantic(feature)
    names = tuple(feature.feature_name for feature in records)
    if names != tuple(sorted(set(names))):
        raise DataQualityError("feature semantics must be sorted and uniquely named")
    if not _REQUIRED_NAMES.issubset(names):
        raise DataQualityError("feature semantics registry is missing required Lift 2 vocabulary")
    families = {feature.normalization_family for feature in records}
    if not _REQUIRED_NORMALIZATION_FAMILIES.issubset(families):
        raise DataQualityError("feature semantics registry is missing required unit families")
    return names


def feature_semantics_v1() -> tuple[FeatureSemantic, ...]:
    """Return version 1 of the immutable, entirely unimplemented feature vocabulary.

    Units: encoded per metadata entry; no unit conversion occurs. Time semantics: entries define
    future availability requirements but consume no data. Missingness: entries require explicit
    withholding. Raises: ``DataQualityError`` if the static registry violates its contract.
    """

    validate_feature_semantics_registry(_FEATURES_V1)
    return _FEATURES_V1


def feature_semantics_v2() -> tuple[FeatureSemantic, ...]:
    """Return the Lift 2 measurement registry without mutating version 1.

    Units and normalization are declared per entry. Time semantics: measurement
    entries require point-in-time completed inputs. Missingness: unavailable values
    are withheld rather than coerced. Raises: ``DataQualityError`` for a duplicate,
    missing, or incorrectly classified vocabulary entry.
    """

    names = tuple(feature.feature_name for feature in _FEATURES_V2)
    if names != tuple(sorted(set(names))):
        raise DataQualityError("Lift 2 feature semantics must be sorted and unique")
    measured = {
        feature.feature_name
        for feature in _FEATURES_V2
        if feature.implementation_status is _RESEARCH_MEASUREMENT
    }
    if measured != set(_MEASUREMENT_VOCABULARY):
        raise DataQualityError("Lift 2 measured vocabulary is incomplete")
    unimplemented = {
        feature.feature_name
        for feature in _FEATURES_V2
        if feature.implementation_status is _NOT_IMPLEMENTED
    }
    if unimplemented != set(_UNIMPLEMENTED_V2_NAMES):
        raise DataQualityError("Lift 2 unimplemented vocabulary changed")
    for feature in _FEATURES_V2:
        validate_feature_semantic(feature)
    return _FEATURES_V2


__all__ = (
    "feature_semantics_v1",
    "feature_semantics_v2",
    "validate_feature_semantics_registry",
)

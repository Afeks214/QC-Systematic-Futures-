from __future__ import annotations

from collections.abc import Sequence

from systematic_futures.domain.errors import DataQualityError
from systematic_futures.domain.research_contracts import (
    FeatureImplementationStatus,
    FeatureSemantic,
    validate_feature_semantic,
)

_NOT_IMPLEMENTED = FeatureImplementationStatus.NOT_IMPLEMENTED
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


__all__ = ("feature_semantics_v1", "validate_feature_semantics_registry")

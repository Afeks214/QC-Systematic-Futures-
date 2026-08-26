from __future__ import annotations

# pyright: reportUnnecessaryIsInstance=false
from collections.abc import Sequence
from dataclasses import dataclass

from systematic_futures.domain.enums import DatasetCertificationStatus
from systematic_futures.domain.errors import DataQualityError

CONTINUOUS_BACKWARDS_RATIO_ID = "continuous_backwards_ratio_series"
BLS_DATASET_ID = "bls_macro_releases"
US_TREASURY_YIELD_CURVE_ID = "us_treasury_yield_curve"
FRED_DATASET_ID = "fred_macro_series"
ECONOMIC_EVENTS_ID = "economic_events_calendar"


@dataclass(frozen=True, slots=True)
class DatasetUsePolicy:
    dataset_id: str
    dataset_name: str
    observation_semantics: str
    known_publication_semantics: str
    revision_risk: str
    certification_status: DatasetCertificationStatus
    permitted_uses: tuple[str, ...]
    prohibited_uses: tuple[str, ...]
    missingness_policy: str
    required_future_certification: str
    policy_version: str


_UNDER_REVIEW = DatasetCertificationStatus.UNDER_REVIEW

_POLICIES = (
    DatasetUsePolicy(
        dataset_id=BLS_DATASET_ID,
        dataset_name="BLS",
        observation_semantics=(
            "Release-specific official observations; observation period and first release are "
            "distinct clocks."
        ),
        known_publication_semantics=(
            "Release schedules are series-specific; exact release and platform-delivery timing "
            "is not certified in Lift 1."
        ),
        revision_risk="Revisions and benchmark revisions require first-release or vintage data.",
        certification_status=_UNDER_REVIEW,
        permitted_uses=("descriptive_research", "risk_context_research"),
        prohibited_uses=("forecast_input", "signal_input", "silent_revised_history"),
        missingness_policy="Withhold absent releases; never forward-fill or replace with zero.",
        required_future_certification=(
            "Certify each series release schedule, first-release history, revisions, delivery "
            "timing, DST, holidays, and missing/correction behavior."
        ),
        policy_version="lift1.dataset-use.v1",
    ),
    DatasetUsePolicy(
        dataset_id=CONTINUOUS_BACKWARDS_RATIO_ID,
        dataset_name="Continuous Backwards-Ratio Series",
        observation_semantics=(
            "A continuity-oriented transformed futures series whose historical prices reflect "
            "the delivered mapping and normalization chain."
        ),
        known_publication_semantics=(
            "Usability follows the actual futures data and mapping observations delivered by "
            "the research environment; runtime timing remains under review."
        ),
        revision_risk=(
            "Historical adjusted values can depend on the mapping chain and must retain the "
            "normalization mode and retrieval lineage."
        ),
        certification_status=_UNDER_REVIEW,
        permitted_uses=(
            "continuity_research",
            "long_horizon_research_representation",
            "normalized_comparisons",
        ),
        prohibited_uses=(
            "actual_execution_price",
            "actual_fill_simulation",
            "actual_realized_pnl",
            "actual_volume_profile_price_bins",
        ),
        missingness_policy="Withhold missing intervals; never splice or fill with zero.",
        required_future_certification=(
            "Observe the real mapping chain and delivery timing, preserve actual mapped-contract "
            "prices separately, and certify each intended research use."
        ),
        policy_version="lift1.dataset-use.v1",
    ),
    DatasetUsePolicy(
        dataset_id=ECONOMIC_EVENTS_ID,
        dataset_name="Economic Events",
        observation_semantics=(
            "Event-calendar records whose scheduled time, actual value, and historical estimate "
            "availability are separate observations."
        ),
        known_publication_semantics=(
            "Calendar/risk research only until historical schedule changes, consensus vintages, "
            "and platform delivery are proven point in time."
        ),
        revision_risk="Schedules, estimates, and reported values can be revised or corrected.",
        certification_status=_UNDER_REVIEW,
        permitted_uses=("calendar_research", "risk_context_research"),
        prohibited_uses=("historical_surprise_signal", "signal_input", "silent_latest_estimate"),
        missingness_policy="Keep unknown schedules or estimates missing; do not infer or backfill.",
        required_future_certification=(
            "Certify schedule-as-known history, estimate vintages, actual release time, revisions, "
            "delivery timing, holidays, and corrections."
        ),
        policy_version="lift1.dataset-use.v1",
    ),
    DatasetUsePolicy(
        dataset_id=FRED_DATASET_ID,
        dataset_name="FRED",
        observation_semantics=(
            "Series observations whose economic period differs from publication and retrieval time."
        ),
        known_publication_semantics=(
            "No signal use until first-release or vintage semantics and platform delivery are "
            "proven for each series."
        ),
        revision_risk="Default historical values may reflect later revisions without vintage data.",
        certification_status=_UNDER_REVIEW,
        permitted_uses=("descriptive_research", "risk_context_research"),
        prohibited_uses=("forecast_input", "signal_input", "silent_latest_vintage"),
        missingness_policy="Retain missing observations; no interpolation or zero substitution.",
        required_future_certification=(
            "Certify release calendars, ALFRED or equivalent vintages, revision behavior, vendor "
            "delivery, holidays, and missing/correction handling by series."
        ),
        policy_version="lift1.dataset-use.v1",
    ),
    DatasetUsePolicy(
        dataset_id=US_TREASURY_YIELD_CURVE_ID,
        dataset_name="US Treasury Yield Curve",
        observation_semantics=(
            "Official tenor observations identified by observation date separately from their "
            "publication and platform-delivery times."
        ),
        known_publication_semantics=(
            "Exact official publication, holiday, correction, and platform-delivery timing is not "
            "certified in Lift 1."
        ),
        revision_risk="Corrections and latest-history behavior require an explicit audit.",
        certification_status=_UNDER_REVIEW,
        permitted_uses=("descriptive_research", "risk_context_research"),
        prohibited_uses=("forecast_input", "signal_input", "silent_revised_history"),
        missingness_policy="Withhold absent tenors/dates; never interpolate or substitute zero.",
        required_future_certification=(
            "Certify source timestamps, publication and platform delivery, tenor schema, holiday "
            "gaps, corrections, and revision behavior."
        ),
        policy_version="lift1.dataset-use.v1",
    ),
)


def validate_dataset_use_policy(policy: DatasetUsePolicy) -> None:
    """Validate one explicit, conservative dataset-use classification.

    Units: source units are retained and no values are normalized. Time semantics: observation,
    publication, revision, and future-certification semantics must be non-blank. Missingness: a
    non-blank policy is mandatory. Raises: ``DataQualityError`` for incomplete, overlapping, or
    signal-certified Lift 1 policy metadata.
    """

    for field_name, value in (
        ("dataset_id", policy.dataset_id),
        ("dataset_name", policy.dataset_name),
        ("observation_semantics", policy.observation_semantics),
        ("known_publication_semantics", policy.known_publication_semantics),
        ("revision_risk", policy.revision_risk),
        ("missingness_policy", policy.missingness_policy),
        ("required_future_certification", policy.required_future_certification),
        ("policy_version", policy.policy_version),
    ):
        if not isinstance(value, str) or not value.strip():
            raise DataQualityError(f"{field_name} must be a non-blank string")
    if policy.certification_status is not DatasetCertificationStatus.UNDER_REVIEW:
        raise DataQualityError("closure dataset-use policies must remain UNDER_REVIEW")
    for field_name, values in (
        ("permitted_uses", policy.permitted_uses),
        ("prohibited_uses", policy.prohibited_uses),
    ):
        if not isinstance(values, tuple) or not values:
            raise DataQualityError(f"{field_name} must be a non-empty tuple")
        if values != tuple(sorted(set(values))):
            raise DataQualityError(f"{field_name} must be sorted and contain no duplicates")
        if any(not isinstance(value, str) or not value.strip() for value in values):
            raise DataQualityError(f"{field_name} entries must be non-blank strings")
    overlap = set(policy.permitted_uses).intersection(policy.prohibited_uses)
    if overlap:
        raise DataQualityError("permitted and prohibited uses must not overlap")


def validate_dataset_use_policies(policies: Sequence[DatasetUsePolicy]) -> tuple[str, ...]:
    """Validate the five conservative closure dataset-use policies.

    Units: source-specific and unchanged. Time semantics: each record separates observation,
    publication, revision, and future certification. Missingness: all required policy IDs must be
    present exactly once. Raises: ``DataQualityError`` for a missing, duplicate, unsorted, or
    weakened policy. Returns the validated dataset IDs.
    """

    records = tuple(policies)
    for policy in records:
        validate_dataset_use_policy(policy)
    dataset_ids = tuple(policy.dataset_id for policy in records)
    if dataset_ids != tuple(sorted(set(dataset_ids))):
        raise DataQualityError("dataset-use policies must be sorted and uniquely identified")
    required = {
        BLS_DATASET_ID,
        CONTINUOUS_BACKWARDS_RATIO_ID,
        ECONOMIC_EVENTS_ID,
        FRED_DATASET_ID,
        US_TREASURY_YIELD_CURVE_ID,
    }
    if set(dataset_ids) != required:
        raise DataQualityError("dataset-use registry must contain the five exact closure policies")
    return dataset_ids


def dataset_use_policies() -> tuple[DatasetUsePolicy, ...]:
    """Return the deterministic Lift 1 dataset-use policy matrix.

    Units: source-specific and unchanged. Time semantics: no data is released by this registry.
    Missingness: all five classifications are explicit. Raises: ``DataQualityError`` if a static
    policy violates the conservative closure contract.
    """

    validate_dataset_use_policies(_POLICIES)
    return _POLICIES


def get_dataset_use_policy(dataset_id: str) -> DatasetUsePolicy:
    """Return one exact policy without a fallback.

    Units: source-specific and unchanged. Time semantics: lookup does not establish availability.
    Missingness: an unknown ID raises. Raises: ``DataQualityError`` for a blank or unknown ID.
    """

    if not isinstance(dataset_id, str) or not dataset_id.strip():
        raise DataQualityError("dataset_id must be a non-blank string")
    for policy in dataset_use_policies():
        if policy.dataset_id == dataset_id:
            return policy
    raise DataQualityError(f"Unknown dataset-use policy: {dataset_id!r}")


__all__ = (
    "BLS_DATASET_ID",
    "CONTINUOUS_BACKWARDS_RATIO_ID",
    "ECONOMIC_EVENTS_ID",
    "FRED_DATASET_ID",
    "US_TREASURY_YIELD_CURVE_ID",
    "DatasetUsePolicy",
    "dataset_use_policies",
    "get_dataset_use_policy",
    "validate_dataset_use_policies",
    "validate_dataset_use_policy",
)

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from systematic_futures.data.policies import (
    DatasetPolicy,
    SyntheticCftcTimingPolicy,
    UnderReviewDatasetPolicy,
)
from systematic_futures.domain.enums import DatasetCertificationStatus
from systematic_futures.domain.errors import DataQualityError

QC_FUTURES_TRADE_DATA_ID = "qc_futures_trade_data"
QC_FUTURES_QUOTE_DATA_ID = "qc_futures_quote_data"
QC_FUTURES_OPEN_INTEREST_ID = "qc_futures_open_interest"
QC_FUTURES_CONTRACT_MAPPING_ID = "qc_futures_contract_mapping"
CFTC_COMMITMENTS_OF_TRADERS_ID = "cftc_commitments_of_traders_synthetic_timing"

_SCHEMA_VERSION = "lift1.raw.v1"
_DISPLAY_NAMES: Mapping[str, str] = MappingProxyType(
    {
        QC_FUTURES_TRADE_DATA_ID: "QC Futures Trade Data",
        QC_FUTURES_QUOTE_DATA_ID: "QC Futures Quote Data",
        QC_FUTURES_OPEN_INTEREST_ID: "QC Futures Open Interest",
        QC_FUTURES_CONTRACT_MAPPING_ID: "QC Futures Contract Mapping",
        CFTC_COMMITMENTS_OF_TRADERS_ID: "CFTC Commitments of Traders",
    }
)

_POLICIES: Mapping[str, DatasetPolicy] = MappingProxyType(
    {
        QC_FUTURES_TRADE_DATA_ID: UnderReviewDatasetPolicy(
            dataset_id=QC_FUTURES_TRADE_DATA_ID,
            schema_version=_SCHEMA_VERSION,
            additional_quality_flags=("vendor_timing_semantics_not_certified",),
        ),
        QC_FUTURES_QUOTE_DATA_ID: UnderReviewDatasetPolicy(
            dataset_id=QC_FUTURES_QUOTE_DATA_ID,
            schema_version=_SCHEMA_VERSION,
            additional_quality_flags=("vendor_timing_semantics_not_certified",),
        ),
        QC_FUTURES_OPEN_INTEREST_ID: UnderReviewDatasetPolicy(
            dataset_id=QC_FUTURES_OPEN_INTEREST_ID,
            schema_version=_SCHEMA_VERSION,
            additional_quality_flags=(
                "revision_semantics_not_certified",
                "vendor_timing_semantics_not_certified",
            ),
        ),
        QC_FUTURES_CONTRACT_MAPPING_ID: UnderReviewDatasetPolicy(
            dataset_id=QC_FUTURES_CONTRACT_MAPPING_ID,
            schema_version=_SCHEMA_VERSION,
            additional_quality_flags=(
                "mapping_delivery_semantics_not_certified",
                "revision_semantics_not_certified",
            ),
        ),
        CFTC_COMMITMENTS_OF_TRADERS_ID: SyntheticCftcTimingPolicy(
            dataset_id=CFTC_COMMITMENTS_OF_TRADERS_ID,
            schema_version=_SCHEMA_VERSION,
        ),
    }
)


def all_dataset_policies() -> tuple[DatasetPolicy, ...]:
    """Return the five Lift 1 dataset policies in deterministic ID order.

    Units: dataset values retain source units.
    Time semantics: each policy requires explicit source-release and platform-delivery
    timestamps; CFTC timing is a synthetic proof only.
    Missingness: no policy is omitted or defaulted.
    Raises: DataQualityError if any policy is ever configured as CERTIFIED_SIGNAL.
    """
    policies = tuple(_POLICIES[key] for key in sorted(_POLICIES))
    if any(
        policy.certification_status is DatasetCertificationStatus.CERTIFIED_SIGNAL
        for policy in policies
    ):
        raise DataQualityError("No Lift 1 dataset may begin as CERTIFIED_SIGNAL")
    return policies


def dataset_policy_registry() -> Mapping[str, DatasetPolicy]:
    """Return a read-only dataset-ID-to-policy mapping.

    Units: inherited from each source payload.
    Time semantics: policies compute usable time from explicit record clocks.
    Missingness: all five required dataset IDs are present.
    Raises: DataQualityError if a signal-certified policy is detected.
    """
    all_dataset_policies()
    return _POLICIES


def get_dataset_policy(dataset_id: str) -> DatasetPolicy:
    """Return one exact dataset policy.

    Units: inherited from the source payload.
    Time semantics: no clock is evaluated by lookup.
    Missingness: an unknown ID raises instead of falling back.
    Raises: DataQualityError for an unknown or blank dataset ID.
    """
    policy = _POLICIES.get(dataset_id)
    if policy is None:
        raise DataQualityError(f"Unknown dataset ID: {dataset_id!r}")
    return policy


def dataset_display_name(dataset_id: str) -> str:
    """Return the human-readable policy name for a stable dataset ID.

    Units: not applicable.
    Time semantics: not applicable.
    Missingness: unknown IDs raise and are never relabeled silently.
    Raises: DataQualityError for an unknown dataset ID.
    """
    name = _DISPLAY_NAMES.get(dataset_id)
    if name is None:
        raise DataQualityError(f"Unknown dataset ID: {dataset_id!r}")
    return name


__all__ = (
    "CFTC_COMMITMENTS_OF_TRADERS_ID",
    "QC_FUTURES_CONTRACT_MAPPING_ID",
    "QC_FUTURES_OPEN_INTEREST_ID",
    "QC_FUTURES_QUOTE_DATA_ID",
    "QC_FUTURES_TRADE_DATA_ID",
    "DatasetPolicy",
    "all_dataset_policies",
    "dataset_display_name",
    "dataset_policy_registry",
    "get_dataset_policy",
)

from collections.abc import Iterable

from systematic_futures.domain.enums import DataQualityStatus, MeasurementQualitySeverity
from systematic_futures.domain.errors import DataQualityError

_MEASUREMENT_QUALITY_SEVERITY = {
    # Source capability and deterministically excluded observations.
    "PROVENANCE:DEDUPLICATION_UNVERIFIABLE": MeasurementQualitySeverity.BLOCKING,
    "DATA:SOURCE_SUSPICIOUS_EXCLUDED": MeasurementQualitySeverity.WARNING,
    "DATA:DUPLICATE_SOURCE_ID_EXCLUDED": MeasurementQualitySeverity.INFORMATIONAL,
    "DATA:DUPLICATE_SOURCE_SEQUENCE_EXCLUDED": MeasurementQualitySeverity.INFORMATIONAL,
    "DATA:NON_POSITIVE_PRICE_EXCLUDED": MeasurementQualitySeverity.WARNING,
    "DATA:NON_POSITIVE_QUANTITY_EXCLUDED": MeasurementQualitySeverity.WARNING,
    "DATA:OFF_TICK_GRID_EXCLUDED": MeasurementQualitySeverity.WARNING,
    # Historical-state corruption or unresolved identity/session state.
    "DATA:LATE_TRADE_AFTER_FINAL_PROFILE": MeasurementQualitySeverity.BLOCKING,
    "DATA:LATE": MeasurementQualitySeverity.BLOCKING,
    "DATA:LATE_TRADE_IGNORED": MeasurementQualitySeverity.BLOCKING,
    "DATA:OUT_OF_ORDER": MeasurementQualitySeverity.BLOCKING,
    "DATA:OUT_OF_ORDER_TRADE_IGNORED": MeasurementQualitySeverity.BLOCKING,
    "CONTRACT_IDENTITY_AMBIGUOUS": MeasurementQualitySeverity.BLOCKING,
    "SESSION_INVALID": MeasurementQualitySeverity.BLOCKING,
    "DATASET_QUARANTINED": MeasurementQualitySeverity.BLOCKING,
    # Explicit session and roll eligibility policy.
    "SESSION:MAINTENANCE": MeasurementQualitySeverity.BLOCKING,
    "SESSION:CLOSED": MeasurementQualitySeverity.BLOCKING,
    "SESSION:UNKNOWN": MeasurementQualitySeverity.BLOCKING,
    "ROLL:NORMAL": MeasurementQualitySeverity.INFORMATIONAL,
    "ROLL:POST_ROLL": MeasurementQualitySeverity.INFORMATIONAL,
    "ROLL:ROLL_TRANSITION": MeasurementQualitySeverity.BLOCKING,
    "ROLL:PRE_ROLL": MeasurementQualitySeverity.BLOCKING,
    "ROLL:BLACKOUT": MeasurementQualitySeverity.BLOCKING,
    # Auction readiness and descriptive profile context.
    "AUCTION:MEASUREMENT_NOT_READY": MeasurementQualitySeverity.BLOCKING,
    "NO_PRIOR_SAME_SESSION_TYPE_PROFILE": MeasurementQualitySeverity.INFORMATIONAL,
    "DEGENERATE_PROFILE": MeasurementQualitySeverity.WARNING,
    "AUCTION:NO_PRIOR_SAME_SESSION_TYPE_PROFILE": MeasurementQualitySeverity.INFORMATIONAL,
    "AUCTION:DEGENERATE_PROFILE": MeasurementQualitySeverity.WARNING,
    # Optional component availability is an ablation dimension, not a base-event blocker.
    "IMSI:MISSING": MeasurementQualitySeverity.WARNING,
    "IMSI:STALE": MeasurementQualitySeverity.WARNING,
    "IMSI:MEASUREMENT_NOT_READY": MeasurementQualitySeverity.WARNING,
    "ICM:MISSING": MeasurementQualitySeverity.WARNING,
    "ICM:STALE": MeasurementQualitySeverity.WARNING,
    "ICM:MEASUREMENT_NOT_READY": MeasurementQualitySeverity.WARNING,
    "IAE:MISSING": MeasurementQualitySeverity.WARNING,
    "IAE:STALE": MeasurementQualitySeverity.WARNING,
    "IAE:MEASUREMENT_NOT_READY": MeasurementQualitySeverity.WARNING,
    # Component-local guards retained as explicit nonblocking context.
    "IMSI:IMSI_TOD_WARMUP": MeasurementQualitySeverity.INFORMATIONAL,
    "IMSI:IMSI_COVARIANCE_DEGENERATE": MeasurementQualitySeverity.WARNING,
    "IMSI:IMSI_COVARIANCE_UNSTABLE": MeasurementQualitySeverity.WARNING,
    "IMSI:IMSI_RARITY_WARMUP": MeasurementQualitySeverity.INFORMATIONAL,
    "IMSI:IMSI_COVARIANCE_WARMUP": MeasurementQualitySeverity.INFORMATIONAL,
    "IMSI:IMSI_FULL_MODEL_DEFERRED": MeasurementQualitySeverity.INFORMATIONAL,
    "ICM:ICM_FLAT_SCALE_GUARD": MeasurementQualitySeverity.WARNING,
    "ICM:ICM_REGIME_GUARD": MeasurementQualitySeverity.WARNING,
    "ICM:ICM_RESIDUAL_AUTOCORRELATION_DEGENERATE": MeasurementQualitySeverity.WARNING,
    "ICM:ICM_LOCAL_SCALE_UNAVAILABLE": MeasurementQualitySeverity.INFORMATIONAL,
    "ICM:ICM_WINDOW_WARMUP": MeasurementQualitySeverity.INFORMATIONAL,
    "IAE:IAE_BAR_GAP_RESET": MeasurementQualitySeverity.INFORMATIONAL,
    "IAE:IAE_ATR_WARMUP": MeasurementQualitySeverity.INFORMATIONAL,
    "IAE:IAE_FORMATION_DEGENERATE": MeasurementQualitySeverity.INFORMATIONAL,
    "IAE:IAE_FORMATION_GATED": MeasurementQualitySeverity.INFORMATIONAL,
    "IAE:IAE_TOD_WARMUP": MeasurementQualitySeverity.INFORMATIONAL,
    "IAE:IAE_TOD_DEGENERATE_MAD": MeasurementQualitySeverity.WARNING,
    "IAE:IAE_SCORE_TOD_UNAVAILABLE": MeasurementQualitySeverity.INFORMATIONAL,
}


def measurement_quality_severity(flag: str) -> MeasurementQualitySeverity:
    """Return the explicit measurement severity for one exact flag.

    Units: not applicable. Time semantics: none. Missingness: no prefix or default
    inference is permitted. Raises: ``DataQualityError`` for blank or unclassified flags.
    """

    candidate = flag.strip()
    if not candidate:
        raise DataQualityError("measurement quality flag must be non-blank")
    try:
        return _MEASUREMENT_QUALITY_SEVERITY[candidate]
    except KeyError as error:
        raise DataQualityError(f"unclassified measurement quality flag: {candidate}") from error


def blocking_measurement_flags(flags: Iterable[str]) -> tuple[str, ...]:
    """Return sorted unique flags explicitly classified as measurement-blocking.

    Units: not applicable. Time semantics: none. Missingness: an empty iterable yields
    an empty tuple. Raises: ``DataQualityError`` for any blank or unclassified flag.
    """

    normalized = normalize_quality_flags(flags)
    return tuple(
        flag
        for flag in normalized
        if measurement_quality_severity(flag) is MeasurementQualitySeverity.BLOCKING
    )


def normalize_quality_flags(flags: Iterable[str]) -> tuple[str, ...]:
    """Return unique, sorted, non-blank quality flags.

    Units: not applicable. Time semantics: none. Missingness: an empty input
    yields an empty tuple; blank individual flags are invalid. Raises:
    ``DataQualityError`` for a blank flag.
    """
    normalized: set[str] = set()
    for flag in flags:
        candidate = flag.strip()
        if not candidate:
            raise DataQualityError("quality flags must be non-blank")
        normalized.add(candidate)
    return tuple(sorted(normalized))


def quality_status_from_evidence(
    quality_flags: tuple[str, ...],
    missing_reason: str | None,
) -> DataQualityStatus:
    """Classify quality from explicit flags and missingness only.

    Units: not applicable. Time semantics: none. Missingness: an explicit
    missing reason produces ``WITHHELD``; flags produce ``PARTIAL``; otherwise
    the record is ``VALID``. Raises: ``DataQualityError`` for a blank missing
    reason or non-normalized flags.
    """
    normalized_flags = normalize_quality_flags(quality_flags)
    if normalized_flags != quality_flags:
        raise DataQualityError("quality flags must be normalized before classification")
    if missing_reason is not None:
        if not missing_reason.strip():
            raise DataQualityError("missing_reason must be non-blank when present")
        return DataQualityStatus.WITHHELD
    if normalized_flags:
        return DataQualityStatus.PARTIAL
    return DataQualityStatus.VALID


def ensure_quality_not_upgraded(
    source_status: DataQualityStatus,
    emitted_status: DataQualityStatus,
) -> None:
    """Reject silent upgrades from stale, withheld, or rejected evidence.

    Units: not applicable. Time semantics: none. Missingness: quality states are
    required enum values. Raises: ``DataQualityError`` when an emitted state is
    more permissive than a restricted source state.
    """
    restricted = {
        DataQualityStatus.STALE,
        DataQualityStatus.WITHHELD,
        DataQualityStatus.REJECTED,
    }
    if source_status in restricted and emitted_status not in restricted:
        raise DataQualityError(
            f"quality status cannot be upgraded from {source_status.value} "
            f"to {emitted_status.value}"
        )

from collections.abc import Iterable

from systematic_futures.domain.enums import DataQualityStatus
from systematic_futures.domain.errors import DataQualityError


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

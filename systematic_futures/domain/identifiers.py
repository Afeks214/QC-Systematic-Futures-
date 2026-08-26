from __future__ import annotations

# pyright: reportUnnecessaryIsInstance=false
from datetime import UTC, datetime

from systematic_futures.domain.errors import DataQualityError, TimeSemanticsError
from systematic_futures.domain.serialization import sha256_hex


def _normalized_timestamp(value: datetime, field_name: str) -> tuple[datetime, str]:
    if value.tzinfo is None or value.utcoffset() is None:
        raise TimeSemanticsError(f"{field_name} must be timezone-aware")
    normalized = value.astimezone(UTC)
    token = normalized.strftime("%Y%m%dT%H%M%S%fZ")
    return normalized, token


def _require_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DataQualityError(f"{field_name} must not be blank")
    return value


def make_run_id(created_at_utc: datetime, configuration_hash: str) -> str:
    """Build a deterministic run identifier from its UTC creation time and configuration hash.

    Units: not applicable. Time semantics: ``created_at_utc`` must be aware and is normalized to
    UTC. Missingness: neither input may be missing or blank. Raises ``TimeSemanticsError`` for a
    naive timestamp and ``DataQualityError`` for a blank configuration hash.
    """

    normalized_time, timestamp_token = _normalized_timestamp(created_at_utc, "created_at_utc")
    normalized_hash = _require_text(configuration_hash, "configuration_hash")
    digest = sha256_hex({"configuration_hash": normalized_hash, "created_at_utc": normalized_time})
    return f"run_{timestamp_token}_{digest[:20]}"


def make_experiment_id(
    hypothesis_name: str,
    hypothesis_version: str,
    registered_at_utc: datetime,
) -> str:
    """Build a deterministic experiment identifier from pre-registration inputs.

    Units: not applicable. Time semantics: ``registered_at_utc`` must be aware and is normalized
    to UTC. Missingness: names and versions may not be blank. Raises ``TimeSemanticsError`` for a
    naive timestamp and ``DataQualityError`` for blank text.
    """

    normalized_time, timestamp_token = _normalized_timestamp(registered_at_utc, "registered_at_utc")
    normalized_name = _require_text(hypothesis_name, "hypothesis_name")
    normalized_version = _require_text(hypothesis_version, "hypothesis_version")
    digest = sha256_hex(
        {
            "hypothesis_name": normalized_name,
            "hypothesis_version": normalized_version,
            "registered_at_utc": normalized_time,
        }
    )
    return f"experiment_{timestamp_token}_{digest[:20]}"


def make_lineage_hash(
    dataset_id: str,
    series_id: str,
    observation_time_utc: datetime,
    source_version: str,
    payload: object,
) -> str:
    """Hash the immutable source identity and canonical payload of one observation.

    Units: payload units are preserved. Time semantics: ``observation_time_utc`` must be aware and
    is normalized to UTC. Missingness: the payload may be ``None`` when missingness is explicit;
    identifier and version strings may not be blank. Raises ``TimeSemanticsError`` for a naive
    timestamp and ``DataQualityError`` for blank text or a non-canonical payload.
    """

    normalized_time, _ = _normalized_timestamp(observation_time_utc, "observation_time_utc")
    return sha256_hex(
        {
            "dataset_id": _require_text(dataset_id, "dataset_id"),
            "observation_time_utc": normalized_time,
            "payload": payload,
            "series_id": _require_text(series_id, "series_id"),
            "source_version": _require_text(source_version, "source_version"),
        }
    )


__all__ = ("make_experiment_id", "make_lineage_hash", "make_run_id")

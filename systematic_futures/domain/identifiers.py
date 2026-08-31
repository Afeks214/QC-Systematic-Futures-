from datetime import UTC, datetime

from systematic_futures.domain.errors import DataQualityError, TimeSemanticsError
from systematic_futures.domain.serialization import sha256_hex


def make_lineage_hash(
    dataset_id: str,
    series_id: str,
    observation_time_utc: datetime,
    source_version: str,
    payload: object,
    *,
    market: str | None,
    instrument_id: str | None,
    schema_version: str,
    revision_id: str | None = None,
    source_release_time_utc: datetime | None = None,
) -> str:
    """Hash one immutable source identity, revision, and canonical payload."""

    observation = _normalized_timestamp(observation_time_utc, "observation_time_utc")
    release = None
    if source_release_time_utc is not None:
        release = _normalized_timestamp(source_release_time_utc, "source_release_time_utc")
    if revision_id is not None:
        _require_text(revision_id, "revision_id")
    return sha256_hex(
        {
            "dataset_id": _require_text(dataset_id, "dataset_id"),
            "instrument_id": _optional_text(instrument_id, "instrument_id"),
            "market": _optional_text(market, "market"),
            "observation_time_utc": observation,
            "payload": payload,
            "revision_id": revision_id,
            "series_id": _require_text(series_id, "series_id"),
            "schema_version": _require_text(schema_version, "schema_version"),
            "source_release_time_utc": release,
            "source_version": _require_text(source_version, "source_version"),
        }
    )


def _normalized_timestamp(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise TimeSemanticsError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _require_text(value: str, field_name: str) -> str:
    if not value.strip():
        raise DataQualityError(f"{field_name} must not be blank")
    return value


def _optional_text(value: str | None, field_name: str) -> str | None:
    if value is None:
        return None
    return _require_text(value, field_name)


__all__ = ("make_lineage_hash",)

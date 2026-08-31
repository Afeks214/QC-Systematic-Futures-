from datetime import UTC, datetime

from systematic_futures.domain.errors import TimeSemanticsError


def ensure_aware_utc(value: datetime, field_name: str) -> datetime:
    """Preserve one aware instant while normalizing its representation to UTC."""

    if not field_name.strip():
        raise TimeSemanticsError("field_name must be non-blank")
    if value.tzinfo is None or value.utcoffset() is None:
        raise TimeSemanticsError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


__all__ = ("ensure_aware_utc",)

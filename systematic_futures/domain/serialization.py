import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from datetime import UTC, date, datetime, time
from enum import Enum
from typing import cast

from systematic_futures.domain.errors import DataQualityError, TimeSemanticsError


def _canonical_datetime(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise TimeSemanticsError("canonical JSON cannot contain a timezone-naive datetime")
    normalized = value.astimezone(UTC)
    return normalized.isoformat(timespec="microseconds").replace("+00:00", "Z")


def canonicalize_for_json(value: object) -> object:
    """Convert a supported value to a deterministic JSON-compatible value.

    Units: preserves numeric units without conversion. Time semantics: aware datetimes are
    normalized to UTC ISO-8601 with ``Z``; local ``date`` and ``time`` values retain their ISO
    representation. Missingness: ``None`` is preserved. Raises ``TimeSemanticsError`` for a naive
    datetime and ``DataQualityError`` for non-finite numbers, non-string mapping keys, or an
    unsupported value whose representation is not guaranteed stable.
    """

    if isinstance(value, Enum):
        return canonicalize_for_json(value.value)
    if isinstance(value, datetime):
        return _canonical_datetime(value)
    if isinstance(value, time):
        return value.isoformat(timespec="microseconds")
    if isinstance(value, date):
        return value.isoformat()
    if value is None or isinstance(value, str | bool | int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise DataQualityError("canonical JSON prohibits NaN and Infinity")
        return value
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: canonicalize_for_json(getattr(value, field.name)) for field in fields(value)
        }
    if isinstance(value, Mapping):
        mapping = cast(Mapping[object, object], value)
        normalized_items: list[tuple[str, object]] = []
        for key, item in mapping.items():
            if not isinstance(key, str):
                raise DataQualityError("canonical JSON mapping keys must be strings")
            normalized_items.append((key, canonicalize_for_json(item)))
        return dict(sorted(normalized_items, key=lambda pair: pair[0]))
    if isinstance(value, tuple | list):
        sequence = cast(tuple[object, ...] | list[object], value)
        return [canonicalize_for_json(item) for item in sequence]
    raise DataQualityError(
        f"canonical JSON does not support values of type {type(value).__qualname__}"
    )


def canonical_json_bytes(value: object) -> bytes:
    """Serialize a supported value as canonical compact UTF-8 JSON bytes.

    Units: preserves numeric units. Time semantics: aware datetimes become UTC ISO-8601 strings.
    Missingness: ``None`` becomes JSON ``null``. Raises ``TimeSemanticsError`` or
    ``DataQualityError`` when ``canonicalize_for_json`` rejects an input.
    """

    normalized = canonicalize_for_json(value)
    serialized = json.dumps(
        normalized,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return serialized.encode("utf-8")


def sha256_hex(value: object) -> str:
    """Return the lowercase SHA-256 digest of a value's canonical JSON bytes.

    Units: not applicable. Time semantics: datetimes are normalized to UTC before hashing.
    Missingness: ``None`` is hashable as JSON ``null``. Raises ``TimeSemanticsError`` or
    ``DataQualityError`` when canonical serialization rejects an input.
    """

    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


__all__ = ("canonical_json_bytes", "canonicalize_for_json", "sha256_hex")

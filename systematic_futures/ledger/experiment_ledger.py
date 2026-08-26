from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import cast

from systematic_futures.domain.enums import ExperimentDecision
from systematic_futures.domain.errors import (
    DuplicateIdentifierError,
    LedgerIntegrityError,
    TimeSemanticsError,
)
from systematic_futures.domain.schemas import ExperimentRecord, validate_experiment_record
from systematic_futures.domain.serialization import (
    canonical_json_bytes,
    canonicalize_for_json,
    sha256_hex,
)

_LEDGER_SCHEMA_VERSION = "1.0.0"
_PRE_REGISTRATION = "experiment_pre_registration"
_DECISION = "experiment_decision"


class ExperimentLedger:
    """Append-only, hash-chained experiment registration ledger.

    Units: timestamps are timezone-aware UTC datetimes.
    Time semantics: caller-provided registration/decision times are authoritative;
    the ledger never obtains or rewrites current time.
    Missingness: a missing ledger file is an empty valid ledger; malformed content is
    an integrity failure.
    Raises: LedgerIntegrityError for malformed chains/invalid transitions,
    DuplicateIdentifierError for reused experiment IDs, TimeSemanticsError for an
    invalid decision timestamp, and OSError for filesystem failures.
    """

    def __init__(self, path: Path) -> None:
        """Bind the ledger to ``path`` without creating or modifying it.

        Units: not applicable.
        Time semantics: not applicable.
        Missingness: a nonexistent path represents an empty ledger.
        Raises: LedgerIntegrityError if ``path`` exists but is not a regular file.
        """
        if path.exists() and not path.is_file():
            raise LedgerIntegrityError(f"Ledger path is not a regular file: {path}")
        self._path = path

    def pre_register(self, record: ExperimentRecord) -> str:
        """Append a pending experiment pre-registration and return its row hash.

        Units: horizon values inside ``record`` are minutes.
        Time semantics: ``record.registered_at_utc`` becomes the append timestamp.
        Missingness: required human-readable fields may not be blank.
        Raises: DuplicateIdentifierError, LedgerIntegrityError, TimeSemanticsError,
        or OSError.
        """
        validate_experiment_record(record)
        if record.decision is not ExperimentDecision.PENDING:
            raise LedgerIntegrityError("A pre-registration must have PENDING decision state")
        if not _is_human_readable_name(record.hypothesis_name):
            raise LedgerIntegrityError("A human-readable hypothesis name is mandatory")
        rows = self._verified_rows()
        if record.experiment_id in _registered_ids(rows):
            raise DuplicateIdentifierError(f"Duplicate experiment ID: {record.experiment_id}")
        row = _build_row(
            record_type=_PRE_REGISTRATION,
            recorded_at_utc=record.registered_at_utc,
            payload=canonicalize_for_json(record),
            previous_record_hash=_last_hash(rows),
        )
        self._atomic_append(row)
        return _required_text(row, "record_hash")

    def append_decision(
        self,
        experiment_id: str,
        decision: ExperimentDecision,
        reason: str,
        decided_at_utc: datetime,
    ) -> str:
        """Append a decision for a registered experiment and return its row hash.

        Units: not applicable.
        Time semantics: ``decided_at_utc`` must be aware UTC-normalizable and cannot
        precede the experiment registration time.
        Missingness: blank identifiers/reasons are rejected.
        Raises: LedgerIntegrityError, TimeSemanticsError, or OSError.
        """
        normalized_time = _aware_utc(decided_at_utc, "decided_at_utc")
        if not experiment_id.strip():
            raise LedgerIntegrityError("experiment_id must not be blank")
        if not reason.strip():
            raise LedgerIntegrityError("Decision reason must not be blank")
        if decision is ExperimentDecision.PENDING:
            raise LedgerIntegrityError("PENDING is a registration state, not an appended decision")
        rows = self._verified_rows()
        registration_time = _registration_time(rows, experiment_id)
        if normalized_time < registration_time:
            raise LedgerIntegrityError("Decision time precedes experiment registration")
        payload: Mapping[str, object] = {
            "decided_at_utc": normalized_time,
            "decision": decision,
            "experiment_id": experiment_id,
            "reason": reason.strip(),
        }
        row = _build_row(
            record_type=_DECISION,
            recorded_at_utc=normalized_time,
            payload=payload,
            previous_record_hash=_last_hash(rows),
        )
        self._atomic_append(row)
        return _required_text(row, "record_hash")

    def read_all(self) -> tuple[Mapping[str, object], ...]:
        """Return verified rows in append order.

        Units: not applicable.
        Time semantics: serialized row timestamps remain UTC ISO-8601 strings.
        Missingness: a missing or empty file returns an empty tuple.
        Raises: LedgerIntegrityError for any malformed or mutated row and OSError for
        filesystem failures.
        """
        return tuple(self._verified_rows())

    def verify_chain(self) -> bool:
        """Return whether every stored row and chain link verifies.

        Units: not applicable.
        Time semantics: recorded timestamps are included in each content hash.
        Missingness: a missing or empty ledger is a valid empty chain.
        Raises: OSError for filesystem failures; malformed content returns ``False``.
        """
        try:
            self._verified_rows()
        except LedgerIntegrityError:
            return False
        return True

    def _verified_rows(self) -> list[Mapping[str, object]]:
        rows = _read_rows(self._path)
        previous: str | None = None
        for index, row in enumerate(rows, start=1):
            _verify_row(row, previous, index)
            previous = _required_text(row, "record_hash")
        return rows

    def _atomic_append(self, row: Mapping[str, object]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        existing = self._path.read_bytes() if self._path.exists() else b""
        if existing and not existing.endswith(b"\n"):
            raise LedgerIntegrityError("Existing ledger does not end at a row boundary")
        next_bytes = existing + canonical_json_bytes(row) + b"\n"
        file_descriptor, temporary_name = tempfile.mkstemp(
            dir=self._path.parent,
            prefix=f".{self._path.name}.",
            suffix=".tmp",
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(file_descriptor, "wb") as handle:
                handle.write(next_bytes)
                handle.flush()
                os.fsync(handle.fileno())
            temporary_path.replace(self._path)
        except OSError:
            temporary_path.unlink(missing_ok=True)
            raise


def _read_rows(path: Path) -> list[Mapping[str, object]]:
    if not path.exists():
        return []
    rows: list[Mapping[str, object]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise LedgerIntegrityError("Ledger is not valid UTF-8") from error
    for index, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            raise LedgerIntegrityError(f"Blank ledger row at line {index}")
        try:
            parsed: object = json.loads(line)
        except json.JSONDecodeError as error:
            raise LedgerIntegrityError(f"Invalid JSON at ledger line {index}") from error
        if not isinstance(parsed, dict):
            raise LedgerIntegrityError(f"Ledger row {index} is not a JSON object")
        raw_mapping = cast(dict[object, object], parsed)
        if not all(isinstance(key, str) for key in raw_mapping):
            raise LedgerIntegrityError(f"Ledger row {index} contains a non-string key")
        rows.append(cast(dict[str, object], raw_mapping))
    return rows


def _verify_row(row: Mapping[str, object], previous: str | None, index: int) -> None:
    required = {
        "schema_version",
        "record_type",
        "recorded_at_utc",
        "payload",
        "previous_record_hash",
        "record_hash",
    }
    if set(row) != required:
        raise LedgerIntegrityError(f"Ledger row {index} has an unexpected schema")
    if row["schema_version"] != _LEDGER_SCHEMA_VERSION:
        raise LedgerIntegrityError(f"Ledger row {index} has an unsupported schema version")
    if row["previous_record_hash"] != previous:
        raise LedgerIntegrityError(f"Ledger row {index} has a broken previous-hash link")
    stored_hash = _required_text(row, "record_hash")
    hash_input = {key: value for key, value in row.items() if key != "record_hash"}
    if sha256_hex(hash_input) != stored_hash:
        raise LedgerIntegrityError(f"Ledger row {index} content hash does not match")
    if row["record_type"] not in {_PRE_REGISTRATION, _DECISION}:
        raise LedgerIntegrityError(f"Ledger row {index} has an unknown record type")
    if not isinstance(row["payload"], dict):
        raise LedgerIntegrityError(f"Ledger row {index} payload is not an object")


def _build_row(
    *,
    record_type: str,
    recorded_at_utc: datetime,
    payload: object,
    previous_record_hash: str | None,
) -> Mapping[str, object]:
    normalized_time = _aware_utc(recorded_at_utc, "recorded_at_utc")
    content: dict[str, object] = {
        "schema_version": _LEDGER_SCHEMA_VERSION,
        "record_type": record_type,
        "recorded_at_utc": normalized_time,
        "payload": payload,
        "previous_record_hash": previous_record_hash,
    }
    content["record_hash"] = sha256_hex(content)
    canonical = canonicalize_for_json(content)
    if not isinstance(canonical, dict):
        raise LedgerIntegrityError("Canonical ledger row is not an object")
    return cast(dict[str, object], canonical)


def _registered_ids(rows: list[Mapping[str, object]]) -> set[str]:
    identifiers: set[str] = set()
    for row in rows:
        if row["record_type"] == _PRE_REGISTRATION:
            payload = _required_payload(row)
            identifiers.add(_required_text(payload, "experiment_id"))
    return identifiers


def _registration_time(rows: list[Mapping[str, object]], experiment_id: str) -> datetime:
    for row in rows:
        if row["record_type"] != _PRE_REGISTRATION:
            continue
        payload = _required_payload(row)
        if payload.get("experiment_id") == experiment_id:
            return _parse_utc(_required_text(row, "recorded_at_utc"))
    raise LedgerIntegrityError(f"Experiment is not pre-registered: {experiment_id}")


def _required_payload(row: Mapping[str, object]) -> Mapping[str, object]:
    payload = row.get("payload")
    if not isinstance(payload, dict):
        raise LedgerIntegrityError("Ledger row payload is not an object")
    return cast(dict[str, object], payload)


def _required_text(mapping: Mapping[str, object], key: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value:
        raise LedgerIntegrityError(f"Ledger field {key!r} must be non-empty text")
    return value


def _last_hash(rows: list[Mapping[str, object]]) -> str | None:
    if not rows:
        return None
    return _required_text(rows[-1], "record_hash")


def _is_human_readable_name(name: str) -> bool:
    words = [part for part in name.strip().split() if part]
    return len(words) >= 3 and any(character.islower() for character in name)


def _aware_utc(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise TimeSemanticsError(f"{field_name} must be timezone-aware")
    from datetime import UTC

    return value.astimezone(UTC)


def _parse_utc(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise LedgerIntegrityError("Ledger timestamp is not ISO-8601") from error
    return _aware_utc(parsed, "recorded_at_utc")

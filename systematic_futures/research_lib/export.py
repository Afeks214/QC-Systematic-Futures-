from __future__ import annotations

import hashlib
import tempfile
from collections.abc import Sequence
from pathlib import Path

from systematic_futures.domain.errors import DuplicateIdentifierError
from systematic_futures.domain.schemas import DataProbeResult, validate_data_probe_result
from systematic_futures.domain.serialization import canonical_json_bytes


def write_canonical_json(value: object, output_path: Path) -> str:
    """Atomically write one canonical JSON value and return its byte SHA-256.

    Units: values retain their declared units. Time semantics: aware datetimes are
    serialized as UTC ISO-8601 ``Z`` by canonical serialization. Missingness: explicit
    ``None`` becomes JSON ``null``; unsupported or non-finite values raise. The parent
    directory is created when absent. Raises: canonical-serialization or filesystem
    exceptions; no existing output is modified unless the replacement succeeds.
    """

    payload = canonical_json_bytes(value)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=output_path.parent,
            prefix=f".{output_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(payload)
            handle.flush()
            temporary_path = Path(handle.name)
        temporary_path.replace(output_path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
    return hashlib.sha256(payload).hexdigest()


def export_probe_results_file(
    results: Sequence[DataProbeResult],
    output_path: Path,
) -> str:
    """Export sorted, validated probe summaries without raw market data.

    Units: inherited from ``DataProbeResult``.
    Time semantics: aware datetimes serialize as UTC ISO-8601 ``Z``.
    Missingness: an empty result set is rejected; optional observed metadata remains
    JSON ``null``. Raises:
    ``DuplicateIdentifierError``, schema/canonical errors, or filesystem exceptions.
    Returns the SHA-256 of the exact canonical bytes written.
    """

    if not results:
        raise DuplicateIdentifierError("at least one probe result is required for export")
    ordered = tuple(sorted(results, key=lambda result: result.market))
    markets = tuple(result.market for result in ordered)
    if len(markets) != len(set(markets)):
        raise DuplicateIdentifierError("probe result markets must be unique")
    for result in ordered:
        validate_data_probe_result(result)
    return write_canonical_json(
        {
            "artifact_type": "lift_1_reference_futures_data_probe",
            "schema_version": "1.0.0",
            "results": ordered,
        },
        output_path,
    )


__all__ = ("export_probe_results_file", "write_canonical_json")

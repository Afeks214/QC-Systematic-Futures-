from __future__ import annotations

import argparse
import hashlib
import os
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if not (PROJECT_ROOT / "systematic_futures").is_dir():
    raise RuntimeError("Repository package directory is missing")
sys.path.insert(0, str(PROJECT_ROOT))

from systematic_futures.config.research import (  # noqa: E402 - repository script entrypoint
    PROBE_END_DATE,
    PROBE_START_DATE,
    REFERENCE_MARKETS,
    RESEARCH_RANDOM_SEED,
    lift_1_manifest_configuration,
)
from systematic_futures.domain.enums import (  # noqa: E402 - repository script entrypoint
    ResearchEnvironment,
)
from systematic_futures.domain.schemas import (  # noqa: E402 - repository script entrypoint
    ResearchRunManifest,
)
from systematic_futures.domain.serialization import (  # noqa: E402 - repository script entrypoint
    canonical_json_bytes,
)
from systematic_futures.ledger.run_manifest import (  # noqa: E402 - repository script entrypoint
    RunManifestBuilder,
)

DEFAULT_OUTPUT = PROJECT_ROOT / "artifacts/manifests/lift_1_rebuild_check.json"
SOURCE_DOCUMENTS = (
    PROJECT_ROOT / "upload/Institutional_Systematic_Futures_Program_Master_Spec_v1.0(2).docx",
    PROJECT_ROOT / "upload/Intraday_Alpha_Capture_Execution_Extension_v1.0_HE(2).docx",
)
VERIFIED_SOURCE_DOCUMENT_HASHES = {
    "Institutional_Systematic_Futures_Program_Master_Spec_v1.0(2).docx": (
        "ef19e4242a48747ef13b235e38f9c9fa0c09a7ed07085b5bb689be39a8786747"
    ),
    "Intraday_Alpha_Capture_Execution_Extension_v1.0_HE(2).docx": (
        "bdebaf3e0ec38c3cb13d605b1fdc289db0a6316218756d0264ed23856f3195b2"
    ),
}
DEPENDENCY_FILES = (
    PROJECT_ROOT / "pyproject.toml",
    PROJECT_ROOT / "requirements.txt",
)


def parse_created_at(value: str) -> datetime:
    """Parse an explicit ISO-8601 creation time and normalize it to UTC.

    Units: UTC datetime.
    Time semantics: a trailing ``Z`` is accepted; a timezone offset is mandatory.
    Missingness: blank or timezone-naive values are rejected.
    Raises: argparse.ArgumentTypeError for invalid input.
    """
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise argparse.ArgumentTypeError("created-at must be ISO-8601") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("created-at must include a timezone")
    return parsed.astimezone(UTC)


def build_manifest(created_at_utc: datetime) -> ResearchRunManifest:
    """Build the local Lift 1 manifest from explicit project inputs.

    Units: probe dates are ISO calendar dates; seed is dimensionless.
    Time semantics: ``created_at_utc`` is supplied by the composition-root caller.
    Missingness: private specifications may be absent from a public clone; their
    verified digests remain explicit inputs. LEAN version and repository revision
    remain ``None`` because this historical local manifest does not qualify runtime or
    Git evidence. Raises: domain validation errors, FileNotFoundError for an incomplete
    private-document mount, or RuntimeError if mounted bytes disagree with the verified
    digest.
    """
    _verify_mounted_source_documents()
    return RunManifestBuilder().build(
        environment=ResearchEnvironment.LOCAL,
        created_at_utc=created_at_utc,
        configuration=lift_1_manifest_configuration(),
        source_document_paths=(),
        source_document_hashes=VERIFIED_SOURCE_DOCUMENT_HASHES,
        dependency_files=DEPENDENCY_FILES,
        reference_markets=REFERENCE_MARKETS,
        probe_start_date=PROBE_START_DATE,
        probe_end_date=PROBE_END_DATE,
        lean_version=None,
        repository_revision=None,
        random_seed=RESEARCH_RANDOM_SEED,
    )


def _verify_mounted_source_documents() -> None:
    present = tuple(path.is_file() for path in SOURCE_DOCUMENTS)
    if not any(present):
        return
    if not all(present):
        missing = SOURCE_DOCUMENTS[present.index(False)]
        raise FileNotFoundError(missing)
    for path in SOURCE_DOCUMENTS:
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        expected = VERIFIED_SOURCE_DOCUMENT_HASHES[path.name]
        if actual != expected:
            raise RuntimeError(f"Private source-document digest mismatch: {path.name}")


def write_manifest(manifest: object, output_path: Path) -> None:
    """Atomically write one canonical manifest JSON document.

    Units: values and timestamps retain manifest semantics.
    Time semantics: no timestamp is generated or rewritten here.
    Missingness: parent directories are created; no missing field is filled.
    Raises: OSError for filesystem failures and domain serialization errors.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=output_path.parent,
        prefix=f".{output_path.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(canonical_json_bytes(manifest) + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary_path.replace(output_path)
    except OSError:
        temporary_path.unlink(missing_ok=True)
        raise


def main() -> int:
    """Build the manifest and return a process status code.

    Units: CLI `--created-at` is an ISO-8601 instant.
    Time semantics: absent `--created-at` uses the explicit composition-root wall
    clock; the builder itself never obtains current time.
    Missingness: output defaults to a disposable rebuild-check path so the immutable
    historical `lift_1_manifest.json` is never overwritten by a quality command.
    Raises: argparse, domain, and filesystem errors are surfaced to the caller.
    """
    parser = argparse.ArgumentParser(description="Build the deterministic Lift 1 manifest")
    parser.add_argument("--created-at", type=parse_created_at)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    arguments = parser.parse_args()
    created_at = cast(datetime | None, arguments.created_at)
    output_path = cast(Path, arguments.output)
    if created_at is None:
        created_at = datetime.now(UTC)
    manifest = build_manifest(created_at)
    write_manifest(manifest, output_path)
    print(f"Manifest written: {output_path}")
    print(f"Manifest hash: {manifest.manifest_hash}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

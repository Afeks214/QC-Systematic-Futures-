from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if not (PROJECT_ROOT / "systematic_futures").is_dir():
    raise RuntimeError("Repository package directory is missing")
sys.path.insert(0, str(PROJECT_ROOT))

from systematic_futures.config.feature_semantics import (  # noqa: E402
    feature_semantics_v3,
    feature_semantics_v4,
)
from systematic_futures.config.markets import all_market_definitions  # noqa: E402
from systematic_futures.config.research import (  # noqa: E402 - repository script entrypoint
    PROBE_END_DATE,
    PROBE_START_DATE,
    REFERENCE_MARKETS,
    RESEARCH_RANDOM_SEED,
    lift_1_manifest_configuration,
    lift_2_measurement_configuration,
)
from systematic_futures.data.sessions import (  # noqa: E402
    reference_session_policies,
)
from systematic_futures.domain.enums import (  # noqa: E402 - repository script entrypoint
    ResearchEnvironment,
)
from systematic_futures.domain.schemas import (  # noqa: E402 - repository script entrypoint
    ResearchRunManifest,
)
from systematic_futures.domain.serialization import (  # noqa: E402 - repository script entrypoint
    canonical_json_bytes,
    sha256_hex,
)
from systematic_futures.ledger.run_manifest import (  # noqa: E402 - repository script entrypoint
    RunManifestBuilder,
)

DEFAULT_OUTPUT = PROJECT_ROOT / "artifacts/manifests/lift_2_rebuild_check.json"
LIFT1_DEFAULT_OUTPUT = PROJECT_ROOT / "artifacts/manifests/lift_1_rebuild_check.json"
LIFT2_MANIFEST = PROJECT_ROOT / "artifacts/manifests/lift_2_manifest.json"
LIFT2_RUNTIME_EVIDENCE = PROJECT_ROOT / "artifacts/certification/lift2_runtime_measurement.json"
LIFT2_COVERAGE_EVIDENCE = PROJECT_ROOT / "artifacts/certification/lift2_candidate_coverage.json"
LIFT2_EVIDENCE_INDEX = PROJECT_ROOT / "artifacts/certification/lift_2_evidence_index.json"
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
INDICATOR_SPECIFICATION_HASHES = {
    "IAE-Full-Research-Specification.docx": (
        "b62e43a2195215475c2431e0840a5b1fa59ee0a8501d473b0ed50e7d34d61f91"
    ),
    "ICM-Full-Research-Specification.docx": (
        "487ffd40cd2c15c66bd2c003d36a72f99587cf3176fe0ec44bf011bbbb18ec26"
    ),
    "IMSI_Research_Notebook_Specification.docx": (
        "1adb0dd434e8c830e42e8c9a0f60e224f28200c5de03fec9fcf3fcc1efbcfa59"
    ),
}
DEPENDENCY_FILES = (
    PROJECT_ROOT / "pyproject.toml",
    PROJECT_ROOT / "requirements.txt",
)
LIFT2_RUNTIME_SOURCE_FILES = (
    PROJECT_ROOT / "main.py",
    PROJECT_ROOT / "systematic_futures/__init__.py",
    PROJECT_ROOT / "systematic_futures/config/__init__.py",
    PROJECT_ROOT / "systematic_futures/config/markets.py",
    PROJECT_ROOT / "systematic_futures/config/research.py",
    PROJECT_ROOT / "systematic_futures/data/__init__.py",
    PROJECT_ROOT / "systematic_futures/data/point_in_time.py",
    PROJECT_ROOT / "systematic_futures/data/policies.py",
    PROJECT_ROOT / "systematic_futures/data/quality.py",
    PROJECT_ROOT / "systematic_futures/data/rolls.py",
    PROJECT_ROOT / "systematic_futures/data/sessions.py",
    PROJECT_ROOT / "systematic_futures/domain/__init__.py",
    PROJECT_ROOT / "systematic_futures/domain/enums.py",
    PROJECT_ROOT / "systematic_futures/domain/errors.py",
    PROJECT_ROOT / "systematic_futures/domain/identifiers.py",
    PROJECT_ROOT / "systematic_futures/domain/schemas.py",
    PROJECT_ROOT / "systematic_futures/domain/serialization.py",
    *sorted((PROJECT_ROOT / "systematic_futures/measurement").glob("*.py")),
    PROJECT_ROOT / "systematic_futures/qc_adapters/__init__.py",
    PROJECT_ROOT / "systematic_futures/qc_adapters/lift2_runtime.py",
    PROJECT_ROOT / "systematic_futures/qc_adapters/futures_registration.py",
    PROJECT_ROOT / "systematic_futures/qc_adapters/probe_recorder.py",
    PROJECT_ROOT / "systematic_futures/research_lib/__init__.py",
    PROJECT_ROOT / "systematic_futures/research_lib/certification.py",
    PROJECT_ROOT / "systematic_futures/config/feature_semantics.py",
    PROJECT_ROOT / "systematic_futures/domain/research_contracts.py",
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


def lift2_source_contract() -> dict[str, object]:
    """Return deterministic hashes for the current Lift 2 policy and runtime files.

    Units: SHA-256 digests and the installed NumPy version. Time semantics: no wall
    clock is read. Missingness: every authorized runtime file must exist. Raises:
    ``OSError`` or canonical-serialization errors.
    """

    source_hashes = {
        str(path.relative_to(PROJECT_ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in LIFT2_RUNTIME_SOURCE_FILES
    }
    from systematic_futures.measurement.profile import DEFAULT_PROFILE_DEFINITION

    return {
        "feature_semantics_v3_hash": sha256_hex(feature_semantics_v3()),
        "feature_semantics_v4_hash": sha256_hex(feature_semantics_v4()),
        "indicator_specification_hashes": INDICATOR_SPECIFICATION_HASHES,
        "market_registry_hash": sha256_hex(all_market_definitions()),
        "measurement_policy_hash": sha256_hex(lift_2_measurement_configuration()),
        "numpy_version": np.__version__,
        "profile_definition_hash": sha256_hex(DEFAULT_PROFILE_DEFINITION),
        "runtime_source_file_hashes": source_hashes,
        "runtime_source_tree_hash": sha256_hex(source_hashes),
        "session_policy_hash": sha256_hex(reference_session_policies()),
    }


def build_lift2_rebuild_check() -> dict[str, object]:
    """Build a disposable source/evidence validation record for the quality gate.

    Units: hashes and validation status. Time semantics: deterministic and clock-free.
    Missingness: absent final artifacts are reported as source-ready evidence pending;
    a partially present final set raises. Raises: evidence/hash validation errors.
    """

    contract = lift2_source_contract()
    required = (
        LIFT2_MANIFEST,
        LIFT2_RUNTIME_EVIDENCE,
        LIFT2_COVERAGE_EVIDENCE,
        LIFT2_EVIDENCE_INDEX,
    )
    present = tuple(path.is_file() for path in required)
    if any(present) and not all(present):
        missing = [
            str(path.relative_to(PROJECT_ROOT))
            for path, exists in zip(required, present, strict=True)
            if not exists
        ]
        raise RuntimeError(f"partial Lift 2 evidence set; missing {missing}")
    if all(present):
        _validate_lift2_final_evidence(contract)
        status = "PASS_FINAL_EVIDENCE_VALIDATED"
    else:
        status = "PASS_SOURCE_READY_RUNTIME_EVIDENCE_PENDING"
    payload: dict[str, object] = {
        "schema_version": "lift2-rebuild-check-v1",
        "source_contract": contract,
        "status": status,
    }
    payload["content_hash"] = sha256_hex(payload)
    return payload


def _validate_lift2_final_evidence(source_contract: dict[str, object]) -> None:
    manifest = _read_and_validate_content_hash(LIFT2_MANIFEST)
    runtime = _read_and_validate_content_hash(LIFT2_RUNTIME_EVIDENCE)
    coverage = _read_and_validate_content_hash(LIFT2_COVERAGE_EVIDENCE)
    _read_and_validate_content_hash(LIFT2_EVIDENCE_INDEX)
    for field_name in (
        "feature_semantics_v3_hash",
        "feature_semantics_v4_hash",
        "indicator_specification_hashes",
        "market_registry_hash",
        "measurement_policy_hash",
        "numpy_version",
        "profile_definition_hash",
        "runtime_source_file_hashes",
        "runtime_source_tree_hash",
        "session_policy_hash",
    ):
        if manifest.get(field_name) != source_contract[field_name]:
            raise RuntimeError(f"Lift 2 manifest current-source mismatch: {field_name}")
    if manifest.get("runtime_measurement_hash") != runtime["content_hash"]:
        raise RuntimeError("Lift 2 runtime measurement hash mismatch")
    if manifest.get("candidate_coverage_hash") != coverage["content_hash"]:
        raise RuntimeError("Lift 2 candidate coverage hash mismatch")
    for field_name in (
        "source_git_sha",
        "evidence_git_sha",
        "qc_project_id",
        "qc_build_ids",
        "qc_backtest_ids",
        "lean_version",
        "python_version",
        "test_result_hash",
    ):
        if not manifest.get(field_name):
            raise RuntimeError(f"Lift 2 manifest field is missing: {field_name}")


def _read_and_validate_content_hash(path: Path) -> dict[str, object]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise RuntimeError(f"evidence root must be an object: {path.name}")
    document = cast(dict[str, object], raw)
    expected = document.get("content_hash")
    if not isinstance(expected, str) or len(expected) != 64:
        raise RuntimeError(f"evidence content_hash is invalid: {path.name}")
    payload = dict(document)
    del payload["content_hash"]
    if sha256_hex(payload) != expected:
        raise RuntimeError(f"evidence content_hash mismatch: {path.name}")
    return document


def main() -> int:
    """Build the manifest and return a process status code.

    Units: CLI `--created-at` is an ISO-8601 instant.
    Time semantics: absent `--created-at` uses the explicit composition-root wall
    clock; the builder itself never obtains current time.
    Missingness: output defaults to a disposable rebuild-check path so the immutable
    historical `lift_1_manifest.json` is never overwritten by a quality command.
    Raises: argparse, domain, and filesystem errors are surfaced to the caller.
    """
    parser = argparse.ArgumentParser(description="Build or validate a deterministic lift manifest")
    parser.add_argument("--lift", choices=("1", "2"), default="2")
    parser.add_argument("--created-at", type=parse_created_at)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    arguments = parser.parse_args()
    lift = cast(str, arguments.lift)
    created_at = cast(datetime | None, arguments.created_at)
    output_path = cast(Path, arguments.output)
    if lift == "2":
        check = build_lift2_rebuild_check()
        write_manifest(check, output_path)
        source_contract = cast(dict[str, object], check["source_contract"])
        print(f"Lift 2 rebuild check written: {output_path}")
        print(f"Lift 2 source tree hash: {source_contract['runtime_source_tree_hash']}")
        print(f"Lift 2 evidence status: {check['status']}")
        return 0
    if output_path == DEFAULT_OUTPUT:
        output_path = LIFT1_DEFAULT_OUTPUT
    if created_at is None:
        created_at = datetime.now(UTC)
    manifest = build_manifest(created_at)
    write_manifest(manifest, output_path)
    print(f"Manifest written: {output_path}")
    print(f"Manifest hash: {manifest.manifest_hash}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

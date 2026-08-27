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
    feature_semantics_v5,
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
LIFT2_MATH_EVIDENCE = PROJECT_ROOT / "artifacts/certification/lift2_math_certification.json"
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
    *sorted(
        path
        for path in (PROJECT_ROOT / "systematic_futures/measurement").glob("*.py")
        if path.name not in {"profile.py", "types.py"}
    ),
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
        "feature_semantics_v5_hash": sha256_hex(feature_semantics_v5()),
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
        LIFT2_MATH_EVIDENCE,
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
    evidence_index = _read_and_validate_content_hash(LIFT2_EVIDENCE_INDEX)
    math = _read_and_validate_content_hash(LIFT2_MATH_EVIDENCE)
    _validate_lift2_runtime_evidence(runtime)
    _validate_lift2_coverage_evidence(coverage, runtime)
    _validate_lift2_math_evidence(math)
    for field_name in (
        "feature_semantics_v3_hash",
        "feature_semantics_v4_hash",
        "feature_semantics_v5_hash",
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
    if manifest.get("math_certification_hash") != math["content_hash"]:
        raise RuntimeError("Lift 2 math certification hash mismatch")
    if manifest.get("source_git_sha") != math["source_git_sha"]:
        raise RuntimeError("Lift 2 math certification source SHA mismatch")
    indexed_hashes = evidence_index.get("artifact_hashes")
    expected_hashes = {
        "lift2_candidate_coverage.json": coverage["content_hash"],
        "lift2_math_certification.json": math["content_hash"],
        "lift2_runtime_measurement.json": runtime["content_hash"],
    }
    if indexed_hashes != expected_hashes:
        raise RuntimeError("Lift 2 evidence index artifact hashes mismatch")
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


def _validate_lift2_runtime_evidence(document: dict[str, object]) -> None:
    expected_runs = {
        *(("deep", root) for root in ("ES", "ZN", "6E")),
        *(("smoke", root) for root in ("ES", "NQ", "RTY", "ZT", "ZN", "6E", "6J", "6B")),
    }
    raw_runs = document.get("runs")
    if not isinstance(raw_runs, list):
        raise RuntimeError("Lift 2 runtime evidence runs must be a list")
    runs = cast(list[object], raw_runs)
    if len(runs) != len(expected_runs):
        raise RuntimeError("Lift 2 runtime evidence must contain 3 deep and 8 smoke runs")
    observed_runs: set[tuple[str, str]] = set()
    build_ids: set[str] = set()
    backtest_ids: set[str] = set()
    for raw_run in runs:
        if not isinstance(raw_run, dict):
            raise RuntimeError("Lift 2 runtime run must be an object")
        run = cast(dict[str, object], raw_run)
        mode = run.get("mode")
        root = run.get("root")
        if not isinstance(mode, str) or not isinstance(root, str):
            raise RuntimeError("Lift 2 runtime run requires text mode and root")
        observed_runs.add((mode, root))
        if run.get("status") != "COMPLETED":
            raise RuntimeError(f"Lift 2 runtime run did not complete: {mode}/{root}")
        for field_name in ("build_id", "backtest_id", "backtest_name"):
            value = run.get(field_name)
            if not isinstance(value, str) or not value:
                raise RuntimeError(f"Lift 2 runtime field is missing: {mode}/{root}/{field_name}")
        build_ids.add(cast(str, run["build_id"]))
        backtest_id = cast(str, run["backtest_id"])
        if backtest_id in backtest_ids:
            raise RuntimeError(f"Lift 2 runtime backtest ID is duplicated: {backtest_id}")
        backtest_ids.add(backtest_id)
        expected_period = (
            {"start": "2024-02-15", "end": "2024-03-25"}
            if mode == "deep"
            else {"start": "2024-03-04", "end": "2024-03-06"}
        )
        if run.get("period") != expected_period:
            raise RuntimeError(f"Lift 2 runtime period mismatch: {mode}/{root}")
        for field_name in ("contract_count", "chain_observations"):
            _require_positive_count(run, field_name, mode, root)
        contracts = run.get("contracts")
        if not isinstance(contracts, list):
            raise RuntimeError(f"Lift 2 runtime contracts are missing: {mode}/{root}")
        contract_names = cast(list[object], contracts)
        if any(not isinstance(item, str) or not item for item in contract_names):
            raise RuntimeError(f"Lift 2 runtime contracts are invalid: {mode}/{root}")
        validated_contract_names = cast(list[str], contract_names)
        if len(validated_contract_names) != run["contract_count"] or (
            validated_contract_names != sorted(set(validated_contract_names))
        ):
            raise RuntimeError(f"Lift 2 runtime contracts are invalid: {mode}/{root}")
        counts = run.get("counts")
        if not isinstance(counts, dict):
            raise RuntimeError(f"Lift 2 runtime counts are missing: {mode}/{root}")
        count_map = cast(dict[str, object], counts)
        for field_name in (
            "trade_ticks",
            "five_minute_bars",
            "thirty_minute_bars",
            "developing_profiles",
            "auction_snapshots",
            "iae_snapshots",
            "unique_sessions",
        ):
            _require_positive_count(count_map, field_name, mode, root)
        if mode == "deep":
            for field_name in (
                "final_profiles",
                "imsi_snapshots",
                "icm_snapshots",
                "icm_ready",
                "candidate_events",
            ):
                _require_positive_count(count_map, field_name, mode, root)
        zero_actions = run.get("zero_actions")
        if zero_actions != {"insights": 0, "orders": 0, "portfolio_targets": 0}:
            raise RuntimeError(f"Lift 2 zero-action invariant failed: {mode}/{root}")
        for field_name in ("measurement_hash", "coverage_hash"):
            value = run.get(field_name)
            if not isinstance(value, str) or not _is_lower_hex(value, 64):
                raise RuntimeError(f"Lift 2 runtime hash is invalid: {mode}/{root}/{field_name}")
    if observed_runs != expected_runs:
        raise RuntimeError("Lift 2 runtime evidence run matrix mismatch")
    if document.get("qc_build_ids") != sorted(build_ids):
        raise RuntimeError("Lift 2 runtime build ID summary mismatch")
    if document.get("qc_backtest_ids") != sorted(backtest_ids):
        raise RuntimeError("Lift 2 runtime backtest ID summary mismatch")


def _validate_lift2_coverage_evidence(
    document: dict[str, object],
    runtime: dict[str, object],
) -> None:
    if _contains_forbidden_economic_key(document):
        raise RuntimeError("Lift 2 coverage evidence contains an economic outcome field")
    raw_runs = document.get("runs")
    raw_runtime_runs = runtime.get("runs")
    if not isinstance(raw_runs, list) or not isinstance(raw_runtime_runs, list):
        raise RuntimeError("Lift 2 coverage/runtime run lists are missing")
    runs = cast(list[object], raw_runs)
    runtime_runs = cast(list[object], raw_runtime_runs)
    runtime_hashes: dict[tuple[object, object, object], object] = {}
    for raw_runtime_run in runtime_runs:
        if not isinstance(raw_runtime_run, dict):
            raise RuntimeError("Lift 2 runtime run must be an object")
        runtime_run = cast(dict[str, object], raw_runtime_run)
        runtime_key = (
            runtime_run.get("mode"),
            runtime_run.get("root"),
            runtime_run.get("backtest_id"),
        )
        runtime_hashes[runtime_key] = runtime_run.get("coverage_hash")
    observed_hashes: dict[tuple[object, object, object], object] = {}
    for raw_run in runs:
        if not isinstance(raw_run, dict):
            raise RuntimeError("Lift 2 coverage run must be an object")
        run = cast(dict[str, object], raw_run)
        key = (run.get("mode"), run.get("root"), run.get("backtest_id"))
        observed_hashes[key] = run.get("coverage_hash")
        raw_coverage = run.get("coverage")
        if not isinstance(raw_coverage, dict):
            raise RuntimeError(f"Lift 2 coverage payload is missing: {key}")
        coverage = cast(dict[str, object], raw_coverage)
        raw_count = coverage.get("raw_event_count")
        unique_count = coverage.get("unique_event_count")
        if raw_count != unique_count:
            raise RuntimeError(f"Lift 2 candidate events are not unique: {key}")
        required_quality_counts = (
            "candidate_events_total",
            "candidate_events_inputs_present",
            "candidate_events_inputs_ready",
            "candidate_events_not_ready",
            "candidate_events_missing_imsi",
            "candidate_events_missing_icm",
            "candidate_events_missing_iae",
        )
        if any(
            isinstance(coverage.get(field), bool)
            or not isinstance(coverage.get(field), int)
            or cast(int, coverage[field]) < 0
            for field in required_quality_counts
        ):
            raise RuntimeError(f"Lift 2 coverage readiness counts are invalid: {key}")
        if coverage["candidate_events_total"] != unique_count:
            raise RuntimeError(f"Lift 2 coverage total does not match unique events: {key}")
        if (
            cast(int, coverage["candidate_events_inputs_ready"])
            + cast(int, coverage["candidate_events_not_ready"])
            != unique_count
        ):
            raise RuntimeError(f"Lift 2 readiness counts do not reconcile: {key}")
        if coverage.get("quality_blocked_events") != coverage["candidate_events_not_ready"]:
            raise RuntimeError(f"Lift 2 blocked-event alias does not reconcile: {key}")
    if observed_hashes != runtime_hashes:
        raise RuntimeError("Lift 2 coverage hashes do not reconcile to runtime evidence")


def _require_positive_count(
    values: dict[str, object],
    field_name: str,
    mode: str,
    root: str,
) -> None:
    value = values.get(field_name)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise RuntimeError(f"Lift 2 runtime count must be positive: {mode}/{root}/{field_name}")


def _contains_forbidden_economic_key(value: object) -> bool:
    forbidden = {"pnl", "profit", "return", "returns", "sharpe"}
    if isinstance(value, dict):
        mapping = cast(dict[object, object], value)
        return any(
            str(key).lower() in forbidden or _contains_forbidden_economic_key(item)
            for key, item in mapping.items()
        )
    if isinstance(value, list):
        return any(_contains_forbidden_economic_key(item) for item in cast(list[object], value))
    return False


def _validate_lift2_math_evidence(document: dict[str, object]) -> None:
    required_fields = {
        "source_git_sha",
        "specification_hashes",
        "profile_definition_version",
        "IMSI_math_version",
        "ICM_math_version",
        "IAE_math_version",
        "analytic_test_count",
        "differential_test_count",
        "metamorphic_test_count",
        "causality_test_count",
        "stress_test_count",
        "all_passed",
        "reference_vector_hash",
        "prefix_equivalence_hash",
        "qc_parity_hash",
        "content_hash",
    }
    if set(document) != required_fields:
        raise RuntimeError("Lift 2 math certification fields do not match the directive")
    if document.get("specification_hashes") != INDICATOR_SPECIFICATION_HASHES:
        raise RuntimeError("Lift 2 math certification specification hashes mismatch")
    if document.get("all_passed") is not True:
        raise RuntimeError("Lift 2 math certification is not passing")
    expected_counts = {
        "analytic_test_count": 19,
        "differential_test_count": 9,
        "metamorphic_test_count": 14,
        "causality_test_count": 13,
        "stress_test_count": 19,
    }
    for field_name, expected in expected_counts.items():
        if document.get(field_name) != expected:
            raise RuntimeError(f"Lift 2 math certification count mismatch: {field_name}")
    source_git_sha = document.get("source_git_sha")
    if not isinstance(source_git_sha, str) or not _is_lower_hex(source_git_sha, 40):
        raise RuntimeError("Lift 2 math certification source_git_sha is invalid")
    for field_name in (
        "profile_definition_version",
        "IMSI_math_version",
        "ICM_math_version",
        "IAE_math_version",
    ):
        value = document.get(field_name)
        if not isinstance(value, str) or not value:
            raise RuntimeError(f"Lift 2 math certification field is missing: {field_name}")
    for field_name in (
        "reference_vector_hash",
        "prefix_equivalence_hash",
        "qc_parity_hash",
    ):
        value = document.get(field_name)
        if not isinstance(value, str) or not _is_lower_hex(value, 64):
            raise RuntimeError(f"Lift 2 math certification hash is invalid: {field_name}")


def _is_lower_hex(value: str, length: int) -> bool:
    return len(value) == length and all(character in "0123456789abcdef" for character in value)


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

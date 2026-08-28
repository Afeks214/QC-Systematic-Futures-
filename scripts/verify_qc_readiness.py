from __future__ import annotations

import argparse
import ast
import base64
import hashlib
import json
import os
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

PROJECT_ROOT = Path(__file__).resolve().parents[1]
QC_API_BASE = "https://www.quantconnect.com/api/v2"
QC_PROJECT_ID = 35697180
QUALIFICATION_PATH = PROJECT_ROOT / "artifacts/certification/lift2_readiness_qualification.json"
READINESS_MANIFEST_PATH = PROJECT_ROOT / "artifacts/manifests/lift_2_readiness_manifest.json"
PREVIOUS_LIFT2_MANIFEST_PATH = PROJECT_ROOT / "artifacts/manifests/lift_2_manifest.json"
MATH_CERTIFICATION_PATH = PROJECT_ROOT / "artifacts/certification/lift2_math_certification.json"

_EXPLICIT_RUNTIME_FILES = (
    "main.py",
    "systematic_futures/__init__.py",
    "systematic_futures/config/__init__.py",
    "systematic_futures/config/markets.py",
    "systematic_futures/config/research.py",
    "systematic_futures/data/__init__.py",
    "systematic_futures/data/point_in_time.py",
    "systematic_futures/data/policies.py",
    "systematic_futures/data/quality.py",
    "systematic_futures/data/rolls.py",
    "systematic_futures/data/sessions.py",
    "systematic_futures/domain/__init__.py",
    "systematic_futures/domain/enums.py",
    "systematic_futures/domain/errors.py",
    "systematic_futures/domain/identifiers.py",
    "systematic_futures/domain/schemas.py",
    "systematic_futures/domain/serialization.py",
    "systematic_futures/qc_adapters/__init__.py",
    "systematic_futures/qc_adapters/lift2_runtime.py",
    "systematic_futures/qc_adapters/futures_registration.py",
    "systematic_futures/qc_adapters/probe_recorder.py",
    "systematic_futures/research_lib/__init__.py",
    "systematic_futures/research_lib/certification.py",
    "systematic_futures/config/feature_semantics.py",
    "systematic_futures/domain/research_contracts.py",
)
_MATRIX = (
    *((root, "readiness") for root in ("ES", "ZN", "6E")),
    *((root, "smoke") for root in ("ES", "NQ", "RTY", "ZT", "ZN", "6E", "6J", "6B")),
)
_READINESS_COUNT_FIELDS = (
    "candidate_events_total",
    "candidate_events_base_ready",
    "candidate_events_imsi_ready",
    "candidate_events_icm_ready",
    "candidate_events_iae_structural_ready",
    "candidate_events_iae_score_ready",
)


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _content_hash(value: object) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def qc_post(endpoint: str, payload: Mapping[str, object]) -> Mapping[str, object]:
    """Call one official QuantConnect v2 POST endpoint without exposing credentials."""

    user_id = os.environ.get("QC_USER_ID")
    api_token = os.environ.get("QC_API_TOKEN")
    if not user_id or not api_token:
        raise RuntimeError("QC_USER_ID and QC_API_TOKEN must be present in the environment")
    normalized_endpoint = endpoint.strip("/")
    if not normalized_endpoint:
        raise RuntimeError("QC endpoint must be non-blank")
    timestamp = str(int(time.time()))
    token_hash = hashlib.sha256(f"{api_token}:{timestamp}".encode()).hexdigest()
    encoded_auth = base64.b64encode(f"{user_id}:{token_hash}".encode()).decode("ascii")
    request = urllib.request.Request(
        f"{QC_API_BASE}/{normalized_endpoint}",
        data=_canonical_json_bytes(dict(payload)),
        headers={
            "Authorization": f"Basic {encoded_auth}",
            "Content-Type": "application/json",
            "Timestamp": timestamp,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            decoded: object = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"QC API {normalized_endpoint} returned HTTP {error.code}: {body}"
        ) from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"QC API {normalized_endpoint} request failed") from error
    if not isinstance(decoded, dict):
        raise RuntimeError(f"QC API {normalized_endpoint} returned a non-object response")
    result = cast(dict[str, object], decoded)
    if result.get("success") is not True:
        errors = result.get("errors")
        raise RuntimeError(f"QC API {normalized_endpoint} failed: {errors!r}")
    return result


def _runtime_file_names() -> tuple[str, ...]:
    measurement_files = tuple(
        str(path.relative_to(PROJECT_ROOT))
        for path in sorted((PROJECT_ROOT / "systematic_futures/measurement").glob("*.py"))
        if path.name not in {"profile.py", "types.py"}
    )
    names = (*_EXPLICIT_RUNTIME_FILES[:17], *measurement_files, *_EXPLICIT_RUNTIME_FILES[17:])
    if names != tuple(sorted(set(names), key=names.index)):
        raise RuntimeError("authorized runtime file set contains duplicate paths")
    return names


def _source_hashes_from_bytes(files: Mapping[str, bytes]) -> dict[str, str]:
    expected_names = _runtime_file_names()
    if set(files) != set(expected_names):
        missing = sorted(set(expected_names) - set(files))
        extra = sorted(set(files) - set(expected_names))
        raise RuntimeError(f"runtime file-set mismatch; missing={missing}, extra={extra}")
    return {name: hashlib.sha256(files[name]).hexdigest() for name in expected_names}


def _local_runtime_source() -> tuple[dict[str, bytes], dict[str, str], str]:
    files = {name: (PROJECT_ROOT / name).read_bytes() for name in _runtime_file_names()}
    hashes = _source_hashes_from_bytes(files)
    return files, hashes, _content_hash(hashes)


def _read_qc_project_files() -> dict[str, str]:
    result = qc_post("files/read", {"projectId": QC_PROJECT_ID})
    raw_files = result.get("files")
    if not isinstance(raw_files, list):
        raise RuntimeError("QC files/read response has no files list")
    files: dict[str, str] = {}
    for raw_file in cast(list[object], raw_files):
        if not isinstance(raw_file, dict):
            raise RuntimeError("QC files/read returned a non-object file")
        item = cast(dict[str, object], raw_file)
        name = item.get("name")
        content = item.get("content")
        if not isinstance(name, str) or not isinstance(content, str):
            raise RuntimeError("QC project file lacks text name/content")
        if name in files:
            raise RuntimeError(f"QC project returned duplicate file name: {name}")
        files[name] = content
    return files


def _qc_runtime_source_hash(project_files: Mapping[str, str]) -> tuple[dict[str, str], str]:
    authorized = {
        name: project_files[name].encode("utf-8")
        for name in _runtime_file_names()
        if name in project_files
    }
    hashes = _source_hashes_from_bytes(authorized)
    return hashes, _content_hash(hashes)


def _upload_runtime_source(local_files: Mapping[str, bytes]) -> None:
    remote_files = _read_qc_project_files()
    for name in _runtime_file_names():
        content = local_files[name].decode("utf-8")
        if name not in remote_files:
            endpoint = "files/create"
        elif remote_files[name] != content:
            endpoint = "files/update"
        else:
            continue
        qc_post(
            endpoint,
            {
                "projectId": QC_PROJECT_ID,
                "name": name,
                "content": content,
                "codeSourceId": "Lift 2 readiness verifier",
            },
        )


def _git_sha() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _portfolio_target_source_evidence() -> Mapping[str, object]:
    forbidden_calls = {"PortfolioTarget", "PortfolioConstructionModel", "create_targets"}
    forbidden_dynamic_calls = {"eval", "exec", "__import__"}
    violations: list[str] = []
    file_hashes: dict[str, str] = {}
    for name in _runtime_file_names():
        if not name.endswith(".py"):
            continue
        source = (PROJECT_ROOT / name).read_text(encoding="utf-8")
        file_hashes[name] = hashlib.sha256(source.encode()).hexdigest()
        tree = ast.parse(source, filename=name)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                call_name: str | None = None
                if isinstance(node.func, ast.Name):
                    call_name = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    call_name = node.func.attr
                if call_name in forbidden_calls | forbidden_dynamic_calls:
                    violations.append(f"{name}:{node.lineno}:{call_name}")
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name in forbidden_calls:
                        violations.append(f"{name}:{node.lineno}:import:{alias.name}")
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                if node.value in forbidden_calls:
                    violations.append(f"{name}:{node.lineno}:dynamic-string:{node.value}")
    if violations:
        raise RuntimeError(f"PortfolioTarget source-static invariant failed: {violations}")
    evidence: dict[str, object] = {
        "classification": "SOURCE-STATIC ZERO",
        "runtime_python_file_hashes": file_hashes,
        "violations": violations,
    }
    evidence["evidence_hash"] = _content_hash(evidence)
    return evidence


def _poll_compile(compile_id: str, timeout_seconds: int) -> Mapping[str, object]:
    deadline = time.monotonic() + timeout_seconds
    while True:
        result = qc_post(
            "compile/read",
            {"projectId": QC_PROJECT_ID, "compileId": compile_id},
        )
        state = result.get("state")
        if state == "BuildSuccess":
            return result
        if state == "BuildError":
            raise RuntimeError(f"QC compilation failed: {result.get('logs')!r}")
        if time.monotonic() >= deadline:
            raise RuntimeError("QC compilation timed out")
        time.sleep(5)


def _backtest_from_response(result: Mapping[str, object]) -> dict[str, object]:
    raw_backtest = result.get("backtest")
    if not isinstance(raw_backtest, dict):
        raise RuntimeError("QC backtest response has no backtest object")
    return cast(dict[str, object], raw_backtest)


def _backtest_id(result: Mapping[str, object]) -> str:
    backtest = _backtest_from_response(result)
    value = backtest.get("backtestId")
    if not isinstance(value, str) or not value:
        raise RuntimeError("QC backtest create response has no backtestId")
    return value


def _poll_backtests(
    created: Sequence[tuple[str, str, str]], timeout_seconds: int
) -> dict[str, dict[str, object]]:
    pending = {backtest_id for _, _, backtest_id in created}
    completed: dict[str, dict[str, object]] = {}
    deadline = time.monotonic() + timeout_seconds
    while pending:
        for backtest_id in tuple(sorted(pending)):
            result = qc_post(
                "backtests/read",
                {"projectId": QC_PROJECT_ID, "backtestId": backtest_id},
            )
            backtest = _backtest_from_response(result)
            if backtest.get("completed") is True:
                error = backtest.get("error") or backtest.get("stackTrace")
                if error:
                    raise RuntimeError(f"QC backtest {backtest_id} completed with error: {error}")
                completed[backtest_id] = backtest
                pending.remove(backtest_id)
        if not pending:
            break
        if time.monotonic() >= deadline:
            raise RuntimeError(f"QC backtests timed out: {sorted(pending)}")
        time.sleep(15)
    return completed


def _statistics(backtest: Mapping[str, object]) -> dict[str, object]:
    merged: dict[str, object] = {}
    for field_name in ("statistics", "runtimeStatistics"):
        raw = backtest.get(field_name)
        if isinstance(raw, dict):
            merged.update(cast(dict[str, object], raw))
    return merged


def _coverage(backtest: Mapping[str, object]) -> dict[str, object]:
    raw = _statistics(backtest).get("L2.Coverage")
    if not isinstance(raw, str):
        raise RuntimeError("completed QC backtest is missing L2.Coverage summary evidence")
    decoded: object = json.loads(raw)
    if not isinstance(decoded, dict):
        raise RuntimeError("L2.Coverage summary is not an object")
    return cast(dict[str, object], decoded)


def _api_zero_count(endpoint: str, collection_name: str, backtest_id: str) -> tuple[int, str]:
    result = qc_post(
        endpoint,
        {
            "projectId": QC_PROJECT_ID,
            "backtestId": backtest_id,
            "start": 0,
            "end": 1,
        },
    )
    collection = result.get(collection_name)
    if not isinstance(collection, list):
        raise RuntimeError(f"QC {endpoint} response lacks {collection_name}")
    count = len(cast(list[object], collection))
    reported_length = result.get("length")
    if isinstance(reported_length, int) and not isinstance(reported_length, bool):
        if reported_length != count:
            raise RuntimeError(f"QC {endpoint} count disagrees with returned collection")
    if count != 0:
        raise RuntimeError(f"QC {endpoint} returned {count} records for {backtest_id}")
    return count, _content_hash(result)


def _positive_int(mapping: Mapping[str, object], field_name: str, run_name: str) -> int:
    value = mapping.get(field_name)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise RuntimeError(f"{run_name} requires positive {field_name}; received {value!r}")
    return value


def _validate_readiness_coverage(root: str, coverage: Mapping[str, object]) -> Mapping[str, object]:
    counts = {
        field_name: _positive_int(coverage, field_name, f"{root}/readiness")
        for field_name in _READINESS_COUNT_FIELDS
    }
    raw_blocking = coverage.get("blocking_reason_counts")
    raw_informational = coverage.get("informational_reason_counts")
    if not isinstance(raw_blocking, dict) or not isinstance(raw_informational, dict):
        raise RuntimeError(f"{root}/readiness lacks quality-reason decomposition")
    blocking = cast(dict[str, object], raw_blocking)
    informational = cast(dict[str, object], raw_informational)
    provenance_flag = "PROVENANCE:DEDUPLICATION_UNVERIFIABLE"
    if provenance_flag in blocking:
        raise RuntimeError(f"{root}/readiness incorrectly blocks source dedup capability")
    _positive_int(informational, provenance_flag, f"{root}/readiness informational reasons")
    raw_by_contract = coverage.get("readiness_by_contract")
    raw_post_roll = coverage.get("post_roll_contracts")
    if not isinstance(raw_by_contract, dict) or not isinstance(raw_post_roll, list):
        raise RuntimeError(f"{root}/readiness lacks post-roll contract evidence")
    by_contract = cast(dict[str, object], raw_by_contract)
    post_roll_contracts = cast(list[object], raw_post_roll)
    if not post_roll_contracts or any(not isinstance(item, str) for item in post_roll_contracts):
        raise RuntimeError(f"{root}/readiness has no identified post-roll contract")
    recovery: dict[str, object] = {}
    for contract in cast(list[str], post_roll_contracts):
        raw_contract = by_contract.get(contract)
        if not isinstance(raw_contract, dict):
            raise RuntimeError(f"{root}/readiness post-roll contract is absent: {contract}")
        contract_data = cast(dict[str, object], raw_contract)
        base_count = _positive_int(contract_data, "base_ready_count", contract)
        imsi_count = _positive_int(contract_data, "imsi_ready_count", contract)
        first_base = contract_data.get("first_base_ready_event_utc")
        first_imsi = contract_data.get("first_imsi_ready_event_utc")
        if not isinstance(first_base, str) or not isinstance(first_imsi, str):
            raise RuntimeError(f"{contract} lacks first post-roll readiness timestamps")
        recovery[contract] = {
            "base_ready_count": base_count,
            "imsi_ready_count": imsi_count,
            "first_base_ready_event_utc": first_base,
            "first_imsi_ready_event_utc": first_imsi,
        }
    return {"candidate_readiness_counts": counts, "post_roll_recovery": recovery}


def _version_value(statistics: Mapping[str, object], key: str) -> str:
    value = statistics.get(key)
    if not isinstance(value, str) or not value:
        raise RuntimeError(f"QC backtest lacks version statistic {key}")
    return value


def _atomic_write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(_canonical_json_bytes(dict(payload)) + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary_path.replace(path)
    except OSError:
        temporary_path.unlink(missing_ok=True)
        raise


def _read_hashed_artifact(path: Path) -> dict[str, object]:
    decoded: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(decoded, dict):
        raise RuntimeError(f"artifact is not a JSON object: {path}")
    document = cast(dict[str, object], decoded)
    claimed = document.get("content_hash")
    unhashed = {key: value for key, value in document.items() if key != "content_hash"}
    if claimed != _content_hash(unhashed):
        raise RuntimeError(f"artifact content hash is invalid: {path}")
    return document


def _run_qc_certification(upload_source: bool, timeout_seconds: int) -> None:
    local_files, local_file_hashes, local_tree_hash = _local_runtime_source()
    source_git_sha = _git_sha()
    portfolio_evidence = _portfolio_target_source_evidence()
    if upload_source:
        _upload_runtime_source(local_files)
    qc_files_before = _read_qc_project_files()
    qc_hashes_before, qc_tree_hash_before = _qc_runtime_source_hash(qc_files_before)
    if qc_tree_hash_before != local_tree_hash or qc_hashes_before != local_file_hashes:
        raise RuntimeError(
            "QC project runtime source differs from local source; compilation stopped"
        )

    compile_created = qc_post("compile/create", {"projectId": QC_PROJECT_ID})
    compile_id = compile_created.get("compileId")
    if not isinstance(compile_id, str) or not compile_id:
        raise RuntimeError("QC compile/create returned no compileId")
    compile_result = _poll_compile(compile_id, timeout_seconds)
    compile_signature = compile_result.get("signature") or compile_created.get("signature")
    if not isinstance(compile_signature, str) or not compile_signature:
        raise RuntimeError("QC compilation returned no signature")
    qc_files_after = _read_qc_project_files()
    qc_hashes_after, qc_tree_hash_after = _qc_runtime_source_hash(qc_files_after)
    if not (
        qc_tree_hash_before == qc_tree_hash_after == local_tree_hash
        and qc_hashes_before == qc_hashes_after == local_file_hashes
    ):
        raise RuntimeError("runtime source hash changed across QC compilation; backtests stopped")

    created: list[tuple[str, str, str]] = []
    for root, mode in _MATRIX:
        response = qc_post(
            "backtests/create",
            {
                "projectId": QC_PROJECT_ID,
                "compileId": compile_id,
                "backtestName": f"lift2-readiness-{source_git_sha[:12]}-{mode}-{root}",
                "parameters": {"lift2_root": root, "lift2_mode": mode},
            },
        )
        created.append((root, mode, _backtest_id(response)))
    completed = _poll_backtests(created, timeout_seconds)

    readiness_runs: list[dict[str, object]] = []
    smoke_runs: list[dict[str, object]] = []
    independent_order_counts: dict[str, object] = {}
    independent_insight_counts: dict[str, object] = {}
    lean_versions: set[str] = set()
    python_versions: set[str] = set()
    numpy_versions: set[str] = set()
    for root, mode, backtest_id in created:
        backtest = completed[backtest_id]
        statistics = _statistics(backtest)
        coverage = _coverage(backtest)
        lean_version = backtest.get("leanVersion") or backtest.get("version")
        if not isinstance(lean_version, str) or not lean_version:
            raise RuntimeError(f"{root}/{mode} lacks a LEAN version")
        lean_versions.add(lean_version)
        python_versions.add(_version_value(statistics, "L2.PythonVersion"))
        numpy_versions.add(_version_value(statistics, "L2.NumPyVersion"))
        order_count, order_hash = _api_zero_count("backtests/orders/read", "orders", backtest_id)
        insight_count, insight_hash = _api_zero_count(
            "backtests/read/insights", "insights", backtest_id
        )
        independent_order_counts[backtest_id] = {
            "count": order_count,
            "api_result_hash": order_hash,
        }
        independent_insight_counts[backtest_id] = {
            "count": insight_count,
            "api_result_hash": insight_hash,
        }
        run: dict[str, object] = {
            "root": root,
            "mode": mode,
            "project_id": QC_PROJECT_ID,
            "compile_id": compile_id,
            "backtest_id": backtest_id,
            "parameters": {"lift2_root": root, "lift2_mode": mode},
            "status": "COMPLETED",
            "lean_version": lean_version,
            "coverage": coverage,
            "coverage_hash": _content_hash(coverage),
        }
        if mode == "readiness":
            run.update(_validate_readiness_coverage(root, coverage))
            readiness_runs.append(run)
        else:
            smoke_runs.append(run)

    if len(readiness_runs) != 3 or len(smoke_runs) != 8:
        raise RuntimeError("qualifying QC matrix is not exactly 3 readiness plus 8 smoke runs")
    if len(lean_versions) != 1 or len(python_versions) != 1 or len(numpy_versions) != 1:
        raise RuntimeError("qualifying QC runs disagree on runtime versions")
    payload: dict[str, object] = {
        "schema_version": "lift2-readiness-qualification-v1",
        "source_git_sha": source_git_sha,
        "local_runtime_tree_hash": local_tree_hash,
        "local_runtime_file_hashes": local_file_hashes,
        "qc_project_runtime_tree_hash": qc_tree_hash_after,
        "qc_project_id": QC_PROJECT_ID,
        "compile_id": compile_id,
        "compile_signature": compile_signature,
        "compile_state": compile_result.get("state"),
        "lean_version": next(iter(lean_versions)),
        "python_version": next(iter(python_versions)),
        "numpy_version": next(iter(numpy_versions)),
        "readiness_runs": readiness_runs,
        "smoke_runs": smoke_runs,
        "independent_order_counts": independent_order_counts,
        "independent_insight_counts": independent_insight_counts,
        "portfolio_target_evidence_type": "SOURCE-STATIC ZERO",
        "portfolio_target_source_evidence": portfolio_evidence,
        "source_identity_capability": "NOT_EXPOSED",
    }
    payload["content_hash"] = _content_hash(payload)
    _atomic_write_json(QUALIFICATION_PATH, payload)
    print(
        json.dumps(
            {
                "status": "QC_READINESS_QUALIFIED",
                "artifact": str(QUALIFICATION_PATH.relative_to(PROJECT_ROOT)),
                "content_hash": payload["content_hash"],
                "compile_id": compile_id,
                "backtest_ids": [backtest_id for _, _, backtest_id in created],
            },
            sort_keys=True,
        )
    )


def _build_readiness_manifest(evidence_git_sha: str) -> None:
    if evidence_git_sha != _git_sha():
        raise RuntimeError("evidence Git SHA must equal current HEAD")
    qualification = _read_hashed_artifact(QUALIFICATION_PATH)
    math = _read_hashed_artifact(MATH_CERTIFICATION_PATH)
    previous = _read_hashed_artifact(PREVIOUS_LIFT2_MANIFEST_PATH)
    readiness_runs = qualification.get("readiness_runs")
    smoke_runs = qualification.get("smoke_runs")
    if not isinstance(readiness_runs, list) or not isinstance(smoke_runs, list):
        raise RuntimeError("qualification artifact lacks run lists")
    raw_runs = (*cast(list[object], readiness_runs), *cast(list[object], smoke_runs))
    backtest_ids: list[str] = []
    for raw_run in raw_runs:
        if not isinstance(raw_run, dict):
            raise RuntimeError("qualification run is not an object")
        backtest_id = cast(dict[str, object], raw_run).get("backtest_id")
        if not isinstance(backtest_id, str) or not backtest_id:
            raise RuntimeError("qualification run lacks backtest_id")
        backtest_ids.append(backtest_id)
    if len(backtest_ids) != 11 or len(set(backtest_ids)) != 11:
        raise RuntimeError("readiness manifest requires 11 unique backtest IDs")
    payload: dict[str, object] = {
        "schema_version": "lift2-readiness-manifest-v1",
        "source_git_sha": qualification.get("source_git_sha"),
        "evidence_git_sha": evidence_git_sha,
        "runtime_source_tree_hash": qualification.get("local_runtime_tree_hash"),
        "qc_project_runtime_tree_hash": qualification.get("qc_project_runtime_tree_hash"),
        "qc_project_id": qualification.get("qc_project_id"),
        "compile_id": qualification.get("compile_id"),
        "compile_signature": qualification.get("compile_signature"),
        "qc_backtest_ids": sorted(backtest_ids),
        "readiness_qualification_hash": qualification.get("content_hash"),
        "math_certification_hash": math.get("content_hash"),
        "previous_lift_2_manifest_hash": previous.get("content_hash"),
    }
    payload["content_hash"] = _content_hash(payload)
    _atomic_write_json(READINESS_MANIFEST_PATH, payload)
    print(
        json.dumps(
            {
                "status": "READINESS_MANIFEST_WRITTEN",
                "artifact": str(READINESS_MANIFEST_PATH.relative_to(PROJECT_ROOT)),
                "content_hash": payload["content_hash"],
            },
            sort_keys=True,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify Lift 2 readiness in QC Cloud")
    parser.add_argument(
        "--upload-source",
        action="store_true",
        help="synchronize the authorized local runtime files before source verification",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=21_600,
        help="maximum compile/backtest polling duration",
    )
    parser.add_argument(
        "--manifest-evidence-git-sha",
        help="build the no-self-reference manifest for the committed evidence SHA",
    )
    args = parser.parse_args()
    if args.timeout_seconds <= 0:
        parser.error("--timeout-seconds must be positive")
    if args.manifest_evidence_git_sha:
        if args.upload_source:
            parser.error("--upload-source cannot be combined with manifest-only mode")
        _build_readiness_manifest(cast(str, args.manifest_evidence_git_sha))
        return
    _run_qc_certification(cast(bool, args.upload_source), cast(int, args.timeout_seconds))


if __name__ == "__main__":
    main()

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from systematic_futures.domain.serialization import sha256_hex
from systematic_futures.ledger.closure_manifest import ClosureManifestBuilder

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_closure_manifest_is_complete_and_deterministic(tmp_path: Path) -> None:
    source = tmp_path / "master.docx"
    dependency = tmp_path / "requirements.txt"
    source.write_bytes(b"synthetic source-document hash fixture")
    dependency.write_text("pytest==8.4.2\n", encoding="utf-8")
    digest = "a" * 64
    arguments = {
        "created_at_utc": datetime(2024, 3, 26, 0, 0, tzinfo=UTC),
        "git_revision": "0123456789abcdef0123456789abcdef01234567",
        "lean_version": "v2.5.0.0",
        "lean_docker_image": "quantconnect/lean:synthetic-test-fixture",
        "docker_image_digest": f"sha256:{'b' * 64}",
        "python_version": "3.11.11",
        "host_architecture": "arm64",
        "runtime_architecture": "x86_64",
        "configuration": {"markets": ("ES", "ZN", "6E")},
        "source_document_paths": (source,),
        "dependency_files": (dependency,),
        "qc_project_id": "synthetic-test-project",
        "qc_cloud_backtest_id": "synthetic-test-backtest",
        "qc_probe_result_hash": digest,
        "notebook_01_result_hash": digest,
        "cftc_certification_artifact_hash": digest,
        "session_certification_artifact_hash": digest,
        "market_registry": {"roots": ("ES", "ZN", "6E")},
        "random_seed": 1729,
    }
    builder = ClosureManifestBuilder()

    first = builder.build(**arguments)
    second = builder.build(**arguments)

    assert first.manifest_hash == second.manifest_hash
    assert first.git_revision
    assert first.lean_version
    assert first.qc_project_id
    assert first.qc_cloud_backtest_id


def test_closure_evidence_index_resolves_every_claim_to_exact_files() -> None:
    index = json.loads(
        (PROJECT_ROOT / "artifacts/certification/lift_1_evidence_index.json").read_text(
            encoding="utf-8"
        )
    )
    expected_content_hash = index["content_hash"]
    content = {key: value for key, value in index.items() if key != "content_hash"}
    assert sha256_hex(content) == expected_content_hash

    assert index["final_readiness_decision"] == "READY_FOR_LIFT_2"
    for source in index["source_documents"]:
        assert source["name"].strip()
        assert len(source["sha256"]) == 64
        assert set(source["sha256"]) <= set("0123456789abcdef")
    records = []
    for claim in index["claims"]:
        records.extend(claim["evidence"])
        assert claim["result"] != "BLOCKED_EXTERNAL_SECRET_OR_ENTITLEMENT"
    for record in records:
        path = PROJECT_ROOT / record["path"]
        assert path.is_file(), record["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == record["sha256"]


def test_local_certification_artifacts_have_valid_content_hashes() -> None:
    paths = (
        "artifacts/certification/python311_quality_gate.json",
        "artifacts/certification/reference_market_session_matrix.json",
        "artifacts/certification/lift1_dataset_certification_matrix.json",
        "artifacts/certification/qc_futures_runtime_probe.json",
        "artifacts/certification/cftc_release_delivery_audit.json",
        "artifacts/manifests/lift_1_closure_manifest.json",
    )
    for relative_path in paths:
        artifact = json.loads((PROJECT_ROOT / relative_path).read_text(encoding="utf-8"))
        expected = artifact.pop("content_hash")
        assert sha256_hex(artifact) == expected


def test_qualified_closure_manifest_binds_real_zero_action_runtime_evidence() -> None:
    manifest = json.loads(
        (PROJECT_ROOT / "artifacts/manifests/lift_1_closure_manifest.json").read_text(
            encoding="utf-8"
        )
    )

    assert manifest["readiness_decision"] == "READY_FOR_LIFT_2"
    assert manifest["certified_source_git_revision"] == ("cbfee265cbf5e94c7768667d469e2773f62e3080")
    assert manifest["quantconnect"] == {
        "project_id": "35697180",
        "project_url": "https://www.quantconnect.com/project/35697180",
        "cloud_build_id": "67d2fc-f0a27f",
        "futures_backtest_id": "b22d565d649c5b31650fd033cdc89cf3",
        "cftc_backtest_id": "a7ba4f84937fb19bc3f6f63bc773e3c3",
    }
    assert manifest["notebook_01_parity"]["classification"] == (
        "THIN_CLIENT_RUNTIME_PARITY_VERIFIED"
    )
    assert manifest["trading_action_counts"] == {
        "orders": 0,
        "insights": 0,
        "portfolio_targets": 0,
    }
    assert manifest["qualification"]["unresolved_foundational_blockers"] == 0

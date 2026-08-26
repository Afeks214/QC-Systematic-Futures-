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

    assert index["final_readiness_decision"] == "EXTERNAL_SECRET_OR_ENTITLEMENT_REQUIRED"
    for source in index["source_documents"]:
        assert source["name"].strip()
        assert len(source["sha256"]) == 64
        assert set(source["sha256"]) <= set("0123456789abcdef")
    records = []
    for claim in index["claims"]:
        records.extend(claim["evidence"])
        missing_path = claim.get("missing_required_artifact")
        if missing_path is not None:
            assert not (PROJECT_ROOT / missing_path).exists()
    for record in records:
        path = PROJECT_ROOT / record["path"]
        assert path.is_file(), record["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == record["sha256"]


def test_local_certification_artifacts_have_valid_content_hashes() -> None:
    paths = (
        "artifacts/certification/python311_quality_gate.json",
        "artifacts/certification/reference_market_session_matrix.json",
        "artifacts/certification/lift1_dataset_certification_matrix.json",
    )
    for relative_path in paths:
        artifact = json.loads((PROJECT_ROOT / relative_path).read_text(encoding="utf-8"))
        expected = artifact.pop("content_hash")
        assert sha256_hex(artifact) == expected

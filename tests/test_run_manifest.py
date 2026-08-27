from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from systematic_futures.domain.enums import ResearchEnvironment
from systematic_futures.ledger.run_manifest import RunManifestBuilder


def test_identical_manifest_inputs_produce_identical_hash(tmp_path: Path) -> None:
    master_spec = tmp_path / "master_spec.txt"
    dependency_file = tmp_path / "requirements.txt"
    master_spec.write_text("synthetic master specification fixture\n", encoding="utf-8")
    dependency_file.write_text("pytest==8.4.2\n", encoding="utf-8")
    arguments = {
        "environment": ResearchEnvironment.LOCAL,
        "created_at_utc": datetime(2024, 2, 1, 12, 0, tzinfo=UTC),
        "configuration": {"probe": {"markets": ("ES", "ZN", "6E")}},
        "source_document_paths": (master_spec,),
        "dependency_files": (dependency_file,),
        "reference_markets": ("ES", "ZN", "6E"),
        "probe_start_date": "2024-02-15",
        "probe_end_date": "2024-03-25",
        "lean_version": None,
        "repository_revision": None,
        "random_seed": 1729,
    }
    builder = RunManifestBuilder()

    first = builder.build(**arguments)
    second = builder.build(**arguments)

    assert first.manifest_hash == second.manifest_hash


def test_manifest_accepts_verified_private_source_hashes_without_documents(
    tmp_path: Path,
) -> None:
    dependency_file = tmp_path / "requirements.txt"
    dependency_file.write_text("pytest==8.4.2\n", encoding="utf-8")
    source_hashes = {"private-master.docx": "a" * 64}

    manifest = RunManifestBuilder().build(
        environment=ResearchEnvironment.LOCAL,
        created_at_utc=datetime(2024, 2, 1, 12, 0, tzinfo=UTC),
        configuration={"probe": {"markets": ("ES", "ZN", "6E")}},
        source_document_paths=(),
        source_document_hashes=source_hashes,
        dependency_files=(dependency_file,),
        reference_markets=("ES", "ZN", "6E"),
        probe_start_date="2024-02-15",
        probe_end_date="2024-03-25",
        lean_version=None,
        repository_revision=None,
        random_seed=1729,
    )

    source_hashes["private-master.docx"] = "b" * 64
    assert manifest.source_document_hashes == {"private-master.docx": "a" * 64}


def test_manifest_rejects_ambiguous_source_document_inputs(tmp_path: Path) -> None:
    source = tmp_path / "master.docx"
    dependency = tmp_path / "requirements.txt"
    source.write_bytes(b"private source fixture")
    dependency.write_text("pytest==8.4.2\n", encoding="utf-8")

    with pytest.raises(ValueError, match="mutually exclusive"):
        RunManifestBuilder().build(
            environment=ResearchEnvironment.LOCAL,
            created_at_utc=datetime(2024, 2, 1, 12, 0, tzinfo=UTC),
            configuration={},
            source_document_paths=(source,),
            source_document_hashes={"master.docx": "a" * 64},
            dependency_files=(dependency,),
            reference_markets=("ES", "ZN", "6E"),
            probe_start_date="2024-02-15",
            probe_end_date="2024-03-25",
            lean_version=None,
            repository_revision=None,
            random_seed=1729,
        )

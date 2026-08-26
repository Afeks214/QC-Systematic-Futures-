from __future__ import annotations

# pyright: reportUnnecessaryIsInstance=false
import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType

from systematic_futures.domain.errors import (
    DuplicateIdentifierError,
    LedgerIntegrityError,
    TimeSemanticsError,
)
from systematic_futures.domain.identifiers import make_run_id
from systematic_futures.domain.serialization import sha256_hex


@dataclass(frozen=True, slots=True)
class Lift1ClosureManifest:
    """Qualified, evidence-linked manifest for a Lift 1 closure run."""

    run_id: str
    created_at_utc: datetime
    git_revision: str
    lean_version: str
    lean_docker_image: str
    docker_image_digest: str
    python_version: str
    host_architecture: str
    runtime_architecture: str
    dependency_hash: str
    configuration_hash: str
    source_document_hashes: Mapping[str, str]
    qc_project_id: str
    qc_cloud_backtest_id: str
    qc_probe_result_hash: str
    notebook_01_result_hash: str
    cftc_certification_artifact_hash: str
    session_certification_artifact_hash: str
    market_registry_hash: str
    random_seed: int
    manifest_hash: str

    def __post_init__(self) -> None:
        copied = dict(sorted(self.source_document_hashes.items()))
        object.__setattr__(self, "source_document_hashes", MappingProxyType(copied))


class ClosureManifestBuilder:
    """Build a qualified closure manifest from explicit, non-null evidence inputs."""

    def build(
        self,
        *,
        created_at_utc: datetime,
        git_revision: str,
        lean_version: str,
        lean_docker_image: str,
        docker_image_digest: str,
        python_version: str,
        host_architecture: str,
        runtime_architecture: str,
        configuration: object,
        source_document_paths: Sequence[Path],
        dependency_files: Sequence[Path],
        qc_project_id: str,
        qc_cloud_backtest_id: str,
        qc_probe_result_hash: str,
        notebook_01_result_hash: str,
        cftc_certification_artifact_hash: str,
        session_certification_artifact_hash: str,
        market_registry: object,
        random_seed: int,
    ) -> Lift1ClosureManifest:
        """Create a validated deterministic qualified-closure manifest.

        Units: ``random_seed`` is dimensionless; hashes are lowercase SHA-256.
        Time semantics: ``created_at_utc`` must be aware and is normalized to UTC.
        Missingness: every runtime, Git, QC, and artifact field is mandatory; this
        builder refuses to create an unqualified manifest with null substitutes.
        Raises: ``FileNotFoundError``, ``DuplicateIdentifierError``,
        ``TimeSemanticsError``, ``DataQualityError``, or ``LedgerIntegrityError``.
        """

        created_at = _aware_utc(created_at_utc, "created_at_utc")
        source_hashes = _named_file_hashes(source_document_paths)
        dependency_hash = sha256_hex(_named_file_hashes(dependency_files))
        configuration_hash = sha256_hex(configuration)
        market_registry_hash = sha256_hex(market_registry)
        run_id = make_run_id(created_at, configuration_hash)
        content: dict[str, object] = {
            "run_id": run_id,
            "created_at_utc": created_at,
            "git_revision": git_revision,
            "lean_version": lean_version,
            "lean_docker_image": lean_docker_image,
            "docker_image_digest": docker_image_digest,
            "python_version": python_version,
            "host_architecture": host_architecture,
            "runtime_architecture": runtime_architecture,
            "dependency_hash": dependency_hash,
            "configuration_hash": configuration_hash,
            "source_document_hashes": source_hashes,
            "qc_project_id": qc_project_id,
            "qc_cloud_backtest_id": qc_cloud_backtest_id,
            "qc_probe_result_hash": qc_probe_result_hash,
            "notebook_01_result_hash": notebook_01_result_hash,
            "cftc_certification_artifact_hash": cftc_certification_artifact_hash,
            "session_certification_artifact_hash": session_certification_artifact_hash,
            "market_registry_hash": market_registry_hash,
            "random_seed": random_seed,
        }
        manifest = Lift1ClosureManifest(
            run_id=run_id,
            created_at_utc=created_at,
            git_revision=git_revision,
            lean_version=lean_version,
            lean_docker_image=lean_docker_image,
            docker_image_digest=docker_image_digest,
            python_version=python_version,
            host_architecture=host_architecture,
            runtime_architecture=runtime_architecture,
            dependency_hash=dependency_hash,
            configuration_hash=configuration_hash,
            source_document_hashes=source_hashes,
            qc_project_id=qc_project_id,
            qc_cloud_backtest_id=qc_cloud_backtest_id,
            qc_probe_result_hash=qc_probe_result_hash,
            notebook_01_result_hash=notebook_01_result_hash,
            cftc_certification_artifact_hash=cftc_certification_artifact_hash,
            session_certification_artifact_hash=session_certification_artifact_hash,
            market_registry_hash=market_registry_hash,
            random_seed=random_seed,
            manifest_hash=sha256_hex(content),
        )
        validate_lift1_closure_manifest(manifest)
        return manifest


def validate_lift1_closure_manifest(manifest: Lift1ClosureManifest) -> None:
    """Validate completeness and hashes of a qualified closure manifest.

    Units: hashes are lowercase SHA-256 strings and the seed is dimensionless.
    Time semantics: creation time must be timezone-aware and normalized to UTC.
    Missingness: no field permits ``None`` or blank text; source hashes must be
    non-empty. Raises: ``TimeSemanticsError`` or ``LedgerIntegrityError``.
    """

    _aware_utc(manifest.created_at_utc, "created_at_utc", require_utc=True)
    for field_name, value in (
        ("run_id", manifest.run_id),
        ("git_revision", manifest.git_revision),
        ("lean_version", manifest.lean_version),
        ("lean_docker_image", manifest.lean_docker_image),
        ("docker_image_digest", manifest.docker_image_digest),
        ("python_version", manifest.python_version),
        ("host_architecture", manifest.host_architecture),
        ("runtime_architecture", manifest.runtime_architecture),
        ("qc_project_id", manifest.qc_project_id),
        ("qc_cloud_backtest_id", manifest.qc_cloud_backtest_id),
    ):
        _require_text(value, field_name)
    for field_name, value in (
        ("dependency_hash", manifest.dependency_hash),
        ("configuration_hash", manifest.configuration_hash),
        ("qc_probe_result_hash", manifest.qc_probe_result_hash),
        ("notebook_01_result_hash", manifest.notebook_01_result_hash),
        (
            "cftc_certification_artifact_hash",
            manifest.cftc_certification_artifact_hash,
        ),
        (
            "session_certification_artifact_hash",
            manifest.session_certification_artifact_hash,
        ),
        ("market_registry_hash", manifest.market_registry_hash),
        ("manifest_hash", manifest.manifest_hash),
    ):
        _require_sha256(value, field_name)
    if not manifest.source_document_hashes:
        raise LedgerIntegrityError("source_document_hashes must not be empty")
    for name, digest in manifest.source_document_hashes.items():
        _require_text(name, "source document name")
        _require_sha256(digest, f"source_document_hashes[{name}]")
    if isinstance(manifest.random_seed, bool) or not isinstance(manifest.random_seed, int):
        raise LedgerIntegrityError("random_seed must be an integer")


def _named_file_hashes(paths: Sequence[Path]) -> Mapping[str, str]:
    hashes: dict[str, str] = {}
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(path)
        if path.name in hashes:
            raise DuplicateIdentifierError(f"duplicate closure input name: {path.name}")
        hashes[path.name] = _sha256_file(path)
    if not hashes:
        raise LedgerIntegrityError("at least one input file is required")
    return MappingProxyType(dict(sorted(hashes.items())))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _aware_utc(
    value: datetime,
    field_name: str,
    *,
    require_utc: bool = False,
) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise TimeSemanticsError(f"{field_name} must be timezone-aware")
    normalized = value.astimezone(UTC)
    if require_utc and value.utcoffset() != UTC.utcoffset(value):
        raise TimeSemanticsError(f"{field_name} must be normalized to UTC")
    return normalized


def _require_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise LedgerIntegrityError(f"{field_name} must be a non-blank string")


def _require_sha256(value: str, field_name: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise LedgerIntegrityError(f"{field_name} must be a lowercase SHA-256 digest")


__all__ = (
    "ClosureManifestBuilder",
    "Lift1ClosureManifest",
    "validate_lift1_closure_manifest",
)

from __future__ import annotations

import hashlib
import platform
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import cast

from systematic_futures.domain.enums import ResearchEnvironment
from systematic_futures.domain.errors import DuplicateIdentifierError, TimeSemanticsError
from systematic_futures.domain.identifiers import make_run_id
from systematic_futures.domain.schemas import ResearchRunManifest, validate_research_run_manifest
from systematic_futures.domain.serialization import canonicalize_for_json, sha256_hex


class RunManifestBuilder:
    """Build deterministic manifests from explicit research inputs.

    Units: probe dates are calendar strings; ``random_seed`` is dimensionless.
    Time semantics: ``created_at_utc`` must be aware and is never synthesized.
    Missingness: unavailable LEAN/Git versions remain ``None``.
    Raises: FileNotFoundError for a missing input file,
    DuplicateIdentifierError for colliding file names, TimeSemanticsError for a
    naive creation time, or a schema-specific domain error for invalid content.
    """

    def build(
        self,
        *,
        environment: ResearchEnvironment,
        created_at_utc: datetime,
        configuration: object,
        source_document_paths: Sequence[Path],
        source_document_hashes: Mapping[str, str] | None = None,
        dependency_files: Sequence[Path],
        reference_markets: Sequence[str],
        probe_start_date: str,
        probe_end_date: str,
        lean_version: str | None,
        repository_revision: str | None,
        random_seed: int,
    ) -> ResearchRunManifest:
        """Create a validated manifest without reading hidden environment state.

        Units: dates are ISO calendar dates; seed is dimensionless.
        Time semantics: creation time is normalized to UTC; probe dates are retained
        exactly after schema validation.
        Missingness: absent version/revision values remain ``None``. Private source
        documents may be represented by their previously verified SHA-256 mapping
        only when no source paths are supplied. Raises: FileNotFoundError,
        DuplicateIdentifierError, TimeSemanticsError, ValueError for ambiguous source
        inputs, or a domain validation error.
        """
        normalized_time = _aware_utc(created_at_utc)
        if source_document_hashes is not None:
            if source_document_paths:
                raise ValueError(
                    "source_document_paths and source_document_hashes are mutually exclusive"
                )
            source_hashes = _canonical_mapping(source_document_hashes)
        else:
            source_hashes = _named_file_hashes(source_document_paths)
        dependency_hashes = _named_file_hashes(dependency_files)
        configuration_hash = sha256_hex(configuration)
        run_id = make_run_id(normalized_time, configuration_hash)
        base: dict[str, object] = {
            "run_id": run_id,
            "created_at_utc": normalized_time,
            "environment": environment,
            "python_version": platform.python_version(),
            "lean_version": lean_version,
            "repository_revision": repository_revision,
            "configuration_hash": configuration_hash,
            "source_document_hashes": source_hashes,
            "dependency_hash": sha256_hex(dependency_hashes),
            "random_seed": random_seed,
            "reference_markets": tuple(reference_markets),
            "probe_start_date": probe_start_date,
            "probe_end_date": probe_end_date,
        }
        manifest = ResearchRunManifest(
            run_id=run_id,
            created_at_utc=normalized_time,
            environment=environment,
            python_version=platform.python_version(),
            lean_version=lean_version,
            repository_revision=repository_revision,
            configuration_hash=configuration_hash,
            source_document_hashes=_canonical_mapping(source_hashes),
            dependency_hash=sha256_hex(dependency_hashes),
            random_seed=random_seed,
            reference_markets=tuple(reference_markets),
            probe_start_date=probe_start_date,
            probe_end_date=probe_end_date,
            manifest_hash=sha256_hex(base),
        )
        validate_research_run_manifest(manifest)
        return manifest


def _named_file_hashes(paths: Sequence[Path]) -> Mapping[str, str]:
    hashes: dict[str, str] = {}
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(path)
        if path.name in hashes:
            raise DuplicateIdentifierError(f"Duplicate manifest file name: {path.name}")
        hashes[path.name] = _sha256_file(path)
    return dict(sorted(hashes.items()))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_mapping(value: Mapping[str, str]) -> Mapping[str, str]:
    canonical = canonicalize_for_json(value)
    if not isinstance(canonical, dict):
        raise TypeError("Canonical file hash mapping must be an object")
    return cast(dict[str, str], canonical)


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise TimeSemanticsError("created_at_utc must be timezone-aware")
    from datetime import UTC

    return value.astimezone(UTC)

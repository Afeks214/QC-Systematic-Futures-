#!/usr/bin/env bash
set -euo pipefail

worktree_hash() {
    python - <<'PY'
import hashlib
import subprocess
from pathlib import Path

root = Path.cwd()
paths = subprocess.check_output(
    ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"]
).split(b"\0")
digest = hashlib.sha256()
digest.update(subprocess.check_output(["git", "status", "--porcelain=v1", "-z"]))
digest.update(subprocess.check_output(["git", "ls-files", "--stage", "-z"]))
for encoded in sorted(item for item in paths if item):
    digest.update(encoded)
    path = root / encoded.decode("utf-8")
    if not path.is_file():
        digest.update(b"\0MISSING\0")
        continue
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
print(digest.hexdigest())
PY
}

initial_worktree_hash="$(worktree_hash)"

python -m pip check
python -m compileall systematic_futures main.py
ruff format --diff . || true
ruff format --check .
ruff check .
pyright
pytest -q
pytest -q tests/test_architecture_boundaries.py tests/test_runtime.py
python scripts/validate_notebooks.py

final_worktree_hash="$(worktree_hash)"
if [[ "${initial_worktree_hash}" != "${final_worktree_hash}" ]]; then
    echo "Quality validation mutated the worktree." >&2
    exit 1
fi

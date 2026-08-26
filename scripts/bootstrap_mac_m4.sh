#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${PROJECT_ROOT}/.venv"

if [[ "$(uname -s)" != "Darwin" ]]; then
    printf 'WARNING: this bootstrap targets macOS; detected %s.\n' "$(uname -s)"
fi

if [[ "$(uname -m)" != "arm64" ]]; then
    printf 'WARNING: Apple Silicon arm64 was expected; detected %s.\n' "$(uname -m)"
fi

if ! command -v python3.11 >/dev/null 2>&1; then
    printf 'ERROR: python3.11 is required and was not found on PATH.\n' >&2
    printf 'Install Python 3.11, then rerun this script.\n' >&2
    exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
    printf 'WARNING: Docker Desktop was not found; local LEAN commands will remain unavailable.\n'
else
    printf 'Found Docker: %s\n' "$(docker --version)"
fi

if ! command -v code >/dev/null 2>&1; then
    printf 'WARNING: the VS Code command-line launcher was not found.\n'
else
    printf 'Found VS Code command-line launcher.\n'
fi

if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
    python3.11 -m venv "${VENV_DIR}"
fi

"${VENV_DIR}/bin/python" -m pip install --requirement "${PROJECT_ROOT}/requirements.txt"
"${VENV_DIR}/bin/python" -m pip check

if command -v lean >/dev/null 2>&1; then
    printf 'Found LEAN CLI: %s\n' "$(lean --version)"
else
    printf 'LEAN CLI is not installed in the active shell.\n'
fi

printf 'Bootstrap complete. Next manual steps:\n'
printf '  1. source "%s/bin/activate"\n' "${VENV_DIR}"
printf '  2. Install the verified CLI explicitly if needed: python -m pip install lean==1.0.228\n'
printf '  3. Start Docker Desktop.\n'
printf '  4. Run lean login manually; never place credentials in this repository.\n'
printf '  5. Follow docs/MAC_M4_QC_BOOTSTRAP.md for lean init, project creation, research, and probe commands.\n'

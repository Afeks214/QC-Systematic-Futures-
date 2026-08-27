from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Protocol, cast

import nbformat


class _NbformatApi(Protocol):
    def read(self, fp: Path, *, as_version: int) -> object: ...

    def validate(self, nbdict: object) -> None: ...


_NBFORMAT = cast(_NbformatApi, nbformat)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK_1 = PROJECT_ROOT / "research_notebooks/01_data_state_research.ipynb"
NOTEBOOK_2 = PROJECT_ROOT / "research_notebooks/02_auction_mechanism_event_studies.ipynb"
NOTEBOOK_3 = PROJECT_ROOT / "research_notebooks/03_robustness_go_no_go.ipynb"
ROOT_NOTEBOOK = PROJECT_ROOT / "research.ipynb"
SHELL_PROHIBITION = "NOT IMPLEMENTED IN LIFT 1"

_NOTEBOOK_1_MARKERS = (
    "Lift 1 scope",
    "Environment and version reporting",
    "Market registry",
    "Build a QuantBook",
    "Register ES, ZN, and 6E",
    "Request fixed-period history",
    "Coverage inspection",
    "Continuous and actual contract identity",
    "Mapping events and roll-window observations",
    "Session counts",
    "DataProbeResult",
    "Export audited artifacts",
    "Verified facts, unresolved facts, and limitations",
)

_NOTEBOOK_2_MARKERS = (
    "# 1. Scope",
    "# 2. Environment",
    "# 3. Profile QA",
    "# 4. Auction Features",
    "# 5. IMSI State",
    "# 6. ICM State",
    "# 7. IAE-L1",
    "# 8. Candidate Event Coverage",
    "# 9. Data Quality",
    "# 10. Final Lift 2 Summary",
)

_PROHIBITED_CODE_TOKENS = (
    "market_order",
    "limit_order",
    "stop_market_order",
    "set_holdings",
    "liquidate",
    "emit_insights",
    "Insight(",
    "PortfolioTarget(",
    "pct_change(",
    "calculate_returns",
    "market_profile",
)


def validate_notebooks(paths: Sequence[Path] | None = None) -> tuple[str, ...]:
    """Parse and structurally validate the four Lift 1 notebooks.

    Units: not applicable.
    Time semantics: Notebook 1 must retain the fixed-period section, but this
    structural validator does not execute history requests.
    Missingness: missing files or required sections are returned as errors.
    Raises: OSError for unreadable files and nbformat validation errors for malformed
    notebook documents.
    """
    selected = (
        tuple(paths)
        if paths is not None
        else (
            ROOT_NOTEBOOK,
            NOTEBOOK_1,
            NOTEBOOK_2,
            NOTEBOOK_3,
        )
    )
    notebooks: dict[Path, Mapping[str, object]] = {}
    errors: list[str] = []
    for path in selected:
        if not path.is_file():
            errors.append(f"missing notebook: {path.relative_to(PROJECT_ROOT)}")
            continue
        parsed = _NBFORMAT.read(path, as_version=4)
        _NBFORMAT.validate(parsed)
        if not isinstance(parsed, Mapping):
            errors.append(f"notebook root is not an object: {path.relative_to(PROJECT_ROOT)}")
            continue
        notebooks[path] = cast(Mapping[str, object], parsed)
    if NOTEBOOK_1 in notebooks:
        errors.extend(_validate_notebook_1(notebooks[NOTEBOOK_1]))
    if NOTEBOOK_2 in notebooks:
        errors.extend(_validate_notebook_2(notebooks[NOTEBOOK_2]))
    if NOTEBOOK_3 in notebooks:
        errors.extend(_validate_shell(NOTEBOOK_3, notebooks[NOTEBOOK_3]))
    if ROOT_NOTEBOOK in notebooks:
        errors.extend(_validate_root_index(notebooks[ROOT_NOTEBOOK]))
    return tuple(errors)


def _cells(notebook: Mapping[str, object]) -> tuple[Mapping[str, object], ...]:
    raw_cells = notebook.get("cells")
    if not isinstance(raw_cells, list):
        return ()
    cells: list[Mapping[str, object]] = []
    for raw_cell in cast(list[object], raw_cells):
        if isinstance(raw_cell, Mapping):
            cells.append(cast(Mapping[str, object], raw_cell))
    return tuple(cells)


def _source(cell: Mapping[str, object]) -> str:
    raw_source = cell.get("source", "")
    if isinstance(raw_source, str):
        return raw_source
    if isinstance(raw_source, list):
        source_lines = cast(list[object], raw_source)
        if all(isinstance(line, str) for line in source_lines):
            return "".join(cast(list[str], source_lines))
    return ""


def _validate_notebook_1(notebook: Mapping[str, object]) -> list[str]:
    cells = _cells(notebook)
    errors: list[str] = []
    if len(cells) != len(_NOTEBOOK_1_MARKERS):
        errors.append(
            f"Notebook 1 must contain {len(_NOTEBOOK_1_MARKERS)} ordered cells; found {len(cells)}"
        )
        return errors
    expected_types = ("markdown",) + ("code",) * 11 + ("markdown",)
    for index, (cell, marker, expected_type) in enumerate(
        zip(cells, _NOTEBOOK_1_MARKERS, expected_types, strict=True),
        start=1,
    ):
        if cell.get("cell_type") != expected_type:
            errors.append(f"Notebook 1 cell {index} must be {expected_type}")
        if marker not in _source(cell):
            errors.append(f"Notebook 1 cell {index} is missing marker {marker!r}")
    first = _source(cells[0])
    if "no strategy or P&L is being tested" not in first:
        errors.append("Notebook 1 scope statement is missing")
    code = "\n".join(_source(cell) for cell in cells if cell.get("cell_type") == "code")
    for token in _PROHIBITED_CODE_TOKENS:
        if token in code:
            errors.append(f"Notebook 1 contains prohibited code token: {token}")
    return errors


def _validate_shell(path: Path, notebook: Mapping[str, object]) -> list[str]:
    cells = _cells(notebook)
    errors: list[str] = []
    if any(cell.get("cell_type") == "code" for cell in cells):
        errors.append(f"{path.name} must be documentation-only")
    if SHELL_PROHIBITION not in "\n".join(_source(cell) for cell in cells):
        errors.append(f"{path.name} is missing the exact Lift 1 prohibition")
    return errors


def _validate_notebook_2(notebook: Mapping[str, object]) -> list[str]:
    cells = _cells(notebook)
    errors: list[str] = []
    if len(cells) != 20:
        return [f"Notebook 2 must contain 20 alternating section cells; found {len(cells)}"]
    for index, marker in enumerate(_NOTEBOOK_2_MARKERS):
        markdown = cells[index * 2]
        code_cell = cells[index * 2 + 1]
        if markdown.get("cell_type") != "markdown" or marker not in _source(markdown):
            errors.append(f"Notebook 2 section {index + 1} is missing marker {marker!r}")
        if code_cell.get("cell_type") != "code":
            errors.append(f"Notebook 2 section {index + 1} must have one code client cell")
    text = "\n".join(_source(cell) for cell in cells)
    if "Lift 2 measurement only. No outcome or strategy study." not in text:
        errors.append("Notebook 2 scope statement is missing")
    code = "\n".join(_source(cell) for cell in cells if cell.get("cell_type") == "code")
    for token in _PROHIBITED_CODE_TOKENS:
        if token in code:
            errors.append(f"Notebook 2 contains prohibited code token: {token}")
    for line in code.splitlines():
        if line.startswith("def ") or line.startswith("class "):
            errors.append("Notebook 2 may not define business-logic functions or classes")
    for import_name in (
        "systematic_futures.measurement.types",
        "systematic_futures.measurement.events",
    ):
        if import_name not in code:
            errors.append(f"Notebook 2 is missing shared-code import {import_name}")
    return errors


def _validate_root_index(notebook: Mapping[str, object]) -> list[str]:
    text = "\n".join(_source(cell) for cell in _cells(notebook))
    required = (
        "01_data_state_research.ipynb",
        "02_auction_mechanism_event_studies.ipynb",
        "03_robustness_go_no_go.ipynb",
    )
    return [f"research.ipynb is missing {name}" for name in required if name not in text]


def main() -> int:
    """Validate notebooks and return a process status code.

    Units: not applicable.
    Time semantics: no notebook cell is executed.
    Missingness: missing notebooks produce a nonzero status.
    Raises: OSError or nbformat validation errors for unreadable/malformed notebooks.
    """
    errors = validate_notebooks()
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("Notebook validation: PASS (4 notebooks parsed; Lift 1/2 boundaries verified)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

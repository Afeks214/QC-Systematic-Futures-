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
ROOT_NOTEBOOK = PROJECT_ROOT / "research.ipynb"
PROHIBITED_CODE_TOKENS = (
    "market_order",
    "limit_order",
    "stop_market_order",
    "set_holdings",
    "liquidate",
    "emit_insights",
    "Insight(",
    "PortfolioTarget(",
)


def validate_notebooks(paths: Sequence[Path] | None = None) -> tuple[str, ...]:
    """Validate the thin measurement notebook without executing any cell."""

    selected = tuple(paths) if paths is not None else (ROOT_NOTEBOOK,)
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
        errors.extend(_validate_thin_client(path, cast(Mapping[str, object], parsed)))
    return tuple(errors)


def _validate_thin_client(path: Path, notebook: Mapping[str, object]) -> list[str]:
    cells = _cells(notebook)
    errors: list[str] = []
    if len(cells) != 3:
        errors.append(f"{path.name} must contain exactly three cells")
        return errors
    if tuple(cell.get("cell_type") for cell in cells) != ("markdown", "code", "markdown"):
        errors.append(f"{path.name} must contain markdown, code, markdown")
    text = "\n".join(_source(cell) for cell in cells)
    for statement in (
        "descriptive measurement only",
        "No orders, forecasts, targets, or portfolio logic",
    ):
        if statement not in text:
            errors.append(f"{path.name} is missing boundary statement: {statement}")
    code = _source(cells[1])
    for import_name in (
        "systematic_futures.config.markets",
        "systematic_futures.config.measurement",
    ):
        if import_name not in code:
            errors.append(f"{path.name} is missing shared-code import {import_name}")
    for token in PROHIBITED_CODE_TOKENS:
        if token in code:
            errors.append(f"{path.name} contains prohibited code token: {token}")
    for line in code.splitlines():
        if line.startswith("def ") or line.startswith("class "):
            errors.append(f"{path.name} may not define business logic")
    if cells[1].get("execution_count") is not None or cells[1].get("outputs") != []:
        errors.append(f"{path.name} must not retain execution state or outputs")
    return errors


def _cells(notebook: Mapping[str, object]) -> tuple[Mapping[str, object], ...]:
    raw_cells = notebook.get("cells")
    if not isinstance(raw_cells, list):
        return ()
    return tuple(
        cast(Mapping[str, object], cell)
        for cell in cast(list[object], raw_cells)
        if isinstance(cell, Mapping)
    )


def _source(cell: Mapping[str, object]) -> str:
    raw_source = cell.get("source", "")
    if isinstance(raw_source, str):
        return raw_source
    if isinstance(raw_source, list):
        lines = cast(list[object], raw_source)
        if all(isinstance(line, str) for line in lines):
            return "".join(cast(list[str], lines))
    return ""


def main() -> int:
    errors = validate_notebooks()
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("Notebook validation: PASS (1 thin client; no execution state)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

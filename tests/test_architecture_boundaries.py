from __future__ import annotations

import ast
from pathlib import Path

from scripts.validate_notebooks import validate_notebooks

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CORE_DIRECTORIES = (
    PROJECT_ROOT / "systematic_futures/domain",
    PROJECT_ROOT / "systematic_futures/data",
    PROJECT_ROOT / "systematic_futures/ledger",
)
PROHIBITED_CORE_NAMES = {
    "AlgorithmImports",
    "QuantConnect",
    "QCAlgorithm",
    "Slice",
    "Insight",
    "PortfolioTarget",
}
PROHIBITED_MAIN_TOKENS = (
    "market_order",
    "limit_order",
    "stop_market_order",
    "set_holdings",
    "liquidate",
    "emit_insights",
    "Insight(",
    "PortfolioTarget(",
)
PROHIBITED_LIFT2_IMPORT_ROOTS = {"catboost", "sklearn", "torch", "xgboost"}
PROHIBITED_LIFT2_SYMBOLS = {
    "AlphaModel",
    "AuctionState",
    "CandidateEventDataset",
    "ExecutionModel",
    "IAE",
    "ICM",
    "IMSI",
    "PortfolioConstructionModel",
    "RiskManagementModel",
    "VolumeProfileEngine",
}


def test_core_has_no_quantconnect_imports() -> None:
    violations: list[str] = []
    for directory in CORE_DIRECTORIES:
        for path in sorted(directory.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                names = _import_names(node)
                found = sorted(PROHIBITED_CORE_NAMES.intersection(names))
                if found:
                    relative = path.relative_to(PROJECT_ROOT)
                    violations.append(f"{relative}: {', '.join(found)}")
    assert violations == []


def test_main_contains_no_trading_api() -> None:
    source = (PROJECT_ROOT / "main.py").read_text(encoding="utf-8")
    found = [token for token in PROHIBITED_MAIN_TOKENS if token in source]
    assert found == []


def test_notebooks_parse_and_preserve_lift_1_scope() -> None:
    assert validate_notebooks() == ()


def test_executable_python_contains_no_lift_2_implementation() -> None:
    paths = (
        PROJECT_ROOT / "main.py",
        *sorted((PROJECT_ROOT / "systematic_futures").rglob("*.py")),
        *sorted((PROJECT_ROOT / "scripts").glob("*.py")),
    )
    violations: list[str] = []
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots = {alias.name.split(".")[0] for alias in node.names}
                found_imports = sorted(roots.intersection(PROHIBITED_LIFT2_IMPORT_ROOTS))
                if found_imports:
                    violations.append(f"{path.name}: imports {', '.join(found_imports)}")
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                root = node.module.split(".")[0]
                if root in PROHIBITED_LIFT2_IMPORT_ROOTS:
                    violations.append(f"{path.name}: imports {root}")
            elif isinstance(node, ast.ClassDef) and node.name in PROHIBITED_LIFT2_SYMBOLS:
                violations.append(f"{path.name}: defines {node.name}")
            elif isinstance(node, ast.Name) and node.id in PROHIBITED_LIFT2_SYMBOLS:
                violations.append(f"{path.name}: references {node.id}")
    assert violations == []


def _import_names(node: ast.AST) -> set[str]:
    names: set[str] = set()
    if isinstance(node, ast.Import):
        for alias in node.names:
            names.update(alias.name.split("."))
    elif isinstance(node, ast.ImportFrom):
        if node.module is not None:
            names.update(node.module.split("."))
        names.update(alias.name for alias in node.names)
    return names

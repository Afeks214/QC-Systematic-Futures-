from __future__ import annotations

import ast
from dataclasses import fields, is_dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from systematic_futures.config.feature_semantics import (
    feature_semantics_v1,
    feature_semantics_v2,
    feature_semantics_v3,
    feature_semantics_v4,
)
from systematic_futures.data.sessions import SessionEngine, reference_session_policies
from systematic_futures.domain.research_contracts import FeatureImplementationStatus
from systematic_futures.measurement.types import (
    AuctionFeatureVector,
    AuctionStateSnapshot,
    CandidateEventObservation,
    CompletedTradeBar,
    IAEStateSnapshot,
    ICMStateSnapshot,
    IMSIStateSnapshot,
    IndicatorSynergySnapshot,
    ProfileDefinition,
    TradeObservation,
    VolumeProfileSnapshot,
)
from systematic_futures.qc_adapters import lift2_runtime

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MEASUREMENT_ROOT = PROJECT_ROOT / "systematic_futures/measurement"
RUNTIME_PACKAGE_INITIALIZERS = (
    PROJECT_ROOT / "systematic_futures/config/__init__.py",
    PROJECT_ROOT / "systematic_futures/domain/__init__.py",
    PROJECT_ROOT / "systematic_futures/qc_adapters/__init__.py",
    PROJECT_ROOT / "systematic_futures/research_lib/__init__.py",
)


def test_runtime_package_initializers_are_side_effect_free() -> None:
    for path in RUNTIME_PACKAGE_INITIALIZERS:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imports = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Import | ast.ImportFrom)
            and not (isinstance(node, ast.ImportFrom) and node.module == "__future__")
        ]
        assert imports == [], f"{path} must not import runtime submodules"


def test_measurement_modules_are_qc_free_and_use_only_authorized_dependency() -> None:
    prohibited = {"AlgorithmImports", "QCAlgorithm", "Slice", "Insight", "PortfolioTarget"}
    external_roots: set[str] = set()
    violations: list[str] = []
    for path in sorted(MEASUREMENT_ROOT.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0]
                    if root in prohibited:
                        violations.append(f"{path.name}: {root}")
                    if root not in {"systematic_futures"}:
                        external_roots.add(root)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                root = node.module.split(".")[0]
                if root in prohibited:
                    violations.append(f"{path.name}: {root}")
                if root not in {"systematic_futures", "__future__"}:
                    external_roots.add(root)
    assert violations == []
    standard_library = {
        "collections",
        "dataclasses",
        "datetime",
        "enum",
        "itertools",
        "math",
        "typing",
    }
    assert external_roots - standard_library == {"numpy"}


def test_executable_source_has_no_trading_calls_or_ml_imports() -> None:
    prohibited_calls = {
        "emit_insights",
        "limit_order",
        "liquidate",
        "market_order",
        "set_holdings",
        "stop_market_order",
    }
    prohibited_constructors = {"Insight", "PortfolioTarget"}
    prohibited_imports = {"catboost", "lightgbm", "sklearn", "tensorflow", "torch", "xgboost"}
    violations: list[str] = []
    paths = (PROJECT_ROOT / "main.py", *sorted((PROJECT_ROOT / "systematic_futures").rglob("*.py")))
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = None
                if isinstance(node.func, ast.Name):
                    name = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    name = node.func.attr
                if name in prohibited_calls | prohibited_constructors:
                    violations.append(f"{path.name}: calls {name}")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in prohibited_imports:
                        violations.append(f"{path.name}: imports {alias.name}")
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                if node.module.split(".")[0] in prohibited_imports:
                    violations.append(f"{path.name}: imports {node.module}")
    assert violations == []


def test_feature_v1_is_preserved_and_v2_marks_only_measurements() -> None:
    v1 = feature_semantics_v1()
    assert all(
        feature.implementation_status is FeatureImplementationStatus.NOT_IMPLEMENTED
        for feature in v1
    )
    v2 = feature_semantics_v2()
    unimplemented = {
        feature.feature_name
        for feature in v2
        if feature.implementation_status is FeatureImplementationStatus.NOT_IMPLEMENTED
    }
    assert unimplemented == {
        "acceptance_score",
        "expected_shortfall_fraction_nav",
        "rejection_score",
        "return_h",
        "volatility_percentile",
    }
    measured = {
        feature.feature_name
        for feature in v2
        if feature.implementation_status is FeatureImplementationStatus.RESEARCH_MEASUREMENT
    }
    assert len(measured) == 40
    v2_by_name = {feature.feature_name: feature for feature in v2}
    assert v2_by_name["imsi_dist_vwap_pct"].unit == "decimal_ratio"
    assert "imsi_covariance_shrinkage_delta" not in v2_by_name
    v3 = feature_semantics_v3()
    measured_v3 = {
        feature.feature_name
        for feature in v3
        if feature.implementation_status is FeatureImplementationStatus.RESEARCH_MEASUREMENT
    }
    assert len(measured_v3) == 43
    v3_by_name = {feature.feature_name: feature for feature in v3}
    assert v3_by_name["imsi_dist_vwap_pct"].unit == "percentage_points"
    assert (
        v3_by_name["imsi_covariance_shrinkage_delta"].normalization_family
        == "prior_state_ewma_shrinkage"
    )
    v4 = feature_semantics_v4()
    measured_v4 = {
        feature.feature_name
        for feature in v4
        if feature.implementation_status is FeatureImplementationStatus.RESEARCH_MEASUREMENT
    }
    assert len(measured_v4) == 53
    v4_by_name = {feature.feature_name: feature for feature in v4}
    assert v4_by_name["atr_5m_24"].normalization_family == "atr_5m_24_arithmetic_true_range"
    assert v4_by_name["icm_slope_per_bar"].unit == "native_price_per_bar"
    assert "icm_z_score" not in v4_by_name


def test_required_types_are_frozen_slotted_dataclasses() -> None:
    required = (
        TradeObservation,
        CompletedTradeBar,
        ProfileDefinition,
        VolumeProfileSnapshot,
        AuctionFeatureVector,
        AuctionStateSnapshot,
        IMSIStateSnapshot,
        ICMStateSnapshot,
        IAEStateSnapshot,
        IndicatorSynergySnapshot,
        CandidateEventObservation,
    )
    for data_type in required:
        assert is_dataclass(data_type)
        assert data_type.__dataclass_params__.frozen
        assert hasattr(data_type, "__slots__")
        assert tuple(field.name for field in fields(data_type))


def test_all_eight_roots_resolve_one_open_semantic_session_segment() -> None:
    engine = SessionEngine(reference_session_policies())
    timestamps = {
        "ES": datetime(2024, 3, 4, 15, tzinfo=UTC),
        "NQ": datetime(2024, 3, 4, 15, tzinfo=UTC),
        "RTY": datetime(2024, 3, 4, 15, tzinfo=UTC),
        "ZT": datetime(2024, 3, 4, 14, tzinfo=UTC),
        "ZN": datetime(2024, 3, 4, 14, tzinfo=UTC),
        "6E": datetime(2024, 3, 4, 14, tzinfo=UTC),
        "6J": datetime(2024, 3, 4, 14, tzinfo=UTC),
        "6B": datetime(2024, 3, 4, 14, tzinfo=UTC),
    }
    for root, timestamp in timestamps.items():
        start, end = engine.session_bounds(root, timestamp)
        assert start <= timestamp < end
        assert engine.session_id(root, timestamp).startswith("session_")


def test_runtime_adapter_uses_actual_trade_ticks_and_main_stays_thin() -> None:
    adapter = (PROJECT_ROOT / "systematic_futures/qc_adapters/lift2_runtime.py").read_text(
        encoding="utf-8"
    )
    main = (PROJECT_ROOT / "main.py").read_text(encoding="utf-8")
    assert "add_future_contract" in adapter
    assert "TickType" in adapter and ".TRADE" in adapter
    assert "continuous.price" not in adapter.lower()
    assert "Lift2Runtime.create" in main
    for formula_token in ("lstsq", "mahalanobis", "value_area", "gap_width"):
        assert formula_token not in main.lower()


def test_runtime_boundary_filters_quotes_and_routes_trade_ticks(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    class _Resolution:
        TICK = "tick"

    class _TickType:
        TRADE = "trade"

    monkeypatch.setattr(
        lift2_runtime,
        "_load_lift2_qc_api",
        lambda: (_Resolution, _TickType),
    )

    class _Host:
        def __init__(self, timestamp: datetime) -> None:
            self.time = timestamp
            self.statistics: dict[str, object] = {}
            self.logs: list[str] = []

        def add_future_contract(self, symbol: object, **kwargs: object) -> object:
            assert str(symbol) == "ESH24"
            assert kwargs == {
                "resolution": "tick",
                "fill_forward": False,
                "extended_market_hours": True,
            }
            return SimpleNamespace(symbol_properties=SimpleNamespace(minimum_price_variation=0.25))

        def set_summary_statistic(self, name: str, value: object) -> None:
            self.statistics[name] = value

        def log(self, message: str) -> None:
            self.logs.append(message)

    start = datetime(2024, 3, 4, 14, 30, 10, tzinfo=UTC)
    host = _Host(start + timedelta(minutes=6))
    runtime = lift2_runtime.Lift2Runtime(
        "ES",
        SimpleNamespace(mapped="ESH24", symbol="ES-CONT"),
        SessionEngine(reference_session_policies()),
    )
    ticks = [
        SimpleNamespace(tick_type="quote", end_time=start, price=5000, quantity=99),
        SimpleNamespace(
            tick_type="trade",
            end_time=start.replace(tzinfo=None),
            price=5000,
            quantity=1,
        ),
        SimpleNamespace(
            tick_type="trade",
            end_time=start + timedelta(minutes=4),
            price=5000.25,
            quantity=2,
        ),
        SimpleNamespace(
            tick_type="trade",
            end_time=start + timedelta(minutes=5),
            price=5000.50,
            quantity=3,
        ),
    ]
    runtime.on_slice(
        host,
        SimpleNamespace(
            future_chains={"ES-CONT": ("ESH24",)},
            ticks={"ESH24": ticks},
        ),
    )
    runtime.finalize(host)
    assert runtime.runtime_summary is not None
    assert runtime.runtime_summary["quote_ticks_ignored"] == 1
    assert runtime.runtime_summary["counts"]["trade_ticks"] == 3
    assert host.statistics["L2.ES.FiveMinuteBars"] == 1
    assert host.statistics["L2.NoOrders"] == 0
    assert host.statistics["L2.NoInsights"] == 0
    assert host.statistics["L2.NoPortfolioTargets"] == 0

from __future__ import annotations

import ast
from dataclasses import fields, is_dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from systematic_futures.config.markets import all_market_definitions
from systematic_futures.config.measurement import REFERENCE_END_DATE, REFERENCE_START_DATE
from systematic_futures.data.sessions import SessionEngine, reference_session_policies
from systematic_futures.domain.enums import RollState
from systematic_futures.domain.errors import UnverifiedQuantConnectApiError
from systematic_futures.measurement.state_models import (
    AuctionFeatureVector,
    AuctionStateSnapshot,
    CandidateEventObservation,
    CompletedTradeBar,
    IAEStateSnapshot,
    ICMStateSnapshot,
    IMSIStateSnapshot,
    IndicatorSynergySnapshot,
    PriceScale,
    ProfileDefinition,
    ProfileReferenceSet,
    TradeObservation,
    VolumeProfileSnapshot,
)
from systematic_futures.qc_adapters import futures_registration as registration_module
from systematic_futures.qc_adapters import runtime as runtime_module

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MEASUREMENT_ROOT = PROJECT_ROOT / "systematic_futures/measurement"
PACKAGE_INITIALIZERS = (
    PROJECT_ROOT / "systematic_futures/config/__init__.py",
    PROJECT_ROOT / "systematic_futures/domain/__init__.py",
    PROJECT_ROOT / "systematic_futures/qc_adapters/__init__.py",
)


def test_package_initializers_are_side_effect_free() -> None:
    for path in PACKAGE_INITIALIZERS:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imports = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Import | ast.ImportFrom)
            and not (isinstance(node, ast.ImportFrom) and node.module == "__future__")
        ]
        assert imports == [], f"{path} must not import runtime submodules"


def test_measurement_modules_are_qc_free() -> None:
    prohibited = {"AlgorithmImports", "QCAlgorithm", "Slice", "Insight", "PortfolioTarget"}
    violations: list[str] = []
    for path in sorted(MEASUREMENT_ROOT.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names: set[str] = set()
            if isinstance(node, ast.Import):
                names.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                names.add(node.module.split(".")[0])
            found = sorted(names.intersection(prohibited))
            if found:
                violations.append(f"{path.name}: {', '.join(found)}")
    assert violations == []


def test_state_models_are_frozen_slotted_dataclasses() -> None:
    required = (
        TradeObservation,
        CompletedTradeBar,
        ProfileDefinition,
        PriceScale,
        ProfileReferenceSet,
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


def test_runtime_adapter_uses_actual_trade_ticks_and_main_stays_thin() -> None:
    adapter = (PROJECT_ROOT / "systematic_futures/qc_adapters/runtime.py").read_text(
        encoding="utf-8"
    )
    main = (PROJECT_ROOT / "main.py").read_text(encoding="utf-8")
    assert "add_future_contract" in adapter
    assert "TickType" in adapter and ".TRADE" in adapter
    assert "continuous.price" not in adapter.lower()
    assert "MeasurementRuntime.create" in main
    for formula_token in ("lstsq", "mahalanobis", "value_area", "gap_width"):
        assert formula_token not in main.lower()


def test_runtime_create_configures_the_exact_reference_boundary(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    subscription = SimpleNamespace(symbol="ZN-CONT", mapped=None)
    registered_roots: list[str] = []

    def register(_host: object, market: object) -> object:
        registered_roots.append(market.root)  # type: ignore[attr-defined]
        return subscription

    monkeypatch.setattr(runtime_module, "register_measurement_future", register)

    class _Host:
        def __init__(self) -> None:
            self.timezone: str | None = None
            self.start: tuple[int, int, int] | None = None
            self.end: tuple[int, int, int] | None = None

        def get_parameter(self, name: str, default: str) -> str:
            return {"measurement_root": "ZN", "measurement_mode": "reference"}.get(
                name,
                default,
            )

        def set_time_zone(self, timezone: str) -> None:
            self.timezone = timezone

        def set_start_date(self, year: int, month: int, day: int) -> None:
            self.start = (year, month, day)

        def set_end_date(self, year: int, month: int, day: int) -> None:
            self.end = (year, month, day)

    host = _Host()
    runtime = runtime_module.MeasurementRuntime.create(host)
    assert runtime.root == "ZN"
    assert runtime.mode == "reference"
    assert registered_roots == ["ZN"]
    assert host.timezone == "UTC"
    assert host.start == (2024, 2, 15)
    assert host.end == (2024, 3, 25)


def test_future_registration_resolves_all_eight_verified_constants(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    class _Subscription:
        symbol = "continuous"

        def __init__(self) -> None:
            self.filter: tuple[int, int] | None = None

        def set_filter(self, minimum_days: int, maximum_days: int) -> None:
            self.filter = (minimum_days, maximum_days)

    class _Host:
        def __init__(self) -> None:
            self.calls: list[tuple[object, object, dict[str, object]]] = []
            self.subscription = _Subscription()

        def add_future(
            self,
            symbol: object,
            resolution_value: object,
            **kwargs: object,
        ) -> _Subscription:
            self.calls.append((symbol, resolution_value, kwargs))
            return self.subscription

    futures = SimpleNamespace(
        Indices=SimpleNamespace(
            SP_500_E_MINI="Futures.Indices.SP_500_E_MINI",
            NASDAQ_100_E_MINI="Futures.Indices.NASDAQ_100_E_MINI",
            RUSSELL_2000_E_MINI="Futures.Indices.RUSSELL_2000_E_MINI",
        ),
        Financials=SimpleNamespace(
            Y_2_TREASURY_NOTE="Futures.Financials.Y_2_TREASURY_NOTE",
            Y_10_TREASURY_NOTE="Futures.Financials.Y_10_TREASURY_NOTE",
        ),
        Currencies=SimpleNamespace(
            EUR="Futures.Currencies.EUR",
            JPY="Futures.Currencies.JPY",
            GBP="Futures.Currencies.GBP",
        ),
    )
    mapping = SimpleNamespace(OPEN_INTEREST="open-interest")
    normalization = SimpleNamespace(BACKWARDS_RATIO="backwards-ratio")
    resolution = SimpleNamespace(MINUTE="minute")
    monkeypatch.setattr(
        registration_module,
        "_load_registration_api",
        lambda: (mapping, normalization, futures, resolution),
    )

    for market in all_market_definitions():
        host = _Host()
        returned = registration_module.register_measurement_future(host, market)
        assert returned is host.subscription
        assert host.calls == [
            (
                market.qc_root_identity,
                "minute",
                {
                    "extended_market_hours": True,
                    "data_mapping_mode": "open-interest",
                    "data_normalization_mode": "backwards-ratio",
                    "contract_depth_offset": 0,
                },
            )
        ]
        assert host.subscription.filter == (0, market.contract_filter_days)


def test_runtime_filters_non_trade_ticks_and_routes_actual_contract_trades(
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    class _Resolution:
        TICK = "tick"

    class _TickType:
        TRADE = "trade"

    monkeypatch.setattr(runtime_module, "_load_qc_api", lambda: (_Resolution, _TickType))

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
    runtime = runtime_module.MeasurementRuntime(
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
            suspicious=False,
            sale_condition="",
        ),
        SimpleNamespace(
            tick_type="trade",
            end_time=start + timedelta(minutes=4),
            price=5000.25,
            quantity=2,
            suspicious=False,
            sale_condition="A",
        ),
        SimpleNamespace(
            tick_type="trade",
            end_time=start + timedelta(minutes=5),
            price=5000.50,
            quantity=3,
            suspicious=False,
            sale_condition="",
        ),
        SimpleNamespace(
            tick_type="trade",
            end_time=start + timedelta(minutes=5, seconds=1),
            price=9000,
            quantity=100,
            suspicious=True,
            sale_condition="LATE",
        ),
    ]
    runtime.on_slice(
        host,
        SimpleNamespace(future_chains={"ES-CONT": ("ESH24",)}, ticks={"ESH24": ticks}),
    )
    runtime.finalize(host)

    assert runtime.runtime_summary is not None
    assert runtime.runtime_summary["non_trade_ticks_ignored"] == 1
    assert runtime.runtime_summary["counts"]["trade_ticks"] == 3
    assert runtime.runtime_summary["counts"]["rejected_trade_ticks"] == 1
    assert runtime.runtime_summary["quality_counts"]["DATA:SOURCE_SUSPICIOUS_EXCLUDED"] == 1
    assert runtime.runtime_summary["quality_counts"]["PROVENANCE:DEDUPLICATION_UNVERIFIABLE"] == 3
    assert runtime.runtime_summary["mode"] == "reference"
    assert runtime.runtime_summary["period"] == {
        "end": REFERENCE_END_DATE,
        "start": REFERENCE_START_DATE,
    }
    assert runtime.runtime_summary["zero_actions"] == {
        "insights": 0,
        "orders": 0,
        "portfolio_targets": 0,
    }
    assert host.statistics["Measurement.ES.FiveMinuteBars"] == 1
    assert host.statistics["Measurement.NoOrders"] == 0
    assert host.statistics["Measurement.NoInsights"] == 0
    assert host.statistics["Measurement.NoPortfolioTargets"] == 0


def test_runtime_rejects_missing_trade_fields_and_excludes_transition_ticks(
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    class _Resolution:
        TICK = "tick"

    class _TickType:
        TRADE = "trade"

    class _Host:
        def __init__(self, timestamp: datetime) -> None:
            self.time = timestamp
            self.statistics: dict[str, object] = {}

        def add_future_contract(self, symbol: object, **kwargs: object) -> object:
            return SimpleNamespace(symbol_properties=SimpleNamespace(minimum_price_variation=0.25))

        def set_summary_statistic(self, name: str, value: object) -> None:
            self.statistics[name] = value

        def log(self, message: str) -> None:
            pass

    monkeypatch.setattr(runtime_module, "_load_qc_api", lambda: (_Resolution, _TickType))
    timestamp = datetime(2024, 3, 13, 14, 30, tzinfo=UTC)
    host = _Host(timestamp)
    runtime = runtime_module.MeasurementRuntime(
        "ES",
        SimpleNamespace(mapped="ESM24", symbol="ES-CONT"),
        SessionEngine(reference_session_policies()),
    )
    missing_price = SimpleNamespace(
        tick_type="trade",
        end_time=timestamp,
        quantity=1,
        suspicious=False,
        sale_condition="",
    )
    with pytest.raises(UnverifiedQuantConnectApiError, match="price/quantity"):
        runtime.on_slice(
            host,
            SimpleNamespace(future_chains={}, ticks={"ESM24": [missing_price]}),
        )

    transition_tick = SimpleNamespace(
        tick_type="trade",
        end_time=timestamp,
        price=5100.0,
        quantity=1,
        suspicious=False,
        sale_condition="",
    )
    monkeypatch.setattr(
        runtime._rolls,
        "current_roll_state",
        lambda root, as_of_utc: RollState.ROLL_TRANSITION,
    )
    runtime.on_slice(
        host,
        SimpleNamespace(future_chains={}, ticks={"ESM24": [transition_tick]}),
    )
    runtime.finalize(host)
    assert runtime.runtime_summary is not None
    assert runtime.runtime_summary["roll_ticks_ignored"] == 1
    assert runtime.runtime_summary["counts"].get("trade_ticks", 0) == 0


def test_contract_switch_provenance_and_internal_state_are_failure_atomic(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    class _Resolution:
        TICK = "tick"

    class _TickType:
        TRADE = "trade"

    class _Host:
        def __init__(self, timestamp: datetime) -> None:
            self.time = timestamp
            self.minimum_tick = 0.25

        def add_future_contract(self, symbol: object, **_kwargs: object) -> object:
            return SimpleNamespace(
                symbol_properties=SimpleNamespace(
                    minimum_price_variation=self.minimum_tick,
                )
            )

    monkeypatch.setattr(runtime_module, "_load_qc_api", lambda: (_Resolution, _TickType))
    continuous = SimpleNamespace(mapped="ESH24", symbol="ES-CONT")
    host = _Host(datetime(2024, 3, 4, 14, 30, tzinfo=UTC))
    runtime = runtime_module.MeasurementRuntime(
        "ES",
        continuous,
        SessionEngine(reference_session_policies()),
    )
    empty_slice = SimpleNamespace(future_chains={}, ticks={})
    runtime.on_slice(host, empty_slice)
    original_stream = runtime._stream
    first_observation = runtime._rolls.observations_for_root("ES")[0]
    assert first_observation.source == "QuantConnect.Security.mapped"

    continuous.mapped = "ESM24"
    host.time += timedelta(days=1)
    host.minimum_tick = 0.0
    with pytest.raises(UnverifiedQuantConnectApiError, match="minimum tick"):
        runtime.on_slice(host, empty_slice)

    assert runtime._stream is original_stream
    assert runtime._mapped_symbol_text == "ESH24"
    assert runtime._completed_streams == []
    assert runtime._roll_count == 0
    assert runtime._rolls.observations_for_root("ES") == (first_observation,)

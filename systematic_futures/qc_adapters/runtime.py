import platform
from collections import Counter
from collections.abc import Iterable, Mapping
from datetime import datetime
from types import MappingProxyType
from typing import Any, cast

import numpy as np

from systematic_futures.config.markets import (
    ALL_MARKETS,
    REFERENCE_MARKETS,
    get_market_definition,
)
from systematic_futures.config.measurement import (
    REFERENCE_END_DATE,
    REFERENCE_START_DATE,
    SMOKE_END_DATE,
    SMOKE_START_DATE,
)
from systematic_futures.config.system import DEFAULT_STRUCTURAL_FEATURE_CONFIG
from systematic_futures.data.rolls import make_mapping_observation
from systematic_futures.data.sessions import (
    SessionEngine,
    reference_session_calendar_exceptions,
    reference_session_policies,
)
from systematic_futures.domain.enums import RollState
from systematic_futures.domain.errors import (
    ContractBoundaryError,
    DataQualityError,
    MarketConfigurationError,
    UnverifiedQuantConnectApiError,
)
from systematic_futures.domain.serialization import canonical_json_bytes, sha256_hex
from systematic_futures.measurement.market_pipeline import (
    ActualContractActivation,
    MarketInputBatch,
    MarketPipeline,
)
from systematic_futures.qc_adapters.data import (
    continuous_bar_from_slice,
    curve_observation_from_chain,
    latest_quote_from_ticks,
    qc_datetime_to_utc,
    trade_observations_from_ticks,
)
from systematic_futures.qc_adapters.futures_registration import register_measurement_future


def _load_qc_api() -> tuple[Any, Any]:
    from AlgorithmImports import Resolution, TickType  # type: ignore[import-not-found]

    return Resolution, TickType


class MeasurementRuntime:
    """QuantConnect composition boundary for deterministic multi-market measurement."""

    def __init__(
        self,
        roots: tuple[str, ...],
        continuous_subscriptions: Mapping[str, object],
        session_engine: SessionEngine,
        *,
        mode: str,
        period_start: str,
        period_end: str,
    ) -> None:
        if not roots or roots != tuple(root for root in ALL_MARKETS if root in roots):
            raise MarketConfigurationError(
                "runtime roots must be a non-empty canonical-order subset of ALL_MARKETS"
            )
        if set(continuous_subscriptions) != set(roots):
            raise MarketConfigurationError(
                "every runtime root requires one continuous subscription"
            )
        self.roots = roots
        self.mode = mode
        self._period_start = period_start
        self._period_end = period_end
        self._sessions = session_engine
        self._continuous: Mapping[str, Any] = MappingProxyType(
            {root: cast(Any, continuous_subscriptions[root]) for root in roots}
        )
        self._pipelines: Mapping[str, MarketPipeline] = MappingProxyType(
            {
                root: MarketPipeline(
                    root=root,
                    continuous_symbol=str(
                        getattr(cast(Any, continuous_subscriptions[root]), "symbol", "")
                    ).strip(),
                    session_engine=session_engine,
                    structural_config=DEFAULT_STRUCTURAL_FEATURE_CONFIG,
                )
                for root in roots
            }
        )
        self._chain_observations: Counter[str] = Counter()
        self._non_market_ticks_ignored: Counter[str] = Counter()
        self._finalized = False
        self._runtime_summary: Mapping[str, object] | None = None

    @classmethod
    def create(cls, algorithm: object) -> "MeasurementRuntime":
        """Create single, reference-three, or all-eight zero-action measurement runtime."""

        host = cast(Any, algorithm)
        requested_root = str(host.get_parameter("measurement_root", "ES")).strip().upper()
        mode = str(host.get_parameter("measurement_mode", "single")).strip().lower()
        if requested_root not in ALL_MARKETS:
            raise MarketConfigurationError(f"measurement_root must be one of {ALL_MARKETS}")
        roots_by_mode = {
            "single": (requested_root,),
            "reference": tuple(root for root in ALL_MARKETS if root in REFERENCE_MARKETS),
            "smoke": ALL_MARKETS,
        }
        roots = roots_by_mode.get(mode)
        if roots is None:
            raise MarketConfigurationError(
                "measurement_mode must be 'single', 'reference', or 'smoke'"
            )
        periods = {
            "single": (REFERENCE_START_DATE, REFERENCE_END_DATE),
            "reference": (REFERENCE_START_DATE, REFERENCE_END_DATE),
            "smoke": (SMOKE_START_DATE, SMOKE_END_DATE),
        }
        start, end = periods[mode]
        start_date = datetime.fromisoformat(start)
        end_date = datetime.fromisoformat(end)
        host.set_time_zone("UTC")
        host.set_start_date(start_date.year, start_date.month, start_date.day)
        host.set_end_date(end_date.year, end_date.month, end_date.day)
        subscriptions = {
            root: register_measurement_future(host, get_market_definition(root)) for root in roots
        }
        return cls(
            roots,
            subscriptions,
            SessionEngine(
                reference_session_policies(),
                reference_session_calendar_exceptions(),
            ),
            mode=mode,
            period_start=start,
            period_end=end,
        )

    @property
    def root(self) -> str:
        """Return the sole root for single mode, otherwise the explicit MULTI label."""

        return self.roots[0] if len(self.roots) == 1 else "MULTI"

    @property
    def runtime_summary(self) -> Mapping[str, object] | None:
        """Return compact finalized runtime evidence, if available."""

        return self._runtime_summary

    def on_slice(self, algorithm: object, qc_slice: object) -> None:
        """Translate one Slice into deterministic root-scoped batches and state updates."""

        if self._finalized:
            raise DataQualityError("finalized runtime cannot process another Slice")
        host = cast(Any, algorithm)
        data = cast(Any, qc_slice)
        observed_at = qc_datetime_to_utc(
            host.time,
            "algorithm time",
            naive_source_timezone="UTC",
        )
        _, tick_type = _load_qc_api()
        for root in self.roots:
            subscription = self._continuous[root]
            pipeline = self._pipelines[root]
            mapped = getattr(subscription, "mapped", None)
            activation = self._activation_if_changed(
                host,
                root,
                subscription,
                pipeline,
                mapped,
                observed_at,
                source="QuantConnect.Security.mapped",
            )
            actual_contract = (
                activation.mapping.actual_contract
                if activation is not None
                else pipeline.actual_contract
            )
            if actual_contract is None:
                continue
            roll_state = (
                activation.mapping.roll_state
                if activation is not None
                else pipeline.current_roll_state(observed_at)
            )
            chain = self._future_chain(data, subscription)
            curve = None
            if chain is not None:
                self._chain_observations[root] += 1
                curve = curve_observation_from_chain(
                    root=root,
                    continuous_symbol=getattr(subscription, "symbol", None),
                    mapped_contract=actual_contract,
                    future_chain=chain,
                    observed_at_utc=observed_at,
                )
            ticks = self._ticks_for_contract(data, actual_contract)
            minimum_tick = (
                activation.minimum_tick
                if activation is not None
                else self._required_minimum_tick(pipeline)
            )
            quote = latest_quote_from_ticks(
                root=root,
                actual_contract=actual_contract,
                ticks=ticks,
                quote_tick_type=tick_type.QUOTE,
                observed_at_utc=observed_at,
                minimum_tick=minimum_tick,
            )
            trades = trade_observations_from_ticks(
                root=root,
                actual_contract=actual_contract,
                ticks=ticks,
                trade_tick_type=tick_type.TRADE,
                observed_at_utc=observed_at,
                minimum_tick=minimum_tick,
                session_engine=self._sessions,
                roll_state=roll_state,
            )
            self._non_market_ticks_ignored[root] += sum(
                getattr(tick, "tick_type", None) not in {tick_type.TRADE, tick_type.QUOTE}
                for tick in ticks
            )
            continuous_bar = continuous_bar_from_slice(
                root=root,
                continuous_symbol=getattr(subscription, "symbol", None),
                mapped_contract=actual_contract,
                qc_slice=data,
                observed_at_utc=observed_at,
                session_engine=self._sessions,
                roll_state=roll_state,
            )
            batch = MarketInputBatch(
                root=root,
                observed_at_utc=observed_at,
                activation=activation,
                continuous_bar=continuous_bar,
                curve_observation=curve,
                quote_observation=quote,
                trades=trades,
                quality_flags=(),
                lineage_hash=sha256_hex(
                    {
                        "root": root,
                        "observed_at_utc": observed_at,
                        "activation": (
                            None if activation is None else activation.mapping.lineage_hash
                        ),
                        "continuous_bar": (
                            None if continuous_bar is None else continuous_bar.source_lineage_hash
                        ),
                        "curve": None if curve is None else curve.source_lineage_hash,
                        "quote": None if quote is None else quote.source_lineage_hash,
                        "trades": trades,
                    }
                ),
            )
            pipeline.on_batch(batch)

    def on_mapping_events(self, algorithm: object, events: object) -> None:
        """Apply explicit QC mapping observations before the matching Slice is processed."""

        if self._finalized:
            raise DataQualityError("finalized runtime cannot process mapping events")
        host = cast(Any, algorithm)
        qc_events = cast(Any, events)
        items = getattr(qc_events, "items", None)
        if items is None or not callable(items):
            raise UnverifiedQuantConnectApiError("SymbolChangedEvents lacks items()")
        observed_at = qc_datetime_to_utc(
            host.time,
            "mapping observed_at",
            naive_source_timezone="UTC",
        )
        root_by_continuous = {
            str(getattr(self._continuous[root], "symbol", "")): root for root in self.roots
        }
        event_items = cast(Iterable[tuple[object, object]], items())
        for continuous, changed_event in event_items:
            root = root_by_continuous.get(str(continuous))
            if root is None:
                raise ContractBoundaryError(f"unknown continuous mapping event: {continuous}")
            pipeline = self._pipelines[root]
            old_symbol = getattr(changed_event, "old_symbol", None)
            if (
                pipeline.actual_contract is not None
                and old_symbol is not None
                and str(old_symbol).strip()
                and str(old_symbol).strip() != pipeline.actual_contract
            ):
                raise ContractBoundaryError(
                    "mapping event old contract differs from active contract"
                )
            new_symbol = getattr(changed_event, "new_symbol", None)
            if new_symbol is None or not str(new_symbol).strip():
                raise ContractBoundaryError("mapping event has no new actual contract")
            activation = self._activation_if_changed(
                host,
                root,
                self._continuous[root],
                pipeline,
                new_symbol,
                observed_at,
                source="QuantConnect.SymbolChangedEvent",
            )
            if activation is None:
                continue
            pipeline.on_batch(
                MarketInputBatch(
                    root=root,
                    observed_at_utc=observed_at,
                    activation=activation,
                    continuous_bar=None,
                    curve_observation=None,
                    quote_observation=None,
                    trades=(),
                    quality_flags=(),
                    lineage_hash=sha256_hex((root, activation.mapping.lineage_hash)),
                )
            )

    def finalize(self, algorithm: object) -> None:
        """Finalize every root and publish compact zero-action runtime evidence once."""

        if self._finalized:
            raise DataQualityError("MeasurementRuntime may only be finalized once")
        host = cast(Any, algorithm)
        observed_at = qc_datetime_to_utc(
            host.time,
            "algorithm final time",
            naive_source_timezone="UTC",
        )
        markets = {root: dict(self._pipelines[root].finalize(observed_at)) for root in self.roots}
        total_counts: Counter[str] = Counter()
        total_quality: Counter[str] = Counter()
        total_coverage: Counter[str] = Counter()
        for root, market in markets.items():
            total_counts.update(cast(Mapping[str, int], market["counts"]))
            total_quality.update(cast(Mapping[str, int], market["quality_counts"]))
            total_coverage.update(cast(Mapping[str, int], market["coverage"]))
            prefix = f"Measurement.{root}"
            counts = cast(Mapping[str, int], market["counts"])
            coverage = cast(Mapping[str, int], market["coverage"])
            host.set_summary_statistic(f"{prefix}.TradeTicks", counts.get("trade_ticks", 0))
            host.set_summary_statistic(
                f"{prefix}.FiveMinuteBars", counts.get("five_minute_bars", 0)
            )
            host.set_summary_statistic(
                f"{prefix}.ThirtyMinuteBars", counts.get("thirty_minute_bars", 0)
            )
            host.set_summary_statistic(
                f"{prefix}.StructuralSnapshots", counts.get("structural_snapshots", 0)
            )
            host.set_summary_statistic(
                f"{prefix}.CandidateEvents", coverage.get("candidate_events_total", 0)
            )
            host.set_summary_statistic(
                f"{prefix}.ContractCount", cast(int, market["contract_count"])
            )
            host.set_summary_statistic(f"{prefix}.RollCount", cast(int, market["roll_count"]))
        measurement_hash = sha256_hex(
            tuple((root, markets[root]["measurement_hash"]) for root in self.roots)
        )
        summary: dict[str, object] = {
            "mode": self.mode,
            "root": self.root,
            "roots": self.roots,
            "period": {"start": self._period_start, "end": self._period_end},
            "markets": markets,
            "counts": dict(sorted(total_counts.items())),
            "quality_counts": dict(sorted(total_quality.items())),
            "coverage": dict(sorted(total_coverage.items())),
            "chain_observations": dict(sorted(self._chain_observations.items())),
            "non_market_ticks_ignored": dict(sorted(self._non_market_ticks_ignored.items())),
            "measurement_hash": measurement_hash,
            "numpy_version": np.__version__,
            "python_version": platform.python_version(),
            "zero_actions": {"insights": 0, "orders": 0, "portfolio_targets": 0},
        }
        if len(self.roots) == 1:
            root_summary = markets[self.roots[0]]
            summary["contract_count"] = root_summary["contract_count"]
            summary["contracts"] = root_summary["contracts"]
            summary["roll_count"] = root_summary["roll_count"]
            summary["non_trade_ticks_ignored"] = self._non_market_ticks_ignored[self.roots[0]]
        self._runtime_summary = MappingProxyType(summary)
        host.set_summary_statistic("Measurement.NoOrders", 0)
        host.set_summary_statistic("Measurement.NoInsights", 0)
        host.set_summary_statistic("Measurement.NoPortfolioTargets", 0)
        host.set_summary_statistic("Measurement.Hash", measurement_hash)
        host.set_summary_statistic("Measurement.NumPyVersion", np.__version__)
        host.set_summary_statistic("Measurement.PythonVersion", platform.python_version())
        host.set_summary_statistic(
            "Measurement.Roots",
            canonical_json_bytes(self.roots).decode("utf-8"),
        )
        host.log(f"MEASUREMENT_RUNTIME {canonical_json_bytes(summary).decode('utf-8')}")
        self._finalized = True

    def _activation_if_changed(
        self,
        algorithm: Any,
        root: str,
        subscription: Any,
        pipeline: MarketPipeline,
        mapped_symbol: object,
        observed_at: datetime,
        *,
        source: str,
    ) -> ActualContractActivation | None:
        mapped_text = str(mapped_symbol).strip() if mapped_symbol is not None else ""
        if not mapped_text or mapped_text == pipeline.actual_contract:
            return None
        resolution, _ = _load_qc_api()
        security = algorithm.add_future_contract(
            mapped_symbol,
            resolution=resolution.TICK,
            fill_forward=False,
            extended_market_hours=True,
        )
        properties = getattr(security, "symbol_properties", None)
        minimum_tick = float(getattr(properties, "minimum_price_variation", 0.0))
        if not minimum_tick > 0:
            raise UnverifiedQuantConnectApiError(
                "actual future subscription returned no positive minimum tick"
            )
        old_contract = pipeline.actual_contract
        observation = make_mapping_observation(
            root=root,
            continuous_symbol=str(getattr(subscription, "symbol", "")).strip(),
            old_mapped_contract=old_contract,
            new_mapped_contract=mapped_text,
            actual_contract=mapped_text,
            event_time_utc=observed_at,
            available_time_utc=observed_at,
            mapping_mode=get_market_definition(root).mapping_mode,
            source=source,
            roll_state=(RollState.NORMAL if old_contract is None else RollState.ROLL_TRANSITION),
        )
        return ActualContractActivation(observation, minimum_tick)

    @staticmethod
    def _future_chain(data: Any, subscription: Any) -> object | None:
        chains = getattr(data, "future_chains", None)
        if chains is None:
            return None
        getter = getattr(chains, "get", None)
        if getter is None or not callable(getter):
            raise UnverifiedQuantConnectApiError("Slice.future_chains lacks get()")
        return getter(getattr(subscription, "symbol", None))

    @staticmethod
    def _ticks_for_contract(data: Any, actual_contract: str) -> tuple[object, ...]:
        tick_mapping = getattr(data, "ticks", None)
        if tick_mapping is None:
            raise UnverifiedQuantConnectApiError("Slice lacks ticks collection")
        items = getattr(tick_mapping, "items", None)
        if items is None or not callable(items):
            raise UnverifiedQuantConnectApiError("Slice.ticks lacks items()")
        for symbol, ticks in cast(Iterable[tuple[object, Iterable[object]]], items()):
            if str(symbol) == actual_contract:
                return tuple(ticks)
        return ()

    @staticmethod
    def _required_minimum_tick(pipeline: MarketPipeline) -> float:
        minimum_tick = pipeline.minimum_tick
        if minimum_tick is None or not minimum_tick > 0:
            raise ContractBoundaryError("active actual contract has no minimum tick")
        return minimum_tick


__all__ = ("MeasurementRuntime", "qc_datetime_to_utc")

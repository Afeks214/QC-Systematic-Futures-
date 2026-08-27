import platform
from collections import Counter
from collections.abc import Mapping
from datetime import datetime
from types import MappingProxyType
from typing import Any, cast

import numpy as np

from systematic_futures.config.markets import get_market_definition
from systematic_futures.config.research import (
    LIFT2_ALL_MARKETS,
    LIFT2_DEEP_END_DATE,
    LIFT2_DEEP_START_DATE,
    LIFT2_REFERENCE_MARKETS,
    LIFT2_SMOKE_END_DATE,
    LIFT2_SMOKE_START_DATE,
)
from systematic_futures.data.rolls import MappingObservation, RollManager
from systematic_futures.data.sessions import SessionEngine, reference_session_policies
from systematic_futures.domain.errors import (
    ContractBoundaryError,
    DataQualityError,
    MarketConfigurationError,
    UnverifiedQuantConnectApiError,
)
from systematic_futures.domain.serialization import canonical_json_bytes, sha256_hex
from systematic_futures.measurement.events import candidate_coverage
from systematic_futures.measurement.state_models import TradeObservation
from systematic_futures.measurement.stream import MeasurementStream
from systematic_futures.qc_adapters.futures_registration import register_measurement_future
from systematic_futures.qc_adapters.probe_recorder import qc_datetime_to_utc


def _load_lift2_qc_api() -> tuple[Any, Any]:
    from AlgorithmImports import Resolution, TickType  # type: ignore[import-not-found]

    return Resolution, TickType


class Lift2Runtime:
    """Thin QuantConnect boundary around the shared deterministic measurement core."""

    def __init__(
        self,
        root: str,
        continuous_subscription: object,
        session_engine: SessionEngine,
        *,
        mode: str = "deep",
        period_start: str = LIFT2_DEEP_START_DATE,
        period_end: str = LIFT2_DEEP_END_DATE,
    ) -> None:
        self.root = root
        self.mode = mode
        self._period_start = period_start
        self._period_end = period_end
        self._continuous = cast(Any, continuous_subscription)
        self._sessions = session_engine
        self._rolls = RollManager()
        self._mapped_symbol: object | None = None
        self._mapped_symbol_text: str | None = None
        self._stream: MeasurementStream | None = None
        self._completed_streams: list[MeasurementStream] = []
        self._contracts: set[str] = set()
        self._roll_count = 0
        self._quote_ticks_ignored = 0
        self._chain_observations = 0
        self._finalized = False
        self._runtime_summary: Mapping[str, object] | None = None

    @classmethod
    def create(cls, algorithm: object) -> "Lift2Runtime":
        """Configure one root's deep or smoke replay from verified QC parameters.

        Units: calendar dates and tick/minute subscriptions. Time semantics: UTC
        algorithm time; `deep` is the fixed reference window and `smoke` is the fixed
        bounded all-market window. Missingness: invalid roots/modes raise without a
        fallback. Raises: configuration or verified QC API errors.
        """

        host = cast(Any, algorithm)
        root = str(host.get_parameter("lift2_root", "ES")).strip().upper()
        mode = str(host.get_parameter("lift2_mode", "deep")).strip().lower()
        if root not in LIFT2_ALL_MARKETS:
            raise MarketConfigurationError(f"lift2_root must be one of {LIFT2_ALL_MARKETS}")
        if mode not in {"deep", "smoke"}:
            raise MarketConfigurationError("lift2_mode must be 'deep' or 'smoke'")
        if mode == "deep" and root not in LIFT2_REFERENCE_MARKETS:
            raise MarketConfigurationError("deep mode is restricted to ES, ZN, and 6E")
        start = LIFT2_DEEP_START_DATE if mode == "deep" else LIFT2_SMOKE_START_DATE
        end = LIFT2_DEEP_END_DATE if mode == "deep" else LIFT2_SMOKE_END_DATE
        start_date = datetime.fromisoformat(start)
        end_date = datetime.fromisoformat(end)
        host.set_time_zone("UTC")
        host.set_start_date(start_date.year, start_date.month, start_date.day)
        host.set_end_date(end_date.year, end_date.month, end_date.day)
        subscription = register_measurement_future(host, get_market_definition(root))
        return cls(
            root,
            subscription,
            SessionEngine(reference_session_policies()),
            mode=mode,
            period_start=start,
            period_end=end,
        )

    @property
    def runtime_summary(self) -> Mapping[str, object] | None:
        """Return the compact finalized runtime summary, if finalization occurred."""

        return self._runtime_summary

    def on_slice(self, algorithm: object, qc_slice: object) -> None:
        """Observe mapping/chain identity and admit only mapped actual-contract trades.

        Units: QC native tick price and quantity. Time semantics: LEAN delivers tick
        EndTime in the configured algorithm timezone (UTC); availability is the same
        UTC time frontier.
        Missingness: no mapped contract means no measurement row. Raises: API,
        boundary, session, timing, or data-quality errors.
        """

        host = cast(Any, algorithm)
        data = cast(Any, qc_slice)
        observed_at = qc_datetime_to_utc(
            host.time,
            "algorithm time",
            naive_source_timezone="UTC",
        )
        mapped = getattr(self._continuous, "mapped", None)
        if mapped is not None and str(mapped).strip():
            self._switch_contract(host, mapped, observed_at)
        chains = getattr(data, "future_chains", None)
        if chains is not None:
            chain = chains.get(getattr(self._continuous, "symbol", None))
            if chain is not None:
                self._chain_observations += 1
        if self._stream is None or self._mapped_symbol_text is None:
            return
        _, tick_type = _load_lift2_qc_api()
        tick_mapping = getattr(data, "ticks", None)
        if tick_mapping is None:
            raise UnverifiedQuantConnectApiError("Slice lacks ticks collection")
        for symbol, ticks in tick_mapping.items():
            if str(symbol) != self._mapped_symbol_text:
                continue
            for tick in ticks:
                if getattr(tick, "tick_type", None) != tick_type.TRADE:
                    self._quote_ticks_ignored += 1
                    continue
                exchange_time = qc_datetime_to_utc(
                    getattr(tick, "end_time", None),
                    "trade tick end_time",
                    naive_source_timezone="UTC",
                )
                if not hasattr(tick, "suspicious") or not hasattr(tick, "sale_condition"):
                    raise UnverifiedQuantConnectApiError(
                        "trade Tick lacks verified suspicious/sale_condition metadata"
                    )
                price = float(getattr(tick, "price", 0.0))
                quantity = float(getattr(tick, "quantity", 0.0))
                trade_condition_text = str(tick.sale_condition).strip()
                source_quality_flags = ("SOURCE_SUSPICIOUS",) if bool(tick.suspicious) else ()
                session_id = self._sessions.session_id(self.root, exchange_time)
                roll_state = self._rolls.current_roll_state(self.root, observed_at)
                self._stream.on_trade(
                    TradeObservation(
                        root=self.root,
                        contract_symbol=self._mapped_symbol_text,
                        exchange_time_utc=exchange_time,
                        available_at_utc=observed_at,
                        price=price,
                        quantity=quantity,
                        minimum_tick=self._stream.minimum_tick,
                        session_id=session_id,
                        roll_state=roll_state,
                        trade_condition=trade_condition_text or None,
                        source_quality_flags=source_quality_flags,
                    )
                )

    def on_mapping_events(self, algorithm: object, events: object) -> None:
        """Finalize/reset on an explicit mapping change delivered by QC.

        Units: one mapping observation. Time semantics: the UTC algorithm clock is the
        visibility and availability time; no event is backdated. Missingness: unknown
        continuous identities are rejected. Raises: verified API or contract errors.
        """

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
        continuous_text = str(getattr(self._continuous, "symbol", ""))
        for continuous, changed_event in items():
            if str(continuous) != continuous_text:
                raise ContractBoundaryError(f"unknown continuous mapping event: {continuous}")
            new_symbol = getattr(changed_event, "new_symbol", None)
            if new_symbol is None or not str(new_symbol).strip():
                raise ContractBoundaryError("mapping event has no new actual contract")
            self._switch_contract(host, new_symbol, observed_at)

    def finalize(self, algorithm: object) -> None:
        """Finalize compact evidence and publish QC summary statistics exactly once.

        Units: observed counts and content hashes. Time semantics: remaining completed
        buckets use the final UTC algorithm clock; incomplete tails are not emitted.
        Missingness: absent rare events remain zero. Raises: measurement, canonical
        serialization, or verified QC statistic errors.
        """

        if self._finalized:
            raise DataQualityError("Lift2Runtime may only be finalized once")
        host = cast(Any, algorithm)
        observed_at = qc_datetime_to_utc(
            host.time,
            "algorithm final time",
            naive_source_timezone="UTC",
        )
        if self._stream is not None:
            self._stream.finalize(observed_at, observed_at)
            self._completed_streams.append(self._stream)
            self._stream = None
        counts: Counter[str] = Counter()
        events = []
        synergies = {}
        session_types = {}
        stream_hashes = []
        quality: Counter[str] = Counter()
        for stream in self._completed_streams:
            counts.update(stream.counts)
            quality.update(stream.quality_counts)
            events.extend(stream.candidate_events)
            synergies.update(stream.synergy_snapshots)
            session_types.update(stream.session_types)
            stream_hashes.append(stream.measurement_hash())
        coverage = candidate_coverage(events, synergies, session_types)
        measurement_hash = sha256_hex(tuple(stream_hashes))
        summary = {
            "chain_observations": self._chain_observations,
            "contract_count": len(self._contracts),
            "contracts": sorted(self._contracts),
            "counts": dict(sorted(counts.items())),
            "coverage": coverage,
            "coverage_hash": sha256_hex(coverage),
            "measurement_hash": measurement_hash,
            "mode": self.mode,
            "numpy_version": np.__version__,
            "period": {"end": self._period_end, "start": self._period_start},
            "python_version": platform.python_version(),
            "quality_counts": dict(sorted(quality.items())),
            "quote_ticks_ignored": self._quote_ticks_ignored,
            "roll_count": self._roll_count,
            "root": self.root,
            "zero_actions": {"insights": 0, "orders": 0, "portfolio_targets": 0},
        }
        self._runtime_summary = MappingProxyType(summary)
        prefix = f"L2.{self.root}"
        statistic_counts = {
            "TradeTicks": counts["trade_ticks"],
            "FiveMinuteBars": counts["five_minute_bars"],
            "ThirtyMinuteBars": counts["thirty_minute_bars"],
            "ProfileSnapshots": counts["developing_profiles"] + counts["rolling_profiles"],
            "FinalProfiles": counts["final_profiles"],
            "IMSISnapshots": counts["imsi_snapshots"],
            "ICMSnapshots": counts["icm_snapshots"],
            "IAERetestEvents": counts["iae_retest_events"],
            "CandidateEvents": counts["candidate_events"],
            "UniqueSessions": len(session_types),
            "ContractCount": len(self._contracts),
            "RollCount": self._roll_count,
        }
        for name, value in statistic_counts.items():
            host.set_summary_statistic(f"{prefix}.{name}", value)
        host.set_summary_statistic("L2.NoOrders", 0)
        host.set_summary_statistic("L2.NoInsights", 0)
        host.set_summary_statistic("L2.NoPortfolioTargets", 0)
        host.set_summary_statistic("L2.MeasurementHash", measurement_hash)
        host.set_summary_statistic("L2.NumPyVersion", np.__version__)
        host.set_summary_statistic("L2.PythonVersion", platform.python_version())
        host.set_summary_statistic("L2.CoverageHash", summary["coverage_hash"])
        host.set_summary_statistic(
            "L2.Coverage",
            canonical_json_bytes(coverage).decode("utf-8"),
        )
        host.log(f"LIFT_2_RUNTIME {canonical_json_bytes(summary).decode('utf-8')}")
        self._finalized = True

    def _switch_contract(
        self,
        algorithm: Any,
        mapped_symbol: object,
        observed_at: datetime,
    ) -> None:
        mapped_text = str(mapped_symbol).strip()
        if not mapped_text:
            raise ContractBoundaryError("mapped actual contract must be non-blank")
        if mapped_text == self._mapped_symbol_text:
            return
        old_text = self._mapped_symbol_text
        if self._stream is not None:
            self._stream.finalize(observed_at, observed_at)
            self._completed_streams.append(self._stream)
            self._roll_count += 1
        self._rolls.observe_mapping(
            MappingObservation(
                root=self.root,
                old_mapped_symbol=old_text,
                new_mapped_symbol=mapped_text,
                observed_at_utc=observed_at,
                effective_at_utc=observed_at,
            )
        )
        resolution, _ = _load_lift2_qc_api()
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
        self._mapped_symbol = mapped_symbol
        self._mapped_symbol_text = mapped_text
        self._contracts.add(mapped_text)
        self._stream = MeasurementStream(
            self.root,
            mapped_text,
            minimum_tick,
            self._sessions,
        )


__all__ = ("Lift2Runtime",)

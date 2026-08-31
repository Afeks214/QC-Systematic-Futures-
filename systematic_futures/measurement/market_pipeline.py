from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from types import MappingProxyType

from systematic_futures.config.system import StructuralFeatureConfig
from systematic_futures.data.rolls import MappingObservation, RollManager
from systematic_futures.data.sessions import SessionEngine
from systematic_futures.domain.enums import RollState
from systematic_futures.domain.errors import (
    ContractBoundaryError,
    DataQualityError,
    DataTimingInvariantError,
    TimeSemanticsError,
)
from systematic_futures.domain.serialization import sha256_hex
from systematic_futures.measurement.state_models import (
    CandidateEventObservation,
    TradeObservation,
)
from systematic_futures.measurement.stream import MeasurementStream
from systematic_futures.measurement.structural import StructuralStateEngine
from systematic_futures.measurement.structural_inputs import (
    ContinuousBarObservation,
    ContractCurveObservation,
    QuoteObservation,
)
from systematic_futures.measurement.structural_sessions import ContinuousSessionCloseBuilder
from systematic_futures.measurement.structural_state import StructuralStateSnapshot


def _require_utc(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise TimeSemanticsError(f"{field_name} must be timezone-aware")
    if value.utcoffset() != timedelta(0):
        raise TimeSemanticsError(f"{field_name} must be normalized to UTC")


def _require_text(value: str, field_name: str) -> None:
    if not value.strip():
        raise DataQualityError(f"{field_name} must be non-blank")


@dataclass(frozen=True, slots=True)
class ActualContractActivation:
    """One validated actual-contract activation produced at the QC boundary.

    ``minimum_tick`` is native contract price per tick. The mapping observation remains
    descriptive and never authorizes an execution roll.
    """

    mapping: MappingObservation
    minimum_tick: float

    def __post_init__(self) -> None:
        if not self.minimum_tick > 0:
            raise DataQualityError("minimum_tick must be positive")


@dataclass(frozen=True, slots=True)
class MarketInputBatch:
    """One root-scoped immutable batch visible at a single runtime frontier."""

    root: str
    observed_at_utc: datetime
    activation: ActualContractActivation | None
    continuous_bar: ContinuousBarObservation | None
    curve_observation: ContractCurveObservation | None
    quote_observation: QuoteObservation | None
    trades: tuple[TradeObservation, ...]
    quality_flags: tuple[str, ...]
    lineage_hash: str

    def __post_init__(self) -> None:
        _require_text(self.root, "root")
        _require_utc(self.observed_at_utc, "observed_at_utc")
        if self.quality_flags != tuple(sorted(set(self.quality_flags))):
            raise DataQualityError("quality_flags must be sorted and unique")
        components: tuple[object | None, ...] = (
            self.activation.mapping if self.activation is not None else None,
            self.continuous_bar,
            self.curve_observation,
            self.quote_observation,
        )
        for component in components:
            if component is not None and getattr(component, "root", None) != self.root:
                raise ContractBoundaryError("batch component root differs from batch root")
        previous_trade_time: datetime | None = None
        for trade in self.trades:
            if trade.root != self.root:
                raise ContractBoundaryError("trade root differs from batch root")
            if trade.available_at_utc > self.observed_at_utc:
                raise DataTimingInvariantError("trade is unavailable at batch frontier")
            if previous_trade_time is not None and trade.exchange_time_utc < previous_trade_time:
                raise DataTimingInvariantError(
                    "batch trades must preserve nondecreasing delivery time"
                )
            previous_trade_time = trade.exchange_time_utc
        for component in (
            self.continuous_bar,
            self.curve_observation,
            self.quote_observation,
        ):
            if component is not None and component.available_at_utc > self.observed_at_utc:
                raise DataTimingInvariantError("batch component is unavailable at batch frontier")
        if len(self.lineage_hash) != 64:
            raise DataQualityError("lineage_hash must be a SHA-256 digest")


@dataclass(frozen=True, slots=True)
class MarketPipelineUpdate:
    """Outputs produced by one deterministic root-scoped batch update."""

    root: str
    observed_at_utc: datetime
    structural_snapshot: StructuralStateSnapshot | None
    latest_quote: QuoteObservation | None
    candidate_events: tuple[CandidateEventObservation, ...]
    quality_flags: tuple[str, ...]
    lineage_hash: str


class MarketPipeline:
    """Own one market's actual-contract measurements and slow structural state."""

    def __init__(
        self,
        *,
        root: str,
        continuous_symbol: str,
        session_engine: SessionEngine,
        structural_config: StructuralFeatureConfig,
    ) -> None:
        _require_text(root, "root")
        _require_text(continuous_symbol, "continuous_symbol")
        self.root = root
        self.continuous_symbol = continuous_symbol
        self._sessions = session_engine
        self._rolls = RollManager()
        self._structural = StructuralStateEngine(root, continuous_symbol, structural_config)
        self._close_builder = ContinuousSessionCloseBuilder(root, continuous_symbol)
        self._stream: MeasurementStream | None = None
        self._actual_contract: str | None = None
        self._minimum_tick: float | None = None
        self._latest_quote: QuoteObservation | None = None
        self._latest_structural: StructuralStateSnapshot | None = None
        self._last_frontier_utc: datetime | None = None
        self._archive_counts: Counter[str] = Counter()
        self._archive_quality: Counter[str] = Counter()
        self._coverage_counts: Counter[str] = Counter()
        self._archive_hash = sha256_hex(())
        self._contracts: set[str] = set()
        self._roll_count = 0

    @property
    def actual_contract(self) -> str | None:
        """Return the active actual contract identity, if mapped."""

        return self._actual_contract

    @property
    def minimum_tick(self) -> float | None:
        """Return native minimum tick for the active contract."""

        return self._minimum_tick

    @property
    def latest_structural(self) -> StructuralStateSnapshot | None:
        """Return the latest immutable structural snapshot."""

        return self._latest_structural

    @property
    def latest_quote(self) -> QuoteObservation | None:
        """Return the latest complete two-sided actual-contract quote."""

        return self._latest_quote

    def current_roll_state(self, as_of_utc: datetime) -> RollState:
        """Return the causal descriptive roll state at one frontier."""

        return self._rolls.current_roll_state(self.root, as_of_utc)

    def on_batch(self, batch: MarketInputBatch) -> MarketPipelineUpdate:
        """Process mapping, curve, quote, trade, then completed structural state.

        This method has no forecasting, sizing, risk, or order authority.
        """

        if batch.root != self.root:
            raise ContractBoundaryError("batch root differs from market pipeline")
        if self._last_frontier_utc is not None and batch.observed_at_utc < self._last_frontier_utc:
            raise DataTimingInvariantError("market pipeline frontier cannot move backward")
        self._last_frontier_utc = batch.observed_at_utc
        if batch.activation is not None:
            self._activate_contract(batch.activation, batch.observed_at_utc)
        if batch.curve_observation is not None:
            self._structural.update_curve(batch.curve_observation)
        if batch.quote_observation is not None:
            self._accept_quote(batch.quote_observation)
        before = self._active_candidate_count()
        stream = self._stream
        if stream is not None:
            for trade in batch.trades:
                if trade.contract_symbol != self._actual_contract:
                    raise ContractBoundaryError("trade differs from active actual contract")
                if trade.roll_state not in {RollState.NORMAL, RollState.POST_ROLL}:
                    self._archive_counts["roll_ticks_ignored"] += 1
                    continue
                stream.on_trade(trade)
        elif batch.trades:
            raise ContractBoundaryError("trades arrived before actual-contract activation")
        structural_snapshot: StructuralStateSnapshot | None = None
        if batch.continuous_bar is not None:
            if batch.continuous_bar.mapped_contract != self._actual_contract:
                raise ContractBoundaryError(
                    "continuous bar mapping differs from active actual contract"
                )
            completed = self._close_builder.update(batch.continuous_bar)
            if completed is not None:
                structural_snapshot = self._structural.update_session_close(completed)
                self._latest_structural = structural_snapshot
                self._archive_counts["structural_snapshots"] += 1
                if structural_snapshot.measurement_ready:
                    self._archive_counts["trend_ready_snapshots"] += 1
                if (
                    structural_snapshot.carry is not None
                    and structural_snapshot.carry.normalized_carry is not None
                ):
                    self._archive_counts["carry_ready_snapshots"] += 1
        candidates = self._active_candidate_slice(before)
        flags = set(batch.quality_flags)
        if structural_snapshot is not None:
            flags.update(structural_snapshot.quality_flags)
        update_hash = sha256_hex(
            {
                "batch": batch.lineage_hash,
                "structural_snapshot": (
                    None if structural_snapshot is None else structural_snapshot.snapshot_id
                ),
                "quote": (
                    None if self._latest_quote is None else self._latest_quote.source_lineage_hash
                ),
                "candidate_ids": tuple(event.event_id for event in candidates),
            }
        )
        return MarketPipelineUpdate(
            root=self.root,
            observed_at_utc=batch.observed_at_utc,
            structural_snapshot=structural_snapshot,
            latest_quote=self._latest_quote,
            candidate_events=candidates,
            quality_flags=tuple(sorted(flags)),
            lineage_hash=update_hash,
        )

    def finalize(self, as_of_utc: datetime) -> Mapping[str, object]:
        """Finalize active state and return compact bounded runtime evidence."""

        _require_utc(as_of_utc, "as_of_utc")
        pending_close = self._close_builder.finalize(as_of_utc)
        if pending_close is not None:
            self._latest_structural = self._structural.update_session_close(pending_close)
            self._archive_counts["structural_snapshots"] += 1
        if self._stream is not None:
            self._stream.finalize(as_of_utc, as_of_utc)
            self._archive_stream(self._stream)
            self._stream = None
        return self.summary()

    def summary(self) -> Mapping[str, object]:
        """Return compact deterministic evidence without retaining completed streams."""

        active_counts: Counter[str] = Counter()
        active_quality: Counter[str] = Counter()
        if self._stream is not None:
            active_counts.update(self._stream.counts)
            active_quality.update(self._stream.quality_counts)
        counts: Counter[str] = self._archive_counts + active_counts
        quality: Counter[str] = self._archive_quality + active_quality
        payload: dict[str, object] = {
            "root": self.root,
            "continuous_symbol": self.continuous_symbol,
            "actual_contract": self._actual_contract,
            "contracts": tuple(sorted(self._contracts)),
            "contract_count": len(self._contracts),
            "roll_count": self._roll_count,
            "counts": dict(sorted(counts.items())),
            "quality_counts": dict(sorted(quality.items())),
            "coverage": dict(sorted(self._coverage_counts.items())),
            "measurement_hash": self._combined_measurement_hash(),
            "latest_structural_snapshot_id": (
                None if self._latest_structural is None else self._latest_structural.snapshot_id
            ),
            "latest_quote_lineage_hash": (
                None if self._latest_quote is None else self._latest_quote.source_lineage_hash
            ),
            "bounded_state": {
                "completed_stream_objects": 0,
                "active_stream_objects": int(self._stream is not None),
                "structural_close_capacity": self._structural.config.maximum_trend_lookback + 1,
                "carry_history_capacity": (
                    self._structural.config.carry_normalization_window_sessions
                ),
            },
        }
        return MappingProxyType(payload)

    def _activate_contract(
        self,
        activation: ActualContractActivation,
        observed_at_utc: datetime,
    ) -> None:
        observation = activation.mapping
        if observation.root != self.root or observation.continuous_symbol != self.continuous_symbol:
            raise ContractBoundaryError("activation identity differs from market pipeline")
        if observation.available_time_utc > observed_at_utc:
            raise DataTimingInvariantError("activation is unavailable at batch frontier")
        if observation.new_mapped_contract == self._actual_contract:
            self._rolls.observe_mapping(observation)
            return
        staged = RollManager()
        for existing in self._rolls.observations_for_root(self.root):
            staged.observe_mapping(existing)
        staged.observe_mapping(observation)
        next_stream = MeasurementStream(
            self.root,
            observation.actual_contract,
            activation.minimum_tick,
            self._sessions,
        )
        old_stream = self._stream
        if old_stream is not None:
            old_stream.finalize(observed_at_utc, observed_at_utc)
        self._rolls.observe_mapping(observation)
        if old_stream is not None:
            self._archive_stream(old_stream)
            self._roll_count += 1
        self._stream = next_stream
        self._actual_contract = observation.actual_contract
        self._minimum_tick = activation.minimum_tick
        self._contracts.add(observation.actual_contract)
        self._latest_quote = None

    def _accept_quote(self, quote: QuoteObservation) -> None:
        if quote.root != self.root or quote.actual_contract != self._actual_contract:
            raise ContractBoundaryError("quote differs from active actual contract")
        if (
            self._latest_quote is not None
            and quote.event_time_utc < self._latest_quote.event_time_utc
        ):
            raise DataTimingInvariantError("quote state cannot move backward")
        self._latest_quote = quote
        self._archive_counts["quote_observations"] += 1

    def _archive_stream(self, stream: MeasurementStream) -> None:
        self._archive_counts.update(stream.counts)
        self._archive_quality.update(stream.quality_counts)
        events = stream.candidate_events
        self._coverage_counts["candidate_events_total"] += len(events)
        self._coverage_counts["candidate_events_base_ready"] += sum(
            event.readiness.base_event_ready for event in events
        )
        self._coverage_counts["candidate_events_imsi_ready"] += sum(
            event.readiness.imsi_state_ready for event in events
        )
        self._coverage_counts["candidate_events_icm_ready"] += sum(
            event.readiness.icm_state_ready for event in events
        )
        self._coverage_counts["candidate_events_iae_structural_ready"] += sum(
            event.readiness.iae_structural_ready for event in events
        )
        self._coverage_counts["candidate_events_iae_score_ready"] += sum(
            event.readiness.iae_score_ready for event in events
        )
        self._archive_hash = sha256_hex((self._archive_hash, stream.measurement_hash()))

    def _combined_measurement_hash(self) -> str:
        if self._stream is None:
            return self._archive_hash
        return sha256_hex((self._archive_hash, self._stream.measurement_hash()))

    def _active_candidate_count(self) -> int:
        return 0 if self._stream is None else len(self._stream.candidate_events)

    def _active_candidate_slice(self, start: int) -> tuple[CandidateEventObservation, ...]:
        if self._stream is None:
            return ()
        return self._stream.candidate_events[start:]


__all__ = (
    "ActualContractActivation",
    "MarketInputBatch",
    "MarketPipeline",
    "MarketPipelineUpdate",
)

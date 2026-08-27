import math
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta

from systematic_futures.config.research import MEASUREMENT_CLOCK_POLICY
from systematic_futures.data.sessions import SessionEngine
from systematic_futures.domain.enums import (
    ProfileKind,
    RollState,
    SessionType,
)
from systematic_futures.domain.errors import (
    ContractBoundaryError,
    DataQualityError,
    DataTimingInvariantError,
    SessionBoundaryError,
)
from systematic_futures.domain.serialization import sha256_hex
from systematic_futures.measurement.events import (
    AuctionTransitionEngine,
    CandidateEventGenerator,
    EventTrigger,
    SnapshotAligner,
)
from systematic_futures.measurement.iae import IAEEngine, IAERetestObservation
from systematic_futures.measurement.icm import ICMEngine
from systematic_futures.measurement.imsi import IMSIStateCore
from systematic_futures.measurement.state_models import (
    ATRMeasurement,
    AuctionStateSnapshot,
    CandidateEventObservation,
    CompletedTradeBar,
    IAEStateSnapshot,
    ICMStateSnapshot,
    IMSIStateSnapshot,
    IndicatorSynergySnapshot,
    ProfileReferenceSet,
    TradeObservation,
    VolumeProfileSnapshot,
)
from systematic_futures.measurement.volatility import ATR5m24
from systematic_futures.measurement.volume_profile import (
    DEFAULT_PROFILE_DEFINITION,
    VolumeProfileEngine,
    auction_features,
    auction_location,
)

_FEATURE_VERSION = "feature_semantics_math_v5"


@dataclass(slots=True)
class _BarBuilder:
    start_utc: datetime
    end_utc: datetime
    session_id: str
    open: float
    high: float
    low: float
    close: float
    volume: float


class _TradeBarAggregator:
    def __init__(self, root: str, contract_symbol: str, period_minutes: int) -> None:
        self.root = root
        self.contract_symbol = contract_symbol
        self.period_minutes = period_minutes
        self._builder: _BarBuilder | None = None

    def close_due(
        self,
        exchange_time_utc: datetime,
        available_at_utc: datetime,
    ) -> CompletedTradeBar | None:
        builder = self._builder
        if builder is None or builder.end_utc > exchange_time_utc:
            return None
        self._builder = None
        return CompletedTradeBar(
            root=self.root,
            contract_symbol=self.contract_symbol,
            period_minutes=self.period_minutes,
            start_utc=builder.start_utc,
            end_utc=builder.end_utc,
            available_at_utc=max(available_at_utc, builder.end_utc),
            open=builder.open,
            high=builder.high,
            low=builder.low,
            close=builder.close,
            volume=builder.volume,
            session_id=builder.session_id,
        )

    def ingest(
        self,
        trade: TradeObservation,
        session_start_utc: datetime,
        session_end_utc: datetime,
    ) -> bool:
        if trade.root != self.root or trade.contract_symbol != self.contract_symbol:
            raise ContractBoundaryError("bar aggregator cannot cross actual contracts")
        elapsed = trade.exchange_time_utc - session_start_utc
        if elapsed.total_seconds() < 0:
            raise SessionBoundaryError("trade precedes semantic session start")
        bucket_index = int(elapsed.total_seconds() // (self.period_minutes * 60))
        bucket_start = session_start_utc + timedelta(minutes=bucket_index * self.period_minutes)
        bucket_end = bucket_start + timedelta(minutes=self.period_minutes)
        if bucket_end > session_end_utc:
            return False
        builder = self._builder
        if builder is None:
            self._builder = _BarBuilder(
                bucket_start,
                bucket_end,
                trade.session_id,
                trade.price,
                trade.price,
                trade.price,
                trade.price,
                trade.quantity,
            )
            return True
        if builder.session_id != trade.session_id:
            raise SessionBoundaryError("bar aggregator session changed before finalization")
        if builder.start_utc != bucket_start:
            raise DataTimingInvariantError("elapsed bar bucket must be closed before ingestion")
        builder.high = max(builder.high, trade.price)
        builder.low = min(builder.low, trade.price)
        builder.close = trade.price
        builder.volume += trade.quantity
        return True


class MeasurementStream:
    """One deterministic actual-contract coordinator for all Lift 2 measurements."""

    def __init__(
        self,
        root: str,
        contract_symbol: str,
        minimum_tick: float,
        session_engine: SessionEngine,
    ) -> None:
        """Create empty contract-local measurement state.

        Units: `minimum_tick` is native price per tick. Time semantics: the supplied
        session engine owns semantic boundaries; incoming observations must be ordered.
        Missingness: identity, tick size, and calendar policy are mandatory. Raises:
        ``DataQualityError`` for invalid configuration.
        """

        if not root.strip() or not contract_symbol.strip():
            raise DataQualityError("measurement stream identity must be non-blank")
        if not math.isfinite(minimum_tick) or minimum_tick <= 0:
            raise DataQualityError("measurement stream minimum_tick must be positive")
        self.root = root
        self.contract_symbol = contract_symbol
        self.minimum_tick = minimum_tick
        self._sessions = session_engine
        self._five = _TradeBarAggregator(
            root,
            contract_symbol,
            MEASUREMENT_CLOCK_POLICY.fast_bar_minutes,
        )
        self._thirty = _TradeBarAggregator(
            root,
            contract_symbol,
            MEASUREMENT_CLOCK_POLICY.medium_state_bar_minutes,
        )
        self._imsi = IMSIStateCore(root, contract_symbol)
        self._icm = ICMEngine(root, contract_symbol)
        self._iae = IAEEngine(root, contract_symbol, minimum_tick)
        self._atr = ATR5m24(root, contract_symbol)
        self._transition = AuctionTransitionEngine(root, contract_symbol)
        self._aligner = SnapshotAligner()
        self._generator = CandidateEventGenerator()
        self._profile: VolumeProfileEngine | None = None
        self._session_id: str | None = None
        self._session_end_utc: datetime | None = None
        self._final_profiles_by_session_type: dict[SessionType, VolumeProfileSnapshot] = {}
        self._iae_snapshots_by_id: dict[str, IAEStateSnapshot] = {}
        self._five_bars: deque[CompletedTradeBar] = deque(maxlen=300)
        self._last_trade_time: datetime | None = None
        self._last_roll_state: RollState | None = None
        self.profile_snapshots: list[VolumeProfileSnapshot] = []
        self.completed_bars: list[CompletedTradeBar] = []
        self.auction_snapshots: list[AuctionStateSnapshot] = []
        self.imsi_snapshots: list[IMSIStateSnapshot] = []
        self.icm_snapshots: list[ICMStateSnapshot] = []
        self.iae_snapshots: list[IAEStateSnapshot] = []
        self.synergy_snapshots: dict[str, IndicatorSynergySnapshot] = {}
        self.session_types: dict[str, SessionType] = {}
        self.counts: Counter[str] = Counter()
        self.quality_counts: Counter[str] = Counter()

    @property
    def candidate_events(self) -> tuple[CandidateEventObservation, ...]:
        """Return all append-once candidate records for this contract run."""

        return self._generator.events

    def on_trade(self, trade: TradeObservation) -> tuple[CandidateEventObservation, ...]:
        """Process one trade in the frozen causal order and return new candidate events.

        Units and clocks are inherited from `TradeObservation`. Time semantics: due
        completed bars, indicators, minute buckets, and Auction snapshots are processed
        before the current trade is ingested. Missingness: unavailable indicator
        snapshots remain absent from alignment. Raises: boundary, timing, or data
        invariant errors; late Profile data becomes an explicit quality incident.
        """

        self._validate_trade(trade)
        session_type = self._sessions.classify(self.root, trade.exchange_time_utc)
        session_id = self._sessions.session_id(self.root, trade.exchange_time_utc)
        session_start, session_end = self._sessions.session_bounds(
            self.root,
            trade.exchange_time_utc,
        )
        if session_id != trade.session_id:
            raise SessionBoundaryError("trade session_id disagrees with SessionEngine")
        before = len(self._generator.events)
        due = tuple(
            bar
            for bar in (
                self._five.close_due(trade.exchange_time_utc, trade.available_at_utc),
                self._thirty.close_due(trade.exchange_time_utc, trade.available_at_utc),
            )
            if bar is not None
        )
        self._process_due_bars(due)
        if self._profile is not None:
            self._profile.finalize_minutes_through(trade.exchange_time_utc)
        if self._session_id is not None and session_id != self._session_id:
            self._finalize_current_profile(self._session_end_utc, trade.available_at_utc)
            self._profile = None
        if self._profile is None:
            self._profile = VolumeProfileEngine(
                self.root,
                self.contract_symbol,
                session_id,
                self.minimum_tick,
                DEFAULT_PROFILE_DEFINITION,
            )
            self._session_id = session_id
            self._session_end_utc = session_end
            self.session_types[session_id] = session_type
            self.counts["unique_sessions"] += 1
        profile = self._require_profile()
        admitted = profile.ingest_trade(trade)
        if not admitted:
            for flag in profile.last_rejection_flags:
                self.quality_counts[flag] += 1
            self.counts["rejected_trade_ticks"] += 1
            return self._generator.events[before:]
        five_admitted = self._five.ingest(trade, session_start, session_end)
        thirty_admitted = self._thirty.ingest(trade, session_start, session_end)
        if not five_admitted:
            self.quality_counts["incomplete_5m_session_tail"] += 1
        if not thirty_admitted:
            self.quality_counts["incomplete_30m_session_tail"] += 1
        self._last_trade_time = trade.exchange_time_utc
        self._last_roll_state = trade.roll_state
        self.counts["trade_ticks"] += 1
        return self._generator.events[before:]

    def finalize(
        self,
        as_of_utc: datetime,
        available_at_utc: datetime,
    ) -> tuple[CandidateEventObservation, ...]:
        """Close due completed bars and immutably finalize the current Profile.

        Units: UTC clocks. Time semantics: only buckets ending no later than `as_of`
        are emitted; availability is never backdated. Missingness: an empty stream is a
        no-op. Raises: timing and measurement invariant errors.
        """

        if as_of_utc > available_at_utc:
            raise DataTimingInvariantError("finalization as-of must not exceed availability")
        before = len(self._generator.events)
        due = tuple(
            bar
            for bar in (
                self._five.close_due(as_of_utc, available_at_utc),
                self._thirty.close_due(as_of_utc, available_at_utc),
            )
            if bar is not None
        )
        self._process_due_bars(due)
        self._finalize_current_profile(as_of_utc, available_at_utc)
        return self._generator.events[before:]

    def measurement_hash(self) -> str:
        """Return a deterministic compact state hash without raw trades."""

        return sha256_hex(
            {
                "auction_snapshot_ids": tuple(item.snapshot_id for item in self.auction_snapshots),
                "candidate_event_ids": tuple(item.event_id for item in self.candidate_events),
                "completed_bar_hashes": tuple(sha256_hex(item) for item in self.completed_bars),
                "counts": dict(sorted(self.counts.items())),
                "icm_snapshot_ids": tuple(item.snapshot_id for item in self.icm_snapshots),
                "iae_snapshot_ids": tuple(item.snapshot_id for item in self.iae_snapshots),
                "imsi_snapshot_ids": tuple(item.snapshot_id for item in self.imsi_snapshots),
                "profile_snapshot_ids": tuple(item.snapshot_id for item in self.profile_snapshots),
                "quality_counts": dict(sorted(self.quality_counts.items())),
                "synergy_snapshot_ids": tuple(sorted(self.synergy_snapshots)),
            }
        )

    def _process_due_bars(self, bars: tuple[CompletedTradeBar, ...]) -> None:
        if not bars:
            return
        grouped: dict[datetime, list[CompletedTradeBar]] = defaultdict(list)
        for bar in bars:
            self.completed_bars.append(bar)
            grouped[bar.end_utc].append(bar)
        for boundary in sorted(grouped):
            boundary_bars = grouped[boundary]
            retests: list[IAERetestObservation] = []
            atr_by_end: dict[datetime, ATRMeasurement] = {}
            five_bars = [
                bar
                for bar in boundary_bars
                if bar.period_minutes == MEASUREMENT_CLOCK_POLICY.fast_bar_minutes
            ]
            thirty_bars = [
                bar
                for bar in boundary_bars
                if bar.period_minutes == MEASUREMENT_CLOCK_POLICY.medium_state_bar_minutes
            ]
            for bar in five_bars:
                self._five_bars.append(bar)
                atr = self._atr.on_bar(bar)
                atr_by_end[bar.end_utc] = atr
                session_type = self._sessions.classify(self.root, bar.start_utc)
                session_start, _ = self._sessions.session_bounds(self.root, bar.start_utc)
                update = self._iae.on_bar(
                    bar,
                    atr,
                    session_type,
                    session_start,
                )
                if update.bar_snapshot is not None:
                    self._record_iae_snapshot(update.bar_snapshot)
                    for flag in update.bar_snapshot.quality_flags:
                        self.quality_counts[flag] += 1
                for retest_snapshot in update.retest_snapshots:
                    self._record_iae_snapshot(retest_snapshot)
                    self.counts["iae_retest_snapshots"] += 1
                retests.extend(update.retests)
                self.counts["five_minute_bars"] += 1
            for bar in thirty_bars:
                session_type = self._sessions.classify(self.root, bar.start_utc)
                session_start, _ = self._sessions.session_bounds(self.root, bar.start_utc)
                imsi = self._imsi.on_bar(bar, session_type, session_start)
                if imsi is not None:
                    self.imsi_snapshots.append(imsi)
                    self._aligner.add_imsi(imsi)
                    self.counts["imsi_snapshots"] += 1
                    if imsi.warmup_complete:
                        self.counts["imsi_ready"] += 1
                atr_for_boundary = atr_by_end.get(bar.end_utc)
                icm = self._icm.on_bar(
                    bar,
                    atr_for_boundary.as_price_scale() if atr_for_boundary is not None else None,
                )
                if icm is not None:
                    self.icm_snapshots.append(icm)
                    self._aligner.add_icm(icm)
                    self.counts["icm_snapshots"] += 1
                    if icm.z_effective is not None:
                        self.counts["icm_ready"] += 1
                    for flag in icm.quality_flags:
                        self.quality_counts[flag] += 1
                else:
                    for flag in self._icm.last_quality_flags:
                        self.quality_counts[flag] += 1
                self.counts["thirty_minute_bars"] += 1
            profile = self._profile
            if profile is not None:
                profile.finalize_minutes_through(boundary)
            for bar in five_bars:
                self._publish_auction(bar, retests, atr_by_end[bar.end_utc])

    def _publish_auction(
        self,
        bar: CompletedTradeBar,
        retests: list[IAERetestObservation],
        atr: ATRMeasurement,
    ) -> None:
        profile = self._require_profile()
        developing = profile.snapshot(
            ProfileKind.DEVELOPING_SESSION,
            bar.end_utc,
            bar.available_at_utc,
        )
        self.profile_snapshots.append(developing)
        self.counts["developing_profiles"] += 1
        rolling_snapshots: dict[ProfileKind, VolumeProfileSnapshot] = {}
        for kind in (
            ProfileKind.ROLLING_30M,
            ProfileKind.ROLLING_60M,
            ProfileKind.ROLLING_120M,
        ):
            try:
                rolling = profile.snapshot(kind, bar.end_utc, bar.available_at_utc)
            except DataQualityError:
                self.quality_counts[f"{kind.value}_warmup"] += 1
            else:
                self.profile_snapshots.append(rolling)
                rolling_snapshots[kind] = rolling
                self.counts["rolling_profiles"] += 1
        session_type = self.session_types[bar.session_id]
        reference_profile = self._final_profiles_by_session_type.get(session_type)
        location = auction_location(bar.close, self.minimum_tick, reference_profile)
        triggers = self._transition.advance(
            session_id=bar.session_id,
            location=location,
            developing_poc_tick=developing.poc_tick,
            prior_profile=reference_profile,
            event_time_utc=bar.end_utc,
            available_at_utc=bar.available_at_utc,
        )
        features, feature_flags = auction_features(
            developing,
            reference_profile,
            atr,
            tuple(item for item in self._five_bars if item.session_id == bar.session_id),
            self._transition.metrics,
        )
        flags = set(feature_flags)
        flags.update(developing.quality_flags)
        if reference_profile is None:
            flags.add("NO_PRIOR_SAME_SESSION_TYPE_PROFILE")
        else:
            flags.update(reference_profile.quality_flags)
        if self._last_roll_state is not None:
            flags.add(f"ROLL:{self._last_roll_state.value.upper()}")
        references = ProfileReferenceSet(
            prior_same_session_type_id=(
                reference_profile.snapshot_id if reference_profile is not None else None
            ),
            prior_rth_id=(
                self._final_profiles_by_session_type[SessionType.RTH].snapshot_id
                if SessionType.RTH in self._final_profiles_by_session_type
                else None
            ),
            prior_eth_id=(
                self._final_profiles_by_session_type[SessionType.ETH].snapshot_id
                if SessionType.ETH in self._final_profiles_by_session_type
                else None
            ),
            rolling_30m_id=(
                rolling_snapshots[ProfileKind.ROLLING_30M].snapshot_id
                if ProfileKind.ROLLING_30M in rolling_snapshots
                else None
            ),
            rolling_60m_id=(
                rolling_snapshots[ProfileKind.ROLLING_60M].snapshot_id
                if ProfileKind.ROLLING_60M in rolling_snapshots
                else None
            ),
            rolling_120m_id=(
                rolling_snapshots[ProfileKind.ROLLING_120M].snapshot_id
                if ProfileKind.ROLLING_120M in rolling_snapshots
                else None
            ),
        )
        measurement_ready = (
            reference_profile is not None
            and atr.warmup_complete
            and not any(flag.startswith("DATA:") for flag in flags)
            and self._last_roll_state is RollState.NORMAL
        )
        identity = {
            "active_excursion_id": self._transition.active_excursion_id,
            "as_of_utc": bar.end_utc,
            "developing_profile_id": developing.snapshot_id,
            "feature_version": _FEATURE_VERSION,
            "features": features,
            "location_state": location,
            "references": references,
            "migration_reference_profile_id": (
                reference_profile.snapshot_id if reference_profile is not None else None
            ),
            "measurement_ready": measurement_ready,
        }
        auction = AuctionStateSnapshot(
            snapshot_id=f"auction_{sha256_hex(identity)}",
            root=self.root,
            contract_symbol=self.contract_symbol,
            session_id=bar.session_id,
            as_of_utc=bar.end_utc,
            available_at_utc=bar.available_at_utc,
            location_state=location,
            developing_profile_id=developing.snapshot_id,
            references=references,
            migration_reference_profile_id=(
                reference_profile.snapshot_id if reference_profile is not None else None
            ),
            features=features,
            active_excursion_id=self._transition.active_excursion_id,
            measurement_ready=measurement_ready,
            quality_flags=tuple(sorted(flags)),
            feature_version=_FEATURE_VERSION,
        )
        self.auction_snapshots.append(auction)
        self.counts["auction_snapshots"] += 1
        synergy = self._aligner.align(auction, bar.available_at_utc)
        self.synergy_snapshots[synergy.snapshot_id] = synergy
        for trigger in triggers:
            self._generator.create(trigger, auction, synergy)
            self.counts["candidate_events"] += 1
        for retest in retests:
            if retest.event_time_utc == bar.end_utc:
                exact_iae = self._iae_snapshots_by_id.get(retest.iae_snapshot_id)
                if exact_iae is None or exact_iae.gap_id != retest.gap_id:
                    raise DataQualityError("IAE retest snapshot lineage is unresolved")
                retest_synergy = self._aligner.align(
                    auction,
                    retest.available_at_utc,
                    iae_override=exact_iae,
                )
                self.synergy_snapshots[retest_synergy.snapshot_id] = retest_synergy
                trigger = EventTrigger(
                    event_type=retest.event_type,
                    event_time_utc=retest.event_time_utc,
                    available_at_utc=retest.available_at_utc,
                    session_id=retest.session_id,
                    direction=retest.direction,
                    parent_event_id=retest.gap_id,
                )
                self._generator.create(trigger, auction, retest_synergy)
                self.counts["candidate_events"] += 1
                self.counts["iae_retest_events"] += 1

    def _finalize_current_profile(
        self,
        as_of_utc: datetime | None,
        available_at_utc: datetime,
    ) -> None:
        profile = self._profile
        if profile is None or as_of_utc is None:
            return
        if self._last_trade_time is None:
            return
        final_as_of = max(self._last_trade_time, as_of_utc)
        profile.finalize_minutes_through(final_as_of)
        final = profile.snapshot(ProfileKind.FINAL_SESSION, final_as_of, available_at_utc)
        self.profile_snapshots.append(final)
        session_type = self.session_types.get(final.session_id)
        if session_type is None:
            raise DataQualityError("final Profile session type is unavailable")
        self._final_profiles_by_session_type[session_type] = final
        self.counts["final_profiles"] += 1

    def _record_iae_snapshot(self, snapshot: IAEStateSnapshot) -> None:
        existing = self._iae_snapshots_by_id.get(snapshot.snapshot_id)
        if existing is not None and existing != snapshot:
            raise DataQualityError("IAE snapshot ID collision")
        if existing is None:
            self._iae_snapshots_by_id[snapshot.snapshot_id] = snapshot
            self.iae_snapshots.append(snapshot)
            self._aligner.add_iae(snapshot)
            self.counts["iae_snapshots"] += 1

    def _validate_trade(self, trade: TradeObservation) -> None:
        if trade.root != self.root or trade.contract_symbol != self.contract_symbol:
            raise ContractBoundaryError("measurement stream cannot cross actual contracts")
        if not math.isclose(trade.minimum_tick, self.minimum_tick, rel_tol=0, abs_tol=1e-15):
            raise DataQualityError("minimum tick changed inside measurement stream")
        if self._last_trade_time is not None and trade.exchange_time_utc < self._last_trade_time:
            raise DataTimingInvariantError("measurement trades must arrive chronologically")

    def _require_profile(self) -> VolumeProfileEngine:
        if self._profile is None:
            raise DataQualityError("measurement stream has no active Profile")
        return self._profile


__all__ = ("MeasurementStream",)

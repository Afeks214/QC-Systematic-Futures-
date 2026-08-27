from __future__ import annotations

from collections import Counter, deque
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol, TypeVar

from systematic_futures.config.research import MEASUREMENT_CLOCK_POLICY
from systematic_futures.domain.enums import (
    AuctionLocationState,
    CandidateEventType,
    SessionType,
)
from systematic_futures.domain.errors import (
    ContractBoundaryError,
    DataQualityError,
    DataTimingInvariantError,
    DuplicateIdentifierError,
)
from systematic_futures.domain.serialization import sha256_hex
from systematic_futures.measurement.state_models import (
    AuctionStateSnapshot,
    AuctionTransitionMetrics,
    CandidateEventObservation,
    IAEStateSnapshot,
    ICMStateSnapshot,
    IMSIStateSnapshot,
    IndicatorSynergySnapshot,
    VolumeProfileSnapshot,
)

_FEATURE_VERSION = "feature_semantics_math_v5"
_SYNERGY_VERSION = "indicator_alignment_v2"
_MAX_ALIGNMENT_HISTORY = 512
_AUCTION_TRANSITION_VERSION = "auction_transition_metrics_v2"


@dataclass(frozen=True, slots=True)
class EventTrigger:
    """One descriptive transition awaiting snapshot alignment."""

    event_type: CandidateEventType
    event_time_utc: datetime
    available_at_utc: datetime
    session_id: str
    direction: int
    parent_event_id: str | None


def candidate_event_id(
    *,
    root: str,
    contract_symbol: str,
    event_type: CandidateEventType,
    event_time_utc: datetime,
    parent_event_id: str | None,
    feature_version: str = _FEATURE_VERSION,
) -> str:
    """Return the deterministic ID from the six frozen identity components.

    Units: opaque SHA-256 identifier. Time semantics: event time is canonicalized as
    aware UTC by the shared serializer. Missingness: parent may be ``None``. Raises:
    domain serialization errors for invalid clocks or values.
    """

    identity = (
        root,
        contract_symbol,
        event_type,
        event_time_utc,
        parent_event_id,
        feature_version,
    )
    return f"event_{sha256_hex(identity)}"


class AuctionTransitionEngine:
    """Track one session's location transitions and one active excursion."""

    def __init__(self, root: str, contract_symbol: str) -> None:
        """Create empty transition state for one actual contract."""

        if not root.strip() or not contract_symbol.strip():
            raise DataQualityError("Auction transition identity must be non-blank")
        self.root = root
        self.contract_symbol = contract_symbol
        self._session_id: str | None = None
        self._location: AuctionLocationState | None = None
        self._last_poc_tick: int | None = None
        self._active_excursion_id: str | None = None
        self._active_direction: int | None = None
        self._migration_emitted = False
        self._reentry_count = 0
        self._consecutive_outside_bars = 0
        self._as_of_utc: datetime | None = None

    @property
    def active_excursion_id(self) -> str | None:
        """Return the active exit event ID, if any."""

        return self._active_excursion_id

    @property
    def reentry_count(self) -> int:
        """Return completed value re-entries in the current semantic session."""

        return self._reentry_count

    @property
    def consecutive_minutes_outside(self) -> int:
        """Return consecutive completed five-minute bars outside value in minutes."""

        return self._consecutive_outside_bars * 5

    @property
    def metrics(self) -> AuctionTransitionMetrics:
        """Return typed counters derived from the latest completed transition."""

        if self._session_id is None or self._as_of_utc is None:
            raise DataQualityError("Auction transition metrics are unavailable before advance")
        return AuctionTransitionMetrics(
            root=self.root,
            contract_symbol=self.contract_symbol,
            session_id=self._session_id,
            as_of_utc=self._as_of_utc,
            reentry_count=self._reentry_count,
            consecutive_outside_bars=self._consecutive_outside_bars,
            version=_AUCTION_TRANSITION_VERSION,
        )

    def advance(
        self,
        *,
        session_id: str,
        location: AuctionLocationState,
        developing_poc_tick: int,
        prior_profile: VolumeProfileSnapshot | None,
        event_time_utc: datetime,
        available_at_utc: datetime,
    ) -> tuple[EventTrigger, ...]:
        """Advance one completed 5m Auction state and emit transition-once triggers.

        Units: POC and Value Area are integer ticks. Time semantics: event time cannot
        exceed availability; callers provide successive completed bars. Missingness:
        no prior profile suppresses transition events. Raises: timing/data errors for
        invalid input.
        """

        if event_time_utc > available_at_utc:
            raise DataTimingInvariantError("Auction event time must not exceed availability")
        if self._as_of_utc is not None and event_time_utc <= self._as_of_utc:
            raise DataTimingInvariantError("Auction transition times must strictly increase")
        if not session_id.strip():
            raise DataQualityError("session_id must be non-blank")
        if prior_profile is not None:
            if (
                prior_profile.root != self.root
                or prior_profile.contract_symbol != self.contract_symbol
            ):
                raise ContractBoundaryError("Auction prior Profile identity differs")
            if prior_profile.as_of_utc >= event_time_utc:
                raise DataTimingInvariantError("Auction prior Profile must precede event")
            if prior_profile.available_at_utc > available_at_utc:
                raise DataTimingInvariantError("Auction prior Profile is unavailable at event")
        self._as_of_utc = event_time_utc
        if session_id != self._session_id:
            self._session_id = session_id
            self._location = location
            self._last_poc_tick = developing_poc_tick
            self._active_excursion_id = None
            self._active_direction = None
            self._migration_emitted = False
            self._reentry_count = 0
            self._consecutive_outside_bars = int(
                location in {AuctionLocationState.ABOVE_VALUE, AuctionLocationState.BELOW_VALUE}
            )
            return ()
        previous = self._location
        triggers: list[EventTrigger] = []
        if location in {AuctionLocationState.ABOVE_VALUE, AuctionLocationState.BELOW_VALUE}:
            self._consecutive_outside_bars += 1
        else:
            self._consecutive_outside_bars = 0
        if prior_profile is not None and previous is AuctionLocationState.INSIDE_VALUE:
            if location is AuctionLocationState.ABOVE_VALUE:
                triggers.append(
                    self._start_exit(
                        CandidateEventType.VALUE_EXIT_UP,
                        1,
                        event_time_utc,
                        available_at_utc,
                        session_id,
                    )
                )
            elif location is AuctionLocationState.BELOW_VALUE:
                triggers.append(
                    self._start_exit(
                        CandidateEventType.VALUE_EXIT_DOWN,
                        -1,
                        event_time_utc,
                        available_at_utc,
                        session_id,
                    )
                )
        if (
            previous is AuctionLocationState.ABOVE_VALUE
            and location is AuctionLocationState.INSIDE_VALUE
            and self._active_direction == 1
            and self._active_excursion_id is not None
        ):
            triggers.append(
                EventTrigger(
                    CandidateEventType.VALUE_REENTRY_FROM_ABOVE,
                    event_time_utc,
                    available_at_utc,
                    session_id,
                    -1,
                    self._active_excursion_id,
                )
            )
            self._close_excursion()
        elif (
            previous is AuctionLocationState.BELOW_VALUE
            and location is AuctionLocationState.INSIDE_VALUE
            and self._active_direction == -1
            and self._active_excursion_id is not None
        ):
            triggers.append(
                EventTrigger(
                    CandidateEventType.VALUE_REENTRY_FROM_BELOW,
                    event_time_utc,
                    available_at_utc,
                    session_id,
                    1,
                    self._active_excursion_id,
                )
            )
            self._close_excursion()
        if (
            prior_profile is not None
            and not self._migration_emitted
            and self._active_excursion_id is not None
            and self._last_poc_tick is not None
        ):
            if (
                self._active_direction == 1
                and self._last_poc_tick <= prior_profile.vah_tick < developing_poc_tick
            ):
                triggers.append(
                    EventTrigger(
                        CandidateEventType.POC_MIGRATION_ABOVE_PRIOR_VAH,
                        event_time_utc,
                        available_at_utc,
                        session_id,
                        1,
                        self._active_excursion_id,
                    )
                )
                self._migration_emitted = True
            elif (
                self._active_direction == -1
                and self._last_poc_tick >= prior_profile.val_tick > developing_poc_tick
            ):
                triggers.append(
                    EventTrigger(
                        CandidateEventType.POC_MIGRATION_BELOW_PRIOR_VAL,
                        event_time_utc,
                        available_at_utc,
                        session_id,
                        -1,
                        self._active_excursion_id,
                    )
                )
                self._migration_emitted = True
        self._location = location
        self._last_poc_tick = developing_poc_tick
        return tuple(triggers)

    def _start_exit(
        self,
        event_type: CandidateEventType,
        direction: int,
        event_time_utc: datetime,
        available_at_utc: datetime,
        session_id: str,
    ) -> EventTrigger:
        event_id = candidate_event_id(
            root=self.root,
            contract_symbol=self.contract_symbol,
            event_type=event_type,
            event_time_utc=event_time_utc,
            parent_event_id=None,
        )
        self._active_excursion_id = event_id
        self._active_direction = direction
        self._migration_emitted = False
        return EventTrigger(
            event_type,
            event_time_utc,
            available_at_utc,
            session_id,
            direction,
            None,
        )

    def _close_excursion(self) -> None:
        self._active_excursion_id = None
        self._active_direction = None
        self._migration_emitted = False
        self._reentry_count += 1


class SnapshotAligner:
    """Bounded as-of aligner for the latest component snapshots available by time T."""

    def __init__(self) -> None:
        self._imsi: deque[IMSIStateSnapshot] = deque(maxlen=_MAX_ALIGNMENT_HISTORY)
        self._icm: deque[ICMStateSnapshot] = deque(maxlen=_MAX_ALIGNMENT_HISTORY)
        self._iae: deque[IAEStateSnapshot] = deque(maxlen=_MAX_ALIGNMENT_HISTORY)

    def add_imsi(self, snapshot: IMSIStateSnapshot) -> None:
        """Retain one IMSI snapshot for causal as-of lookup."""

        self._imsi.append(snapshot)

    def add_icm(self, snapshot: ICMStateSnapshot) -> None:
        """Retain one ICM snapshot for causal as-of lookup."""

        self._icm.append(snapshot)

    def add_iae(self, snapshot: IAEStateSnapshot) -> None:
        """Retain one IAE snapshot for causal as-of lookup."""

        self._iae.append(snapshot)

    def align(
        self,
        auction: AuctionStateSnapshot,
        available_at_utc: datetime,
        *,
        iae_override: IAEStateSnapshot | None = None,
    ) -> IndicatorSynergySnapshot:
        """Join only same-contract, same-session snapshots available by event time.

        Units: opaque snapshot references. Time semantics: strict as-of `<=`; a later
        nearest observation is never selected. Missingness: absent components remain
        ``None`` and do not suppress the row. Raises: timing or identity errors for an
        ineligible Auction snapshot.
        """

        if auction.available_at_utc > available_at_utc:
            raise DataTimingInvariantError("Auction snapshot is unavailable at alignment time")
        imsi = _latest_eligible(
            self._imsi,
            root=auction.root,
            contract_symbol=auction.contract_symbol,
            session_id=auction.session_id,
            available_at_utc=available_at_utc,
        )
        icm = _latest_eligible(
            self._icm,
            root=auction.root,
            contract_symbol=auction.contract_symbol,
            session_id=auction.session_id,
            available_at_utc=available_at_utc,
        )
        if iae_override is not None:
            if not _snapshot_is_eligible(
                iae_override,
                root=auction.root,
                contract_symbol=auction.contract_symbol,
                session_id=auction.session_id,
                available_at_utc=available_at_utc,
            ):
                raise DataTimingInvariantError("IAE override is ineligible for Auction alignment")
            iae = iae_override
        else:
            iae = _latest_eligible(
                self._iae,
                root=auction.root,
                contract_symbol=auction.contract_symbol,
                session_id=auction.session_id,
                available_at_utc=available_at_utc,
            )
        components = (("IMSI", imsi), ("ICM", icm), ("IAE", iae))
        component_flags: set[str] = {
            _prefixed_quality("AUCTION", flag) for flag in auction.quality_flags
        }
        blocking_flags: set[str] = set()
        if not auction.measurement_ready:
            blocking_flags.add("AUCTION:MEASUREMENT_NOT_READY")
        freshness_minutes = {
            "IMSI": MEASUREMENT_CLOCK_POLICY.medium_state_bar_minutes,
            "ICM": MEASUREMENT_CLOCK_POLICY.medium_state_bar_minutes,
            "IAE": MEASUREMENT_CLOCK_POLICY.fast_bar_minutes,
        }
        present = all(snapshot is not None for _, snapshot in components)
        fresh = present
        component_ready = True
        for name, snapshot in components:
            if snapshot is None:
                flag = f"{name}:MISSING"
                component_flags.add(flag)
                blocking_flags.add(flag)
                fresh = False
                component_ready = False
                continue
            component_flags.update(_prefixed_quality(name, flag) for flag in snapshot.quality_flags)
            if not _snapshot_is_fresh(snapshot, auction, freshness_minutes[name]):
                flag = f"{name}:STALE"
                component_flags.add(flag)
                blocking_flags.add(flag)
                fresh = False
            if not snapshot.measurement_ready:
                flag = f"{name}:MEASUREMENT_NOT_READY"
                blocking_flags.add(flag)
                component_ready = False
        ready = present and fresh and auction.measurement_ready and component_ready
        component_quality_flags = tuple(sorted(component_flags))
        blocking_quality_flags = tuple(sorted(blocking_flags))
        quality_flags = tuple(sorted(component_flags | blocking_flags))
        identity = {
            "as_of_utc": auction.as_of_utc,
            "auction_snapshot_id": auction.snapshot_id,
            "available_at_utc": available_at_utc,
            "icm_snapshot_id": icm.snapshot_id if icm is not None else None,
            "iae_snapshot_id": iae.snapshot_id if iae is not None else None,
            "imsi_snapshot_id": imsi.snapshot_id if imsi is not None else None,
            "session_id": auction.session_id,
            "all_required_inputs_present": present,
            "all_required_inputs_fresh": fresh,
            "all_required_inputs_ready": ready,
            "quality_flags": quality_flags,
            "version": _SYNERGY_VERSION,
        }
        return IndicatorSynergySnapshot(
            snapshot_id=f"synergy_{sha256_hex(identity)}",
            root=auction.root,
            contract_symbol=auction.contract_symbol,
            session_id=auction.session_id,
            as_of_utc=auction.as_of_utc,
            available_at_utc=available_at_utc,
            auction_snapshot_id=auction.snapshot_id,
            imsi_snapshot_id=imsi.snapshot_id if imsi is not None else None,
            icm_snapshot_id=icm.snapshot_id if icm is not None else None,
            iae_snapshot_id=iae.snapshot_id if iae is not None else None,
            all_required_inputs_present=present,
            all_required_inputs_fresh=fresh,
            all_required_inputs_ready=ready,
            component_quality_flags=component_quality_flags,
            blocking_quality_flags=blocking_quality_flags,
            quality_flags=quality_flags,
            version=_SYNERGY_VERSION,
        )


class CandidateEventGenerator:
    """Append-once immutable candidate-event generator with deterministic IDs."""

    def __init__(self) -> None:
        self._seen_event_ids: set[str] = set()
        self._events: list[CandidateEventObservation] = []

    @property
    def events(self) -> tuple[CandidateEventObservation, ...]:
        """Return the current run's immutable candidate records in arrival order."""

        return tuple(self._events)

    def create(
        self,
        trigger: EventTrigger,
        auction: AuctionStateSnapshot,
        synergy: IndicatorSynergySnapshot,
    ) -> CandidateEventObservation:
        """Create and register one pre-outcome descriptive event.

        Units: direction is descriptive `+1`/`-1`; identifiers are opaque hashes.
        Time semantics: Auction and alignment availability must not exceed the trigger
        availability. Missingness: component references inside synergy may be absent.
        Raises: duplicate, timing, or identity errors.
        """

        if auction.root != synergy.root or auction.contract_symbol != synergy.contract_symbol:
            raise ContractBoundaryError("Auction and synergy identities differ")
        if trigger.session_id != auction.session_id or synergy.session_id != auction.session_id:
            raise DataQualityError("event, Auction, and synergy sessions must match exactly")
        if auction.available_at_utc > trigger.available_at_utc:
            raise DataTimingInvariantError("Auction snapshot is unavailable for event")
        if synergy.available_at_utc > trigger.available_at_utc:
            raise DataTimingInvariantError("Synergy snapshot is unavailable for event")
        event_id = candidate_event_id(
            root=auction.root,
            contract_symbol=auction.contract_symbol,
            event_type=trigger.event_type,
            event_time_utc=trigger.event_time_utc,
            parent_event_id=trigger.parent_event_id,
        )
        if event_id in self._seen_event_ids:
            raise DuplicateIdentifierError(f"duplicate Candidate Event ID: {event_id}")
        self._seen_event_ids.add(event_id)
        data_hash = sha256_hex(
            (
                auction.snapshot_id,
                synergy.snapshot_id,
                synergy.imsi_snapshot_id,
                synergy.icm_snapshot_id,
                synergy.iae_snapshot_id,
            )
        )
        event = CandidateEventObservation(
            event_id=event_id,
            parent_event_id=trigger.parent_event_id,
            event_type=trigger.event_type,
            root=auction.root,
            contract_symbol=auction.contract_symbol,
            event_time_utc=trigger.event_time_utc,
            available_at_utc=trigger.available_at_utc,
            session_id=trigger.session_id,
            direction=trigger.direction,
            auction_snapshot_id=auction.snapshot_id,
            synergy_snapshot_id=synergy.snapshot_id,
            data_snapshot_hash=data_hash,
            feature_version=_FEATURE_VERSION,
            research_ready=synergy.all_required_inputs_ready,
            quality_flags=synergy.quality_flags,
        )
        self._events.append(event)
        return event


def candidate_coverage(
    events: Sequence[CandidateEventObservation],
    synergies: Mapping[str, IndicatorSynergySnapshot],
    session_types: Mapping[str, SessionType],
    *,
    raw_event_count: int | None = None,
) -> Mapping[str, object]:
    """Aggregate event breadth without price performance or repeated-row inflation.

    Units: counts and events per unique session. Time semantics: calendar month uses
    event UTC month; the report does not join later data. Missingness: an unknown
    session type is reported as `unknown`; missing synergy references do not drop an
    event. Raises: ``DataQualityError`` if the supplied raw count is smaller than the
    unique count.
    """

    records = tuple(events)
    unique_ids = {event.event_id for event in records}
    if len(unique_ids) != len(records):
        raise DuplicateIdentifierError("coverage input contains duplicate Event IDs")
    raw_count = len(records) if raw_event_count is None else raw_event_count
    if raw_count < len(records):
        raise DataQualityError("raw_event_count cannot be smaller than unique event count")
    by_root = Counter(event.root for event in records)
    by_type = Counter(event.event_type.value for event in records)
    by_contract = Counter(event.contract_symbol for event in records)
    by_month = Counter(event.event_time_utc.strftime("%Y-%m") for event in records)
    by_session_type = Counter(
        session_types.get(event.session_id, SessionType.UNKNOWN).value for event in records
    )
    unique_sessions = {event.session_id for event in records}
    resolved = [synergies.get(event.synergy_snapshot_id) for event in records]
    parent_ids = {event.parent_event_id for event in records if event.parent_event_id is not None}
    return {
        "by_calendar_month": dict(sorted(by_month.items())),
        "by_contract": dict(sorted(by_contract.items())),
        "by_event_type": dict(sorted(by_type.items())),
        "by_root": dict(sorted(by_root.items())),
        "by_session_type": dict(sorted(by_session_type.items())),
        "events_per_session": len(records) / len(unique_sessions) if unique_sessions else 0.0,
        "events_with_IAE": sum(
            item is not None and item.iae_snapshot_id is not None for item in resolved
        ),
        "events_with_ICM": sum(
            item is not None and item.icm_snapshot_id is not None for item in resolved
        ),
        "events_with_IMSI": sum(
            item is not None and item.imsi_snapshot_id is not None for item in resolved
        ),
        "candidate_events_total": len(records),
        "candidate_events_inputs_present": sum(
            item is not None and item.all_required_inputs_present for item in resolved
        ),
        "candidate_events_inputs_ready": sum(event.research_ready for event in records),
        "candidate_events_not_ready": sum(not event.research_ready for event in records),
        "candidate_events_missing_imsi": sum(
            item is None or item.imsi_snapshot_id is None for item in resolved
        ),
        "candidate_events_missing_icm": sum(
            item is None or item.icm_snapshot_id is None for item in resolved
        ),
        "candidate_events_missing_iae": sum(
            item is None or item.iae_snapshot_id is None for item in resolved
        ),
        "events_with_all_three": sum(
            item is not None and item.all_required_inputs_present for item in resolved
        ),
        "parent_excursion_count": len(parent_ids),
        "quality_blocked_events": sum(not event.research_ready for event in records),
        "raw_event_count": raw_count,
        "unique_event_count": len(records),
        "unique_session_count": len(unique_sessions),
    }


class _AlignableSnapshot(Protocol):
    @property
    def snapshot_id(self) -> str: ...

    @property
    def root(self) -> str: ...

    @property
    def contract_symbol(self) -> str: ...

    @property
    def session_id(self) -> str: ...

    @property
    def as_of_utc(self) -> datetime: ...

    @property
    def available_at_utc(self) -> datetime: ...

    @property
    def measurement_ready(self) -> bool: ...

    @property
    def quality_flags(self) -> tuple[str, ...]: ...


_SnapshotT = TypeVar("_SnapshotT", bound=_AlignableSnapshot)


def _latest_eligible(
    snapshots: Iterable[_SnapshotT],
    *,
    root: str,
    contract_symbol: str,
    session_id: str,
    available_at_utc: datetime,
) -> _SnapshotT | None:
    eligible = [
        snapshot
        for snapshot in snapshots
        if _snapshot_is_eligible(
            snapshot,
            root=root,
            contract_symbol=contract_symbol,
            session_id=session_id,
            available_at_utc=available_at_utc,
        )
    ]
    return max(eligible, key=lambda snapshot: snapshot.available_at_utc, default=None)


def _snapshot_is_eligible(
    snapshot: _AlignableSnapshot,
    *,
    root: str,
    contract_symbol: str,
    session_id: str,
    available_at_utc: datetime,
) -> bool:
    return (
        snapshot.root == root
        and snapshot.contract_symbol == contract_symbol
        and snapshot.session_id == session_id
        and snapshot.available_at_utc <= available_at_utc
    )


def _snapshot_is_fresh(
    snapshot: _AlignableSnapshot,
    auction: AuctionStateSnapshot,
    maximum_age_minutes: int,
) -> bool:
    age = auction.as_of_utc - snapshot.as_of_utc
    return timedelta(0) <= age <= timedelta(minutes=maximum_age_minutes)


def _prefixed_quality(source: str, flag: str) -> str:
    if flag.startswith(("DATA:", "ROLL:", "SESSION:")):
        return flag
    return f"{source}:{flag}"


__all__ = (
    "AuctionTransitionEngine",
    "CandidateEventGenerator",
    "EventTrigger",
    "SnapshotAligner",
    "candidate_coverage",
    "candidate_event_id",
)

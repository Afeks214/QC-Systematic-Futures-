from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from systematic_futures.data.rolls import (
    MappingObservation,
    RollManager,
    make_mapping_observation,
)
from systematic_futures.data.sessions import (
    SessionEngine,
    reference_session_calendar_exceptions,
    reference_session_policies,
)
from systematic_futures.domain.enums import (
    DataQualityStatus,
    EvidenceAvailability,
    RollState,
    SessionType,
)
from systematic_futures.domain.errors import ContractBoundaryError, SessionBoundaryError
from systematic_futures.measurement.state_models import TradeObservation
from systematic_futures.measurement.stream import MeasurementStream

ROOTS = ("ES", "NQ", "RTY", "ZT", "ZN", "6E", "6J", "6B")


def _observation(
    *,
    old: str | None,
    new: str,
    event_time: datetime,
    available_time: datetime,
    roll_state: RollState,
) -> MappingObservation:
    return make_mapping_observation(
        root="ES",
        continuous_symbol="/ES",
        old_mapped_contract=old,
        new_mapped_contract=new,
        actual_contract=new,
        event_time_utc=event_time,
        available_time_utc=available_time,
        mapping_mode="OPEN_INTEREST",
        source="QuantConnect.SymbolChangedEvent",
        roll_state=roll_state,
        liquidity_evidence=EvidenceAvailability.NOT_AVAILABLE,
        open_interest_evidence=EvidenceAvailability.NOT_AVAILABLE,
        quality_flags=("MAPPING_OBSERVED",),
    )


def test_production_session_engine_composes_certified_exceptions_for_all_roots() -> None:
    engine = SessionEngine(
        reference_session_policies(),
        reference_session_calendar_exceptions(),
    )
    instant = datetime(2024, 3, 11, 15, 0, tzinfo=UTC)

    for root in ROOTS:
        assert engine.session_id(root, instant) == engine.session_id(root, instant)
        assert engine.calendar_exceptions_for_market(root)


@pytest.mark.parametrize("root", ROOTS)
def test_t004_t005_dst_holiday_and_early_close_are_composed(root: str) -> None:
    engine = SessionEngine(
        reference_session_policies(),
        reference_session_calendar_exceptions(),
    )
    timezone = engine.windows_for_market(root)[0].timezone_name
    before_dst = datetime(2024, 3, 8, 15, 0, tzinfo=UTC)
    after_dst = datetime(2024, 3, 11, 15, 0, tzinfo=UTC)
    assert engine.classify(root, before_dst) is not SessionType.UNKNOWN
    assert engine.classify(root, after_dst) is not SessionType.UNKNOWN

    holiday_local = datetime.fromisoformat("2026-12-25T10:00:00").replace(tzinfo=ZoneInfo(timezone))
    assert engine.classify(root, holiday_local.astimezone(UTC)) is SessionType.CLOSED

    exception = next(
        item
        for item in engine.calendar_exceptions_for_market(root)
        if item.local_date == date(2024, 5, 27) and not item.all_day_closed
    )
    close = exception.closed_windows[0].start_local_time
    close_local = datetime.combine(
        exception.local_date,
        close,
        ZoneInfo(timezone),
    )
    assert engine.classify(root, close_local.astimezone(UTC)) is SessionType.CLOSED
    assert engine.is_session_complete(
        root,
        (close_local - timedelta(minutes=1)).astimezone(UTC),
        close_local.astimezone(UTC),
    )

    reopen_local = datetime.combine(
        exception.local_date,
        exception.closed_windows[0].end_local_time,
        ZoneInfo(timezone),
    )
    before_id = engine.session_id(root, (close_local - timedelta(minutes=1)).astimezone(UTC))
    next_id = engine.session_id(root, reopen_local.astimezone(UTC))
    assert before_id != next_id


def test_session_is_not_complete_before_its_effective_end() -> None:
    engine = SessionEngine(
        reference_session_policies(),
        reference_session_calendar_exceptions(),
    )
    instant = datetime(2024, 3, 4, 15, 0, tzinfo=UTC)
    _, end = engine.session_bounds("ES", instant)
    assert not engine.is_session_complete("ES", instant, end - timedelta(microseconds=1))
    assert engine.is_session_complete("ES", instant, end)


@pytest.mark.parametrize("root", ROOTS)
def test_regular_weekend_is_closed_until_policy_reopen(root: str) -> None:
    engine = SessionEngine(
        reference_session_policies(),
        reference_session_calendar_exceptions(),
    )
    windows = engine.windows_for_market(root)
    maintenance = next(
        window for window in windows if window.session_type is SessionType.MAINTENANCE
    )
    timezone = ZoneInfo(windows[0].timezone_name)
    friday = date(2024, 3, 8)
    saturday = friday + timedelta(days=1)
    sunday = friday + timedelta(days=2)
    closed_instants = (
        datetime.combine(friday, maintenance.start_local_time, timezone),
        datetime.combine(saturday, datetime.min.time(), timezone) + timedelta(hours=12),
        datetime.combine(sunday, maintenance.end_local_time, timezone) - timedelta(microseconds=1),
    )

    closed_ids = []
    for local_instant in closed_instants:
        utc_instant = local_instant.astimezone(UTC)
        assert engine.classify(root, utc_instant) is SessionType.CLOSED
        closed_ids.append(engine.session_id(root, utc_instant))
        with pytest.raises(SessionBoundaryError, match="weekly closure"):
            engine.session_bounds(root, utc_instant)
    assert len(set(closed_ids)) == 1

    reopen = datetime.combine(sunday, maintenance.end_local_time, timezone).astimezone(UTC)
    assert engine.classify(root, reopen) is not SessionType.CLOSED


def test_early_close_never_emits_final_profile_before_completion() -> None:
    engine = SessionEngine(
        reference_session_policies(),
        reference_session_calendar_exceptions(),
    )
    trade_time = datetime(2024, 5, 27, 16, 59, tzinfo=UTC)
    close_time = datetime(2024, 5, 27, 17, 0, tzinfo=UTC)
    stream = MeasurementStream("ES", "ESM24", 0.25, engine)
    stream.on_trade(
        TradeObservation(
            root="ES",
            contract_symbol="ESM24",
            exchange_time_utc=trade_time,
            available_at_utc=trade_time,
            price=5300.0,
            quantity=1.0,
            minimum_tick=0.25,
            session_id=engine.session_id("ES", trade_time),
            roll_state=RollState.NORMAL,
        )
    )

    stream.finalize(trade_time, trade_time)
    assert stream.counts["final_profiles"] == 0
    assert stream.quality_counts["incomplete_session_profile_not_finalized"] == 1
    stream.finalize(trade_time, close_time)
    assert stream.counts["final_profiles"] == 0
    assert stream.quality_counts["incomplete_session_profile_not_finalized"] == 2
    stream.finalize(close_time, close_time)
    assert stream.counts["final_profiles"] == 1


def test_t006_t007_roll_observation_is_immutable_idempotent_and_causal() -> None:
    manager = RollManager()
    initial = datetime(2024, 3, 1, 12, 0, tzinfo=UTC)
    event = datetime(2024, 3, 13, 4, 0, tzinfo=UTC)
    available = datetime(2024, 3, 10, 12, 0, tzinfo=UTC)
    first = _observation(
        old=None,
        new="ESH24",
        event_time=initial,
        available_time=initial,
        roll_state=RollState.NORMAL,
    )
    transition = _observation(
        old="ESH24",
        new="ESM24",
        event_time=event,
        available_time=available,
        roll_state=RollState.ROLL_TRANSITION,
    )

    manager.observe_mapping(first)
    assert manager.observe_mapping(transition) is RollState.PRE_ROLL
    assert manager.observe_mapping(transition) is RollState.PRE_ROLL
    assert len(manager.observations_for_root("ES")) == 2
    assert manager.current_roll_state("ES", available) is RollState.PRE_ROLL
    assert manager.current_roll_state("ES", event) is RollState.ROLL_TRANSITION
    assert manager.current_roll_state("ES", event + timedelta(seconds=1)) is RollState.POST_ROLL
    stored = manager.observations_for_root("ES")[-1]
    assert stored.old_mapped_contract == "ESH24"
    assert stored.new_mapped_contract == "ESM24"
    assert stored.actual_contract == "ESM24"
    assert stored.event_time_utc == event
    assert stored.available_time_utc == available
    with pytest.raises(FrozenInstanceError):
        stored.root = "NQ"  # type: ignore[misc]


def test_roll_measurement_eligibility_is_fail_closed_until_new_contract_ready() -> None:
    manager = RollManager()
    initial = datetime(2024, 3, 1, 12, 0, tzinfo=UTC)
    transition_at = datetime(2024, 3, 13, 4, 0, tzinfo=UTC)
    manager.observe_mapping(
        _observation(
            old=None,
            new="ESH24",
            event_time=initial,
            available_time=initial,
            roll_state=RollState.NORMAL,
        )
    )
    manager.observe_mapping(
        _observation(
            old="ESH24",
            new="ESM24",
            event_time=transition_at,
            available_time=transition_at,
            roll_state=RollState.ROLL_TRANSITION,
        )
    )

    transition = manager.measurement_eligibility("ES", transition_at, new_contract_ready=False)
    post_not_ready = manager.measurement_eligibility(
        "ES", transition_at + timedelta(seconds=1), new_contract_ready=False
    )
    post_ready = manager.measurement_eligibility(
        "ES", transition_at + timedelta(seconds=1), new_contract_ready=True
    )
    assert not transition.eligible
    assert not post_not_ready.eligible
    assert post_ready.eligible


def test_continuous_identity_cannot_be_used_as_actual_contract() -> None:
    now = datetime(2024, 3, 1, 12, 0, tzinfo=UTC)
    with pytest.raises(ContractBoundaryError):
        MappingObservation(
            root="ES",
            continuous_symbol="/ES",
            old_mapped_contract=None,
            new_mapped_contract="ESH24",
            actual_contract="/ES",
            event_time_utc=now,
            available_time_utc=now,
            mapping_mode="OPEN_INTEREST",
            source="QuantConnect.SymbolChangedEvent",
            roll_state=RollState.NORMAL,
            liquidity_evidence=EvidenceAvailability.NOT_AVAILABLE,
            open_interest_evidence=EvidenceAvailability.NOT_AVAILABLE,
            expiry_evidence=EvidenceAvailability.NOT_AVAILABLE,
            quality_status=DataQualityStatus.VALID,
            quality_flags=("MAPPING_OBSERVED",),
            lineage_hash="0" * 64,
        )

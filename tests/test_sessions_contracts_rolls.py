from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from systematic_futures.data.rolls import MappingObservation, RollManager
from systematic_futures.data.sessions import (
    SessionCalendarException,
    SessionClosureWindow,
    SessionEngine,
    reference_session_policies,
)
from systematic_futures.domain.enums import RollState, SessionType

_LEAN_MARKET_HOURS_SOURCE = (
    "Lean 07fb0182bfe229edd9445cf675ac6509d0069539 "
    "Data/market-hours/market-hours-database.json "
    "sha256:d93f0b417cc9df618da4548f78157fd2b49515e0999f16e83ffddcffd54eef41"
)
_CHICAGO_TIMEZONE = ZoneInfo("America/Chicago")
_NEW_YORK_TIMEZONE = ZoneInfo("America/New_York")
_SESSION_CASES = (
    ("ES", _NEW_YORK_TIMEZONE, SessionType.RTH, time(13), time(18)),
    ("ZN", _CHICAGO_TIMEZONE, SessionType.US_CASH_HOURS, time(12), time(17)),
    ("6E", _CHICAGO_TIMEZONE, SessionType.NEW_YORK, time(16), time(17)),
)


def test_session_id_is_deterministic_for_same_market_and_timestamp() -> None:
    engine = SessionEngine(reference_session_policies())
    timestamp = datetime(2024, 2, 15, 15, 0, tzinfo=UTC)

    first = engine.session_id("ES", timestamp)
    second = engine.session_id("ES", timestamp)

    assert first == second


@pytest.mark.parametrize(("root", "timezone", "expected", "_close", "_reopen"), _SESSION_CASES)
def test_session_classification_preserves_wall_clock_across_dst_transitions(
    root: str,
    timezone: ZoneInfo,
    expected: SessionType,
    _close: time,
    _reopen: time,
) -> None:
    engine = SessionEngine(reference_session_policies())
    local_instants = (
        datetime(2024, 3, 8, 10, 0, tzinfo=timezone),
        datetime(2024, 3, 11, 10, 0, tzinfo=timezone),
        datetime(2024, 11, 1, 10, 0, tzinfo=timezone),
        datetime(2024, 11, 4, 10, 0, tzinfo=timezone),
    )

    classifications = tuple(
        engine.classify(root, local_timestamp.astimezone(UTC)) for local_timestamp in local_instants
    )

    assert classifications == (expected,) * 4


@pytest.mark.parametrize(("root", "timezone", "_expected", "_close", "_reopen"), _SESSION_CASES)
def test_official_lean_holiday_classifies_closed(
    root: str,
    timezone: ZoneInfo,
    _expected: SessionType,
    _close: time,
    _reopen: time,
) -> None:
    holiday = SessionCalendarException(
        exception_name=f"{root.lower()}_2026_christmas_holiday",
        local_date=date(2026, 12, 25),
        timezone_name=timezone.key,
        all_day_closed=True,
        closed_windows=(),
        calendar_version="lean-market-hours-07fb0182",
        source_label=_LEAN_MARKET_HOURS_SOURCE,
    )
    engine = SessionEngine(reference_session_policies(), {root: (holiday,)})
    holiday_instant = datetime(2026, 12, 25, 10, 0, tzinfo=timezone)

    assert engine.classify(root, holiday_instant.astimezone(UTC)) is SessionType.CLOSED


@pytest.mark.parametrize(("root", "timezone", "expected", "close", "reopen"), _SESSION_CASES)
def test_official_lean_early_close_overrides_semantic_session(
    root: str,
    timezone: ZoneInfo,
    expected: SessionType,
    close: time,
    reopen: time,
) -> None:
    early_close = SessionCalendarException(
        exception_name=f"{root.lower()}_2024_memorial_day_early_close",
        local_date=date(2024, 5, 27),
        timezone_name=timezone.key,
        all_day_closed=False,
        closed_windows=(
            SessionClosureWindow(
                closure_name="closed_until_lean_late_open",
                start_local_time=close,
                end_local_time=reopen,
                crosses_midnight=False,
            ),
        ),
        calendar_version="lean-market-hours-07fb0182",
        source_label=_LEAN_MARKET_HOURS_SOURCE,
    )
    engine = SessionEngine(reference_session_policies(), {root: (early_close,)})
    before_close = datetime.combine(date(2024, 5, 27), close, timezone) - timedelta(minutes=1)
    after_close = datetime.combine(date(2024, 5, 27), close, timezone)

    assert engine.classify(root, before_close.astimezone(UTC)) is expected
    assert engine.classify(root, after_close.astimezone(UTC)) is SessionType.CLOSED


@pytest.mark.parametrize(("root", "timezone", "_expected", "_close", "_reopen"), _SESSION_CASES)
def test_cross_midnight_session_id_uses_one_anchor_date(
    root: str,
    timezone: ZoneInfo,
    _expected: SessionType,
    _close: time,
    _reopen: time,
) -> None:
    engine = SessionEngine(reference_session_policies())
    before_midnight = datetime(2024, 2, 18, 18, 30, tzinfo=timezone)
    after_midnight = datetime(2024, 2, 19, 1, 0, tzinfo=timezone)

    assert engine.session_id(root, before_midnight.astimezone(UTC)) == engine.session_id(
        root,
        after_midnight.astimezone(UTC),
    )


def test_future_mapping_observation_does_not_change_earlier_roll_state() -> None:
    manager = RollManager()
    initial_time = datetime(2024, 2, 15, 12, 0, tzinfo=UTC)
    future_time = datetime(2024, 3, 14, 12, 0, tzinfo=UTC)
    earlier_time = datetime(2024, 3, 1, 12, 0, tzinfo=UTC)
    manager.observe_mapping(
        MappingObservation(
            root="ES",
            old_mapped_symbol=None,
            new_mapped_symbol="ESH24",
            observed_at_utc=initial_time,
            effective_at_utc=initial_time,
        )
    )
    immediate_state = manager.observe_mapping(
        MappingObservation(
            root="ES",
            old_mapped_symbol="ESH24",
            new_mapped_symbol="ESM24",
            observed_at_utc=earlier_time,
            effective_at_utc=future_time,
        )
    )

    assert immediate_state is RollState.NORMAL
    assert manager.current_roll_state("ES", earlier_time) is RollState.NORMAL
    assert manager.current_roll_state("ES", future_time) is RollState.ROLL_TRANSITION

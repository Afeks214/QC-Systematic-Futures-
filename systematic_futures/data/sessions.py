from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from itertools import pairwise
from types import MappingProxyType
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from systematic_futures.data.point_in_time import ensure_aware_utc
from systematic_futures.domain.enums import SessionType
from systematic_futures.domain.errors import (
    MarketConfigurationError,
    SessionBoundaryError,
)
from systematic_futures.domain.schemas import SessionWindow, validate_session_window
from systematic_futures.domain.serialization import sha256_hex

_SECONDS_PER_DAY = 86_400.0
_REFERENCE_POLICY_VERSION = "lift1-semantic-v1"
_CHICAGO_TIMEZONE = "America/Chicago"
_NEW_YORK_TIMEZONE = "America/New_York"


@dataclass(frozen=True, slots=True)
class SessionClosureWindow:
    """One explicit exchange-local interval that overrides a session as closed."""

    closure_name: str
    start_local_time: time
    end_local_time: time
    crosses_midnight: bool


@dataclass(frozen=True, slots=True)
class SessionCalendarException:
    """One date-specific, versioned exception to ordinary session windows."""

    exception_name: str
    local_date: date
    timezone_name: str
    all_day_closed: bool
    closed_windows: tuple[SessionClosureWindow, ...]
    calendar_version: str
    source_label: str


class SessionEngine:
    """Classify UTC instants under explicitly versioned local-time windows."""

    def __init__(
        self,
        policies: Mapping[str, tuple[SessionWindow, ...]],
        calendar_exceptions: Mapping[str, tuple[SessionCalendarException, ...]] | None = None,
    ) -> None:
        """Validate and defensively copy root-keyed session policies.

        Units: local wall-clock windows. Time semantics: each market must use
        one resolvable IANA timezone and one policy version; overlap is rejected.
        Date-specific closures are optional and do not alter ordinary behavior
        when omitted. Missingness: blank roots and empty window sets are
        invalid. Raises: ``MarketConfigurationError`` for invalid policy
        structure or timezone, or ``SessionBoundaryError`` for an invalid
        individual window or calendar exception.
        """
        copied: dict[str, tuple[SessionWindow, ...]] = {}
        for root, windows in policies.items():
            normalized_root = root.strip().upper()
            if not normalized_root:
                raise MarketConfigurationError("session-policy root must be non-blank")
            if normalized_root in copied:
                raise MarketConfigurationError(f"duplicate session root: {normalized_root}")
            if not windows:
                raise MarketConfigurationError(
                    f"session policy for {normalized_root} must contain windows"
                )
            for window in windows:
                validate_session_window(window)
            _validate_market_windows(normalized_root, windows)
            copied[normalized_root] = tuple(windows)
        if not copied:
            raise MarketConfigurationError("at least one session policy is required")
        self._policies: Mapping[str, tuple[SessionWindow, ...]] = MappingProxyType(copied)
        self._calendar_exceptions = _copy_calendar_exceptions(
            self._policies,
            calendar_exceptions or {},
        )

    def classify(self, root: str, timestamp_utc: datetime) -> SessionType:
        """Classify one aware instant for ``root``.

        Units: UTC datetime input, enum output. Time semantics: conversion uses
        the policy's IANA timezone and half-open local windows. Missingness: an
        unknown root or uncovered/ambiguous instant is rejected. Raises:
        ``TimeSemanticsError`` or ``SessionBoundaryError``.
        """
        local_timestamp, matches = self._matching_windows(root, timestamp_utc)
        closure = self._matching_calendar_closure(root, local_timestamp)
        if closure is not None:
            return SessionType.CLOSED
        if len(matches) != 1:
            raise SessionBoundaryError(
                f"expected exactly one session match for {root!r}; found {len(matches)}"
            )
        return matches[0].session_type

    def session_id(self, root: str, timestamp_utc: datetime) -> str:
        """Return a deterministic ID for the containing semantic session.

        Units: opaque SHA-256 identifier. Time semantics: cross-midnight windows
        are anchored to their local start date; the policy version is part of
        the ID. Missingness: unknown or ambiguous classifications are rejected.
        Raises: ``TimeSemanticsError`` or ``SessionBoundaryError``.
        """
        local_timestamp, matches = self._matching_windows(root, timestamp_utc)
        closure = self._matching_calendar_closure(root, local_timestamp)
        if closure is None:
            if len(matches) != 1:
                raise SessionBoundaryError(
                    f"expected exactly one session match for {root!r}; found {len(matches)}"
                )
            window = matches[0]
            session_name = window.session_name
            session_type = window.session_type
            policy_version = window.policy_version
            anchor_date = _session_anchor_date(window, local_timestamp)
        else:
            exception, closure_name = closure
            session_name = f"calendar_exception:{exception.exception_name}:{closure_name}"
            session_type = SessionType.CLOSED
            ordinary_version = self.windows_for_market(root)[0].policy_version
            policy_version = f"{ordinary_version}|{exception.calendar_version}"
            anchor_date = exception.local_date
        digest = sha256_hex(
            {
                "root": root.strip().upper(),
                "session_name": session_name,
                "session_type": session_type,
                "policy_version": policy_version,
                "anchor_date": anchor_date.isoformat(),
            }
        )
        return f"session_{digest}"

    def windows_for_market(self, root: str) -> tuple[SessionWindow, ...]:
        """Return immutable semantic windows for ``root``.

        Units: local wall-clock windows. Time semantics: each returned window
        names its timezone and version. Missingness: unknown roots are rejected.
        Raises: ``SessionBoundaryError`` for an unknown root.
        """
        normalized_root = root.strip().upper()
        windows = self._policies.get(normalized_root)
        if windows is None:
            raise SessionBoundaryError(f"no session policy for root {normalized_root!r}")
        return windows

    def calendar_exceptions_for_market(
        self,
        root: str,
    ) -> tuple[SessionCalendarException, ...]:
        """Return immutable, date-specific calendar exceptions for ``root``.

        Units: exchange-local dates and wall-clock times. Time semantics:
        exception dates use the market policy timezone. Missingness: an unknown
        root raises; a configured root without exceptions returns an empty
        tuple. Raises: ``SessionBoundaryError`` for an unknown root.
        """
        normalized_root = root.strip().upper()
        if normalized_root not in self._policies:
            raise SessionBoundaryError(f"no session policy for root {normalized_root!r}")
        return self._calendar_exceptions.get(normalized_root, ())

    def _matching_windows(
        self,
        root: str,
        timestamp_utc: datetime,
    ) -> tuple[datetime, tuple[SessionWindow, ...]]:
        windows = self.windows_for_market(root)
        timestamp = ensure_aware_utc(timestamp_utc, "timestamp_utc")
        local_timestamp = timestamp.astimezone(ZoneInfo(windows[0].timezone_name))
        local_time = local_timestamp.time().replace(tzinfo=None)
        matches = tuple(window for window in windows if _contains(window, local_time))
        return local_timestamp, matches

    def _matching_calendar_closure(
        self,
        root: str,
        local_timestamp: datetime,
    ) -> tuple[SessionCalendarException, str] | None:
        exceptions = self.calendar_exceptions_for_market(root)
        matches: list[tuple[SessionCalendarException, str]] = []
        for exception in exceptions:
            if exception.all_day_closed and local_timestamp.date() == exception.local_date:
                matches.append((exception, "all_day"))
            for window in exception.closed_windows:
                if _calendar_closure_contains(exception.local_date, window, local_timestamp):
                    matches.append((exception, window.closure_name))
        if len(matches) > 1:
            raise SessionBoundaryError(
                f"multiple calendar closures match {root!r} at {local_timestamp.isoformat()}"
            )
        return matches[0] if matches else None


def validate_session_closure_window(window: SessionClosureWindow) -> None:
    """Validate one explicit exchange-local closure interval.

    Units: local wall-clock time. Time semantics: intervals are half-open and
    may cross midnight only when the flag agrees with their endpoints.
    Missingness: blank names and zero-length intervals are rejected. Raises:
    ``SessionBoundaryError`` for invalid content.
    """
    if not window.closure_name.strip():
        raise SessionBoundaryError("closure_name must be non-blank")
    if window.start_local_time == window.end_local_time:
        raise SessionBoundaryError("a closure window cannot have zero duration")
    expected_crossing = window.start_local_time > window.end_local_time
    if window.crosses_midnight != expected_crossing:
        raise SessionBoundaryError("closure window has inconsistent midnight flag")


def validate_session_calendar_exception(exception: SessionCalendarException) -> None:
    """Validate one versioned local-date closure exception.

    Units: exchange-local date and wall-clock time. Time semantics: all-day and
    interval closures are mutually exclusive. Missingness: names, timezone,
    calendar version, source label, and at least one closure form are required.
    Raises: ``SessionBoundaryError`` for malformed content.
    """
    text_fields = {
        "exception_name": exception.exception_name,
        "timezone_name": exception.timezone_name,
        "calendar_version": exception.calendar_version,
        "source_label": exception.source_label,
    }
    for field_name, value in text_fields.items():
        if not value.strip():
            raise SessionBoundaryError(f"{field_name} must be non-blank")
    try:
        ZoneInfo(exception.timezone_name)
    except ZoneInfoNotFoundError as error:
        raise SessionBoundaryError(
            f"unresolvable exception timezone: {exception.timezone_name}"
        ) from error
    if exception.all_day_closed == bool(exception.closed_windows):
        raise SessionBoundaryError(
            "an exception must define exactly one of all-day closure or closed windows"
        )
    closure_names: set[str] = set()
    for window in exception.closed_windows:
        validate_session_closure_window(window)
        if window.closure_name in closure_names:
            raise SessionBoundaryError(f"duplicate closure name: {window.closure_name}")
        closure_names.add(window.closure_name)
    _validate_exception_window_overlap(exception)


def reference_session_policies() -> Mapping[str, tuple[SessionWindow, ...]]:
    """Return Lift 1 semantic windows for ES, ZN, and 6E.

    Units: exchange-local wall-clock times. Time semantics: these versioned
    ordinary-day semantic partitions use each registry market's named timezone;
    they do not certify holidays or early closes. Missingness: no fallback
    market is supplied. Raises: none.
    """
    policies = {
        "ES": (
            _window(
                "es_eth_overnight",
                SessionType.ETH,
                time(18),
                time(9, 30),
                True,
                _NEW_YORK_TIMEZONE,
            ),
            _window(
                "es_rth",
                SessionType.RTH,
                time(9, 30),
                time(16),
                False,
                _NEW_YORK_TIMEZONE,
            ),
            _window(
                "es_eth_afternoon",
                SessionType.ETH,
                time(16),
                time(17),
                False,
                _NEW_YORK_TIMEZONE,
            ),
            _window(
                "es_maintenance",
                SessionType.MAINTENANCE,
                time(17),
                time(18),
                False,
                _NEW_YORK_TIMEZONE,
            ),
        ),
        "ZN": (
            _window(
                "zn_eth_overnight",
                SessionType.ETH,
                time(17),
                time(7, 20),
                True,
                _CHICAGO_TIMEZONE,
            ),
            _window(
                "zn_us_cash_hours",
                SessionType.US_CASH_HOURS,
                time(7, 20),
                time(14),
                False,
                _CHICAGO_TIMEZONE,
            ),
            _window(
                "zn_eth_afternoon",
                SessionType.ETH,
                time(14),
                time(16),
                False,
                _CHICAGO_TIMEZONE,
            ),
            _window(
                "zn_maintenance",
                SessionType.MAINTENANCE,
                time(16),
                time(17),
                False,
                _CHICAGO_TIMEZONE,
            ),
        ),
        "6E": (
            _window(
                "6e_asia",
                SessionType.ASIA,
                time(17),
                time(2),
                True,
                _CHICAGO_TIMEZONE,
            ),
            _window(
                "6e_london",
                SessionType.LONDON,
                time(2),
                time(7),
                False,
                _CHICAGO_TIMEZONE,
            ),
            _window(
                "6e_new_york",
                SessionType.NEW_YORK,
                time(7),
                time(16),
                False,
                _CHICAGO_TIMEZONE,
            ),
            _window(
                "6e_maintenance",
                SessionType.MAINTENANCE,
                time(16),
                time(17),
                False,
                _CHICAGO_TIMEZONE,
            ),
        ),
    }
    return MappingProxyType(policies)


def _window(
    name: str,
    session_type: SessionType,
    start: time,
    end: time,
    crosses_midnight: bool,
    timezone_name: str,
) -> SessionWindow:
    return SessionWindow(
        session_name=name,
        session_type=session_type,
        timezone_name=timezone_name,
        start_local_time=start,
        end_local_time=end,
        crosses_midnight=crosses_midnight,
        policy_version=_REFERENCE_POLICY_VERSION,
    )


def _contains(window: SessionWindow, local_time: time) -> bool:
    if window.crosses_midnight:
        return local_time >= window.start_local_time or local_time < window.end_local_time
    return window.start_local_time <= local_time < window.end_local_time


def _session_anchor_date(window: SessionWindow, local_timestamp: datetime) -> date:
    anchor = local_timestamp.date()
    local_time = local_timestamp.time().replace(tzinfo=None)
    if window.crosses_midnight and local_time < window.end_local_time:
        anchor -= timedelta(days=1)
    return anchor


def _validate_market_windows(root: str, windows: tuple[SessionWindow, ...]) -> None:
    timezone_names = {window.timezone_name for window in windows}
    versions = {window.policy_version for window in windows}
    if len(timezone_names) != 1:
        raise MarketConfigurationError(f"{root} windows must use one timezone")
    if len(versions) != 1:
        raise MarketConfigurationError(f"{root} windows must use one policy version")
    timezone_name = next(iter(timezone_names))
    try:
        ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as error:
        raise MarketConfigurationError(
            f"unresolvable timezone for {root}: {timezone_name}"
        ) from error
    segments: list[tuple[float, float]] = []
    for window in windows:
        start = _seconds_since_midnight(window.start_local_time)
        end = _seconds_since_midnight(window.end_local_time)
        expected_crossing = start > end
        if window.crosses_midnight != expected_crossing:
            raise MarketConfigurationError(
                f"{root} window {window.session_name!r} has inconsistent midnight flag"
            )
        if window.crosses_midnight:
            segments.extend(((0.0, end), (start, _SECONDS_PER_DAY)))
        else:
            segments.append((start, end))
    ordered = sorted(segments)
    for previous, current in pairwise(ordered):
        if current[0] < previous[1]:
            raise MarketConfigurationError(f"overlapping session windows for {root}")


def _copy_calendar_exceptions(
    policies: Mapping[str, tuple[SessionWindow, ...]],
    configured: Mapping[str, tuple[SessionCalendarException, ...]],
) -> Mapping[str, tuple[SessionCalendarException, ...]]:
    copied: dict[str, tuple[SessionCalendarException, ...]] = {}
    for root, exceptions in configured.items():
        normalized_root = root.strip().upper()
        windows = policies.get(normalized_root)
        if windows is None:
            raise MarketConfigurationError(
                f"calendar exceptions reference unknown session root: {normalized_root!r}"
            )
        expected_timezone = windows[0].timezone_name
        exception_names: set[str] = set()
        for exception in exceptions:
            validate_session_calendar_exception(exception)
            if exception.timezone_name != expected_timezone:
                raise MarketConfigurationError(
                    f"calendar exception timezone for {normalized_root} must be "
                    f"{expected_timezone!r}"
                )
            if exception.exception_name in exception_names:
                raise MarketConfigurationError(
                    f"duplicate calendar exception name for {normalized_root}: "
                    f"{exception.exception_name}"
                )
            exception_names.add(exception.exception_name)
        ordered = tuple(
            sorted(
                exceptions,
                key=lambda item: (item.local_date, item.exception_name),
            )
        )
        _validate_calendar_exception_overlap(normalized_root, ordered)
        copied[normalized_root] = ordered
    return MappingProxyType(copied)


def _calendar_closure_contains(
    local_date: date,
    window: SessionClosureWindow,
    local_timestamp: datetime,
) -> bool:
    timestamp_date = local_timestamp.date()
    timestamp_time = local_timestamp.time().replace(tzinfo=None)
    if window.crosses_midnight:
        return (timestamp_date == local_date and timestamp_time >= window.start_local_time) or (
            timestamp_date == local_date + timedelta(days=1)
            and timestamp_time < window.end_local_time
        )
    return (
        timestamp_date == local_date
        and window.start_local_time <= timestamp_time < window.end_local_time
    )


def _validate_exception_window_overlap(exception: SessionCalendarException) -> None:
    segments = sorted(
        _closure_datetime_bounds(exception.local_date, window)
        for window in exception.closed_windows
    )
    for previous, current in pairwise(segments):
        if current[0] < previous[1]:
            raise SessionBoundaryError(
                f"overlapping closure windows in exception {exception.exception_name!r}"
            )


def _validate_calendar_exception_overlap(
    root: str,
    exceptions: tuple[SessionCalendarException, ...],
) -> None:
    intervals: list[tuple[datetime, datetime, str]] = []
    for exception in exceptions:
        if exception.all_day_closed:
            start = datetime.combine(exception.local_date, time.min)
            end = start + timedelta(days=1)
            intervals.append((start, end, exception.exception_name))
        else:
            for window in exception.closed_windows:
                start, end = _closure_datetime_bounds(exception.local_date, window)
                intervals.append((start, end, exception.exception_name))
    ordered = sorted(intervals)
    for previous, current in pairwise(ordered):
        if current[0] < previous[1]:
            raise MarketConfigurationError(
                f"overlapping calendar exceptions for {root}: {previous[2]!r} and {current[2]!r}"
            )


def _closure_datetime_bounds(
    local_date: date,
    window: SessionClosureWindow,
) -> tuple[datetime, datetime]:
    start = datetime.combine(local_date, window.start_local_time)
    end_date = local_date + timedelta(days=1) if window.crosses_midnight else local_date
    end = datetime.combine(end_date, window.end_local_time)
    return start, end


def _seconds_since_midnight(value: time) -> float:
    return value.hour * 3_600 + value.minute * 60 + value.second + value.microsecond / 1_000_000

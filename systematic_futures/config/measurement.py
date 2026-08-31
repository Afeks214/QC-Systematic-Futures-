from collections.abc import Mapping
from dataclasses import dataclass

from systematic_futures.domain.enums import RollState, SessionType
from systematic_futures.domain.errors import DataQualityError

REFERENCE_START_DATE = "2024-02-15"
REFERENCE_END_DATE = "2024-03-25"
SMOKE_START_DATE = "2024-03-04"
SMOKE_END_DATE = "2024-03-06"
MEASUREMENT_ELIGIBLE_ROLL_STATES = frozenset({RollState.NORMAL, RollState.POST_ROLL})
MEASUREMENT_ELIGIBLE_SESSION_TYPES = frozenset(
    session_type
    for session_type in SessionType
    if session_type not in {SessionType.MAINTENANCE, SessionType.CLOSED, SessionType.UNKNOWN}
)
ICM_WINDOWS: Mapping[str, int] = {
    "NQ": 60,
    "ES": 70,
    "RTY": 70,
    "ZT": 140,
    "ZN": 140,
    "6E": 110,
    "6J": 120,
    "6B": 110,
}


@dataclass(frozen=True, slots=True)
class MeasurementClockPolicy:
    """Frozen semantic clocks for the three measurement layers."""

    fast_bar_minutes: int
    medium_state_bar_minutes: int
    profile_snapshot_minutes: int

    def __post_init__(self) -> None:
        values = (
            self.fast_bar_minutes,
            self.medium_state_bar_minutes,
            self.profile_snapshot_minutes,
        )
        if any(type(value) is not int or value <= 0 for value in values):
            raise DataQualityError("measurement clocks must be positive integer minutes")
        if self.profile_snapshot_minutes != self.fast_bar_minutes:
            raise DataQualityError("Auction snapshots must use the fast measurement clock")


MEASUREMENT_CLOCK_POLICY = MeasurementClockPolicy(
    fast_bar_minutes=5,
    medium_state_bar_minutes=30,
    profile_snapshot_minutes=5,
)

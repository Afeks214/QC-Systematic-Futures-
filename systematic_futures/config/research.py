from collections.abc import Mapping
from dataclasses import dataclass

from systematic_futures.domain.enums import RollState, SessionType
from systematic_futures.domain.errors import DataQualityError

PROBE_START_DATE = "2024-02-15"
PROBE_END_DATE = "2024-03-25"
REFERENCE_MARKETS: tuple[str, ...] = ("ES", "ZN", "6E")
RESEARCH_RANDOM_SEED = 20240826
LIFT2_DEEP_START_DATE = "2024-02-15"
LIFT2_DEEP_END_DATE = "2024-03-25"
LIFT2_SMOKE_START_DATE = "2024-03-04"
LIFT2_SMOKE_END_DATE = "2024-03-06"
LIFT2_READINESS_START_DATE = "2024-02-15"
LIFT2_READINESS_END_DATE = "2024-05-31"
LIFT2_REFERENCE_MARKETS: tuple[str, ...] = ("ES", "ZN", "6E")
LIFT2_ALL_MARKETS: tuple[str, ...] = ("ES", "NQ", "RTY", "ZT", "ZN", "6E", "6J", "6B")
LIFT2_MEASUREMENT_ELIGIBLE_ROLL_STATES = frozenset({RollState.NORMAL, RollState.POST_ROLL})
LIFT2_MEASUREMENT_ELIGIBLE_SESSION_TYPES = frozenset(
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
    """Frozen semantic clocks for the three Lift 2 measurement layers."""

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
            raise DataQualityError("Lift 2 Auction snapshots must use the fast measurement clock")


MEASUREMENT_CLOCK_POLICY = MeasurementClockPolicy(
    fast_bar_minutes=5,
    medium_state_bar_minutes=30,
    profile_snapshot_minutes=5,
)


def lift_1_manifest_configuration() -> Mapping[str, object]:
    """Return the canonically hashable Lift 1 research configuration.

    Units: ``contract_filter_days`` is defined in the market registry; the seed is
    dimensionless.
    Time semantics: probe dates are inclusive algorithm calendar bounds as configured
    by LEAN; data availability is handled separately.
    Missingness: every required field is present and no environment value is inferred.
    Raises: no exceptions.
    """
    return {
        "lift": 1,
        "probe_end_date": PROBE_END_DATE,
        "probe_start_date": PROBE_START_DATE,
        "random_seed": RESEARCH_RANDOM_SEED,
        "reference_markets": REFERENCE_MARKETS,
        "scope": "data_truth_only",
    }


def lift_2_measurement_configuration() -> Mapping[str, object]:
    """Return the frozen Lift 2 measurement policy as canonically hashable data.

    Units: windows are completed bars/minutes and fractions are dimensionless.
    Time semantics: all histories and seasonal baselines are strictly prior-only.
    Missingness: warmup shortfalls produce explicit partial snapshots. Raises: no
    exceptions; the returned mapping contains every frozen policy value.
    """

    return {
        "candidate_event_version": "candidate_event_v2",
        "measurement_clock_policy": {
            "fast_bar_minutes": MEASUREMENT_CLOCK_POLICY.fast_bar_minutes,
            "medium_state_bar_minutes": MEASUREMENT_CLOCK_POLICY.medium_state_bar_minutes,
            "profile_snapshot_minutes": MEASUREMENT_CLOCK_POLICY.profile_snapshot_minutes,
        },
        "deep_end_date": LIFT2_DEEP_END_DATE,
        "deep_start_date": LIFT2_DEEP_START_DATE,
        "feature_version": "feature_semantics_math_v5",
        "atr_5m_24_version": "atr_5m_24_arithmetic_tr_floor_1e-6_v2",
        "iae_max_gap_age_bars": 48,
        "iae_min_displacement_efficiency": 0.6,
        "iae_min_wick_absorption": 0.5,
        "iae_min_z_displacement": 1.5,
        "iae_min_z_gap": 0.3,
        "iae_score_threshold": 2.1,
        "iae_time_decay": 0.05,
        "iae_tod_max_prior_sessions": 30,
        "iae_tod_min_observations": 20,
        "iae_volume_z_floor": 0.1,
        "icm_residual_blend": 0.5,
        "icm_regime_ratio_maximum": 1.5,
        "icm_windows": dict(ICM_WINDOWS),
        "icm_z_cap": 4.5,
        "imsi_covariance_condition_maximum": 1000.0,
        "imsi_covariance_ewma_decay": 0.96,
        "imsi_covariance_shrinkage_maximum": 0.95,
        "imsi_covariance_shrinkage_minimum": 0.05,
        "imsi_max_prior_states": 300,
        "imsi_neighbor_embargo_bars": 7,
        "imsi_neighbor_maximum": 15,
        "imsi_prior_distance_minimum": 30,
        "imsi_tod_max_prior_sessions": 30,
        "imsi_tod_min_observations": 30,
        "imsi_vwrsi_period": 14,
        "profile_definition": {
            "price_bin_ticks": 1,
            "rolling_windows_minutes": [30, 60, 120],
            "snapshot_interval_minutes": 5,
            "value_area_fraction": 0.70,
            "version": "volume_profile_math_v2",
        },
        "reference_markets": LIFT2_REFERENCE_MARKETS,
        "readiness_end_date": LIFT2_READINESS_END_DATE,
        "readiness_start_date": LIFT2_READINESS_START_DATE,
        "smoke_end_date": LIFT2_SMOKE_END_DATE,
        "smoke_markets": LIFT2_ALL_MARKETS,
        "smoke_start_date": LIFT2_SMOKE_START_DATE,
    }

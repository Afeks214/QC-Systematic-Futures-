from __future__ import annotations

from collections.abc import Mapping

PROBE_START_DATE = "2024-02-15"
PROBE_END_DATE = "2024-03-25"
REFERENCE_MARKETS: tuple[str, ...] = ("ES", "ZN", "6E")
RESEARCH_RANDOM_SEED = 20240826
LIFT2_DEEP_START_DATE = "2024-02-15"
LIFT2_DEEP_END_DATE = "2024-03-25"
LIFT2_SMOKE_START_DATE = "2024-03-04"
LIFT2_SMOKE_END_DATE = "2024-03-06"
LIFT2_REFERENCE_MARKETS: tuple[str, ...] = ("ES", "ZN", "6E")
LIFT2_ALL_MARKETS: tuple[str, ...] = ("ES", "NQ", "RTY", "ZT", "ZN", "6E", "6J", "6B")
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
        "candidate_event_version": "candidate_event_v1",
        "deep_end_date": LIFT2_DEEP_END_DATE,
        "deep_start_date": LIFT2_DEEP_START_DATE,
        "feature_version": "feature_semantics_v2",
        "iae_max_gap_age_bars": 48,
        "iae_tod_max_prior_sessions": 30,
        "iae_tod_min_observations": 20,
        "icm_residual_blend": 0.5,
        "icm_windows": dict(ICM_WINDOWS),
        "imsi_covariance_floor_absolute": 1e-12,
        "imsi_covariance_floor_relative": 1e-8,
        "imsi_max_prior_states": 300,
        "imsi_neighbor_maximum": 15,
        "imsi_prior_distance_minimum": 30,
        "imsi_tod_max_prior_sessions": 30,
        "imsi_tod_min_observations": 10,
        "imsi_vwrsi_period": 14,
        "local_price_scale_full_bars": 24,
        "local_price_scale_minimum_bars": 12,
        "local_price_scale_version": "local_range_5m_24_v1",
        "profile_definition": {
            "price_bin_ticks": 1,
            "rolling_windows_minutes": [30, 60, 120],
            "snapshot_interval_minutes": 5,
            "value_area_fraction": 0.70,
            "version": "volume_profile_v1",
        },
        "reference_markets": LIFT2_REFERENCE_MARKETS,
        "smoke_end_date": LIFT2_SMOKE_END_DATE,
        "smoke_markets": LIFT2_ALL_MARKETS,
        "smoke_start_date": LIFT2_SMOKE_START_DATE,
    }

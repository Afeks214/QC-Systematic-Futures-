from __future__ import annotations

from collections.abc import Mapping

PROBE_START_DATE = "2024-02-15"
PROBE_END_DATE = "2024-03-25"
REFERENCE_MARKETS: tuple[str, ...] = ("ES", "ZN", "6E")
RESEARCH_RANDOM_SEED = 20240826


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

# Feature Semantics V1

Registry version: `v1`
Implementation status: **NOT_IMPLEMENTED for every entry**
Operating boundary: names and units only; no feature calculation, signal, return
study, Profile, Auction State, IMSI, ICM, IAE, model, or trading behavior exists.

The canonical code registry is `systematic_futures/config/feature_semantics.py`; its
machine-readable export is `artifacts/contracts/feature_semantics_v1.json`. The test
suite requires the JSON content to equal the canonicalized code records. The registry validates stable snake-case
names, explicit units and normalization families, point-in-time requirements,
missingness behavior, and the `NOT_IMPLEMENTED` state. The JSON artifact is referenced
by hash in the closure evidence index; this documentation table is not a substitute
for that check.

## Unit and normalization vocabulary

| Family | Unit examples | Semantic constraint |
|---|---|---|
| Raw ticks | `raw_ticks` | Count exchange-defined minimum price increments; tick metadata must be certified before use |
| Realized-volatility units | `volatility_units` | Divide by an explicit point-in-time volatility scale; no estimator is selected in Lift 1 |
| Session-normalized ratios | `session_normalized_ratio` | Denominator must use only eligible elapsed session observations |
| Rolling percentiles | `percentile_0_1` | Rank only against history usable before the snapshot |
| Returns | `decimal_return` | Horizon and completed observation endpoints must be explicit |
| Risk/NAV units | `fraction_of_nav` | Express future risk exposure as a fraction of explicitly versioned NAV |
| Dimensionless distribution/composite | `dimensionless_ratio`, `dimensionless_score` | Components and scaling must remain explicit; no hidden aggregation |

## Frozen registry

| Feature name | Human definition | Unit | Normalization family | Source family | Point-in-time requirement | Missingness policy | Status |
|---|---|---|---|---|---|---|---|
| `acceptance_score` | Future composite evidence that participation is forming new value | `dimensionless_score` | `component_preserving_composite` | `auction_profile` | Use only observations available at the snapshot time from one actual contract | Withhold; never coerce missing input to zero | `NOT_IMPLEMENTED` |
| `distance_to_current_poc_ticks` | Future signed price distance from the current point of control | `raw_ticks` | `raw_ticks` | `auction_profile` | Use only observations available at the snapshot time from one actual contract | Withhold; never coerce missing input to zero | `NOT_IMPLEMENTED` |
| `distance_to_vah_vol` | Future signed price distance from value-area high in volatility units | `volatility_units` | `realized_volatility_units` | `auction_profile` | Use only observations available at the snapshot time from one actual contract | Withhold; never coerce missing input to zero | `NOT_IMPLEMENTED` |
| `distance_to_val_vol` | Future signed price distance from value-area low in volatility units | `volatility_units` | `realized_volatility_units` | `auction_profile` | Use only observations available at the snapshot time from one actual contract | Withhold; never coerce missing input to zero | `NOT_IMPLEMENTED` |
| `expected_shortfall_fraction_nav` | Future expected-shortfall exposure expressed as a fraction of NAV | `fraction_of_nav` | `risk_nav_units` | `future_risk_contract` | Use only risk inputs available at the declared snapshot time | Withhold; never coerce missing input to zero | `NOT_IMPLEMENTED` |
| `poc_migration_vol` | Future point-of-control migration relative to an explicit prior window | `volatility_units` | `realized_volatility_units` | `auction_profile` | Use only observations available at the snapshot time from one actual contract | Withhold; never coerce missing input to zero | `NOT_IMPLEMENTED` |
| `profile_entropy` | Future normalized entropy of the observed volume-at-price distribution | `dimensionless_ratio` | `normalized_distribution` | `auction_profile` | Use only observations available at the snapshot time from one actual contract | Withhold; never coerce missing input to zero | `NOT_IMPLEMENTED` |
| `rejection_score` | Future composite evidence of excursion failure and value re-entry | `dimensionless_score` | `component_preserving_composite` | `auction_profile` | Use only observations available at the snapshot time from one actual contract | Withhold; never coerce missing input to zero | `NOT_IMPLEMENTED` |
| `return_h` | Future horizon-explicit price return using completed observations | `decimal_return` | `returns` | `market_state` | Both price observations must be usable by the snapshot time | Withhold; never coerce missing input to zero | `NOT_IMPLEMENTED` |
| `time_outside_value_ratio` | Future elapsed eligible time outside an explicit value-area ratio | `session_normalized_ratio` | `session_normalized_ratios` | `auction_profile` | Use only observations available at the snapshot time from one actual contract | Withhold; never coerce missing input to zero | `NOT_IMPLEMENTED` |
| `value_area_width_vol` | Future value-area width expressed in volatility units | `volatility_units` | `realized_volatility_units` | `auction_profile` | Use only observations available at the snapshot time from one actual contract | Withhold; never coerce missing input to zero | `NOT_IMPLEMENTED` |
| `volatility_percentile` | Future point-in-time rolling percentile of realized volatility | `percentile_0_1` | `rolling_percentiles` | `market_state` | Rank only against history usable before the snapshot time | Withhold; never coerce missing input to zero | `NOT_IMPLEMENTED` |
| `volume_outside_value_ratio` | Future observed volume outside value divided by eligible elapsed volume | `session_normalized_ratio` | `session_normalized_ratios` | `auction_profile` | Use only observations available at the snapshot time from one actual contract | Withhold; never coerce missing input to zero | `NOT_IMPLEMENTED` |

## Closure interpretation

Freezing vocabulary prevents later notebooks or modules from silently changing units.
It does not assert that an input dataset is certified, that any feature has been
calculated, or that any feature has predictive value. Every future implementation must
separately establish actual-contract identity, point-in-time availability, session and
roll validity, dataset permissions, and the declared missingness behavior.

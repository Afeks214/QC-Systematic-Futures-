from __future__ import annotations

from collections.abc import Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from systematic_futures.domain.enums import AssetClassGroup
from systematic_futures.domain.errors import MarketConfigurationError
from systematic_futures.domain.schemas import MarketDefinition

_EXPECTED_ROOTS = frozenset({"ES", "NQ", "RTY", "ZT", "ZN", "6E", "6J", "6B"})
_REFERENCE_ROOTS = frozenset({"ES", "ZN", "6E"})
_OPEN_INTEREST = "OPEN_INTEREST"
_BACKWARDS_RATIO = "BACKWARDS_RATIO"
_REFERENCE_FILTER_DAYS = 182

_MARKETS: tuple[MarketDefinition, ...] = (
    MarketDefinition(
        root="ES",
        asset_class=AssetClassGroup.EQUITY_INDEX,
        qc_future_constant_path="Futures.Indices.SP_500_E_MINI",
        exchange_timezone="America/New_York",
        session_policy_id="es_reference_sessions_v1",
        mapping_mode_name=_OPEN_INTEREST,
        normalization_mode_name=_BACKWARDS_RATIO,
        extended_market_hours=True,
        contract_filter_days=_REFERENCE_FILTER_DAYS,
        enabled_for_reference_probe=True,
    ),
    MarketDefinition(
        root="NQ",
        asset_class=AssetClassGroup.EQUITY_INDEX,
        qc_future_constant_path="Futures.Indices.NASDAQ_100_E_MINI",
        exchange_timezone="America/New_York",
        session_policy_id="nq_candidate_sessions_v1",
        mapping_mode_name=_OPEN_INTEREST,
        normalization_mode_name=_BACKWARDS_RATIO,
        extended_market_hours=True,
        contract_filter_days=_REFERENCE_FILTER_DAYS,
        enabled_for_reference_probe=False,
    ),
    MarketDefinition(
        root="RTY",
        asset_class=AssetClassGroup.EQUITY_INDEX,
        qc_future_constant_path="Futures.Indices.RUSSELL_2000_E_MINI",
        exchange_timezone="America/New_York",
        session_policy_id="rty_candidate_sessions_v1",
        mapping_mode_name=_OPEN_INTEREST,
        normalization_mode_name=_BACKWARDS_RATIO,
        extended_market_hours=True,
        contract_filter_days=_REFERENCE_FILTER_DAYS,
        enabled_for_reference_probe=False,
    ),
    MarketDefinition(
        root="ZT",
        asset_class=AssetClassGroup.RATES,
        qc_future_constant_path="Futures.Financials.Y_2_TREASURY_NOTE",
        exchange_timezone="America/Chicago",
        session_policy_id="zt_candidate_sessions_v1",
        mapping_mode_name=_OPEN_INTEREST,
        normalization_mode_name=_BACKWARDS_RATIO,
        extended_market_hours=True,
        contract_filter_days=_REFERENCE_FILTER_DAYS,
        enabled_for_reference_probe=False,
    ),
    MarketDefinition(
        root="ZN",
        asset_class=AssetClassGroup.RATES,
        qc_future_constant_path="Futures.Financials.Y_10_TREASURY_NOTE",
        exchange_timezone="America/Chicago",
        session_policy_id="zn_reference_sessions_v1",
        mapping_mode_name=_OPEN_INTEREST,
        normalization_mode_name=_BACKWARDS_RATIO,
        extended_market_hours=True,
        contract_filter_days=_REFERENCE_FILTER_DAYS,
        enabled_for_reference_probe=True,
    ),
    MarketDefinition(
        root="6E",
        asset_class=AssetClassGroup.FX,
        qc_future_constant_path="Futures.Currencies.EUR",
        exchange_timezone="America/Chicago",
        session_policy_id="6e_reference_sessions_v1",
        mapping_mode_name=_OPEN_INTEREST,
        normalization_mode_name=_BACKWARDS_RATIO,
        extended_market_hours=True,
        contract_filter_days=_REFERENCE_FILTER_DAYS,
        enabled_for_reference_probe=True,
    ),
    MarketDefinition(
        root="6J",
        asset_class=AssetClassGroup.FX,
        qc_future_constant_path="Futures.Currencies.JPY",
        exchange_timezone="America/Chicago",
        session_policy_id="6j_candidate_sessions_v1",
        mapping_mode_name=_OPEN_INTEREST,
        normalization_mode_name=_BACKWARDS_RATIO,
        extended_market_hours=True,
        contract_filter_days=_REFERENCE_FILTER_DAYS,
        enabled_for_reference_probe=False,
    ),
    MarketDefinition(
        root="6B",
        asset_class=AssetClassGroup.FX,
        qc_future_constant_path="Futures.Currencies.GBP",
        exchange_timezone="America/Chicago",
        session_policy_id="6b_candidate_sessions_v1",
        mapping_mode_name=_OPEN_INTEREST,
        normalization_mode_name=_BACKWARDS_RATIO,
        extended_market_hours=True,
        contract_filter_days=_REFERENCE_FILTER_DAYS,
        enabled_for_reference_probe=False,
    ),
)


def all_market_definitions() -> tuple[MarketDefinition, ...]:
    """Return all eight immutable candidate-market definitions.

    Units: ``contract_filter_days`` is calendar days to expiry.
    Time semantics: exchange time zones are IANA names; no session calendar is read.
    Missingness: the registry is all-or-error and never silently omits a market.
    Raises: MarketConfigurationError if the built-in registry is invalid.
    """
    errors = validate_market_registry(_MARKETS)
    if errors:
        raise MarketConfigurationError("; ".join(errors))
    return _MARKETS


def reference_market_definitions() -> tuple[MarketDefinition, ...]:
    """Return the Lift 1 reference markets in deterministic registry order.

    Units: inherited from ``MarketDefinition``.
    Time semantics: no dynamic time selection is performed.
    Missingness: exactly ES, ZN, and 6E are returned or validation raises.
    Raises: MarketConfigurationError if the registry is invalid.
    """
    return tuple(
        market for market in all_market_definitions() if market.enabled_for_reference_probe
    )


def get_market_definition(root: str) -> MarketDefinition:
    """Return one market definition by exact root symbol.

    Units: inherited from ``MarketDefinition``.
    Time semantics: not applicable.
    Missingness: unknown or blank roots raise instead of returning ``None``.
    Raises: MarketConfigurationError for an unknown root or invalid registry.
    """
    for market in all_market_definitions():
        if market.root == root:
            return market
    raise MarketConfigurationError(f"Unknown market root: {root!r}")


def validate_market_registry(markets: Sequence[MarketDefinition]) -> tuple[str, ...]:
    """Return deterministic validation errors for a candidate market registry.

    Units: each filter horizon is calendar days and must be positive.
    Time semantics: every IANA time-zone name must resolve in the local tz database.
    Missingness: every exact root and QC constant path is mandatory.
    Raises: no exception for configuration defects; time-zone lookup failures become
    returned errors.
    """
    errors: list[str] = []
    roots = [market.root for market in markets]
    if len(markets) != 8:
        errors.append(f"expected 8 markets, received {len(markets)}")
    if set(roots) != set(_EXPECTED_ROOTS):
        errors.append(f"roots must be exactly {sorted(_EXPECTED_ROOTS)}")
    if len(roots) != len(set(roots)):
        errors.append("market roots must be unique")
    references = {market.root for market in markets if market.enabled_for_reference_probe}
    if references != set(_REFERENCE_ROOTS):
        errors.append(f"reference roots must be exactly {sorted(_REFERENCE_ROOTS)}")
    policy_ids = [market.session_policy_id for market in markets]
    if len(policy_ids) != len(set(policy_ids)):
        errors.append("session policy identifiers must be unique")
    for market in markets:
        errors.extend(_validate_market(market))
    return tuple(sorted(errors))


def _validate_market(market: MarketDefinition) -> list[str]:
    errors: list[str] = []
    if not _is_asset_class(market.asset_class):
        errors.append(f"{market.root}: invalid asset class")
    if not market.qc_future_constant_path.strip():
        errors.append(f"{market.root}: blank QC constant path")
    if not market.session_policy_id.strip():
        errors.append(f"{market.root}: blank session policy ID")
    if market.contract_filter_days <= 0:
        errors.append(f"{market.root}: filter horizon must be positive")
    if market.mapping_mode_name != _OPEN_INTEREST:
        errors.append(f"{market.root}: mapping mode must be {_OPEN_INTEREST}")
    if market.normalization_mode_name != _BACKWARDS_RATIO:
        errors.append(f"{market.root}: normalization mode must be {_BACKWARDS_RATIO}")
    try:
        ZoneInfo(market.exchange_timezone)
    except ZoneInfoNotFoundError:
        errors.append(f"{market.root}: unresolved timezone {market.exchange_timezone!r}")
    return errors


def _is_asset_class(value: object) -> bool:
    return isinstance(value, AssetClassGroup)

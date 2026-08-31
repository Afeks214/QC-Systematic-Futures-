from __future__ import annotations

from collections.abc import Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from systematic_futures.domain.enums import (
    AssetClassGroup,
    MarketCertificationStatus,
)
from systematic_futures.domain.errors import MarketConfigurationError
from systematic_futures.domain.markets import MarketDefinition, validate_market_definition

_OPEN_INTEREST = "OPEN_INTEREST"
_BACKWARDS_RATIO = "BACKWARDS_RATIO"
_REFERENCE_FILTER_DAYS = 182
_CONTRACT_DEPTH_OFFSET = 0
_HOLIDAY_POLICY = "lean-market-hours-b692bf4-reference-exceptions-v1"
_ROLL_POLICY = "mapping-observation-measurement-v1"
_EXECUTION_IDENTITY_POLICY = "ACTUAL_CONTRACT_ONLY"
_CERTIFICATION_STATUS = MarketCertificationStatus.CERTIFIED_CURRENT_LEAN_REFERENCE
_SOURCE_EVIDENCE = (
    "v2-spec-sha256:ff3bebe1e2d6db16cd65f70c7f89e3f4b9626d505309af1ec7821dfd5bdb567f",
    "lean-commit:b692bf4788e8b54fc23bdcb5659666bf055ce89f",
    "lean-symbol-properties-sha256:53072f5a5ac4ff1b0d6f14a28fb93c43b633c0713635539fda0c2695089e236a",
    "lean-market-hours-sha256:d93f0b417cc9df618da4548f78157fd2b49515e0999f16e83ffddcffd54eef41",
    "qc-api-resolution:2026-08-31",
)


def _market(
    *,
    root: str,
    asset_class: AssetClassGroup,
    exchange: str,
    qc_root_identity: str,
    minimum_tick: float,
    multiplier: float,
    exchange_timezone: str,
    semantic_session_policy_id: str,
    reference: bool,
) -> MarketDefinition:
    return MarketDefinition(
        root=root,
        asset_class=asset_class,
        exchange=exchange,
        currency="USD",
        qc_root_identity=qc_root_identity,
        minimum_tick=minimum_tick,
        multiplier=multiplier,
        exchange_timezone=exchange_timezone,
        semantic_session_policy_id=semantic_session_policy_id,
        holiday_calendar_policy_id=_HOLIDAY_POLICY,
        mapping_mode=_OPEN_INTEREST,
        signal_normalization_mode=_BACKWARDS_RATIO,
        contract_depth_offset=_CONTRACT_DEPTH_OFFSET,
        roll_policy_id=_ROLL_POLICY,
        execution_identity_policy=_EXECUTION_IDENTITY_POLICY,
        certification_status=_CERTIFICATION_STATUS,
        source_evidence_lineage=_SOURCE_EVIDENCE,
        extended_market_hours=True,
        contract_filter_days=_REFERENCE_FILTER_DAYS,
        reference_market=reference,
    )


_MARKETS: tuple[MarketDefinition, ...] = (
    _market(
        root="ES",
        asset_class=AssetClassGroup.EQUITY_INDEX,
        exchange="CME",
        qc_root_identity="Futures.Indices.SP_500_E_MINI",
        minimum_tick=0.25,
        multiplier=50.0,
        exchange_timezone="America/New_York",
        semantic_session_policy_id="es_sessions_v1",
        reference=True,
    ),
    _market(
        root="NQ",
        asset_class=AssetClassGroup.EQUITY_INDEX,
        exchange="CME",
        qc_root_identity="Futures.Indices.NASDAQ_100_E_MINI",
        minimum_tick=0.25,
        multiplier=20.0,
        exchange_timezone="America/New_York",
        semantic_session_policy_id="nq_sessions_v1",
        reference=False,
    ),
    _market(
        root="RTY",
        asset_class=AssetClassGroup.EQUITY_INDEX,
        exchange="CME",
        qc_root_identity="Futures.Indices.RUSSELL_2000_E_MINI",
        minimum_tick=0.1,
        multiplier=50.0,
        exchange_timezone="America/New_York",
        semantic_session_policy_id="rty_sessions_v1",
        reference=False,
    ),
    _market(
        root="ZT",
        asset_class=AssetClassGroup.RATES,
        exchange="CBOT",
        qc_root_identity="Futures.Financials.Y_2_TREASURY_NOTE",
        minimum_tick=0.00390625,
        multiplier=2000.0,
        exchange_timezone="America/Chicago",
        semantic_session_policy_id="zt_sessions_v1",
        reference=False,
    ),
    _market(
        root="ZN",
        asset_class=AssetClassGroup.RATES,
        exchange="CBOT",
        qc_root_identity="Futures.Financials.Y_10_TREASURY_NOTE",
        minimum_tick=0.015625,
        multiplier=1000.0,
        exchange_timezone="America/Chicago",
        semantic_session_policy_id="zn_sessions_v1",
        reference=True,
    ),
    _market(
        root="6E",
        asset_class=AssetClassGroup.FX,
        exchange="CME",
        qc_root_identity="Futures.Currencies.EUR",
        minimum_tick=0.00005,
        multiplier=125000.0,
        exchange_timezone="America/Chicago",
        semantic_session_policy_id="6e_sessions_v1",
        reference=True,
    ),
    _market(
        root="6J",
        asset_class=AssetClassGroup.FX,
        exchange="CME",
        qc_root_identity="Futures.Currencies.JPY",
        minimum_tick=0.0000005,
        multiplier=12500000.0,
        exchange_timezone="America/Chicago",
        semantic_session_policy_id="6j_sessions_v1",
        reference=False,
    ),
    _market(
        root="6B",
        asset_class=AssetClassGroup.FX,
        exchange="CME",
        qc_root_identity="Futures.Currencies.GBP",
        minimum_tick=0.0001,
        multiplier=62500.0,
        exchange_timezone="America/Chicago",
        semantic_session_policy_id="6b_sessions_v1",
        reference=False,
    ),
)
ALL_MARKETS: tuple[str, ...] = tuple(market.root for market in _MARKETS)
REFERENCE_MARKETS: tuple[str, ...] = tuple(
    market.root for market in _MARKETS if market.reference_market
)


def all_market_definitions() -> tuple[MarketDefinition, ...]:
    """Return all eight immutable certified Market Master records.

    Units: official LEAN symbol-property units. Time semantics: exchange zones are
    IANA names and policy identities are explicit. Missingness: all eight records are
    returned or the registry fails closed. Raises: ``MarketConfigurationError``.
    """

    errors = validate_market_registry(_MARKETS)
    if errors:
        raise MarketConfigurationError("; ".join(errors))
    return _MARKETS


def reference_market_definitions() -> tuple[MarketDefinition, ...]:
    """Return ES, ZN, and 6E in deterministic Market Master order."""

    return tuple(market for market in all_market_definitions() if market.reference_market)


def get_market_definition(root: str) -> MarketDefinition:
    """Resolve one exact root without fallback or substitution."""

    for market in all_market_definitions():
        if market.root == root:
            return market
    raise MarketConfigurationError(f"Unknown market root: {root!r}")


def validate_market_registry(markets: Sequence[MarketDefinition]) -> tuple[str, ...]:
    """Return deterministic validation defects for an eight-root Market Master."""

    errors: list[str] = []
    roots = [market.root for market in markets]
    if len(markets) != 8:
        errors.append(f"expected 8 markets, received {len(markets)}")
    if set(roots) != set(ALL_MARKETS):
        errors.append(f"roots must be exactly {sorted(ALL_MARKETS)}")
    if len(roots) != len(set(roots)):
        errors.append("market roots must be unique")
    references = {market.root for market in markets if market.reference_market}
    if references != set(REFERENCE_MARKETS):
        errors.append(f"reference roots must be exactly {sorted(REFERENCE_MARKETS)}")
    policy_ids = [market.semantic_session_policy_id for market in markets]
    if len(policy_ids) != len(set(policy_ids)):
        errors.append("session policy identifiers must be unique")
    for market in markets:
        try:
            validate_market_definition(market)
        except MarketConfigurationError as error:
            errors.append(f"{market.root}: {error}")
        if market.mapping_mode != _OPEN_INTEREST:
            errors.append(f"{market.root}: mapping mode must be {_OPEN_INTEREST}")
        if market.signal_normalization_mode != _BACKWARDS_RATIO:
            errors.append(f"{market.root}: normalization mode must be {_BACKWARDS_RATIO}")
        if market.contract_depth_offset != _CONTRACT_DEPTH_OFFSET:
            errors.append(f"{market.root}: contract depth offset must be zero")
        if market.roll_policy_id != _ROLL_POLICY:
            errors.append(f"{market.root}: unresolved roll policy")
        if market.execution_identity_policy != _EXECUTION_IDENTITY_POLICY:
            errors.append(f"{market.root}: execution identity must be actual-contract only")
        try:
            ZoneInfo(market.exchange_timezone)
        except ZoneInfoNotFoundError:
            errors.append(f"{market.root}: unresolved timezone {market.exchange_timezone!r}")
    return tuple(sorted(errors))


__all__ = (
    "ALL_MARKETS",
    "REFERENCE_MARKETS",
    "all_market_definitions",
    "get_market_definition",
    "reference_market_definitions",
    "validate_market_registry",
)

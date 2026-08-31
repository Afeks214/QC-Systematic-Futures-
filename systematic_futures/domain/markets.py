# pyright: reportUnnecessaryIsInstance=false
from __future__ import annotations

import math
from dataclasses import dataclass
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from systematic_futures.domain.enums import AssetClassGroup, MarketCertificationStatus
from systematic_futures.domain.errors import MarketConfigurationError


@dataclass(frozen=True, slots=True)
class MarketDefinition:
    """One complete immutable Market Master record."""

    root: str
    asset_class: AssetClassGroup
    exchange: str
    currency: str
    qc_root_identity: str
    minimum_tick: float
    multiplier: float
    exchange_timezone: str
    semantic_session_policy_id: str
    holiday_calendar_policy_id: str
    mapping_mode: str
    signal_normalization_mode: str
    contract_depth_offset: int
    roll_policy_id: str
    execution_identity_policy: str
    certification_status: MarketCertificationStatus
    source_evidence_lineage: tuple[str, ...]
    extended_market_hours: bool
    contract_filter_days: int
    reference_market: bool

    @property
    def tick_value(self) -> float:
        """Return deterministic quote-currency value of one minimum tick."""

        return self.minimum_tick * self.multiplier


def validate_market_definition(market: MarketDefinition) -> None:
    """Validate all Market Master units, policies, identities, and lineage."""

    text_fields = {
        "root": market.root,
        "exchange": market.exchange,
        "currency": market.currency,
        "qc_root_identity": market.qc_root_identity,
        "exchange_timezone": market.exchange_timezone,
        "semantic_session_policy_id": market.semantic_session_policy_id,
        "holiday_calendar_policy_id": market.holiday_calendar_policy_id,
        "mapping_mode": market.mapping_mode,
        "signal_normalization_mode": market.signal_normalization_mode,
        "roll_policy_id": market.roll_policy_id,
        "execution_identity_policy": market.execution_identity_policy,
    }
    for field_name, value in text_fields.items():
        _require_text(value, field_name)
    if not isinstance(market.asset_class, AssetClassGroup):
        raise MarketConfigurationError("asset_class must be an AssetClassGroup")
    for field_name, value in (
        ("minimum_tick", market.minimum_tick),
        ("multiplier", market.multiplier),
    ):
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise MarketConfigurationError(f"{field_name} must be a positive number")
        if not math.isfinite(value) or value <= 0:
            raise MarketConfigurationError(f"{field_name} must be a positive number")
    if not math.isfinite(market.tick_value) or market.tick_value <= 0:
        raise MarketConfigurationError("derived tick_value must be positive and finite")
    if (
        isinstance(market.contract_depth_offset, bool)
        or not isinstance(market.contract_depth_offset, int)
        or market.contract_depth_offset < 0
    ):
        raise MarketConfigurationError("contract_depth_offset must be a non-negative integer")
    if (
        isinstance(market.contract_filter_days, bool)
        or not isinstance(market.contract_filter_days, int)
        or market.contract_filter_days <= 0
    ):
        raise MarketConfigurationError("contract_filter_days must be a positive integer")
    if not isinstance(market.extended_market_hours, bool):
        raise MarketConfigurationError("extended_market_hours must be boolean")
    if not isinstance(market.reference_market, bool):
        raise MarketConfigurationError("reference_market must be boolean")
    if not isinstance(market.certification_status, MarketCertificationStatus):
        raise MarketConfigurationError("certification_status must be a MarketCertificationStatus")
    if not isinstance(market.source_evidence_lineage, tuple):
        raise MarketConfigurationError("source_evidence_lineage must be a tuple")
    if not market.source_evidence_lineage:
        raise MarketConfigurationError("source_evidence_lineage must not be empty")
    for index, item in enumerate(market.source_evidence_lineage):
        _require_text(item, f"source_evidence_lineage[{index}]")
    try:
        ZoneInfo(market.exchange_timezone)
    except ZoneInfoNotFoundError as error:
        raise MarketConfigurationError(
            f"exchange_timezone is not resolvable: {market.exchange_timezone}"
        ) from error


def _require_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise MarketConfigurationError(f"{field_name} must be a non-blank string")


__all__ = ("MarketDefinition", "validate_market_definition")

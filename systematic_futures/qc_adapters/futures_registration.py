from typing import Any, cast

from systematic_futures.domain.errors import UnverifiedQuantConnectApiError
from systematic_futures.domain.markets import MarketDefinition, validate_market_definition


def _load_registration_api() -> tuple[Any, Any, Any, Any]:
    from AlgorithmImports import (  # type: ignore[import-not-found]
        DataMappingMode,
        DataNormalizationMode,
        Futures,
        Resolution,
    )

    return DataMappingMode, DataNormalizationMode, Futures, Resolution


def _future_constant(path: str, futures: Any) -> object:
    if path == "Futures.Indices.SP_500_E_MINI":
        return cast(object, futures.Indices.SP_500_E_MINI)
    if path == "Futures.Financials.Y_10_TREASURY_NOTE":
        return cast(object, futures.Financials.Y_10_TREASURY_NOTE)
    if path == "Futures.Currencies.EUR":
        return cast(object, futures.Currencies.EUR)
    if path == "Futures.Indices.NASDAQ_100_E_MINI":
        return cast(object, futures.Indices.NASDAQ_100_E_MINI)
    if path == "Futures.Indices.RUSSELL_2000_E_MINI":
        return cast(object, futures.Indices.RUSSELL_2000_E_MINI)
    if path == "Futures.Financials.Y_2_TREASURY_NOTE":
        return cast(object, futures.Financials.Y_2_TREASURY_NOTE)
    if path == "Futures.Currencies.JPY":
        return cast(object, futures.Currencies.JPY)
    if path == "Futures.Currencies.GBP":
        return cast(object, futures.Currencies.GBP)
    raise UnverifiedQuantConnectApiError(f"no verified future registration for {path!r}")


def _mapping_mode(name: str, data_mapping_mode: Any) -> object:
    if name == "OPEN_INTEREST":
        return cast(object, data_mapping_mode.OPEN_INTEREST)
    raise UnverifiedQuantConnectApiError(f"Unverified futures mapping mode: {name!r}")


def _normalization_mode(name: str, data_normalization_mode: Any) -> object:
    if name == "BACKWARDS_RATIO":
        return cast(object, data_normalization_mode.BACKWARDS_RATIO)
    raise UnverifiedQuantConnectApiError(f"Unverified futures normalization mode: {name!r}")


def register_measurement_future(host: object, market: MarketDefinition) -> object:
    """Register one of the eight verified continuous roots for mapping only.

    Units: minute root resolution and calendar-day expiry filter. Time semantics:
    extended hours, Open Interest mapping, Backwards Ratio normalization, and depth
    zero are explicit. Missingness: an absent subscription/symbol raises. Raises:
    market, API-resolution, or QC runtime errors.
    """

    validate_market_definition(market)
    mapping_api, normalization_api, futures, resolution = _load_registration_api()
    qc_host = cast(Any, host)
    subscription = qc_host.add_future(
        _future_constant(market.qc_root_identity, futures),
        resolution.MINUTE,
        extended_market_hours=market.extended_market_hours,
        data_mapping_mode=_mapping_mode(market.mapping_mode, mapping_api),
        data_normalization_mode=_normalization_mode(
            market.signal_normalization_mode,
            normalization_api,
        ),
        contract_depth_offset=market.contract_depth_offset,
    )
    if subscription is None or getattr(subscription, "symbol", None) is None:
        raise UnverifiedQuantConnectApiError("add_future returned no continuous subscription")
    subscription.set_filter(0, market.contract_filter_days)
    return cast(object, subscription)


__all__ = ("register_measurement_future",)

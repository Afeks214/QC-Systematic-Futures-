import math
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Any, cast

from systematic_futures.domain.errors import (
    DataQualityError,
    DataTimingInvariantError,
    MarketConfigurationError,
    TimeSemanticsError,
    UnverifiedQuantConnectApiError,
)
from systematic_futures.domain.schemas import MarketDefinition, validate_market_definition

_REFERENCE_ROOTS = frozenset({"ES", "ZN", "6E"})
_MEASUREMENT_ROOTS = frozenset({"ES", "NQ", "RTY", "ZT", "ZN", "6E", "6J", "6B"})


def _load_registration_api() -> tuple[Any, Any, Any, Any]:
    from AlgorithmImports import (  # type: ignore[import-not-found]
        DataMappingMode,
        DataNormalizationMode,
        Futures,
        Resolution,
    )

    return DataMappingMode, DataNormalizationMode, Futures, Resolution


def _load_history_api() -> tuple[Any, Any, Any, Any]:
    from AlgorithmImports import (  # type: ignore[import-not-found]
        FutureUniverse,
        Resolution,
        SymbolChangedEvent,
        TradeBar,
    )

    return FutureUniverse, Resolution, SymbolChangedEvent, TradeBar


def _load_cftc_api() -> tuple[Any, Any, Any]:
    from AlgorithmImports import (  # type: ignore[import-not-found]
        CFTC,
        CFTCFinancialFutures,
        Resolution,
    )

    return CFTC, CFTCFinancialFutures, Resolution


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
    raise UnverifiedQuantConnectApiError(
        f"Lift 1 has no verified reference registration for {path!r}"
    )


def _mapping_mode(name: str, data_mapping_mode: Any) -> object:
    if name == "OPEN_INTEREST":
        return cast(object, data_mapping_mode.OPEN_INTEREST)
    raise UnverifiedQuantConnectApiError(f"Unverified futures mapping mode: {name!r}")


def _normalization_mode(name: str, data_normalization_mode: Any) -> object:
    if name == "BACKWARDS_RATIO":
        return cast(object, data_normalization_mode.BACKWARDS_RATIO)
    raise UnverifiedQuantConnectApiError(f"Unverified futures normalization mode: {name!r}")


def _require_reference_markets(markets: Sequence[MarketDefinition]) -> None:
    roots = tuple(market.root for market in markets)
    if len(roots) != 3 or len(set(roots)) != 3 or set(roots) != _REFERENCE_ROOTS:
        raise MarketConfigurationError("QC registration requires exactly ES, ZN, and 6E")
    if any(not market.enabled_for_reference_probe for market in markets):
        raise MarketConfigurationError("Every registered market must be reference-probe enabled")


def register_reference_future(host: object, market: MarketDefinition) -> object:
    """Register one verified reference future on a QCAlgorithm or QuantBook.

    Units: minute resolution; the contract filter is in calendar days to expiry.
    Time semantics: extended-hours behavior follows the explicit market definition.
    Missingness: a missing subscription or continuous symbol raises; no fallback ticker is used.
    Raises: ``MarketConfigurationError``, ``UnverifiedQuantConnectApiError``, or an
    exception emitted by the verified QuantConnect API.
    """

    validate_market_definition(market)
    if market.root not in _REFERENCE_ROOTS or not market.enabled_for_reference_probe:
        raise MarketConfigurationError(f"{market.root} is not a Lift 1 reference market")
    mapping_api, normalization_api, futures, resolution = _load_registration_api()
    qc_host = cast(Any, host)
    subscription = qc_host.add_future(
        _future_constant(market.qc_future_constant_path, futures),
        resolution.MINUTE,
        extended_market_hours=market.extended_market_hours,
        data_mapping_mode=_mapping_mode(market.mapping_mode_name, mapping_api),
        data_normalization_mode=_normalization_mode(
            market.normalization_mode_name, normalization_api
        ),
        contract_depth_offset=0,
    )
    if subscription is None or getattr(subscription, "symbol", None) is None:
        raise UnverifiedQuantConnectApiError("add_future returned no continuous subscription")
    subscription.set_filter(0, market.contract_filter_days)
    return cast(object, subscription)


def register_measurement_future(host: object, market: MarketDefinition) -> object:
    """Register one of the eight verified continuous roots for Lift 2 mapping only.

    Units: minute root resolution and calendar-day expiry filter. Time semantics:
    extended hours, Open Interest mapping, Backwards Ratio normalization, and depth
    zero are explicit. Missingness: an absent subscription/symbol raises. Raises:
    market, API-resolution, or QC runtime errors.
    """

    validate_market_definition(market)
    if market.root not in _MEASUREMENT_ROOTS:
        raise MarketConfigurationError(f"{market.root} is not a Lift 2 measurement market")
    mapping_api, normalization_api, futures, resolution = _load_registration_api()
    qc_host = cast(Any, host)
    subscription = qc_host.add_future(
        _future_constant(market.qc_future_constant_path, futures),
        resolution.MINUTE,
        extended_market_hours=market.extended_market_hours,
        data_mapping_mode=_mapping_mode(market.mapping_mode_name, mapping_api),
        data_normalization_mode=_normalization_mode(
            market.normalization_mode_name,
            normalization_api,
        ),
        contract_depth_offset=0,
    )
    if subscription is None or getattr(subscription, "symbol", None) is None:
        raise UnverifiedQuantConnectApiError("add_future returned no continuous subscription")
    subscription.set_filter(0, market.contract_filter_days)
    return cast(object, subscription)


def register_reference_futures(
    host: object,
    markets: Sequence[MarketDefinition],
) -> Mapping[str, object]:
    """Register exactly ES, ZN, and 6E in caller-supplied deterministic order.

    Units: inherited from each market definition. Time semantics: registrations request
    extended hours explicitly. Missingness: all three markets are mandatory.
    Raises: ``MarketConfigurationError``, ``UnverifiedQuantConnectApiError``, or an
    exception emitted by QuantConnect.
    """

    _require_reference_markets(markets)
    subscriptions = {market.root: register_reference_future(host, market) for market in markets}
    return MappingProxyType(subscriptions)


def register_reference_cftc(host: object) -> Mapping[str, object]:
    """Register the exact TFF market identifiers for ES, ZN, and 6E.

    Units: daily CFTC contracts by trader category. Time semantics: the dataset's
    documented data timezone is Eastern; delivery clocks are measured separately by
    the probe. Missingness: all three subscriptions are returned even if a market has
    no rows in the requested window; no substitute market is used. Raises: verified
    QuantConnect API exceptions or ``UnverifiedQuantConnectApiError``.
    """

    cftc, cftc_financial_futures, resolution = _load_cftc_api()
    market_constants = {
        "ES": cftc.Markets.E_MINI_SP_500,
        "ZN": cftc.Markets.UST_10_Y_NOTE,
        "6E": cftc.Markets.EURO_FX,
    }
    qc_host = cast(Any, host)
    subscriptions: dict[str, object] = {}
    for root in ("ES", "ZN", "6E"):
        security = qc_host.add_data(
            cftc_financial_futures,
            market_constants[root],
            resolution.DAILY,
        )
        symbol = getattr(security, "symbol", None)
        if symbol is None:
            raise UnverifiedQuantConnectApiError(
                f"add_data returned no CFTCFinancialFutures symbol for {root}"
            )
        subscriptions[root] = symbol
    return MappingProxyType(subscriptions)


def configure_quantbook_utc(quantbook: object) -> None:
    """Set the verified QuantBook notebook timezone to UTC.

    Units: not applicable. Time semantics: ``UTC`` is an IANA timezone name accepted by
    ``set_time_zone``. Missingness: a non-QuantBook boundary object raises.
    Raises: ``UnverifiedQuantConnectApiError`` or an exception emitted by QuantConnect.
    """

    setter = getattr(quantbook, "set_time_zone", None)
    if setter is None or not callable(setter):
        raise UnverifiedQuantConnectApiError("QuantBook boundary lacks set_time_zone")
    cast(Any, setter)("UTC")


def _as_naive_quantbook_utc(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise TimeSemanticsError(f"{field_name} must be timezone-aware")
    normalized = value.astimezone(UTC)
    return normalized.replace(tzinfo=None)


def _observed_positive_float(value: object, field_name: str) -> float | None:
    if value is None:
        return None
    observed = float(cast(Any, value))
    if not math.isfinite(observed) or observed <= 0:
        raise DataQualityError(f"QC {field_name} must be finite and positive when present")
    return observed


def _subscription_metadata(subscription: Any) -> Mapping[str, object]:
    symbol = getattr(subscription, "symbol", None)
    properties = getattr(subscription, "symbol_properties", None)
    if symbol is None or properties is None:
        raise UnverifiedQuantConnectApiError("Future lacks symbol or symbol_properties")
    continuous_symbol = str(symbol)
    if not continuous_symbol.strip():
        raise DataQualityError("QC continuous symbol must not be blank")
    return MappingProxyType(
        {
            "continuous_symbol": continuous_symbol,
            "minimum_tick_observed": _observed_positive_float(
                getattr(properties, "minimum_price_variation", None), "minimum tick"
            ),
            "multiplier_observed": _observed_positive_float(
                getattr(properties, "contract_multiplier", None), "contract multiplier"
            ),
        }
    )


def _request_one_history_bundle(
    quantbook: Any,
    subscription: Any,
    start_qc: datetime,
    end_qc: datetime,
    start_utc: datetime,
    end_utc: datetime,
) -> Mapping[str, object]:
    future_universe, resolution, symbol_changed_event, trade_bar = _load_history_api()
    symbol = getattr(subscription, "symbol", None)
    if symbol is None:
        raise UnverifiedQuantConnectApiError("Future subscription lacks symbol")
    metadata = dict(_subscription_metadata(subscription))
    metadata.update(
        {
            "requested_start_utc": start_utc.astimezone(UTC),
            "requested_end_utc": end_utc.astimezone(UTC),
            "chain_history": quantbook.future_history(
                symbol,
                start_qc,
                end_qc,
                resolution.MINUTE,
                fill_forward=False,
                extended_market_hours=True,
            ),
            "continuous_history": quantbook.history(
                trade_bar, symbol, start_qc, end_qc, resolution.MINUTE
            ),
            "mapping_history": quantbook.history(symbol_changed_event, symbol, start_qc, end_qc),
            "universe_history": quantbook.history(
                future_universe, symbol, start_qc, end_qc, flatten=True
            ),
        }
    )
    return MappingProxyType(metadata)


def request_quantbook_histories(
    quantbook: object,
    subscriptions: Mapping[str, object],
    start_utc: datetime,
    end_utc: datetime,
) -> Mapping[str, object]:
    """Request verified chain, continuous, mapping, and daily-universe histories.

    Units: minute trade/chain rows and daily universe/open-interest rows.
    Time semantics: inputs must be aware; they are preserved in the returned bundle and
    converted to naive UTC only for the documented QuantBook overload boundary. The
    QuantBook analysis clock is capped at ``end_utc``. Missingness: every reference
    subscription is mandatory; empty QC results remain empty objects.
    Raises: ``TimeSemanticsError``, ``DataTimingInvariantError``,
    ``MarketConfigurationError``, ``UnverifiedQuantConnectApiError``, or a QC error.
    """

    if set(subscriptions) != _REFERENCE_ROOTS or len(subscriptions) != 3:
        raise MarketConfigurationError("History requires ES, ZN, and 6E subscriptions")
    start_qc = _as_naive_quantbook_utc(start_utc, "start_utc")
    end_qc = _as_naive_quantbook_utc(end_utc, "end_utc")
    if start_qc >= end_qc:
        raise DataTimingInvariantError("QuantBook history start must precede end")
    configure_quantbook_utc(quantbook)
    qc_book = cast(Any, quantbook)
    qc_book.set_start_date(end_qc)
    bundles = {
        root: _request_one_history_bundle(
            qc_book, subscription, start_qc, end_qc, start_utc, end_utc
        )
        for root, subscription in subscriptions.items()
    }
    return MappingProxyType(bundles)


__all__ = (
    "configure_quantbook_utc",
    "register_measurement_future",
    "register_reference_cftc",
    "register_reference_future",
    "register_reference_futures",
    "request_quantbook_histories",
)

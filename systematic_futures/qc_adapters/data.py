from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from datetime import UTC, date, datetime
from typing import Any, cast
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from systematic_futures.domain.enums import RollState
from systematic_futures.domain.errors import (
    ContractBoundaryError,
    DataQualityError,
    TimeSemanticsError,
    UnverifiedQuantConnectApiError,
)
from systematic_futures.domain.serialization import sha256_hex
from systematic_futures.measurement.structural_inputs import (
    ContinuousBarObservation,
    ContractCurveObservation,
    QuoteObservation,
)


def _qc_datetime_to_utc(
    value: object,
    field_name: str,
    *,
    naive_source_timezone: str | None = None,
) -> datetime:
    if not isinstance(value, datetime):
        raise TimeSemanticsError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        if naive_source_timezone is None or not naive_source_timezone.strip():
            raise TimeSemanticsError(
                f"{field_name} is naive and requires an explicit source timezone"
            )
        try:
            source_zone = ZoneInfo(naive_source_timezone)
        except ZoneInfoNotFoundError as error:
            raise TimeSemanticsError(
                f"{field_name} source timezone is not resolvable: {naive_source_timezone}"
            ) from error
        return value.replace(tzinfo=source_zone).astimezone(UTC)
    return value.astimezone(UTC)


def continuous_bar_from_slice(
    *,
    root: str,
    continuous_symbol: object,
    mapped_contract: object,
    qc_slice: object,
    observed_at_utc: datetime,
    session_id: str,
    session_start_utc: datetime,
    session_end_utc: datetime,
    roll_state: RollState,
) -> ContinuousBarObservation | None:
    """Adapt one QC continuous TradeBar without treating it as executable price truth.

    QuantConnect documents the continuous symbol price as adjusted and the mapped symbol
    price as raw. This adapter therefore marks the observation as continuous-series data;
    actual-contract Profile, labels, and execution must use separate records.
    """

    data = cast(Any, qc_slice)
    bars = getattr(data, "bars", None)
    if bars is None:
        return None
    bar = bars.get(continuous_symbol)
    if bar is None:
        return None
    start_utc = _qc_datetime_to_utc(
        getattr(bar, "time", None),
        "continuous TradeBar.time",
        naive_source_timezone="UTC",
    )
    end_utc = _qc_datetime_to_utc(
        getattr(bar, "end_time", None),
        "continuous TradeBar.end_time",
        naive_source_timezone="UTC",
    )
    period_seconds = (end_utc - start_utc).total_seconds()
    if period_seconds <= 0 or period_seconds % 60 != 0:
        raise UnverifiedQuantConnectApiError(
            "continuous TradeBar duration must be a positive whole number of minutes"
        )
    values = _required_numeric_fields(
        bar,
        ("open", "high", "low", "close", "volume"),
        "continuous TradeBar",
    )
    mapped_text = str(mapped_contract).strip()
    continuous_text = str(continuous_symbol).strip()
    if not mapped_text or not continuous_text:
        raise ContractBoundaryError("continuous and mapped contract identities must be present")
    lineage = sha256_hex(
        {
            "source": "QuantConnect.Slice.bars",
            "root": root,
            "continuous_symbol": continuous_text,
            "mapped_contract": mapped_text,
            "start_utc": start_utc,
            "end_utc": end_utc,
            "available_at_utc": observed_at_utc,
            "ohlcv": values,
        }
    )
    return ContinuousBarObservation(
        root=root,
        continuous_symbol=continuous_text,
        mapped_contract=mapped_text,
        session_id=session_id,
        period_minutes=int(period_seconds // 60),
        start_utc=start_utc,
        end_utc=end_utc,
        available_at_utc=observed_at_utc,
        session_start_utc=session_start_utc,
        session_end_utc=session_end_utc,
        open=values["open"],
        high=values["high"],
        low=values["low"],
        close=values["close"],
        volume=values["volume"],
        roll_state=roll_state,
        source_lineage_hash=lineage,
    )


def latest_quote_from_ticks(
    *,
    root: str,
    actual_contract: object,
    ticks: Iterable[object],
    quote_tick_type: object,
    observed_at_utc: datetime,
    minimum_tick: float,
) -> QuoteObservation | None:
    """Return the latest complete two-sided actual-contract quote in delivery order.

    One-sided quotes are skipped because spread and imbalance are undefined. Crossed quotes
    fail closed. Equal event timestamps preserve the order delivered by LEAN.
    """

    contract_text = str(actual_contract).strip()
    if not contract_text:
        raise ContractBoundaryError("actual contract identity must be present")
    latest: QuoteObservation | None = None
    for tick in ticks:
        if getattr(tick, "tick_type", None) != quote_tick_type:
            continue
        if not all(hasattr(tick, name) for name in ("bid_price", "ask_price")):
            raise UnverifiedQuantConnectApiError("quote Tick lacks bid_price/ask_price")
        bid_price = float(tick.bid_price)
        ask_price = float(tick.ask_price)
        if bid_price <= 0 or ask_price <= 0:
            continue
        bid_size = _optional_non_negative_float(getattr(tick, "bid_size", None), "bid_size")
        ask_size = _optional_non_negative_float(getattr(tick, "ask_size", None), "ask_size")
        event_time = _qc_datetime_to_utc(
            getattr(tick, "end_time", None),
            "quote Tick.end_time",
            naive_source_timezone="UTC",
        )
        lineage = sha256_hex(
            {
                "source": "QuantConnect.Slice.ticks.quote",
                "root": root,
                "actual_contract": contract_text,
                "event_time_utc": event_time,
                "available_at_utc": observed_at_utc,
                "bid_price": bid_price,
                "ask_price": ask_price,
                "bid_size": bid_size,
                "ask_size": ask_size,
            }
        )
        candidate = QuoteObservation(
            root=root,
            actual_contract=contract_text,
            event_time_utc=event_time,
            available_at_utc=observed_at_utc,
            bid_price=bid_price,
            ask_price=ask_price,
            bid_size=bid_size,
            ask_size=ask_size,
            minimum_tick=minimum_tick,
            source_lineage_hash=lineage,
        )
        if latest is None or candidate.event_time_utc >= latest.event_time_utc:
            latest = candidate
    return latest


def curve_observation_from_chain(
    *,
    root: str,
    continuous_symbol: object,
    mapped_contract: object,
    future_chain: object,
    observed_at_utc: datetime,
) -> ContractCurveObservation | None:
    """Adapt the mapped and nearest later-expiry contracts from one QC FutureChain.

    Open interest is copied as observed context. QuantConnect documents Futures open
    interest as a daily measure; it is not treated as intraday event flow.
    """

    continuous_text = str(continuous_symbol).strip()
    mapped_text = str(mapped_contract).strip()
    if not continuous_text or not mapped_text:
        raise ContractBoundaryError("continuous and mapped identities must be present")
    contracts_object = getattr(future_chain, "contracts", None)
    if contracts_object is None:
        raise UnverifiedQuantConnectApiError("FutureChain lacks contracts")
    if isinstance(contracts_object, Mapping):
        contracts = tuple(cast(Mapping[object, object], contracts_object).values())
    else:
        values = getattr(contracts_object, "values", None)
        if values is None or not callable(values):
            raise UnverifiedQuantConnectApiError("FutureChain.contracts lacks values()")
        contracts = tuple(cast(Iterable[object], values()))
    parsed: list[tuple[str, date, float, float | None]] = []
    for contract in contracts:
        symbol = str(getattr(contract, "symbol", "")).strip()
        if not symbol:
            continue
        expiry = _contract_expiry_date(getattr(contract, "expiry", None))
        last_price = _positive_or_none(getattr(contract, "last_price", None))
        if last_price is None:
            continue
        open_interest = _optional_non_negative_float(
            getattr(contract, "open_interest", None),
            "open_interest",
        )
        parsed.append((symbol, expiry, last_price, open_interest))
    mapped_rows = [row for row in parsed if row[0] == mapped_text]
    if len(mapped_rows) != 1:
        return None
    mapped_row = mapped_rows[0]
    later_rows = sorted((row for row in parsed if row[1] > mapped_row[1]), key=lambda row: row[1])
    if not later_rows:
        return None
    next_row = later_rows[0]
    lineage = sha256_hex(
        {
            "source": "QuantConnect.FutureChain.contracts",
            "root": root,
            "continuous_symbol": continuous_text,
            "mapped": mapped_row,
            "next": next_row,
            "event_time_utc": observed_at_utc,
        }
    )
    return ContractCurveObservation(
        root=root,
        continuous_symbol=continuous_text,
        mapped_contract=mapped_row[0],
        next_contract=next_row[0],
        mapped_expiry=mapped_row[1],
        next_expiry=next_row[1],
        mapped_price=mapped_row[2],
        next_price=next_row[2],
        mapped_open_interest=mapped_row[3],
        next_open_interest=next_row[3],
        event_time_utc=observed_at_utc,
        available_at_utc=observed_at_utc,
        source_lineage_hash=lineage,
    )


def _required_numeric_fields(
    value: object,
    field_names: tuple[str, ...],
    object_name: str,
) -> dict[str, float]:
    result: dict[str, float] = {}
    for field_name in field_names:
        if not hasattr(value, field_name):
            raise UnverifiedQuantConnectApiError(f"{object_name} lacks {field_name}")
        numeric = float(getattr(value, field_name))
        if not math.isfinite(numeric):
            raise DataQualityError(f"{object_name}.{field_name} must be finite")
        result[field_name] = numeric
    return result


def _optional_non_negative_float(value: object, field_name: str) -> float | None:
    if value is None:
        return None
    numeric = float(value)
    if not math.isfinite(numeric) or numeric < 0:
        raise DataQualityError(f"{field_name} must be finite and non-negative")
    return numeric


def _positive_or_none(value: object) -> float | None:
    if value is None:
        return None
    numeric = float(value)
    if not math.isfinite(numeric) or numeric <= 0:
        return None
    return numeric


def _contract_expiry_date(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raise UnverifiedQuantConnectApiError("FutureContract.expiry must be a date or datetime")


__all__ = (
    "continuous_bar_from_slice",
    "curve_observation_from_chain",
    "latest_quote_from_ticks",
)

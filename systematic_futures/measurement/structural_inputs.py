# pyright: reportUnnecessaryIsInstance=false
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from systematic_futures.domain.enums import RollState
from systematic_futures.domain.errors import (
    ContractBoundaryError,
    DataQualityError,
    DataTimingInvariantError,
    TimeSemanticsError,
)

_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


def _require_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise DataQualityError(f"{field_name} must be a non-blank string")


def _require_utc(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise TimeSemanticsError(f"{field_name} must be timezone-aware")
    if value.utcoffset() != timedelta(0):
        raise TimeSemanticsError(f"{field_name} must be normalized to UTC")


def _require_positive(value: float, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise DataQualityError(f"{field_name} must be a finite positive number")
    if not math.isfinite(value) or value <= 0:
        raise DataQualityError(f"{field_name} must be a finite positive number")


def _require_non_negative_optional(value: float | None, field_name: str) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise DataQualityError(f"{field_name} must be a finite non-negative number")
    if not math.isfinite(value) or value < 0:
        raise DataQualityError(f"{field_name} must be a finite non-negative number")


def _require_flags(flags: tuple[str, ...]) -> None:
    if not isinstance(flags, tuple):
        raise DataQualityError("quality_flags must be a tuple")
    if flags != tuple(sorted(set(flags))):
        raise DataQualityError("quality_flags must be sorted and unique")
    for flag in flags:
        _require_text(flag, "quality_flag")


def _require_hash(value: str, field_name: str) -> None:
    if not isinstance(value, str) or _SHA256_PATTERN.fullmatch(value) is None:
        raise DataQualityError(f"{field_name} must be a lowercase SHA-256 digest")


@dataclass(frozen=True, slots=True)
class ContinuousBarObservation:
    """One completed continuous-series bar with explicit session and mapping identity.

    Prices are normalized continuous-series prices and MUST NOT be interpreted as executable
    actual-contract prices. The bar is usable only at ``available_at_utc``.
    """

    root: str
    continuous_symbol: str
    mapped_contract: str
    session_id: str
    period_minutes: int
    start_utc: datetime
    end_utc: datetime
    available_at_utc: datetime
    session_start_utc: datetime
    session_end_utc: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    roll_state: RollState
    source_lineage_hash: str
    quality_flags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for field_name, value in (
            ("root", self.root),
            ("continuous_symbol", self.continuous_symbol),
            ("mapped_contract", self.mapped_contract),
            ("session_id", self.session_id),
        ):
            _require_text(value, field_name)
        if type(self.period_minutes) is not int or self.period_minutes <= 0:
            raise DataQualityError("period_minutes must be a positive integer")
        for field_name, value in (
            ("start_utc", self.start_utc),
            ("end_utc", self.end_utc),
            ("available_at_utc", self.available_at_utc),
            ("session_start_utc", self.session_start_utc),
            ("session_end_utc", self.session_end_utc),
        ):
            _require_utc(value, field_name)
        if not self.start_utc < self.end_utc <= self.available_at_utc:
            raise DataTimingInvariantError("bar clocks must satisfy start < end <= available")
        if self.end_utc - self.start_utc != timedelta(minutes=self.period_minutes):
            raise DataTimingInvariantError("bar duration must equal period_minutes")
        if not self.session_start_utc <= self.start_utc < self.end_utc <= self.session_end_utc:
            raise DataTimingInvariantError(
                "continuous bar must be contained in its semantic session"
            )
        for field_name, value in (
            ("open", self.open),
            ("high", self.high),
            ("low", self.low),
            ("close", self.close),
        ):
            _require_positive(value, field_name)
        if not self.low <= self.open <= self.high or not self.low <= self.close <= self.high:
            raise DataQualityError("continuous bar OHLC values are inconsistent")
        if isinstance(self.volume, bool) or not isinstance(self.volume, int | float):
            raise DataQualityError("volume must be a finite non-negative number")
        if not math.isfinite(self.volume) or self.volume < 0:
            raise DataQualityError("volume must be a finite non-negative number")
        if not isinstance(self.roll_state, RollState):
            raise DataQualityError("roll_state must be a RollState")
        _require_hash(self.source_lineage_hash, "source_lineage_hash")
        _require_flags(self.quality_flags)


@dataclass(frozen=True, slots=True)
class ContinuousSessionCloseObservation:
    """One completed semantic-session close of a continuous normalized series."""

    root: str
    continuous_symbol: str
    mapped_contract: str
    session_id: str
    session_end_utc: datetime
    available_at_utc: datetime
    close: float
    roll_state: RollState
    source_lineage_hashes: tuple[str, ...]
    quality_flags: tuple[str, ...]

    def __post_init__(self) -> None:
        for field_name, value in (
            ("root", self.root),
            ("continuous_symbol", self.continuous_symbol),
            ("mapped_contract", self.mapped_contract),
            ("session_id", self.session_id),
        ):
            _require_text(value, field_name)
        _require_utc(self.session_end_utc, "session_end_utc")
        _require_utc(self.available_at_utc, "available_at_utc")
        if self.session_end_utc > self.available_at_utc:
            raise DataTimingInvariantError("session close cannot be available before session end")
        _require_positive(self.close, "close")
        if not isinstance(self.roll_state, RollState):
            raise DataQualityError("roll_state must be a RollState")
        if not self.source_lineage_hashes:
            raise DataQualityError("source_lineage_hashes must not be empty")
        for index, value in enumerate(self.source_lineage_hashes):
            _require_hash(value, f"source_lineage_hashes[{index}]")
        _require_flags(self.quality_flags)


@dataclass(frozen=True, slots=True)
class QuoteObservation:
    """One two-sided top-of-book actual-contract quote.

    Prices are native actual-contract prices. Sizes are displayed top-of-book quantities,
    not full-depth liquidity. Crossed quotes are rejected rather than repaired.
    """

    root: str
    actual_contract: str
    event_time_utc: datetime
    available_at_utc: datetime
    bid_price: float
    ask_price: float
    bid_size: float | None
    ask_size: float | None
    minimum_tick: float
    source_lineage_hash: str
    quality_flags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.root, "root")
        _require_text(self.actual_contract, "actual_contract")
        _require_utc(self.event_time_utc, "event_time_utc")
        _require_utc(self.available_at_utc, "available_at_utc")
        if self.event_time_utc > self.available_at_utc:
            raise DataTimingInvariantError("quote event time cannot exceed availability")
        _require_positive(self.bid_price, "bid_price")
        _require_positive(self.ask_price, "ask_price")
        _require_positive(self.minimum_tick, "minimum_tick")
        if self.bid_price > self.ask_price:
            raise DataQualityError("crossed quote is not a valid top-of-book observation")
        _require_non_negative_optional(self.bid_size, "bid_size")
        _require_non_negative_optional(self.ask_size, "ask_size")
        _require_hash(self.source_lineage_hash, "source_lineage_hash")
        _require_flags(self.quality_flags)

    @property
    def mid_price(self) -> float:
        """Return the native-price quote midpoint."""

        return 0.5 * (self.bid_price + self.ask_price)

    @property
    def spread_ticks(self) -> float:
        """Return the top-of-book spread in minimum-tick units."""

        return (self.ask_price - self.bid_price) / self.minimum_tick

    @property
    def top_depth_imbalance(self) -> float | None:
        """Return (bid_size-ask_size)/(bid_size+ask_size) when both sizes are usable."""

        if self.bid_size is None or self.ask_size is None:
            return None
        total = self.bid_size + self.ask_size
        if total <= 0:
            return None
        return (self.bid_size - self.ask_size) / total


@dataclass(frozen=True, slots=True)
class ContractCurveObservation:
    """Mapped-contract versus nearest later-expiry actual-contract curve observation.

    The mapped contract is the explicit reference leg. It is not assumed to be the calendar
    front month when Open-Interest mapping selects another contract.
    """

    root: str
    continuous_symbol: str
    mapped_contract: str
    next_contract: str
    mapped_expiry: date
    next_expiry: date
    mapped_price: float
    next_price: float
    mapped_open_interest: float | None
    next_open_interest: float | None
    event_time_utc: datetime
    available_at_utc: datetime
    source_lineage_hash: str
    quality_flags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for field_name, value in (
            ("root", self.root),
            ("continuous_symbol", self.continuous_symbol),
            ("mapped_contract", self.mapped_contract),
            ("next_contract", self.next_contract),
        ):
            _require_text(value, field_name)
        if self.mapped_contract == self.next_contract:
            raise ContractBoundaryError("curve legs must be distinct actual contracts")
        if self.next_expiry <= self.mapped_expiry:
            raise ContractBoundaryError("next contract expiry must follow mapped contract expiry")
        _require_positive(self.mapped_price, "mapped_price")
        _require_positive(self.next_price, "next_price")
        _require_non_negative_optional(self.mapped_open_interest, "mapped_open_interest")
        _require_non_negative_optional(self.next_open_interest, "next_open_interest")
        _require_utc(self.event_time_utc, "event_time_utc")
        _require_utc(self.available_at_utc, "available_at_utc")
        if self.event_time_utc > self.available_at_utc:
            raise DataTimingInvariantError("curve event time cannot exceed availability")
        _require_hash(self.source_lineage_hash, "source_lineage_hash")
        _require_flags(self.quality_flags)

    @property
    def tenor_years(self) -> float:
        """Return calendar time between mapped and next expiries in ACT/365.25 years."""

        return (self.next_expiry - self.mapped_expiry).days / 365.25

    @property
    def annualized_curve_carry(self) -> float:
        """Return log(mapped_price/next_price) annualized by expiry distance."""

        return math.log(self.mapped_price / self.next_price) / self.tenor_years

    @property
    def front_next_log_spread(self) -> float:
        """Return log(mapped_price/next_price) without annualization."""

        return math.log(self.mapped_price / self.next_price)


__all__ = (
    "ContinuousBarObservation",
    "ContinuousSessionCloseObservation",
    "ContractCurveObservation",
    "QuoteObservation",
)

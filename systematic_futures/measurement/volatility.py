from __future__ import annotations

import math
from collections import deque
from datetime import datetime

from systematic_futures.domain.errors import (
    ContractBoundaryError,
    DataQualityError,
    DataTimingInvariantError,
)
from systematic_futures.measurement.models import ATRMeasurement, CompletedTradeBar

ATR_5M_24_VERSION = "atr_5m_24_arithmetic_tr_v1"
_WINDOW = 24


def true_range(bar: CompletedTradeBar, previous_close: float) -> float:
    """Return one five-minute true range in native price units.

    Time semantics: ``previous_close`` must be the immediately preceding completed
    same-contract bar close, established by the caller. Missingness: no fallback is
    permitted. Raises: ``DataQualityError`` for a non-five-minute bar or invalid close.
    """

    if bar.period_minutes != 5:
        raise DataQualityError("true range requires a completed five-minute bar")
    if not math.isfinite(previous_close) or previous_close <= 0:
        raise DataQualityError("previous_close must be finite and positive")
    value = max(
        bar.high - bar.low,
        abs(bar.high - previous_close),
        abs(bar.low - previous_close),
    )
    if not math.isfinite(value) or value < 0:
        raise DataQualityError("true range produced an invalid value")
    return value


class ATR5m24:
    """Causal contract-local arithmetic mean of the last 24 five-minute true ranges."""

    def __init__(self, root: str, contract_symbol: str) -> None:
        """Create empty state for one actual contract.

        Units: native price. Time semantics: completed bars must be strictly ordered.
        Missingness: the first bar establishes the prior close and contributes no true
        range. Raises: ``DataQualityError`` for blank identity.
        """

        if not root.strip() or not contract_symbol.strip():
            raise DataQualityError("ATR identity must be non-blank")
        self.root = root
        self.contract_symbol = contract_symbol
        self._ranges: deque[float] = deque(maxlen=_WINDOW)
        self._previous_close: float | None = None
        self._last_bar_end: datetime | None = None

    def on_bar(self, bar: CompletedTradeBar) -> ATRMeasurement:
        """Advance with one completed bar and return the point-in-time ATR state.

        The exposed value is withheld until exactly 24 prior-defined true ranges are
        available. Contract/session gaps are retained as true range by definition;
        actual-contract changes require a new instance.
        """

        if bar.root != self.root or bar.contract_symbol != self.contract_symbol:
            raise ContractBoundaryError("ATR cannot cross actual-contract identity")
        if bar.period_minutes != 5:
            raise DataQualityError("ATR requires completed five-minute bars")
        if self._last_bar_end is not None and bar.end_utc <= self._last_bar_end:
            raise DataTimingInvariantError("ATR bars must arrive in increasing end-time order")
        if self._previous_close is not None:
            value = true_range(bar, self._previous_close)
            if value <= 0:
                raise DataQualityError("ATR true range must be positive")
            self._ranges.append(value)
        self._previous_close = bar.close
        self._last_bar_end = bar.end_utc
        observation_count = len(self._ranges)
        ready = observation_count == _WINDOW
        atr = sum(self._ranges) / _WINDOW if ready else None
        return ATRMeasurement(
            root=self.root,
            contract_symbol=self.contract_symbol,
            as_of_utc=bar.end_utc,
            available_at_utc=bar.available_at_utc,
            value=atr,
            observation_count=observation_count,
            warmup_complete=ready,
            version=ATR_5M_24_VERSION,
        )


__all__ = ("ATR_5M_24_VERSION", "ATR5m24", "true_range")

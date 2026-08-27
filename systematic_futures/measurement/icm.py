from __future__ import annotations

import math
from collections import deque
from datetime import datetime

import numpy as np

from systematic_futures.config.research import ICM_WINDOWS
from systematic_futures.domain.errors import (
    ContractBoundaryError,
    DataQualityError,
    DataTimingInvariantError,
    MarketConfigurationError,
)
from systematic_futures.domain.serialization import sha256_hex
from systematic_futures.measurement.models import CompletedTradeBar, ICMStateSnapshot

_VERSION = "icm_quadratic_geometry_v1"
_EPSILON = 1e-12


class ICMEngine:
    """Bounded causal quadratic price-geometry engine for one actual contract."""

    def __init__(self, root: str, contract_symbol: str) -> None:
        """Create an empty engine with the root's frozen provisional window.

        Units: the window is completed 30m bars. Time semantics: no bar from a prior
        contract is retained. Missingness: unsupported roots and blank contracts are
        rejected. Raises: ``MarketConfigurationError`` or ``DataQualityError``.
        """

        if root not in ICM_WINDOWS:
            raise MarketConfigurationError(f"no frozen ICM window for {root!r}")
        if not contract_symbol.strip():
            raise DataQualityError("ICM contract_symbol must be non-blank")
        self.root = root
        self.contract_symbol = contract_symbol
        self.window_size = ICM_WINDOWS[root]
        self._bars: deque[CompletedTradeBar] = deque(maxlen=self.window_size)
        self._last_bar_end: datetime | None = None
        self.last_quality_flags: tuple[str, ...] = ("ICM_WINDOW_WARMUP",)
        self.degenerate_count = 0

    @property
    def bar_count(self) -> int:
        """Return the bounded number of completed bars currently retained."""

        return len(self._bars)

    def on_bar(self, bar: CompletedTradeBar) -> ICMStateSnapshot | None:
        """Update with one completed 30m bar and emit valid full-window geometry.

        Units: fair value/scales are native price; normalized fields are residual-scale
        units. Time semantics: only the current and preceding completed bars enter the
        fit. Missingness: warmup or degenerate residual scale returns ``None`` with an
        explicit `last_quality_flags` state. Raises: boundary, ordering, or numerical
        input errors.
        """

        if bar.root != self.root or bar.contract_symbol != self.contract_symbol:
            raise ContractBoundaryError("ICM cannot cross actual-contract identity")
        if bar.period_minutes != 30:
            raise DataQualityError("ICM requires completed 30m bars")
        if self._last_bar_end is not None and bar.end_utc <= self._last_bar_end:
            raise DataTimingInvariantError("ICM bars must arrive in increasing end-time order")
        self._last_bar_end = bar.end_utc
        self._bars.append(bar)
        if len(self._bars) < self.window_size:
            self.last_quality_flags = ("ICM_WINDOW_WARMUP",)
            return None
        prices = tuple(item.close for item in self._bars)
        beta0, beta1, beta2, sigma_ols, sigma_mad = fit_quadratic_geometry(prices)
        sigma_blend = 0.5 * sigma_ols + 0.5 * sigma_mad
        if not math.isfinite(sigma_blend) or sigma_blend <= _EPSILON:
            self.last_quality_flags = ("ICM_DEGENERATE_SCALE",)
            self.degenerate_count += 1
            return None
        fair_value = float(beta0)
        z_score = (float(prices[-1]) - fair_value) / sigma_blend
        slope_raw = float(beta1)
        curvature_raw = 2.0 * float(beta2)
        r_ratio = sigma_ols / max(sigma_mad, _EPSILON)
        self.last_quality_flags = ()
        identity = {
            "as_of_utc": bar.end_utc,
            "coefficients": (beta0, beta1, beta2),
            "contract_symbol": self.contract_symbol,
            "root": self.root,
            "sigma_blend": sigma_blend,
            "version": _VERSION,
            "window_size": self.window_size,
        }
        return ICMStateSnapshot(
            snapshot_id=f"icm_{sha256_hex(identity)}",
            root=self.root,
            contract_symbol=self.contract_symbol,
            as_of_utc=bar.end_utc,
            available_at_utc=bar.available_at_utc,
            fair_value=fair_value,
            z_score=z_score,
            slope_raw=slope_raw,
            slope_norm=slope_raw / sigma_blend,
            curvature_raw=curvature_raw,
            curvature_norm=curvature_raw / sigma_blend,
            sigma_ols=sigma_ols,
            sigma_mad=sigma_mad,
            sigma_blend=sigma_blend,
            r_ratio=r_ratio,
            window_size=self.window_size,
            warmup_complete=True,
            quality_flags=(),
            version=_VERSION,
        )


def fit_quadratic_geometry(
    prices: tuple[float, ...],
) -> tuple[float, float, float, float, float]:
    """Fit the frozen scaled quadratic and return coefficients plus OLS/MAD scales.

    Units: coefficients and residual scales inherit native price units under
    `tau in [-1, 0]`. Time semantics: tuple order is oldest to newest and no other
    observations are read. Missingness: at least four finite prices are required.
    Raises: ``DataQualityError`` for invalid values or insufficient length.
    """

    if len(prices) <= 3 or any(not math.isfinite(price) or price <= 0 for price in prices):
        raise DataQualityError("quadratic geometry requires at least four positive prices")
    values = np.asarray(prices, dtype=np.float64)
    tau = np.linspace(-1.0, 0.0, len(prices), dtype=np.float64)
    design = np.column_stack((np.ones(len(prices)), tau, tau**2))
    coefficients, _, _, _ = np.linalg.lstsq(design, values, rcond=None)
    beta0, beta1, beta2 = (float(value) for value in coefficients)
    residuals = values - design @ coefficients
    sigma_ols = math.sqrt(float(np.sum(residuals**2)) / (len(prices) - 3))
    residual_median = float(np.median(residuals))
    sigma_mad = 1.4826 * float(np.median(np.abs(residuals - residual_median)))
    return beta0, beta1, beta2, sigma_ols, sigma_mad


__all__ = ("ICMEngine", "fit_quadratic_geometry")

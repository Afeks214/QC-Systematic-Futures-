from __future__ import annotations

# pyright: reportUnnecessaryIsInstance=false
import math
from collections import deque
from datetime import datetime

import numpy as np
import numpy.typing as npt

from systematic_futures.config.research import ICM_WINDOWS, MEASUREMENT_CLOCK_POLICY
from systematic_futures.domain.errors import (
    ContractBoundaryError,
    DataQualityError,
    DataTimingInvariantError,
    MarketConfigurationError,
)
from systematic_futures.domain.serialization import sha256_hex
from systematic_futures.measurement.models import CompletedTradeBar, ICMStateSnapshot, PriceScale

_VERSION = "icm_quadratic_geometry_math_v3|pinv_solver_v1"
_EPSILON = 1e-12
_Z_CAP = 4.5
_REGIME_RATIO_MAXIMUM = 1.5


class ICMEngine:
    """Causal quadratic price geometry with frozen per-root pseudoinverse."""

    def __init__(self, root: str, contract_symbol: str) -> None:
        """Create an empty actual-contract state and precompute its OLS solver.

        Units: the root window is completed 30-minute bars. Time semantics: no prior
        contract state is retained. Missingness: unsupported roots are rejected.
        """

        if root not in ICM_WINDOWS:
            raise MarketConfigurationError(f"no frozen ICM window for {root!r}")
        if not contract_symbol.strip():
            raise DataQualityError("ICM contract_symbol must be non-blank")
        self.root = root
        self.contract_symbol = contract_symbol
        self.window_size = ICM_WINDOWS[root]
        self._design = quadratic_design(self.window_size)
        self._pseudoinverse = np.asarray(np.linalg.pinv(self._design), dtype=np.float64)
        self._bars: deque[CompletedTradeBar] = deque(maxlen=self.window_size)
        self._last_bar_end: datetime | None = None
        self.last_quality_flags: tuple[str, ...] = ("ICM_WINDOW_WARMUP",)
        self.degenerate_count = 0

    @property
    def bar_count(self) -> int:
        """Return the bounded number of completed bars retained."""

        return len(self._bars)

    def on_bar(
        self,
        bar: CompletedTradeBar,
        local_price_scale: PriceScale | None = None,
    ) -> ICMStateSnapshot | None:
        """Update one completed 30-minute bar and emit full-window geometry.

        Public derivatives are native price per bar and native price per bar squared.
        The current bar is the final row at normalized coordinate zero. A full-window
        flat or unstable fit still emits its auditable raw state with effective Z
        withheld and explicit guard flags.
        """

        self._validate_bar(bar)
        self._last_bar_end = bar.end_utc
        self._bars.append(bar)
        if len(self._bars) < self.window_size:
            self.last_quality_flags = ("ICM_WINDOW_WARMUP",)
            return None

        prices = np.asarray([item.close for item in self._bars], dtype=np.float64)
        beta0, beta1, beta2, sigma_ols, sigma_mad = _fit_with_matrix(
            prices,
            self._design,
            self._pseudoinverse,
        )
        sigma_blend = 0.5 * sigma_ols + 0.5 * sigma_mad
        r_ratio = sigma_ols / (sigma_mad + _EPSILON)
        fair_value = beta0
        scale_factor = float(self.window_size - 1)
        slope_per_bar = beta1 / scale_factor
        curvature_per_bar2 = 2.0 * beta2 / (scale_factor**2)

        coefficients = np.asarray((beta0, beta1, beta2), dtype=np.float64)
        residuals = np.asarray(prices - self._design @ coefficients, dtype=np.float64)
        residual_autocorrelation = _lag_one_autocorrelation(residuals)
        flags: set[str] = set()
        blocking_guard = False
        if sigma_blend <= _EPSILON:
            flags.add("ICM_FLAT_SCALE_GUARD")
            self.degenerate_count += 1
            blocking_guard = True
        if r_ratio > _REGIME_RATIO_MAXIMUM:
            flags.add("ICM_REGIME_GUARD")
            blocking_guard = True
        if residual_autocorrelation is None:
            flags.add("ICM_RESIDUAL_AUTOCORRELATION_DEGENERATE")
        if local_price_scale is None or not local_price_scale.warmup_complete:
            fair_value_distance_vol = None
            flags.add("ICM_LOCAL_SCALE_UNAVAILABLE")
        else:
            if local_price_scale.value is None:
                raise DataQualityError("warmed ICM local price scale has no value")
            fair_value_distance_vol = (float(prices[-1]) - fair_value) / local_price_scale.value
        if sigma_blend > 0.0:
            slope_normalized = slope_per_bar / sigma_blend
            curvature_normalized = curvature_per_bar2 / sigma_blend
        else:
            slope_normalized = None
            curvature_normalized = None
        if sigma_blend > _EPSILON:
            z_raw = (float(prices[-1]) - fair_value) / (sigma_blend + _EPSILON)
            z_capped = min(_Z_CAP, max(-_Z_CAP, z_raw))
        else:
            z_raw = None
            z_capped = None
        z_effective = z_capped if z_capped is not None and not blocking_guard else None
        self.last_quality_flags = tuple(sorted(flags))
        identity = {
            "as_of_utc": bar.end_utc,
            "coefficients": (beta0, beta1, beta2),
            "contract_symbol": self.contract_symbol,
            "curvature_per_bar2": curvature_per_bar2,
            "quality_flags": self.last_quality_flags,
            "root": self.root,
            "session_id": bar.session_id,
            "fair_value_distance_vol": fair_value_distance_vol,
            "residual_autocorrelation": residual_autocorrelation,
            "sigma_blend": sigma_blend,
            "slope_per_bar": slope_per_bar,
            "version": _VERSION,
            "window_size": self.window_size,
            "z_capped": z_capped,
            "z_effective": z_effective,
            "z_raw": z_raw,
        }
        return ICMStateSnapshot(
            snapshot_id=f"icm_{sha256_hex(identity)}",
            root=self.root,
            contract_symbol=self.contract_symbol,
            session_id=bar.session_id,
            as_of_utc=bar.end_utc,
            available_at_utc=bar.available_at_utc,
            fair_value=fair_value,
            z_raw=z_raw,
            z_capped=z_capped,
            z_effective=z_effective,
            slope_per_bar=slope_per_bar,
            slope_normalized=slope_normalized,
            curvature_per_bar2=curvature_per_bar2,
            curvature_normalized=curvature_normalized,
            sigma_ols=sigma_ols,
            sigma_mad=sigma_mad,
            sigma_blend=sigma_blend,
            r_ratio=r_ratio,
            fair_value_distance_vol=fair_value_distance_vol,
            residual_autocorrelation=residual_autocorrelation,
            window_size=self.window_size,
            warmup_complete=True,
            measurement_ready=z_effective is not None,
            quality_flags=self.last_quality_flags,
            version=_VERSION,
        )

    def _validate_bar(self, bar: CompletedTradeBar) -> None:
        if bar.root != self.root or bar.contract_symbol != self.contract_symbol:
            raise ContractBoundaryError("ICM cannot cross actual-contract identity")
        if bar.period_minutes != MEASUREMENT_CLOCK_POLICY.medium_state_bar_minutes:
            raise DataQualityError("ICM requires completed medium-state bars")
        if self._last_bar_end is not None and bar.end_utc <= self._last_bar_end:
            raise DataTimingInvariantError("ICM bars must arrive in increasing end-time order")


def quadratic_design(window_size: int) -> npt.NDArray[np.float64]:
    """Return the frozen oldest-minus-one/current-zero quadratic design matrix."""

    if isinstance(window_size, bool) or not isinstance(window_size, int) or window_size <= 3:
        raise DataQualityError("quadratic window_size must be an integer greater than three")
    index = np.arange(window_size, dtype=np.float64)
    tau = (index - float(window_size - 1)) / float(window_size - 1)
    return np.asarray(np.column_stack((np.ones(window_size), tau, tau**2)), dtype=np.float64)


def fit_quadratic_geometry(
    prices: tuple[float, ...],
) -> tuple[float, float, float, float, float]:
    """Fit the specified quadratic with a pseudoinverse and return residual scales.

    Units: coefficients inherit native price under normalized time; scales are native
    price. Tuple order is oldest to newest. At least four finite positive prices are
    required. ``np.linalg.lstsq`` is intentionally reserved for differential tests.
    """

    if len(prices) <= 3 or any(not math.isfinite(price) or price <= 0 for price in prices):
        raise DataQualityError("quadratic geometry requires at least four positive prices")
    values = np.asarray(prices, dtype=np.float64)
    design = quadratic_design(len(prices))
    pseudoinverse = np.asarray(np.linalg.pinv(design), dtype=np.float64)
    return _fit_with_matrix(values, design, pseudoinverse)


def _fit_with_matrix(
    values: npt.NDArray[np.float64],
    design: npt.NDArray[np.float64],
    pseudoinverse: npt.NDArray[np.float64],
) -> tuple[float, float, float, float, float]:
    coefficients = np.asarray(pseudoinverse @ values, dtype=np.float64)
    if coefficients.shape != (3,) or not np.isfinite(coefficients).all():
        raise DataQualityError("ICM coefficient calculation produced invalid values")
    residuals = np.asarray(values - design @ coefficients, dtype=np.float64)
    degrees_of_freedom = len(values) - 3
    sigma_ols = math.sqrt(float(np.sum(residuals**2)) / degrees_of_freedom)
    residual_median = float(np.median(residuals))
    sigma_mad = 1.4826 * float(np.median(np.abs(residuals - residual_median)))
    if not all(math.isfinite(value) and value >= 0 for value in (sigma_ols, sigma_mad)):
        raise DataQualityError("ICM residual scale calculation produced invalid values")
    beta0, beta1, beta2 = (float(value) for value in coefficients)
    return beta0, beta1, beta2, sigma_ols, sigma_mad


def _lag_one_autocorrelation(residuals: npt.NDArray[np.float64]) -> float | None:
    """Return causal lag-one residual autocorrelation or ``None`` when degenerate."""

    if residuals.ndim != 1 or len(residuals) < 2 or not np.isfinite(residuals).all():
        raise DataQualityError("ICM residual autocorrelation requires a finite vector")
    left = residuals[:-1] - float(np.mean(residuals[:-1]))
    right = residuals[1:] - float(np.mean(residuals[1:]))
    denominator = math.sqrt(float(np.sum(left**2)) * float(np.sum(right**2)))
    if denominator <= _EPSILON:
        return None
    value = float(np.sum(left * right)) / denominator
    return min(1.0, max(-1.0, value))


__all__ = ("ICMEngine", "fit_quadratic_geometry", "quadratic_design")

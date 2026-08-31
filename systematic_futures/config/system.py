from dataclasses import dataclass

from systematic_futures.domain.errors import DataQualityError


@dataclass(frozen=True, slots=True)
class StructuralFeatureConfig:
    """Versioned research-candidate configuration for transparent structural state.

    Units: all windows are completed semantic sessions. Time semantics: every rolling
    statistic uses observations strictly no later than the structural decision frontier.
    Missingness: insufficient or degenerate history produces explicit NOT_READY fields.
    """

    trend_lookbacks_sessions: tuple[int, ...]
    realized_volatility_window_sessions: int
    volatility_percentile_window_sessions: int
    volatility_percentile_minimum_history: int
    carry_normalization_window_sessions: int
    carry_minimum_history: int
    annualization_sessions: int
    feature_version: str

    def __post_init__(self) -> None:
        if not self.trend_lookbacks_sessions:
            raise DataQualityError("trend_lookbacks_sessions must not be empty")
        if self.trend_lookbacks_sessions != tuple(sorted(set(self.trend_lookbacks_sessions))):
            raise DataQualityError("trend_lookbacks_sessions must be sorted and unique")
        if any(type(value) is not int or value <= 0 for value in self.trend_lookbacks_sessions):
            raise DataQualityError("trend lookbacks must be positive integers")
        integer_fields = {
            "realized_volatility_window_sessions": self.realized_volatility_window_sessions,
            "volatility_percentile_window_sessions": self.volatility_percentile_window_sessions,
            "volatility_percentile_minimum_history": self.volatility_percentile_minimum_history,
            "carry_normalization_window_sessions": self.carry_normalization_window_sessions,
            "carry_minimum_history": self.carry_minimum_history,
            "annualization_sessions": self.annualization_sessions,
        }
        for field_name, value in integer_fields.items():
            if type(value) is not int or value <= 0:
                raise DataQualityError(f"{field_name} must be a positive integer")
        if self.volatility_percentile_minimum_history > self.volatility_percentile_window_sessions:
            raise DataQualityError(
                "volatility percentile minimum history cannot exceed its rolling window"
            )
        if self.carry_minimum_history > self.carry_normalization_window_sessions:
            raise DataQualityError("carry minimum history cannot exceed its rolling window")
        if not isinstance(self.feature_version, str) or not self.feature_version.strip():
            raise DataQualityError("feature_version must be a non-blank string")

    @property
    def maximum_trend_lookback(self) -> int:
        """Return the longest completed-session trend horizon."""

        return self.trend_lookbacks_sessions[-1]


DEFAULT_STRUCTURAL_FEATURE_CONFIG = StructuralFeatureConfig(
    trend_lookbacks_sessions=(21, 63, 126, 252),
    realized_volatility_window_sessions=63,
    volatility_percentile_window_sessions=252,
    volatility_percentile_minimum_history=126,
    carry_normalization_window_sessions=252,
    carry_minimum_history=126,
    annualization_sessions=252,
    feature_version="structural_state_research_candidate_v1",
)


__all__ = ("DEFAULT_STRUCTURAL_FEATURE_CONFIG", "StructuralFeatureConfig")

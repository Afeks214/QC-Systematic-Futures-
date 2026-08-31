"""Versioned, explicit policy for ASR transition research.

The policy is deliberately separate from Profile and evidence mathematics. Values in
an ``AuctionResearchPolicy`` are research parameters, not institutional truths and not
trading authority.
"""

import math
from dataclasses import dataclass

from systematic_futures.domain.errors import DataQualityError


@dataclass(frozen=True, slots=True)
class AuctionResearchPolicy:
    """Pre-registered thresholds used to classify ASR evidence.

    Units:
        - ``minimum_excursion_vol`` and migration thresholds are local volatility units.
        - minute fields are completed fast-clock minutes.
        - ratios are dimensionless in ``[0, 1]``.
    Time semantics:
        Every input must be available at the Auction snapshot frontier.
    Missingness:
        A missing required evidence component causes the corresponding gate to fail; it
        is never replaced with zero.
    """

    version: str
    minimum_excursion_vol: float
    minimum_outside_minutes: int
    minimum_volume_outside_ratio: float
    minimum_close_persistence_ratio: float
    minimum_poc_migration_vol: float
    minimum_value_migration_vol: float
    required_migration_blocks: int
    max_failure_window_minutes: int
    candidate_validity_minutes: int

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise DataQualityError("Auction policy version must be non-blank")
        for field_name, value in (
            ("minimum_excursion_vol", self.minimum_excursion_vol),
            ("minimum_volume_outside_ratio", self.minimum_volume_outside_ratio),
            ("minimum_close_persistence_ratio", self.minimum_close_persistence_ratio),
            ("minimum_poc_migration_vol", self.minimum_poc_migration_vol),
            ("minimum_value_migration_vol", self.minimum_value_migration_vol),
        ):
            if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
                raise DataQualityError(f"{field_name} must be finite")
            if value < 0:
                raise DataQualityError(f"{field_name} must be non-negative")
        for field_name, value in (
            ("minimum_volume_outside_ratio", self.minimum_volume_outside_ratio),
            ("minimum_close_persistence_ratio", self.minimum_close_persistence_ratio),
        ):
            if value > 1:
                raise DataQualityError(f"{field_name} must be in [0, 1]")
        for field_name, value in (
            ("minimum_outside_minutes", self.minimum_outside_minutes),
            ("max_failure_window_minutes", self.max_failure_window_minutes),
            ("candidate_validity_minutes", self.candidate_validity_minutes),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise DataQualityError(f"{field_name} must be a positive integer")
        if (
            isinstance(self.required_migration_blocks, bool)
            or not isinstance(self.required_migration_blocks, int)
            or not 0 <= self.required_migration_blocks <= 2
        ):
            raise DataQualityError("required_migration_blocks must be an integer in [0, 2]")
        if self.max_failure_window_minutes < self.minimum_outside_minutes:
            raise DataQualityError(
                "failure window must not be shorter than minimum acceptance residence"
            )


__all__ = ("AuctionResearchPolicy",)

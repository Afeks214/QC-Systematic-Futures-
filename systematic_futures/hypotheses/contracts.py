"""Immutable symbolic hypothesis and candidate contracts.

Candidates describe economic eligibility only. They carry no forecast probability,
position size, risk approval, or order instruction.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from systematic_futures.domain.enums import BookType, HorizonFamily
from systematic_futures.domain.errors import DataQualityError, DataTimingInvariantError


def _require_text(value: str, field_name: str) -> None:
    if not value.strip():
        raise DataQualityError(f"{field_name} must be non-blank")


def _require_utc(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise DataTimingInvariantError(f"{field_name} must be aware UTC")


def _validate_pairs(values: tuple[tuple[str, object], ...], field_name: str) -> None:
    keys = tuple(key for key, _ in values)
    if keys != tuple(sorted(set(keys))):
        raise DataQualityError(f"{field_name} must be sorted with unique keys")
    for key in keys:
        _require_text(key, f"{field_name} key")


@dataclass(frozen=True, slots=True)
class HypothesisTemplate:
    """Versioned symbolic mechanism definition; no model or sizing authority."""

    hypothesis_id: str
    version: str
    book: BookType
    archetype: str
    economic_mechanism: str
    eligible_markets: tuple[str, ...]
    horizon_family: HorizonFamily
    forecast_horizons_minutes: tuple[int, ...]
    candidate_validity_minutes: int
    transition_name: str
    side_rule_id: str
    invalidation_rule_id: str
    dedup_rule_id: str
    target_family_ids: tuple[str, ...]
    cost_policy_id: str
    risk_policy_id: str
    preregistration_hash: str

    def __post_init__(self) -> None:
        for field_name, value in (
            ("hypothesis_id", self.hypothesis_id),
            ("version", self.version),
            ("archetype", self.archetype),
            ("economic_mechanism", self.economic_mechanism),
            ("transition_name", self.transition_name),
            ("side_rule_id", self.side_rule_id),
            ("invalidation_rule_id", self.invalidation_rule_id),
            ("dedup_rule_id", self.dedup_rule_id),
            ("cost_policy_id", self.cost_policy_id),
            ("risk_policy_id", self.risk_policy_id),
            ("preregistration_hash", self.preregistration_hash),
        ):
            _require_text(value, field_name)
        if not isinstance(self.book, BookType):
            raise DataQualityError("book must be a BookType")
        if not isinstance(self.horizon_family, HorizonFamily):
            raise DataQualityError("horizon_family must be a HorizonFamily")
        if not self.eligible_markets or len(set(self.eligible_markets)) != len(
            self.eligible_markets
        ):
            raise DataQualityError("eligible_markets must be unique and non-empty")
        if not self.forecast_horizons_minutes or self.forecast_horizons_minutes != tuple(
            sorted(set(self.forecast_horizons_minutes))
        ):
            raise DataQualityError(
                "forecast_horizons_minutes must be sorted, unique, and non-empty"
            )
        if any(value <= 0 for value in self.forecast_horizons_minutes):
            raise DataQualityError("forecast horizons must be positive")
        if self.candidate_validity_minutes <= 0:
            raise DataQualityError("candidate_validity_minutes must be positive")
        if not self.target_family_ids:
            raise DataQualityError("target_family_ids must not be empty")
        for market in self.eligible_markets:
            _require_text(market, "eligible market")
        for target in self.target_family_ids:
            _require_text(target, "target family")


@dataclass(frozen=True, slots=True)
class CandidateEvent:
    """One economic opportunity created at the first knowable transition frontier."""

    candidate_id: str
    parent_event_id: str
    event_cluster_id: str
    hypothesis_id: str
    hypothesis_version: str
    book: BookType
    archetype: str
    root: str
    actual_contract: str
    session_id: str
    excursion_start_time_utc: datetime
    candidate_time_utc: datetime
    available_at_utc: datetime
    excursion_side: int
    side: int
    horizon_family: HorizonFamily
    forecast_horizons_minutes: tuple[int, ...]
    expires_at_utc: datetime
    state_snapshot_ids: tuple[tuple[str, str], ...]
    hard_gate_results: tuple[tuple[str, bool], ...]
    invalidation_rule_id: str
    quality_flags: tuple[str, ...]
    lineage_hash: str

    def __post_init__(self) -> None:
        for field_name, value in (
            ("candidate_id", self.candidate_id),
            ("parent_event_id", self.parent_event_id),
            ("event_cluster_id", self.event_cluster_id),
            ("hypothesis_id", self.hypothesis_id),
            ("hypothesis_version", self.hypothesis_version),
            ("archetype", self.archetype),
            ("root", self.root),
            ("actual_contract", self.actual_contract),
            ("session_id", self.session_id),
            ("invalidation_rule_id", self.invalidation_rule_id),
            ("lineage_hash", self.lineage_hash),
        ):
            _require_text(value, field_name)
        for field_name, value in (
            ("excursion_start_time_utc", self.excursion_start_time_utc),
            ("candidate_time_utc", self.candidate_time_utc),
            ("available_at_utc", self.available_at_utc),
            ("expires_at_utc", self.expires_at_utc),
        ):
            _require_utc(value, field_name)
        if not (
            self.excursion_start_time_utc
            <= self.candidate_time_utc
            <= self.available_at_utc
            < self.expires_at_utc
        ):
            raise DataTimingInvariantError(
                "candidate clocks must satisfy excursion <= candidate <= available < expiry"
            )
        if self.excursion_side not in (-1, 1) or self.side not in (-1, 1):
            raise DataQualityError("candidate sides must be -1 or +1")
        if not isinstance(self.book, BookType):
            raise DataQualityError("book must be a BookType")
        if not isinstance(self.horizon_family, HorizonFamily):
            raise DataQualityError("horizon_family must be a HorizonFamily")
        if not self.forecast_horizons_minutes:
            raise DataQualityError("forecast_horizons_minutes must not be empty")
        _validate_pairs(self.state_snapshot_ids, "state_snapshot_ids")
        _validate_pairs(
            tuple((key, value) for key, value in self.hard_gate_results),
            "hard_gate_results",
        )
        if self.quality_flags != tuple(sorted(set(self.quality_flags))):
            raise DataQualityError("quality_flags must be sorted and unique")


__all__ = ("CandidateEvent", "HypothesisTemplate")

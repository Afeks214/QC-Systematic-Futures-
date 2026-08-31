# pyright: reportUnnecessaryIsInstance=false
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from systematic_futures.domain.enums import (
    DataQualityStatus,
    EvidenceAvailability,
    RollState,
)
from systematic_futures.domain.errors import ContractBoundaryError
from systematic_futures.domain.serialization import sha256_hex
from systematic_futures.domain.time_semantics import ensure_aware_utc

_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True, slots=True)
class MappingObservation:
    """Immutable point-in-time observation of one continuous mapping identity.

    Units: aware UTC clocks. Time semantics: ``event_time_utc`` is the mapping's
    effective event time and ``available_time_utc`` is the first decision-time
    frontier at which the observation is known. Missingness: only the initial row may
    omit ``old_mapped_contract``. OI, liquidity, and expiry availability are explicit
    and are never inferred. Raises: ``ContractBoundaryError`` or time errors during
    construction when any invariant fails.
    """

    root: str
    continuous_symbol: str
    old_mapped_contract: str | None
    new_mapped_contract: str
    actual_contract: str
    event_time_utc: datetime
    available_time_utc: datetime
    mapping_mode: str
    source: str
    roll_state: RollState
    liquidity_evidence: EvidenceAvailability
    open_interest_evidence: EvidenceAvailability
    expiry_evidence: EvidenceAvailability
    quality_status: DataQualityStatus
    quality_flags: tuple[str, ...]
    lineage_hash: str

    def __post_init__(self) -> None:
        validate_mapping_observation(self)


@dataclass(frozen=True, slots=True)
class RollMeasurementEligibility:
    """Descriptive measurement eligibility around a mapping transition."""

    root: str
    state: RollState
    eligible: bool
    reason: str
    actual_contract: str | None


def make_mapping_observation(
    *,
    root: str,
    continuous_symbol: str,
    old_mapped_contract: str | None,
    new_mapped_contract: str,
    actual_contract: str,
    event_time_utc: datetime,
    available_time_utc: datetime,
    mapping_mode: str,
    source: str,
    roll_state: RollState,
    liquidity_evidence: EvidenceAvailability = EvidenceAvailability.NOT_AVAILABLE,
    open_interest_evidence: EvidenceAvailability = EvidenceAvailability.NOT_AVAILABLE,
    expiry_evidence: EvidenceAvailability = EvidenceAvailability.NOT_AVAILABLE,
    quality_status: DataQualityStatus = DataQualityStatus.VALID,
    quality_flags: tuple[str, ...] = ("MAPPING_OBSERVED",),
) -> MappingObservation:
    """Build one normalized observation with deterministic complete lineage."""

    normalized_root = _normalized_root(root)
    continuous = _normalized_text(continuous_symbol, "continuous_symbol")
    old = (
        _normalized_text(old_mapped_contract, "old_mapped_contract")
        if old_mapped_contract is not None
        else None
    )
    new = _normalized_text(new_mapped_contract, "new_mapped_contract")
    actual = _normalized_text(actual_contract, "actual_contract")
    event = ensure_aware_utc(event_time_utc, "event_time_utc")
    available = ensure_aware_utc(available_time_utc, "available_time_utc")
    normalized_mapping = _normalized_text(mapping_mode, "mapping_mode")
    normalized_source = _normalized_text(source, "source")
    flags = tuple(sorted(quality_flags))
    payload = _lineage_payload_values(
        normalized_root,
        continuous,
        old,
        new,
        actual,
        event,
        available,
        normalized_mapping,
        normalized_source,
        roll_state,
        liquidity_evidence,
        open_interest_evidence,
        expiry_evidence,
        quality_status,
        flags,
    )
    return MappingObservation(
        root=normalized_root,
        continuous_symbol=continuous,
        old_mapped_contract=old,
        new_mapped_contract=new,
        actual_contract=actual,
        event_time_utc=event,
        available_time_utc=available,
        mapping_mode=normalized_mapping,
        source=normalized_source,
        roll_state=roll_state,
        liquidity_evidence=liquidity_evidence,
        open_interest_evidence=open_interest_evidence,
        expiry_evidence=expiry_evidence,
        quality_status=quality_status,
        quality_flags=flags,
        lineage_hash=sha256_hex(payload),
    )


def validate_mapping_observation(observation: MappingObservation) -> None:
    """Validate complete mapping identity, clocks, evidence flags, and lineage."""

    if observation.root != _normalized_root(observation.root):
        raise ContractBoundaryError("mapping root must be normalized uppercase")
    text_values = {
        "continuous_symbol": observation.continuous_symbol,
        "new_mapped_contract": observation.new_mapped_contract,
        "actual_contract": observation.actual_contract,
        "mapping_mode": observation.mapping_mode,
        "source": observation.source,
    }
    for field_name, value in text_values.items():
        if value != _normalized_text(value, field_name):
            raise ContractBoundaryError(f"{field_name} must be stripped")
    old = observation.old_mapped_contract
    if old is not None and old != _normalized_text(old, "old_mapped_contract"):
        raise ContractBoundaryError("old_mapped_contract must be stripped")
    if old == observation.new_mapped_contract:
        raise ContractBoundaryError("mapping change must retain separate old and new contracts")
    if observation.continuous_symbol in {
        observation.new_mapped_contract,
        observation.actual_contract,
    }:
        raise ContractBoundaryError("continuous identity cannot be an actual contract identity")
    if observation.actual_contract != observation.new_mapped_contract:
        raise ContractBoundaryError("actual_contract must be the newly mapped actual contract")
    ensure_aware_utc(observation.event_time_utc, "event_time_utc")
    ensure_aware_utc(observation.available_time_utc, "available_time_utc")
    if old is None and observation.roll_state is not RollState.NORMAL:
        raise ContractBoundaryError("initial mapping observation must have NORMAL roll state")
    if old is not None and observation.roll_state is not RollState.ROLL_TRANSITION:
        raise ContractBoundaryError("mapping change observation must identify ROLL_TRANSITION")
    for field_name, value in (
        ("liquidity_evidence", observation.liquidity_evidence),
        ("open_interest_evidence", observation.open_interest_evidence),
        ("expiry_evidence", observation.expiry_evidence),
    ):
        if not isinstance(value, EvidenceAvailability):
            raise ContractBoundaryError(f"{field_name} must be EvidenceAvailability")
    if not isinstance(observation.quality_status, DataQualityStatus):
        raise ContractBoundaryError("quality_status must be DataQualityStatus")
    if not isinstance(observation.quality_flags, tuple):
        raise ContractBoundaryError("quality_flags must be a tuple")
    if observation.quality_flags != tuple(sorted(set(observation.quality_flags))):
        raise ContractBoundaryError("quality_flags must be sorted and unique")
    if "MAPPING_OBSERVED" not in observation.quality_flags:
        raise ContractBoundaryError("quality_flags must retain MAPPING_OBSERVED")
    if _SHA256_PATTERN.fullmatch(observation.lineage_hash) is None:
        raise ContractBoundaryError("lineage_hash must be a lowercase SHA-256 digest")
    expected = sha256_hex(
        _lineage_payload_values(
            observation.root,
            observation.continuous_symbol,
            observation.old_mapped_contract,
            observation.new_mapped_contract,
            observation.actual_contract,
            observation.event_time_utc,
            observation.available_time_utc,
            observation.mapping_mode,
            observation.source,
            observation.roll_state,
            observation.liquidity_evidence,
            observation.open_interest_evidence,
            observation.expiry_evidence,
            observation.quality_status,
            observation.quality_flags,
        )
    )
    if observation.lineage_hash != expected:
        raise ContractBoundaryError("mapping observation lineage does not match its content")


class RollManager:
    """Track causal mapping lifecycle without generating execution instructions."""

    def __init__(self) -> None:
        self._observations: dict[str, list[MappingObservation]] = {}

    def observe_mapping(self, observation: MappingObservation) -> RollState:
        """Append or idempotently deduplicate one causal mapping observation."""

        validate_mapping_observation(observation)
        root = observation.root
        history = self._observations.setdefault(root, [])
        for existing in history:
            if existing.lineage_hash == observation.lineage_hash:
                if existing != observation:
                    raise ContractBoundaryError("mapping lineage collision")
                return self.current_roll_state(root, observation.available_time_utc)
        if not history:
            if observation.old_mapped_contract is not None:
                raise ContractBoundaryError(
                    f"first mapping observation for {root} must not invent an old contract"
                )
            history.append(observation)
            return RollState.NORMAL
        previous = history[-1]
        if observation.available_time_utc <= previous.available_time_utc:
            raise ContractBoundaryError(
                f"mapping availability for {root} must increase monotonically"
            )
        if _transition_at(observation) <= _transition_at(previous):
            raise ContractBoundaryError(f"mapping transition for {root} must move forward")
        if observation.old_mapped_contract != previous.new_mapped_contract:
            raise ContractBoundaryError(
                f"mapping discontinuity for {root}: expected old contract "
                f"{previous.new_mapped_contract!r}"
            )
        if observation.continuous_symbol != previous.continuous_symbol:
            raise ContractBoundaryError(f"continuous identity changed for {root}")
        history.append(observation)
        return self.current_roll_state(root, observation.available_time_utc)

    def current_roll_state(self, root: str, as_of_utc: datetime) -> RollState:
        """Return the causal descriptive state visible at one UTC frontier."""

        normalized_root = _normalized_root(root)
        as_of = ensure_aware_utc(as_of_utc, "as_of_utc")
        visible = tuple(
            item
            for item in self._observations.get(normalized_root, ())
            if item.available_time_utc <= as_of
        )
        if len(visible) <= 1:
            return RollState.NORMAL
        latest = visible[-1]
        transition = _transition_at(latest)
        if as_of < transition:
            return RollState.PRE_ROLL
        if as_of == transition:
            return RollState.ROLL_TRANSITION
        return RollState.POST_ROLL

    def observations_for_root(self, root: str) -> tuple[MappingObservation, ...]:
        """Return immutable observation history for one exact root."""

        return tuple(self._observations.get(_normalized_root(root), ()))

    def measurement_eligibility(
        self,
        root: str,
        as_of_utc: datetime,
        *,
        new_contract_ready: bool,
    ) -> RollMeasurementEligibility:
        """Describe measurement eligibility around an observed mapping transition."""

        normalized_root = _normalized_root(root)
        state = self.current_roll_state(normalized_root, as_of_utc)
        history = self.observations_for_root(normalized_root)
        actual = history[-1].actual_contract if history else None
        if state in {RollState.ROLL_TRANSITION, RollState.BLACKOUT}:
            return RollMeasurementEligibility(
                normalized_root,
                state,
                False,
                "ROLL_TRANSITION_MEASUREMENT_BLOCKED",
                actual,
            )
        if state is RollState.POST_ROLL and not new_contract_ready:
            return RollMeasurementEligibility(
                normalized_root,
                state,
                False,
                "NEW_ACTUAL_CONTRACT_WARMUP_INCOMPLETE",
                actual,
            )
        return RollMeasurementEligibility(
            normalized_root,
            state,
            True,
            "MEASUREMENT_ELIGIBLE",
            actual,
        )


def _transition_at(observation: MappingObservation) -> datetime:
    return max(observation.event_time_utc, observation.available_time_utc)


def _normalized_root(root: str) -> str:
    normalized = root.strip().upper()
    if not normalized:
        raise ContractBoundaryError("mapping root must be non-blank")
    return normalized


def _normalized_text(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ContractBoundaryError(f"{field_name} must be non-blank")
    return normalized


def _lineage_payload_values(
    root: str,
    continuous_symbol: str,
    old_mapped_contract: str | None,
    new_mapped_contract: str,
    actual_contract: str,
    event_time_utc: datetime,
    available_time_utc: datetime,
    mapping_mode: str,
    source: str,
    roll_state: RollState,
    liquidity_evidence: EvidenceAvailability,
    open_interest_evidence: EvidenceAvailability,
    expiry_evidence: EvidenceAvailability,
    quality_status: DataQualityStatus,
    quality_flags: tuple[str, ...],
) -> dict[str, object]:
    return {
        "root": root,
        "continuous_symbol": continuous_symbol,
        "old_mapped_contract": old_mapped_contract,
        "new_mapped_contract": new_mapped_contract,
        "actual_contract": actual_contract,
        "event_time_utc": event_time_utc,
        "available_time_utc": available_time_utc,
        "mapping_mode": mapping_mode,
        "source": source,
        "roll_state": roll_state,
        "liquidity_evidence": liquidity_evidence,
        "open_interest_evidence": open_interest_evidence,
        "expiry_evidence": expiry_evidence,
        "quality_status": quality_status,
        "quality_flags": quality_flags,
    }


__all__ = (
    "MappingObservation",
    "RollManager",
    "RollMeasurementEligibility",
    "make_mapping_observation",
    "validate_mapping_observation",
)

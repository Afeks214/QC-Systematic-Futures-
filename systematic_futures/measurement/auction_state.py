"""Auction-State Representation v2: vector-first evidence and causal state transitions."""

import math
from dataclasses import dataclass
from datetime import datetime, timedelta

from systematic_futures.config.auction import AuctionResearchPolicy
from systematic_futures.domain.enums import (
    AuctionLocationState,
    AuctionPhase,
    AuctionTransitionType,
    RollState,
)
from systematic_futures.domain.errors import (
    ContractBoundaryError,
    DataQualityError,
    DataTimingInvariantError,
)
from systematic_futures.domain.serialization import sha256_hex
from systematic_futures.measurement.state_models import AuctionStateSnapshot

ASR_EVIDENCE_VERSION = "auction_evidence_vector_v1"
ASR_STATE_VERSION = "auction_state_machine_v2"


def _require_utc(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise DataTimingInvariantError(f"{field_name} must be aware UTC")


def _require_text(value: str, field_name: str) -> None:
    if not value.strip():
        raise DataQualityError(f"{field_name} must be non-blank")


def _require_finite(value: float, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise DataQualityError(f"{field_name} must be finite")


def _require_optional_finite(value: float | None, field_name: str) -> None:
    if value is not None:
        _require_finite(value, field_name)


def _normalized_flags(flags: tuple[str, ...]) -> tuple[str, ...]:
    normalized = tuple(sorted(set(flags)))
    if any(not flag.strip() for flag in normalized):
        raise DataQualityError("quality flags must be non-blank")
    return normalized


@dataclass(frozen=True, slots=True)
class AuctionEvidenceVector:
    """Point-in-time evidence for one actual-contract excursion.

    All migration and excursion fields are side-normalized: positive values support the
    initiative direction. Ratios are dimensionless. Minute fields use completed
    fast-clock time. Missing evidence remains ``None``.
    """

    evidence_id: str
    root: str
    contract_symbol: str
    session_id: str
    excursion_id: str
    excursion_side: int
    excursion_start_utc: datetime
    as_of_utc: datetime
    available_at_utc: datetime
    excursion_distance_vol: float | None
    elapsed_minutes: float
    time_outside_minutes: int
    time_outside_value_ratio: float
    volume_outside_value_ratio: float | None
    poc_migration_vol: float | None
    value_mid_migration_vol: float | None
    close_persistence_ratio: float
    retest_survival_ratio: float | None
    migration_consistency: float | None
    reentry_count: int
    reentry_speed_minutes: float | None
    quality_flags: tuple[str, ...]
    feature_version: str

    def __post_init__(self) -> None:
        for field_name, value in (
            ("evidence_id", self.evidence_id),
            ("root", self.root),
            ("contract_symbol", self.contract_symbol),
            ("session_id", self.session_id),
            ("excursion_id", self.excursion_id),
            ("feature_version", self.feature_version),
        ):
            _require_text(value, field_name)
        if self.excursion_side not in (-1, 1):
            raise DataQualityError("excursion_side must be -1 or +1")
        for field_name, value in (
            ("excursion_start_utc", self.excursion_start_utc),
            ("as_of_utc", self.as_of_utc),
            ("available_at_utc", self.available_at_utc),
        ):
            _require_utc(value, field_name)
        if not self.excursion_start_utc <= self.as_of_utc <= self.available_at_utc:
            raise DataTimingInvariantError(
                "evidence clocks must satisfy start <= as_of <= available"
            )
        for field_name, value in (
            ("elapsed_minutes", self.elapsed_minutes),
            ("time_outside_value_ratio", self.time_outside_value_ratio),
            ("close_persistence_ratio", self.close_persistence_ratio),
        ):
            _require_finite(value, field_name)
        for field_name, value in (
            ("excursion_distance_vol", self.excursion_distance_vol),
            ("volume_outside_value_ratio", self.volume_outside_value_ratio),
            ("poc_migration_vol", self.poc_migration_vol),
            ("value_mid_migration_vol", self.value_mid_migration_vol),
            ("retest_survival_ratio", self.retest_survival_ratio),
            ("migration_consistency", self.migration_consistency),
            ("reentry_speed_minutes", self.reentry_speed_minutes),
        ):
            _require_optional_finite(value, field_name)
        if self.elapsed_minutes < 0 or self.time_outside_minutes < 0:
            raise DataQualityError("elapsed and outside time must be non-negative")
        if self.reentry_count < 0:
            raise DataQualityError("reentry_count must be non-negative")
        if self.excursion_distance_vol is not None and self.excursion_distance_vol < 0:
            raise DataQualityError("excursion_distance_vol must be non-negative")
        for field_name, value in (
            ("time_outside_value_ratio", self.time_outside_value_ratio),
            ("volume_outside_value_ratio", self.volume_outside_value_ratio),
            ("close_persistence_ratio", self.close_persistence_ratio),
            ("retest_survival_ratio", self.retest_survival_ratio),
            ("migration_consistency", self.migration_consistency),
        ):
            if value is not None and not 0 <= value <= 1:
                raise DataQualityError(f"{field_name} must be in [0, 1]")
        if self.reentry_speed_minutes is not None and self.reentry_speed_minutes < 0:
            raise DataQualityError("reentry_speed_minutes must be non-negative")
        if self.quality_flags != _normalized_flags(self.quality_flags):
            raise DataQualityError("quality_flags must be sorted and unique")


@dataclass(frozen=True, slots=True)
class AuctionPhaseSnapshot:
    """Immutable ASR state after one completed Auction observation."""

    snapshot_id: str
    root: str
    contract_symbol: str
    session_id: str
    as_of_utc: datetime
    available_at_utc: datetime
    phase: AuctionPhase
    transition: AuctionTransitionType
    side: int
    excursion_id: str | None
    excursion_start_utc: datetime | None
    evidence: AuctionEvidenceVector | None
    gate_results: tuple[tuple[str, bool], ...]
    measurement_ready: bool
    quality_flags: tuple[str, ...]
    policy_version: str
    state_version: str

    def __post_init__(self) -> None:
        for field_name, value in (
            ("snapshot_id", self.snapshot_id),
            ("root", self.root),
            ("contract_symbol", self.contract_symbol),
            ("session_id", self.session_id),
            ("policy_version", self.policy_version),
            ("state_version", self.state_version),
        ):
            _require_text(value, field_name)
        _require_utc(self.as_of_utc, "as_of_utc")
        _require_utc(self.available_at_utc, "available_at_utc")
        if self.as_of_utc > self.available_at_utc:
            raise DataTimingInvariantError("ASR snapshot cannot precede its availability")
        if not isinstance(self.phase, AuctionPhase):
            raise DataQualityError("phase must be an AuctionPhase")
        if not isinstance(self.transition, AuctionTransitionType):
            raise DataQualityError("transition must be an AuctionTransitionType")
        if self.side not in (-1, 0, 1):
            raise DataQualityError("side must be -1, 0, or +1")
        directional = self.phase in {
            AuctionPhase.INITIATIVE,
            AuctionPhase.ACCEPTED,
            AuctionPhase.FAILED,
            AuctionPhase.PULLBACK,
        }
        if directional != (self.side in (-1, 1)):
            raise DataQualityError("directional Auction phases require side -1 or +1")
        if (self.excursion_id is None) != (self.excursion_start_utc is None):
            raise DataQualityError("excursion identity and start must be jointly present")
        if directional and (self.excursion_id is None or self.evidence is None):
            raise DataQualityError("directional Auction phase requires excursion evidence")
        if not directional and self.evidence is not None:
            raise DataQualityError("non-directional Auction phase cannot carry excursion evidence")
        if self.excursion_id is not None:
            _require_text(self.excursion_id, "excursion_id")
        if self.excursion_start_utc is not None:
            _require_utc(self.excursion_start_utc, "excursion_start_utc")
        keys = tuple(key for key, _ in self.gate_results)
        if keys != tuple(sorted(set(keys))):
            raise DataQualityError("gate_results must be sorted with unique keys")
        if self.quality_flags != _normalized_flags(self.quality_flags):
            raise DataQualityError("quality_flags must be sorted and unique")


class AuctionStateMachineV2:
    """Causal ASR state machine over completed actual-contract Auction snapshots."""

    def __init__(
        self,
        root: str,
        contract_symbol: str,
        policy: AuctionResearchPolicy,
    ) -> None:
        if not root.strip() or not contract_symbol.strip():
            raise DataQualityError("ASR identity must be non-blank")
        self.root = root
        self.contract_symbol = contract_symbol
        self.policy = policy
        self._session_id: str | None = None
        self._phase = AuctionPhase.NOT_READY
        self._side = 0
        self._excursion_id: str | None = None
        self._excursion_start_utc: datetime | None = None
        self._total_updates = 0
        self._outside_updates = 0
        self._time_outside_minutes = 0
        self._max_excursion_distance_vol: float | None = None
        self._migration_checks = 0
        self._migration_aligned = 0
        self._last_as_of_utc: datetime | None = None
        self._last_evidence: AuctionEvidenceVector | None = None

    def update(
        self,
        snapshot: AuctionStateSnapshot,
        roll_state: RollState = RollState.NORMAL,
    ) -> AuctionPhaseSnapshot:
        """Advance ASR using one completed, available Auction snapshot.

        The method has no forecasting, sizing, risk, or order authority.
        """

        self._validate_input(snapshot, roll_state)
        session_changed = snapshot.session_id != self._session_id
        if session_changed:
            self._reset_excursion()
            self._session_id = snapshot.session_id
            self._phase = AuctionPhase.NOT_READY

        if roll_state in {RollState.ROLL_TRANSITION, RollState.BLACKOUT}:
            self._reset_excursion()
            self._phase = AuctionPhase.ROLL_TRANSITION
            return self._make_snapshot(
                source=snapshot,
                phase=AuctionPhase.ROLL_TRANSITION,
                transition=AuctionTransitionType.ROLL_TRANSITION,
                side=0,
                evidence=None,
                gates=(),
                ready=False,
                extra_flags=("ASR:ROLL_SUPPRESSED",),
            )

        if (
            not snapshot.measurement_ready
            or snapshot.location_state is AuctionLocationState.NO_REFERENCE
        ):
            self._reset_excursion()
            self._phase = AuctionPhase.NOT_READY
            return self._make_snapshot(
                source=snapshot,
                phase=AuctionPhase.NOT_READY,
                transition=(
                    AuctionTransitionType.SESSION_RESET
                    if session_changed
                    else AuctionTransitionType.NONE
                ),
                side=0,
                evidence=None,
                gates=(),
                ready=False,
                extra_flags=("ASR:MEASUREMENT_NOT_READY",),
            )

        if snapshot.location_state is AuctionLocationState.INSIDE_VALUE:
            return self._handle_inside(snapshot, session_changed)

        side = 1 if snapshot.location_state is AuctionLocationState.ABOVE_VALUE else -1
        return self._handle_outside(snapshot, side)

    def _handle_outside(
        self,
        snapshot: AuctionStateSnapshot,
        side: int,
    ) -> AuctionPhaseSnapshot:
        transition = AuctionTransitionType.NONE
        if (
            self._phase
            not in {
                AuctionPhase.INITIATIVE,
                AuctionPhase.ACCEPTED,
            }
            or self._side != side
            or self._excursion_id is None
        ):
            self._start_excursion(snapshot, side)
            transition = AuctionTransitionType.BALANCE_TO_INITIATIVE
            phase = AuctionPhase.INITIATIVE
        else:
            self._total_updates += 1
            self._outside_updates += 1
            self._time_outside_minutes = max(
                self._time_outside_minutes,
                snapshot.features.consecutive_minutes_outside,
            )
            self._update_migration_consistency(snapshot, side)
            phase = self._phase

        evidence = self._build_evidence(snapshot, reentry_speed_minutes=None)
        gates = self._acceptance_gate_results(evidence)
        if phase is AuctionPhase.INITIATIVE and all(result for _, result in gates):
            phase = AuctionPhase.ACCEPTED
            transition = AuctionTransitionType.INITIATIVE_TO_ACCEPTANCE
        self._phase = phase
        self._last_evidence = evidence
        return self._make_snapshot(
            source=snapshot,
            phase=phase,
            transition=transition,
            side=side,
            evidence=evidence,
            gates=gates,
            ready=True,
        )

    def _handle_inside(
        self,
        snapshot: AuctionStateSnapshot,
        session_changed: bool,
    ) -> AuctionPhaseSnapshot:
        if self._phase is AuctionPhase.INITIATIVE and self._excursion_start_utc is not None:
            self._total_updates += 1
            elapsed = (snapshot.as_of_utc - self._excursion_start_utc).total_seconds() / 60.0
            evidence = self._build_evidence(
                snapshot,
                reentry_speed_minutes=max(elapsed, 0.0),
            )
            gates = self._acceptance_gate_results(evidence)
            failure_eligible = (
                elapsed <= self.policy.max_failure_window_minutes
                and self._minimum_excursion_passes(evidence)
                and not all(result for _, result in gates)
            )
            if failure_eligible:
                self._phase = AuctionPhase.FAILED
                self._last_evidence = evidence
                return self._make_snapshot(
                    source=snapshot,
                    phase=AuctionPhase.FAILED,
                    transition=AuctionTransitionType.INITIATIVE_TO_FAILURE,
                    side=self._side,
                    evidence=evidence,
                    gates=gates,
                    ready=True,
                )
            self._reset_excursion()
            self._phase = AuctionPhase.BALANCE
            return self._make_snapshot(
                source=snapshot,
                phase=AuctionPhase.BALANCE,
                transition=AuctionTransitionType.INITIATIVE_EXPIRED,
                side=0,
                evidence=None,
                gates=(),
                ready=True,
                extra_flags=("ASR:INITIATIVE_EXPIRED_WITHOUT_CLASSIFICATION",),
            )

        if self._phase is AuctionPhase.ACCEPTED and self._last_evidence is not None:
            self._phase = AuctionPhase.PULLBACK
            return self._make_snapshot(
                source=snapshot,
                phase=AuctionPhase.PULLBACK,
                transition=AuctionTransitionType.ACCEPTANCE_TO_PULLBACK,
                side=self._side,
                evidence=self._last_evidence,
                gates=self._acceptance_gate_results(self._last_evidence),
                ready=True,
            )

        self._reset_excursion()
        self._phase = AuctionPhase.BALANCE
        return self._make_snapshot(
            source=snapshot,
            phase=AuctionPhase.BALANCE,
            transition=(
                AuctionTransitionType.SESSION_RESET
                if session_changed
                else AuctionTransitionType.NONE
            ),
            side=0,
            evidence=None,
            gates=(),
            ready=True,
        )

    def _start_excursion(self, snapshot: AuctionStateSnapshot, side: int) -> None:
        self._side = side
        self._excursion_start_utc = snapshot.as_of_utc
        self._excursion_id = snapshot.active_excursion_id or (
            "excursion_"
            + sha256_hex(
                (
                    self.root,
                    self.contract_symbol,
                    snapshot.session_id,
                    snapshot.as_of_utc,
                    side,
                    ASR_STATE_VERSION,
                )
            )
        )
        self._total_updates = 1
        self._outside_updates = 1
        self._time_outside_minutes = snapshot.features.consecutive_minutes_outside
        self._max_excursion_distance_vol = None
        self._migration_checks = 0
        self._migration_aligned = 0
        self._update_migration_consistency(snapshot, side)

    def _reset_excursion(self) -> None:
        self._side = 0
        self._excursion_id = None
        self._excursion_start_utc = None
        self._total_updates = 0
        self._outside_updates = 0
        self._time_outside_minutes = 0
        self._max_excursion_distance_vol = None
        self._migration_checks = 0
        self._migration_aligned = 0
        self._last_evidence = None

    def _update_migration_consistency(
        self,
        snapshot: AuctionStateSnapshot,
        side: int,
    ) -> None:
        raw_values = (
            snapshot.features.poc_migration_vol,
            snapshot.features.value_mid_migration_vol,
        )
        available = tuple(value for value in raw_values if value is not None)
        if not available:
            return
        self._migration_checks += 1
        if all(side * value >= 0 for value in available):
            self._migration_aligned += 1

    def _build_evidence(
        self,
        snapshot: AuctionStateSnapshot,
        reentry_speed_minutes: float | None,
    ) -> AuctionEvidenceVector:
        if self._excursion_id is None or self._excursion_start_utc is None or self._side == 0:
            raise DataQualityError("cannot build evidence without an active excursion")
        distance = self._side_normalized_excursion(snapshot, self._side)
        if distance is not None:
            self._max_excursion_distance_vol = max(
                distance,
                self._max_excursion_distance_vol or distance,
            )
        elapsed = max(
            0.0,
            (snapshot.as_of_utc - self._excursion_start_utc).total_seconds() / 60.0,
        )
        denominator = max(elapsed, float(self._time_outside_minutes), 1.0)
        time_ratio = min(1.0, self._time_outside_minutes / denominator)
        close_ratio = self._outside_updates / max(self._total_updates, 1)
        migration_consistency = (
            self._migration_aligned / self._migration_checks if self._migration_checks else None
        )
        poc = snapshot.features.poc_migration_vol
        value_mid = snapshot.features.value_mid_migration_vol
        quality_flags = set(snapshot.quality_flags)
        if self._max_excursion_distance_vol is None:
            quality_flags.add("ASR:EXCURSION_SCALE_MISSING")
        if snapshot.features.volume_outside_value_ratio is None:
            quality_flags.add("ASR:OUTSIDE_VOLUME_MISSING")
        if poc is None and value_mid is None:
            quality_flags.add("ASR:MIGRATION_MISSING")
        identity = {
            "as_of_utc": snapshot.as_of_utc,
            "available_at_utc": snapshot.available_at_utc,
            "close_persistence_ratio": close_ratio,
            "contract_symbol": self.contract_symbol,
            "elapsed_minutes": elapsed,
            "excursion_distance_vol": self._max_excursion_distance_vol,
            "excursion_id": self._excursion_id,
            "excursion_side": self._side,
            "excursion_start_utc": self._excursion_start_utc,
            "feature_version": ASR_EVIDENCE_VERSION,
            "migration_consistency": migration_consistency,
            "poc_migration_vol": self._side * poc if poc is not None else None,
            "quality_flags": tuple(sorted(quality_flags)),
            "reentry_count": snapshot.features.reentry_count,
            "reentry_speed_minutes": reentry_speed_minutes,
            "root": self.root,
            "session_id": snapshot.session_id,
            "time_outside_minutes": self._time_outside_minutes,
            "time_outside_value_ratio": time_ratio,
            "value_mid_migration_vol": (self._side * value_mid if value_mid is not None else None),
            "volume_outside_value_ratio": snapshot.features.volume_outside_value_ratio,
        }
        return AuctionEvidenceVector(
            evidence_id=f"asr_evidence_{sha256_hex(identity)}",
            root=self.root,
            contract_symbol=self.contract_symbol,
            session_id=snapshot.session_id,
            excursion_id=self._excursion_id,
            excursion_side=self._side,
            excursion_start_utc=self._excursion_start_utc,
            as_of_utc=snapshot.as_of_utc,
            available_at_utc=snapshot.available_at_utc,
            excursion_distance_vol=self._max_excursion_distance_vol,
            elapsed_minutes=elapsed,
            time_outside_minutes=self._time_outside_minutes,
            time_outside_value_ratio=time_ratio,
            volume_outside_value_ratio=snapshot.features.volume_outside_value_ratio,
            poc_migration_vol=self._side * poc if poc is not None else None,
            value_mid_migration_vol=(self._side * value_mid if value_mid is not None else None),
            close_persistence_ratio=close_ratio,
            retest_survival_ratio=None,
            migration_consistency=migration_consistency,
            reentry_count=snapshot.features.reentry_count,
            reentry_speed_minutes=reentry_speed_minutes,
            quality_flags=tuple(sorted(quality_flags)),
            feature_version=ASR_EVIDENCE_VERSION,
        )

    def _acceptance_gate_results(
        self,
        evidence: AuctionEvidenceVector,
    ) -> tuple[tuple[str, bool], ...]:
        poc_pass = (
            evidence.poc_migration_vol is not None
            and evidence.poc_migration_vol >= self.policy.minimum_poc_migration_vol
        )
        value_pass = (
            evidence.value_mid_migration_vol is not None
            and evidence.value_mid_migration_vol >= self.policy.minimum_value_migration_vol
        )
        migration_count = int(poc_pass) + int(value_pass)
        results = {
            "close_persistence": (
                evidence.close_persistence_ratio >= self.policy.minimum_close_persistence_ratio
            ),
            "excursion": self._minimum_excursion_passes(evidence),
            "migration_blocks": migration_count >= self.policy.required_migration_blocks,
            "outside_time": (evidence.time_outside_minutes >= self.policy.minimum_outside_minutes),
            "outside_volume": (
                evidence.volume_outside_value_ratio is not None
                and evidence.volume_outside_value_ratio >= self.policy.minimum_volume_outside_ratio
            ),
        }
        return tuple(sorted(results.items()))

    def _minimum_excursion_passes(self, evidence: AuctionEvidenceVector) -> bool:
        return (
            evidence.excursion_distance_vol is not None
            and evidence.excursion_distance_vol >= self.policy.minimum_excursion_vol
        )

    @staticmethod
    def _side_normalized_excursion(
        snapshot: AuctionStateSnapshot,
        side: int,
    ) -> float | None:
        if side == 1:
            value = snapshot.features.distance_to_vah_vol
        else:
            raw = snapshot.features.distance_to_val_vol
            value = -raw if raw is not None else None
        if value is None:
            return None
        return max(0.0, value)

    def _make_snapshot(
        self,
        *,
        source: AuctionStateSnapshot,
        phase: AuctionPhase,
        transition: AuctionTransitionType,
        side: int,
        evidence: AuctionEvidenceVector | None,
        gates: tuple[tuple[str, bool], ...],
        ready: bool,
        extra_flags: tuple[str, ...] = (),
    ) -> AuctionPhaseSnapshot:
        quality_flags = tuple(sorted(set(source.quality_flags).union(extra_flags)))
        identity = {
            "as_of_utc": source.as_of_utc,
            "available_at_utc": source.available_at_utc,
            "contract_symbol": source.contract_symbol,
            "evidence_id": evidence.evidence_id if evidence is not None else None,
            "excursion_id": self._excursion_id,
            "gate_results": gates,
            "phase": phase,
            "policy_version": self.policy.version,
            "quality_flags": quality_flags,
            "root": source.root,
            "session_id": source.session_id,
            "side": side,
            "state_version": ASR_STATE_VERSION,
            "transition": transition,
        }
        return AuctionPhaseSnapshot(
            snapshot_id=f"asr_state_{sha256_hex(identity)}",
            root=source.root,
            contract_symbol=source.contract_symbol,
            session_id=source.session_id,
            as_of_utc=source.as_of_utc,
            available_at_utc=source.available_at_utc,
            phase=phase,
            transition=transition,
            side=side,
            excursion_id=self._excursion_id,
            excursion_start_utc=self._excursion_start_utc,
            evidence=evidence,
            gate_results=gates,
            measurement_ready=ready,
            quality_flags=quality_flags,
            policy_version=self.policy.version,
            state_version=ASR_STATE_VERSION,
        )

    def _validate_input(
        self,
        snapshot: AuctionStateSnapshot,
        roll_state: RollState,
    ) -> None:
        if snapshot.root != self.root or snapshot.contract_symbol != self.contract_symbol:
            raise ContractBoundaryError("ASR input cannot cross actual-contract identity")
        if not isinstance(roll_state, RollState):
            raise DataQualityError("roll_state must be a RollState")
        if self._last_as_of_utc is not None and snapshot.as_of_utc <= self._last_as_of_utc:
            raise DataTimingInvariantError("ASR snapshot times must strictly increase")
        self._last_as_of_utc = snapshot.as_of_utc


__all__ = (
    "ASR_EVIDENCE_VERSION",
    "ASR_STATE_VERSION",
    "AuctionEvidenceVector",
    "AuctionPhaseSnapshot",
    "AuctionStateMachineV2",
)

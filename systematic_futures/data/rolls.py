from dataclasses import dataclass
from datetime import datetime

from systematic_futures.data.point_in_time import ensure_aware_utc
from systematic_futures.domain.enums import RollState
from systematic_futures.domain.errors import ContractBoundaryError


@dataclass(frozen=True, slots=True)
class MappingObservation:
    """One observed mapping identity change with effective and observed clocks."""

    root: str
    old_mapped_symbol: str | None
    new_mapped_symbol: str
    observed_at_utc: datetime
    effective_at_utc: datetime


def validate_mapping_observation(observation: MappingObservation) -> None:
    """Validate one mapping observation without changing manager state.

    Units: UTC datetimes. Time semantics: both observed and effective timestamps
    must be aware; their relative order may differ, and visibility is their
    maximum. Missingness: only the first observation may omit the old symbol;
    manager history enforces that contextual rule. Raises:
    ``TimeSemanticsError`` or ``ContractBoundaryError``.
    """
    _normalized_root(observation.root)
    new_symbol = observation.new_mapped_symbol.strip()
    if not new_symbol:
        raise ContractBoundaryError("new_mapped_symbol must be non-blank")
    if observation.old_mapped_symbol is not None:
        old_symbol = observation.old_mapped_symbol.strip()
        if not old_symbol:
            raise ContractBoundaryError("old_mapped_symbol must be non-blank when present")
        if old_symbol == new_symbol:
            raise ContractBoundaryError("a mapping change must retain separate old and new IDs")
    ensure_aware_utc(observation.observed_at_utc, "observed_at_utc")
    ensure_aware_utc(observation.effective_at_utc, "effective_at_utc")


class RollManager:
    """Track mapping transitions without volume-based or future inference."""

    def __init__(self) -> None:
        """Create an empty instance-local mapping history.

        Units: not applicable. Time semantics: no implicit initial mapping or
        clock exists. Missingness: roots without observations are ``NORMAL``.
        Raises: none.
        """
        self._observations: dict[str, list[MappingObservation]] = {}

    def observe_mapping(self, observation: MappingObservation) -> RollState:
        """Record an explicit mapping observation and return its immediate state.

        Units: UTC datetimes. Time semantics: ingestion for each root must be
        non-decreasing by observed time; a change cannot become visible before
        max(observed, effective). Missingness: the first observation must omit
        old identity; subsequent observations must name the prior mapped symbol.
        Raises: ``TimeSemanticsError`` or ``ContractBoundaryError``.
        """
        validate_mapping_observation(observation)
        normalized = _normalized_observation(observation)
        root = normalized.root
        history = self._observations.setdefault(root, [])
        if not history:
            if normalized.old_mapped_symbol is not None:
                raise ContractBoundaryError(
                    f"first mapping observation for {root} must not invent an old symbol"
                )
            history.append(normalized)
            return RollState.NORMAL
        previous = history[-1]
        if normalized.observed_at_utc <= previous.observed_at_utc:
            raise ContractBoundaryError(
                f"mapping observations for {root} must have increasing observed times"
            )
        if _visible_at(normalized) <= _visible_at(previous):
            raise ContractBoundaryError(f"mapping visibility for {root} must move forward in time")
        if normalized.old_mapped_symbol != previous.new_mapped_symbol:
            raise ContractBoundaryError(
                f"mapping discontinuity for {root}: expected old symbol "
                f"{previous.new_mapped_symbol!r}"
            )
        history.append(normalized)
        return self.current_roll_state(root, normalized.observed_at_utc)

    def current_roll_state(self, root: str, as_of_utc: datetime) -> RollState:
        """Return roll state using only observations visible by ``as_of_utc``.

        Units: UTC datetime. Time semantics: an observation is visible no
        earlier than both its observed and effective timestamps. Future mapping
        rows cannot affect the answer. A visible contract change is
        ``ROLL_TRANSITION`` only at its exact visibility instant and ``POST_ROLL``
        afterward; Lift 1 infers no duration, pre-roll, or blackout window.
        Missingness: no visible mapping, or only the initial mapping, is ``NORMAL``.
        Raises: ``TimeSemanticsError`` or ``ContractBoundaryError`` for invalid identity.
        """
        normalized_root = _normalized_root(root)
        as_of = ensure_aware_utc(as_of_utc, "as_of_utc")
        history = self._observations.get(normalized_root, [])
        visible = tuple(item for item in history if _visible_at(item) <= as_of)
        if len(visible) <= 1:
            return RollState.NORMAL
        latest = visible[-1]
        if as_of == _visible_at(latest):
            return RollState.ROLL_TRANSITION
        return RollState.POST_ROLL


def _normalized_observation(observation: MappingObservation) -> MappingObservation:
    return MappingObservation(
        root=_normalized_root(observation.root),
        old_mapped_symbol=(
            observation.old_mapped_symbol.strip()
            if observation.old_mapped_symbol is not None
            else None
        ),
        new_mapped_symbol=observation.new_mapped_symbol.strip(),
        observed_at_utc=ensure_aware_utc(observation.observed_at_utc, "observed_at_utc"),
        effective_at_utc=ensure_aware_utc(
            observation.effective_at_utc,
            "effective_at_utc",
        ),
    )


def _visible_at(observation: MappingObservation) -> datetime:
    return max(observation.observed_at_utc, observation.effective_at_utc)


def _normalized_root(root: str) -> str:
    normalized = root.strip().upper()
    if not normalized:
        raise ContractBoundaryError("mapping root must be non-blank")
    return normalized

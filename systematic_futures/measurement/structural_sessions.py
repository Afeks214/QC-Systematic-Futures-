from datetime import datetime

from systematic_futures.domain.errors import (
    ContractBoundaryError,
    DataTimingInvariantError,
)
from systematic_futures.measurement.structural_inputs import (
    ContinuousBarObservation,
    ContinuousSessionCloseObservation,
    _require_text,
    _require_utc,
)


class ContinuousSessionCloseBuilder:
    """Convert ordered continuous minute bars into completed semantic-session closes."""

    def __init__(self, root: str, continuous_symbol: str) -> None:
        _require_text(root, "root")
        _require_text(continuous_symbol, "continuous_symbol")
        self.root = root
        self.continuous_symbol = continuous_symbol
        self._current_session_id: str | None = None
        self._last_bar: ContinuousBarObservation | None = None
        self._lineage_hashes: list[str] = []
        self._quality_flags: set[str] = set()
        self._last_bar_end_utc: datetime | None = None
        self.incomplete_session_count = 0

    def update(self, bar: ContinuousBarObservation) -> ContinuousSessionCloseObservation | None:
        """Consume one completed bar and emit the prior session only after its exact close."""

        self._validate_identity_and_order(bar)
        emitted: ContinuousSessionCloseObservation | None = None
        if self._current_session_id is not None and bar.session_id != self._current_session_id:
            emitted = self._build_current_session_close(bar.available_at_utc)
            self._reset_session_state()
        if self._current_session_id is None:
            self._current_session_id = bar.session_id
        if self._last_bar is not None and self._last_bar.mapped_contract != bar.mapped_contract:
            self._quality_flags.add("MAPPED_CONTRACT_CHANGED_WITHIN_SESSION")
        self._last_bar = bar
        self._lineage_hashes.append(bar.source_lineage_hash)
        self._quality_flags.update(bar.quality_flags)
        self._last_bar_end_utc = bar.end_utc
        return emitted

    def finalize(self, available_at_utc: datetime) -> ContinuousSessionCloseObservation | None:
        """Emit the current session only if the last bar reaches the declared session end."""

        _require_utc(available_at_utc, "available_at_utc")
        emitted = self._build_current_session_close(available_at_utc)
        self._reset_session_state()
        return emitted

    def _validate_identity_and_order(self, bar: ContinuousBarObservation) -> None:
        if bar.root != self.root or bar.continuous_symbol != self.continuous_symbol:
            raise ContractBoundaryError("continuous close builder identity mismatch")
        if self._last_bar_end_utc is not None and bar.end_utc <= self._last_bar_end_utc:
            raise DataTimingInvariantError(
                "continuous bars must arrive in strictly increasing order"
            )

    def _build_current_session_close(
        self,
        available_at_utc: datetime,
    ) -> ContinuousSessionCloseObservation | None:
        bar = self._last_bar
        if bar is None:
            return None
        if bar.end_utc != bar.session_end_utc:
            self.incomplete_session_count += 1
            return None
        return ContinuousSessionCloseObservation(
            root=bar.root,
            continuous_symbol=bar.continuous_symbol,
            mapped_contract=bar.mapped_contract,
            session_id=bar.session_id,
            session_end_utc=bar.session_end_utc,
            available_at_utc=max(available_at_utc, bar.available_at_utc, bar.session_end_utc),
            close=bar.close,
            roll_state=bar.roll_state,
            source_lineage_hashes=tuple(self._lineage_hashes),
            quality_flags=tuple(sorted(self._quality_flags)),
        )

    def _reset_session_state(self) -> None:
        self._current_session_id = None
        self._last_bar = None
        self._lineage_hashes = []
        self._quality_flags = set()


__all__ = ("ContinuousSessionCloseBuilder",)

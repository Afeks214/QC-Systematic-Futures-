from __future__ import annotations

from datetime import datetime

from systematic_futures.data.point_in_time import ensure_aware_utc
from systematic_futures.domain.errors import ContractBoundaryError
from systematic_futures.domain.schemas import ContractSnapshot, validate_contract_snapshot


class FuturesContractManager:
    """Retain separate continuous and mapped identities through observed time."""

    def __init__(self) -> None:
        """Create an empty, instance-local contract observation store.

        Units: not applicable. Time semantics: no current clock is read.
        Missingness: no implicit initial contract exists. Raises: none.
        """
        self._snapshots: dict[str, list[ContractSnapshot]] = {}
        self._continuous_symbols: dict[str, str] = {}

    def observe_contract_snapshot(self, snapshot: ContractSnapshot) -> None:
        """Record one explicit, immutable as-of contract snapshot.

        Units: multiplier and tick retain QC-observed units. Time semantics:
        ``as_of_utc`` and expiry must be aware UTC; observations may be loaded
        historically but duplicate instants are rejected. Missingness: no field
        is inferred. Raises: ``ContractBoundaryError`` or schema-validation
        exceptions for inconsistent identity or duplicate observation time.
        """
        validate_contract_snapshot(snapshot)
        self.validate_symbol_relationship(
            snapshot.root,
            snapshot.continuous_symbol,
            snapshot.mapped_symbol,
        )
        root = _normalized_root(snapshot.root)
        history = self._snapshots.setdefault(root, [])
        if any(item.as_of_utc == snapshot.as_of_utc for item in history):
            raise ContractBoundaryError(
                f"duplicate contract observation time for {root}: {snapshot.as_of_utc.isoformat()}"
            )
        history.append(snapshot)
        history.sort(key=lambda item: item.as_of_utc)
        self._continuous_symbols.setdefault(root, snapshot.continuous_symbol)

    def current_snapshot(
        self,
        root: str,
        as_of_utc: datetime,
    ) -> ContractSnapshot:
        """Return the latest explicitly observed snapshot at ``as_of_utc``.

        Units: stored metadata units are unchanged. Time semantics: future
        observations are excluded and no future mapping is inferred.
        Missingness: absence of an eligible observation is rejected. Raises:
        ``TimeSemanticsError`` or ``ContractBoundaryError``.
        """
        normalized_root = _normalized_root(root)
        as_of = ensure_aware_utc(as_of_utc, "as_of_utc")
        history = self._snapshots.get(normalized_root, [])
        eligible = tuple(snapshot for snapshot in history if snapshot.as_of_utc <= as_of)
        if not eligible:
            raise ContractBoundaryError(
                f"no observed contract snapshot for {normalized_root} at {as_of.isoformat()}"
            )
        return eligible[-1]

    def validate_symbol_relationship(
        self,
        root: str,
        continuous_symbol: str,
        mapped_symbol: str,
    ) -> None:
        """Validate explicit continuous-to-mapped symbol separation.

        Units: not applicable. Time semantics: this method validates identity,
        not mapping time. Missingness: blank or identical symbols are rejected;
        no symbol is synthesized. Raises: ``ContractBoundaryError``.
        """
        normalized_root = _normalized_root(root)
        continuous = continuous_symbol.strip()
        mapped = mapped_symbol.strip()
        if not continuous or not mapped:
            raise ContractBoundaryError("continuous and mapped symbols must be non-blank")
        if continuous == mapped:
            raise ContractBoundaryError("continuous and mapped symbols must remain distinct")
        established = self._continuous_symbols.get(normalized_root)
        if established is not None and established != continuous:
            raise ContractBoundaryError(
                f"continuous identity changed for {normalized_root}: "
                f"{established!r} -> {continuous!r}"
            )


def _normalized_root(root: str) -> str:
    normalized = root.strip().upper()
    if not normalized:
        raise ContractBoundaryError("contract root must be non-blank")
    return normalized

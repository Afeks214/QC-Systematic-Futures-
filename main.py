from __future__ import annotations

from AlgorithmImports import QCAlgorithm, Slice, SymbolChangedEvents

from systematic_futures.qc_adapters.lift2_runtime import Lift2Runtime


class InstitutionalFuturesMeasurementAlgorithm(QCAlgorithm):
    """Read-only QuantConnect composition root for Lift 2 measurement."""

    def initialize(self) -> None:
        """Delegate all verified subscription and state construction to Lift2Runtime."""

        self._runtime = Lift2Runtime.create(self)

    def on_data(self, slice: Slice) -> None:  # noqa: A002
        """Delegate one QC Slice without embedding measurement formulas."""

        self._runtime.on_slice(self, slice)

    def on_symbol_changed_events(
        self,
        symbols_changed: SymbolChangedEvents,
    ) -> None:
        """Delegate delivered mapping changes for explicit contract reset."""

        self._runtime.on_mapping_events(self, symbols_changed)

    def on_end_of_algorithm(self) -> None:
        """Delegate compact measurement and zero-action evidence finalization."""

        self._runtime.finalize(self)

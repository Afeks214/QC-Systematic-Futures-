"""Research helper package with side-effect-free initialization.

Notebook and certification clients import their concrete helpers directly.  This
prevents QuantBook-facing modules from loading during a QC backtest import.
"""

__all__: tuple[str, ...] = ()

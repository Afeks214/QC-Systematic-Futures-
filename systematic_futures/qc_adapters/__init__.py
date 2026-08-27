"""QuantConnect adapter package with side-effect-free initialization.

Composition roots import the exact adapter they execute.  Importing this package must
never initialize CFTC, research, or measurement adapters as an incidental side effect.
"""

__all__: tuple[str, ...] = ()

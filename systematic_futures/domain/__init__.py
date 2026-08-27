"""Domain package with side-effect-free initialization.

Domain types and errors are imported from their defining modules.  This avoids
re-entering ``domain.enums`` while Python is resolving a direct submodule import in
restricted runtimes such as QuantConnect Cloud.
"""

from __future__ import annotations

__all__: tuple[str, ...] = ()

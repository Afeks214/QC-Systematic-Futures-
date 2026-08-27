"""Configuration package with side-effect-free initialization.

Import concrete registries from their defining submodules.  Keeping this initializer
empty prevents unrelated dataset policy construction when a runtime requests only the
market or research configuration module.
"""

__all__: tuple[str, ...] = ()

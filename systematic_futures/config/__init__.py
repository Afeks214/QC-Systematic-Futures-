"""Configuration package with side-effect-free initialization.

Import concrete registries from their defining submodules.  Keeping this initializer
empty prevents unrelated construction when a runtime requests one configuration module.
"""

__all__: tuple[str, ...] = ()

"""Compatibility facade for the frozen Lift 2 volume-profile module.

QuantConnect Cloud rejects a runtime file named ``profile.py`` because it
collides with Python's standard-library module.  Runtime code therefore imports
the implementation from :mod:`systematic_futures.measurement.volume_profile`;
this facade preserves the directive-specified public import path locally.
"""

from __future__ import annotations

from systematic_futures.measurement.volume_profile import (
    DEFAULT_PROFILE_DEFINITION,
    LOCAL_PRICE_SCALE_VERSION,
    MinuteVolumeBucket,
    VolumeProfileEngine,
    auction_features,
    auction_location,
    build_profile_snapshot,
    local_price_scale,
    price_to_tick,
    select_poc,
    select_value_area,
)

__all__ = (
    "DEFAULT_PROFILE_DEFINITION",
    "LOCAL_PRICE_SCALE_VERSION",
    "MinuteVolumeBucket",
    "VolumeProfileEngine",
    "auction_features",
    "auction_location",
    "build_profile_snapshot",
    "local_price_scale",
    "price_to_tick",
    "select_poc",
    "select_value_area",
)

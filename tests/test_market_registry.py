from __future__ import annotations

from systematic_futures.config.markets import (
    all_market_definitions,
    reference_market_definitions,
    validate_market_registry,
)


def test_market_registry_has_exact_candidates_and_references() -> None:
    markets = all_market_definitions()
    roots = tuple(market.root for market in markets)
    reference_roots = {market.root for market in reference_market_definitions()}

    assert len(markets) == 8
    assert len(set(roots)) == 8
    assert set(roots) == {"ES", "NQ", "RTY", "ZT", "ZN", "6E", "6J", "6B"}
    assert reference_roots == {"ES", "ZN", "6E"}
    assert validate_market_registry(markets) == ()

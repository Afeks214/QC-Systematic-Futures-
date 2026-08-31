from __future__ import annotations

from systematic_futures.config.markets import (
    all_market_definitions,
    get_market_definition,
    reference_market_definitions,
    validate_market_registry,
)
from systematic_futures.data.sessions import reference_session_policies


def test_market_registry_has_exact_candidates_and_references() -> None:
    markets = all_market_definitions()
    roots = tuple(market.root for market in markets)
    reference_roots = {market.root for market in reference_market_definitions()}

    assert len(markets) == 8
    assert len(set(roots)) == 8
    assert set(roots) == {"ES", "NQ", "RTY", "ZT", "ZN", "6E", "6J", "6B"}
    assert reference_roots == {"ES", "ZN", "6E"}
    assert validate_market_registry(markets) == ()


def test_market_master_is_complete_and_tick_value_reconciles() -> None:
    policies = reference_session_policies()

    for market in all_market_definitions():
        assert market.exchange in {"CME", "CBOT"}
        assert market.currency == "USD"
        assert market.minimum_tick > 0
        assert market.multiplier > 0
        assert market.tick_value == market.minimum_tick * market.multiplier
        assert market.qc_root_identity.startswith("Futures.")
        assert market.semantic_session_policy_id
        assert market.holiday_calendar_policy_id
        assert market.mapping_mode == "OPEN_INTEREST"
        assert market.signal_normalization_mode == "BACKWARDS_RATIO"
        assert market.contract_depth_offset == 0
        assert market.roll_policy_id == "mapping-observation-measurement-v1"
        assert market.execution_identity_policy == "ACTUAL_CONTRACT_ONLY"
        assert market.certification_status.value == "certified_current_lean_reference"
        assert market.source_evidence_lineage
        assert market.root in policies


def test_market_master_has_no_generic_fallback() -> None:
    assert get_market_definition("ES").root == "ES"
    try:
        get_market_definition("UNKNOWN")
    except Exception as error:
        assert "Unknown market root" in str(error)
    else:
        raise AssertionError("unknown root was silently substituted")

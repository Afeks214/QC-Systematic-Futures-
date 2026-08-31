from datetime import UTC, datetime, timedelta

import pytest

from systematic_futures.config.auction import AuctionResearchPolicy
from systematic_futures.domain.enums import (
    AuctionLocationState,
    AuctionPhase,
    AuctionTransitionType,
    RollState,
)
from systematic_futures.domain.errors import DataTimingInvariantError
from systematic_futures.hypotheses.h2_h3 import (
    H2_HYPOTHESIS_ID,
    H3_HYPOTHESIS_ID,
    H2H3HypothesisEngine,
    build_h2_template,
    build_h3_template,
)
from systematic_futures.measurement.auction_state import AuctionStateMachineV2
from systematic_futures.measurement.state_models import (
    AuctionFeatureVector,
    AuctionStateSnapshot,
    PriceScale,
    ProfileReferenceSet,
)

BASE = datetime(2026, 8, 31, 13, 0, tzinfo=UTC)


def policy() -> AuctionResearchPolicy:
    return AuctionResearchPolicy(
        version="asr_research_policy_test_v1",
        minimum_excursion_vol=0.25,
        minimum_outside_minutes=10,
        minimum_volume_outside_ratio=0.30,
        minimum_close_persistence_ratio=0.75,
        minimum_poc_migration_vol=0.10,
        minimum_value_migration_vol=0.10,
        required_migration_blocks=1,
        max_failure_window_minutes=30,
        candidate_validity_minutes=30,
    )


def auction_snapshot(
    minute: int,
    location: AuctionLocationState,
    *,
    side: int = 0,
    distance: float = 0.0,
    outside_minutes: int = 0,
    outside_volume: float = 0.0,
    migration: float = 0.0,
    reentry_count: int = 0,
    excursion_id: str | None = None,
    session_id: str = "ES:RTH:2026-08-31",
) -> AuctionStateSnapshot:
    as_of = BASE + timedelta(minutes=minute)
    distance_to_vah = distance if side == 1 else 0.0
    distance_to_val = -distance if side == -1 else 0.0
    features = AuctionFeatureVector(
        distance_to_current_poc_ticks=0.0,
        distance_to_current_poc_vol=0.0,
        distance_to_prior_poc_vol=0.0,
        distance_to_vah_vol=distance_to_vah,
        distance_to_val_vol=distance_to_val,
        value_area_width_vol=1.0,
        poc_migration_vol=side * migration,
        value_mid_migration_vol=side * migration,
        volume_above_poc_ratio=0.5,
        volume_outside_value_ratio=outside_volume,
        bar_close_outside_value_ratio=1.0 if side else 0.0,
        profile_entropy=0.5,
        profile_skew=0.0,
        profile_kurtosis=3.0,
        profile_overlap_ratio=0.5,
        reentry_count=reentry_count,
        consecutive_minutes_outside=outside_minutes,
        local_price_scale=PriceScale(
            value=1.0,
            observation_count=24,
            warmup_complete=True,
            version="atr_test_v1",
        ),
    )
    references = ProfileReferenceSet(
        prior_same_session_type_id="profile_prior",
        prior_rth_id="profile_prior",
        prior_eth_id=None,
        rolling_30m_id=None,
        rolling_60m_id=None,
        rolling_120m_id=None,
    )
    return AuctionStateSnapshot(
        snapshot_id=f"auction-{minute}-{side}",
        root="ES",
        contract_symbol="ESZ26",
        session_id=session_id,
        as_of_utc=as_of,
        available_at_utc=as_of,
        location_state=location,
        developing_profile_id=f"profile-{minute}",
        references=references,
        migration_reference_profile_id="profile_prior",
        features=features,
        active_excursion_id=excursion_id,
        measurement_ready=True,
        quality_flags=(),
        feature_version="auction_test_v1",
    )


def hypothesis_engine() -> H2H3HypothesisEngine:
    kwargs = {
        "eligible_markets": ("ES",),
        "preregistration_hash": "pre_registration_test_hash",
        "policy_version": policy().version,
        "candidate_validity_minutes": policy().candidate_validity_minutes,
    }
    return H2H3HypothesisEngine(
        build_h2_template(**kwargs),
        build_h3_template(**kwargs),
    )


def test_accepted_auction_uses_first_knowable_transition_time() -> None:
    machine = AuctionStateMachineV2("ES", "ESZ26", policy())
    engine = hypothesis_engine()

    balance = machine.update(auction_snapshot(0, AuctionLocationState.INSIDE_VALUE))
    initiative = machine.update(
        auction_snapshot(
            5,
            AuctionLocationState.ABOVE_VALUE,
            side=1,
            distance=0.50,
            outside_minutes=5,
            outside_volume=0.20,
            migration=0.02,
            excursion_id="excursion-up",
        )
    )
    accepted = machine.update(
        auction_snapshot(
            10,
            AuctionLocationState.ABOVE_VALUE,
            side=1,
            distance=0.75,
            outside_minutes=10,
            outside_volume=0.40,
            migration=0.20,
            excursion_id="excursion-up",
        )
    )

    assert balance.phase is AuctionPhase.BALANCE
    assert initiative.transition is AuctionTransitionType.BALANCE_TO_INITIATIVE
    assert accepted.phase is AuctionPhase.ACCEPTED
    assert accepted.transition is AuctionTransitionType.INITIATIVE_TO_ACCEPTANCE
    assert accepted.evidence is not None
    assert accepted.evidence.excursion_start_utc == BASE + timedelta(minutes=5)

    candidates = engine.evaluate(accepted, structural_snapshot_id="structural-es")
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.hypothesis_id == H2_HYPOTHESIS_ID
    assert candidate.excursion_start_time_utc == BASE + timedelta(minutes=5)
    assert candidate.candidate_time_utc == BASE + timedelta(minutes=10)
    assert candidate.side == 1
    assert dict(candidate.state_snapshot_ids)["structural"] == "structural-es"


def test_failed_auction_is_known_only_on_reentry_and_reverses_side() -> None:
    machine = AuctionStateMachineV2("ES", "ESZ26", policy())
    engine = hypothesis_engine()

    machine.update(auction_snapshot(0, AuctionLocationState.INSIDE_VALUE))
    machine.update(
        auction_snapshot(
            5,
            AuctionLocationState.ABOVE_VALUE,
            side=1,
            distance=0.50,
            outside_minutes=5,
            outside_volume=0.10,
            migration=0.0,
            excursion_id="excursion-fail",
        )
    )
    failed = machine.update(
        auction_snapshot(
            15,
            AuctionLocationState.INSIDE_VALUE,
            reentry_count=1,
            excursion_id=None,
        )
    )

    assert failed.phase is AuctionPhase.FAILED
    assert failed.transition is AuctionTransitionType.INITIATIVE_TO_FAILURE
    assert failed.evidence is not None
    assert failed.evidence.reentry_speed_minutes == 10.0

    candidates = engine.evaluate(failed)
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.hypothesis_id == H3_HYPOTHESIS_ID
    assert candidate.excursion_side == 1
    assert candidate.side == -1
    assert candidate.candidate_time_utc == BASE + timedelta(minutes=15)


def test_expired_initiative_is_not_mislabeled_as_failed() -> None:
    machine = AuctionStateMachineV2("ES", "ESZ26", policy())
    engine = hypothesis_engine()

    machine.update(auction_snapshot(0, AuctionLocationState.INSIDE_VALUE))
    machine.update(
        auction_snapshot(
            5,
            AuctionLocationState.BELOW_VALUE,
            side=-1,
            distance=0.50,
            outside_minutes=5,
            outside_volume=0.10,
            migration=0.0,
            excursion_id="excursion-expired",
        )
    )
    expired = machine.update(
        auction_snapshot(40, AuctionLocationState.INSIDE_VALUE, reentry_count=1)
    )

    assert expired.phase is AuctionPhase.BALANCE
    assert expired.transition is AuctionTransitionType.INITIATIVE_EXPIRED
    assert engine.evaluate(expired) == ()


def test_roll_transition_suppresses_candidate_generation() -> None:
    machine = AuctionStateMachineV2("ES", "ESZ26", policy())
    engine = hypothesis_engine()

    machine.update(auction_snapshot(0, AuctionLocationState.INSIDE_VALUE))
    suppressed = machine.update(
        auction_snapshot(
            5,
            AuctionLocationState.ABOVE_VALUE,
            side=1,
            distance=1.0,
            outside_minutes=5,
            outside_volume=0.8,
            migration=0.5,
            excursion_id="roll-excursion",
        ),
        roll_state=RollState.ROLL_TRANSITION,
    )

    assert suppressed.phase is AuctionPhase.ROLL_TRANSITION
    assert suppressed.transition is AuctionTransitionType.ROLL_TRANSITION
    assert suppressed.side == 0
    assert engine.evaluate(suppressed) == ()


@pytest.mark.metamorphic_math
def test_bull_bear_mirror_preserves_evidence_magnitude() -> None:
    def run(side: int) -> tuple[float, float, int]:
        machine = AuctionStateMachineV2("ES", "ESZ26", policy())
        engine = hypothesis_engine()
        outside = (
            AuctionLocationState.ABOVE_VALUE if side == 1 else AuctionLocationState.BELOW_VALUE
        )
        machine.update(auction_snapshot(0, AuctionLocationState.INSIDE_VALUE))
        machine.update(
            auction_snapshot(
                5,
                outside,
                side=side,
                distance=0.50,
                outside_minutes=5,
                outside_volume=0.20,
                migration=0.02,
                excursion_id=f"excursion-{side}",
            )
        )
        accepted = machine.update(
            auction_snapshot(
                10,
                outside,
                side=side,
                distance=0.75,
                outside_minutes=10,
                outside_volume=0.40,
                migration=0.20,
                excursion_id=f"excursion-{side}",
            )
        )
        assert accepted.evidence is not None
        candidate = engine.evaluate(accepted)[0]
        return (
            accepted.evidence.excursion_distance_vol or 0.0,
            accepted.evidence.poc_migration_vol or 0.0,
            candidate.side,
        )

    bullish = run(1)
    bearish = run(-1)
    assert bullish[:2] == bearish[:2]
    assert bullish[2] == -bearish[2]


def test_candidate_generation_is_append_once_per_transition() -> None:
    machine = AuctionStateMachineV2("ES", "ESZ26", policy())
    engine = hypothesis_engine()
    machine.update(auction_snapshot(0, AuctionLocationState.INSIDE_VALUE))
    machine.update(
        auction_snapshot(
            5,
            AuctionLocationState.ABOVE_VALUE,
            side=1,
            distance=0.50,
            outside_minutes=5,
            outside_volume=0.20,
            migration=0.02,
            excursion_id="dedup-excursion",
        )
    )
    accepted = machine.update(
        auction_snapshot(
            10,
            AuctionLocationState.ABOVE_VALUE,
            side=1,
            distance=0.75,
            outside_minutes=10,
            outside_volume=0.40,
            migration=0.20,
            excursion_id="dedup-excursion",
        )
    )

    first = engine.evaluate(accepted)
    second = engine.evaluate(accepted)
    assert len(first) == 1
    assert second == ()


@pytest.mark.causality_math
def test_asr_rejects_non_increasing_snapshot_time() -> None:
    machine = AuctionStateMachineV2("ES", "ESZ26", policy())
    snapshot = auction_snapshot(0, AuctionLocationState.INSIDE_VALUE)
    machine.update(snapshot)
    with pytest.raises(DataTimingInvariantError):
        machine.update(snapshot)

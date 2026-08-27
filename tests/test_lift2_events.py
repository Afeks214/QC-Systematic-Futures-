from __future__ import annotations

from dataclasses import fields
from datetime import UTC, datetime, timedelta

import pytest

from systematic_futures.domain.enums import (
    AuctionLocationState,
    CandidateEventType,
    ProfileKind,
    SessionType,
)
from systematic_futures.domain.errors import DuplicateIdentifierError
from systematic_futures.measurement.events import (
    AuctionTransitionEngine,
    CandidateEventGenerator,
    SnapshotAligner,
    candidate_coverage,
)
from systematic_futures.measurement.profile import (
    DEFAULT_PROFILE_DEFINITION,
    build_profile_snapshot,
)
from systematic_futures.measurement.types import (
    AuctionFeatureVector,
    AuctionStateSnapshot,
    CandidateEventObservation,
    IAEStateSnapshot,
    ICMStateSnapshot,
    IMSIStateSnapshot,
)


def _profile(timestamp: datetime):  # type: ignore[no-untyped-def]
    return build_profile_snapshot(
        root="ES",
        contract_symbol="ESH24",
        session_id="session-a",
        profile_kind=ProfileKind.FINAL_SESSION,
        as_of_utc=timestamp,
        available_at_utc=timestamp,
        definition=DEFAULT_PROFILE_DEFINITION,
        tick_size=1.0,
        current_price_tick=100,
        volume_by_tick={99: 20.0, 100: 60.0, 101: 20.0},
        expected_total_volume=100.0,
    )


def _features() -> AuctionFeatureVector:
    return AuctionFeatureVector(
        distance_to_current_poc_ticks=0,
        distance_to_prior_poc_vol=None,
        distance_to_vah_vol=None,
        distance_to_val_vol=None,
        value_area_width_vol=None,
        poc_migration_vol=None,
        value_mid_migration_vol=None,
        volume_above_poc_ratio=0.2,
        volume_outside_value_ratio=None,
        time_outside_value_ratio=None,
        profile_entropy=0.5,
        profile_skew=0,
        profile_kurtosis=1,
        profile_overlap_ratio=1,
        reentry_count=0,
        consecutive_minutes_outside=0,
        atr_5m_24=None,
        normalization_version="atr_5m_24_arithmetic_tr_v1",
    )


def _auction(timestamp: datetime) -> AuctionStateSnapshot:
    return AuctionStateSnapshot(
        snapshot_id=f"auction-{timestamp.isoformat()}",
        root="ES",
        contract_symbol="ESH24",
        session_id="session-a",
        as_of_utc=timestamp,
        available_at_utc=timestamp,
        location_state=AuctionLocationState.INSIDE_VALUE,
        developing_profile_id="profile-current",
        prior_profile_id="profile-prior",
        features=_features(),
        active_excursion_id=None,
        quality_flags=(),
        feature_version="feature_semantics_math_v4",
    )


def _imsi(timestamp: datetime, suffix: str) -> IMSIStateSnapshot:
    return IMSIStateSnapshot(
        snapshot_id=f"imsi-{suffix}",
        root="ES",
        contract_symbol="ESH24",
        as_of_utc=timestamp,
        available_at_utc=timestamp,
        vwrsi_raw=50,
        vwrsi_tod_adjusted=0,
        session_vwap=100,
        dist_vwap_pct=0,
        mahalanobis_distance=1,
        state_rarity_percentile=0.5,
        neighbor_distance_mean=1,
        neighbor_distance_p90=2,
        neighbor_support=15,
        covariance_shrinkage_delta=0.5,
        covariance_effective_sample_size=20,
        covariance_condition_number=2,
        warmup_complete=True,
        quality_flags=(),
        version="imsi-v1",
    )


def _icm(timestamp: datetime) -> ICMStateSnapshot:
    return ICMStateSnapshot(
        snapshot_id="icm-old",
        root="ES",
        contract_symbol="ESH24",
        as_of_utc=timestamp,
        available_at_utc=timestamp,
        fair_value=100,
        z_raw=1,
        z_capped=1,
        z_effective=1,
        slope_per_bar=1,
        slope_normalized=1,
        curvature_per_bar2=0,
        curvature_normalized=0,
        sigma_ols=1,
        sigma_mad=1,
        sigma_blend=1,
        r_ratio=1,
        window_size=70,
        warmup_complete=True,
        quality_flags=(),
        version="icm-v1",
    )


def _iae(timestamp: datetime) -> IAEStateSnapshot:
    return IAEStateSnapshot(
        snapshot_id="iae-current",
        root="ES",
        contract_symbol="ESH24",
        as_of_utc=timestamp,
        available_at_utc=timestamp,
        gap_id=None,
        direction=None,
        gap_state=None,
        gap_width_atr=None,
        impulse_body_atr=None,
        displacement_efficiency=None,
        formation_quality=None,
        gap_age_bars=None,
        time_decay=None,
        retest_depth_ratio=None,
        wick_absorption_ratio=None,
        close_position_ratio=None,
        tod_volume_z=None,
        score_raw=None,
        score_effective=None,
        absorption_confirmed=False,
        active_gap_count=0,
        quality_flags=(),
        version="iae-v1",
    )


def test_auction_transitions_emit_once_with_exact_parent_and_poc_migration() -> None:
    start = datetime(2024, 3, 4, 10, tzinfo=UTC)
    prior = _profile(start - timedelta(days=1))
    engine = AuctionTransitionEngine("ES", "ESH24")
    assert (
        engine.advance(
            session_id="session-a",
            location=AuctionLocationState.INSIDE_VALUE,
            developing_poc_tick=100,
            prior_profile=prior,
            event_time_utc=start,
            available_at_utc=start,
        )
        == ()
    )
    exit_triggers = engine.advance(
        session_id="session-a",
        location=AuctionLocationState.ABOVE_VALUE,
        developing_poc_tick=100,
        prior_profile=prior,
        event_time_utc=start + timedelta(minutes=5),
        available_at_utc=start + timedelta(minutes=5),
    )
    assert len(exit_triggers) == 1
    assert exit_triggers[0].event_type is CandidateEventType.VALUE_EXIT_UP
    exit_id = engine.active_excursion_id
    assert exit_id is not None
    migration = engine.advance(
        session_id="session-a",
        location=AuctionLocationState.ABOVE_VALUE,
        developing_poc_tick=102,
        prior_profile=prior,
        event_time_utc=start + timedelta(minutes=10),
        available_at_utc=start + timedelta(minutes=10),
    )
    assert len(migration) == 1
    assert migration[0].event_type is CandidateEventType.POC_MIGRATION_ABOVE_PRIOR_VAH
    assert migration[0].parent_event_id == exit_id
    assert (
        engine.advance(
            session_id="session-a",
            location=AuctionLocationState.ABOVE_VALUE,
            developing_poc_tick=103,
            prior_profile=prior,
            event_time_utc=start + timedelta(minutes=15),
            available_at_utc=start + timedelta(minutes=15),
        )
        == ()
    )
    reentry = engine.advance(
        session_id="session-a",
        location=AuctionLocationState.INSIDE_VALUE,
        developing_poc_tick=101,
        prior_profile=prior,
        event_time_utc=start + timedelta(minutes=20),
        available_at_utc=start + timedelta(minutes=20),
    )
    assert len(reentry) == 1
    assert reentry[0].parent_event_id == exit_id
    assert engine.reentry_count == 1


def test_alignment_is_asof_only_and_missing_components_are_retained() -> None:
    at_1000 = datetime(2024, 3, 4, 10, tzinfo=UTC)
    at_1005 = at_1000 + timedelta(minutes=5)
    aligner = SnapshotAligner()
    aligner.add_imsi(_imsi(at_1000, "old"))
    aligner.add_icm(_icm(at_1000))
    aligner.add_iae(_iae(at_1005))
    aligner.add_imsi(_imsi(at_1005 + timedelta(minutes=1), "future"))
    synergy = aligner.align(_auction(at_1005), at_1005)
    assert synergy.imsi_snapshot_id == "imsi-old"
    assert synergy.icm_snapshot_id == "icm-old"
    assert synergy.iae_snapshot_id == "iae-current"
    assert synergy.all_required_inputs_available

    missing = SnapshotAligner().align(_auction(at_1005), at_1005)
    assert missing.imsi_snapshot_id is None
    assert missing.icm_snapshot_id is None
    assert missing.iae_snapshot_id is None
    assert not missing.all_required_inputs_available


def test_candidate_ids_deduplicate_and_coverage_contains_only_breadth() -> None:
    timestamp = datetime(2024, 3, 4, 10, 5, tzinfo=UTC)
    transition = AuctionTransitionEngine("ES", "ESH24")
    prior = _profile(timestamp - timedelta(days=1))
    transition.advance(
        session_id="session-a",
        location=AuctionLocationState.INSIDE_VALUE,
        developing_poc_tick=100,
        prior_profile=prior,
        event_time_utc=timestamp - timedelta(minutes=5),
        available_at_utc=timestamp - timedelta(minutes=5),
    )
    trigger = transition.advance(
        session_id="session-a",
        location=AuctionLocationState.ABOVE_VALUE,
        developing_poc_tick=100,
        prior_profile=prior,
        event_time_utc=timestamp,
        available_at_utc=timestamp,
    )[0]
    auction = _auction(timestamp)
    synergy = SnapshotAligner().align(auction, timestamp)
    generator = CandidateEventGenerator()
    event = generator.create(trigger, auction, synergy)
    assert event.event_id == transition.active_excursion_id
    with pytest.raises(DuplicateIdentifierError):
        generator.create(trigger, auction, synergy)
    coverage = candidate_coverage(
        generator.events,
        {synergy.snapshot_id: synergy},
        {"session-a": SessionType.RTH},
        raw_event_count=1,
    )
    assert coverage["unique_event_count"] == 1
    assert coverage["by_root"] == {"ES": 1}
    assert coverage["events_with_all_three"] == 0
    assert not any(
        forbidden in key.lower()
        for key in coverage
        for forbidden in ("return", "profit", "sharpe", "win_rate")
    )


def test_candidate_schema_cannot_contain_outcome_fields() -> None:
    names = {field.name.lower() for field in fields(CandidateEventObservation)}
    forbidden = {
        "forward_return",
        "net_return",
        "p&l",
        "target",
        "stop",
        "sharpe",
        "hit",
        "profit",
        "loss",
        "probability",
        "expected_return",
    }
    assert names.isdisjoint(forbidden)

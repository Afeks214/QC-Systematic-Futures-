from __future__ import annotations

from dataclasses import fields
from datetime import UTC, datetime, timedelta

import pytest

from systematic_futures.domain.enums import (
    AuctionLocationState,
    CandidateEventType,
    IAEGapDirection,
    IAEGapState,
    ProfileKind,
    SessionType,
)
from systematic_futures.domain.errors import DuplicateIdentifierError
from systematic_futures.measurement.events import (
    AuctionTransitionEngine,
    CandidateEventGenerator,
    EventTrigger,
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
    PriceScale,
    ProfileReferenceSet,
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
        distance_to_current_poc_vol=None,
        distance_to_prior_poc_vol=None,
        distance_to_vah_vol=None,
        distance_to_val_vol=None,
        value_area_width_vol=None,
        poc_migration_vol=None,
        value_mid_migration_vol=None,
        volume_above_poc_ratio=0.2,
        volume_outside_value_ratio=None,
        bar_close_outside_value_ratio=None,
        profile_entropy=0.5,
        profile_skew=0,
        profile_kurtosis=1,
        profile_overlap_ratio=1,
        reentry_count=0,
        consecutive_minutes_outside=0,
        local_price_scale=PriceScale(
            value=1,
            observation_count=24,
            warmup_complete=True,
            version="atr_5m_24_arithmetic_tr_floor_1e-6_v2",
        ),
    )


def _auction(
    timestamp: datetime,
    *,
    measurement_ready: bool = True,
    quality_flags: tuple[str, ...] = (),
    session_id: str = "session-a",
) -> AuctionStateSnapshot:
    return AuctionStateSnapshot(
        snapshot_id=f"auction-{timestamp.isoformat()}",
        root="ES",
        contract_symbol="ESH24",
        session_id=session_id,
        as_of_utc=timestamp,
        available_at_utc=timestamp,
        location_state=AuctionLocationState.INSIDE_VALUE,
        developing_profile_id="profile-current",
        references=ProfileReferenceSet(
            prior_same_session_type_id="profile-prior",
            prior_rth_id="profile-prior",
            prior_eth_id=None,
            rolling_30m_id=None,
            rolling_60m_id=None,
            rolling_120m_id=None,
        ),
        migration_reference_profile_id="profile-prior",
        features=_features(),
        active_excursion_id=None,
        measurement_ready=measurement_ready,
        quality_flags=quality_flags,
        feature_version="feature_semantics_math_v5",
    )


def _imsi(
    timestamp: datetime,
    suffix: str,
    *,
    session_id: str = "session-a",
    quality_flags: tuple[str, ...] = (),
    measurement_ready: bool = True,
) -> IMSIStateSnapshot:
    return IMSIStateSnapshot(
        snapshot_id=f"imsi-{suffix}",
        root="ES",
        contract_symbol="ESH24",
        session_id=session_id,
        as_of_utc=timestamp,
        available_at_utc=timestamp,
        vwrsi_raw=50,
        vwrsi_tod_adjusted=0,
        session_vwap=100,
        dist_vwap_pct=0,
        mahalanobis_distance=1 if measurement_ready else None,
        state_rarity_percentile=0.5 if measurement_ready else None,
        neighbor_distance_mean=1 if measurement_ready else None,
        neighbor_distance_p90=2 if measurement_ready else None,
        neighbor_support=15 if measurement_ready else 0,
        covariance_shrinkage_delta=0.5 if measurement_ready else None,
        covariance_effective_sample_size=20 if measurement_ready else None,
        covariance_condition_number=2 if measurement_ready else None,
        warmup_complete=measurement_ready,
        measurement_ready=measurement_ready,
        quality_flags=quality_flags,
        version="imsi-v1",
    )


def _icm(timestamp: datetime) -> ICMStateSnapshot:
    return ICMStateSnapshot(
        snapshot_id="icm-old",
        root="ES",
        contract_symbol="ESH24",
        session_id="session-a",
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
        fair_value_distance_vol=0,
        residual_autocorrelation=0,
        window_size=70,
        warmup_complete=True,
        measurement_ready=True,
        quality_flags=(),
        version="icm-v1",
    )


def _iae(timestamp: datetime, *, score_ready: bool = False) -> IAEStateSnapshot:
    return IAEStateSnapshot(
        snapshot_id="iae-current",
        root="ES",
        contract_symbol="ESH24",
        session_id="session-a",
        as_of_utc=timestamp,
        available_at_utc=timestamp,
        gap_id="gap-current",
        direction=IAEGapDirection.BULLISH,
        gap_state=IAEGapState.OPEN,
        gap_width_atr=1,
        impulse_body_atr=2,
        displacement_efficiency=0.8,
        formation_quality=1,
        gap_age_bars=0,
        time_decay=1 if score_ready else None,
        retest_depth_ratio=0.5 if score_ready else None,
        wick_rejection_ratio=1 if score_ready else None,
        close_position_raw=0.5 if score_ready else None,
        close_position_score=0.5 if score_ready else None,
        tod_volume_z_raw=1 if score_ready else None,
        tod_volume_score_input=1 if score_ready else None,
        score_raw=2 if score_ready else None,
        score_effective=2 if score_ready else None,
        absorption_confirmed=False,
        active_gap_count=1,
        measurement_ready=True,
        score_ready=score_ready,
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
    assert synergy.all_required_inputs_present
    assert synergy.all_required_inputs_fresh
    assert synergy.all_required_inputs_ready

    missing = SnapshotAligner().align(_auction(at_1005), at_1005)
    assert missing.imsi_snapshot_id is None
    assert missing.icm_snapshot_id is None
    assert missing.iae_snapshot_id is None
    assert not missing.all_required_inputs_present
    assert not missing.all_required_inputs_fresh
    assert not missing.all_required_inputs_ready


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
    assert coverage["candidate_events_not_ready"] == 0
    assert coverage["candidate_events_base_ready"] == 1
    assert event.research_ready
    assert event.readiness.base_event_ready
    assert not event.readiness.imsi_state_ready
    assert not event.readiness.icm_state_ready
    assert not event.readiness.iae_structural_ready
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


def test_alignment_never_leaks_a_previous_session_snapshot() -> None:
    event_time = datetime(2024, 3, 4, 10, 5, tzinfo=UTC)
    aligner = SnapshotAligner()
    aligner.add_imsi(
        _imsi(
            event_time - timedelta(minutes=1),
            "previous-session",
            session_id="session-previous",
        )
    )
    previous_only = aligner.align(_auction(event_time), event_time)
    assert previous_only.imsi_snapshot_id is None
    assert "IMSI:MISSING" in previous_only.blocking_quality_flags

    aligner.add_imsi(_imsi(event_time - timedelta(minutes=1), "same-session"))
    same_session = aligner.align(_auction(event_time), event_time)
    assert same_session.imsi_snapshot_id == "imsi-same-session"


def test_quality_provenance_preserves_information_and_blocks_unready_math() -> None:
    event_time = datetime(2024, 3, 4, 10, 5, tzinfo=UTC)
    informational = SnapshotAligner()
    informational.add_imsi(
        _imsi(
            event_time,
            "info",
            quality_flags=("IMSI_FULL_MODEL_DEFERRED_LIFT3",),
        )
    )
    informational.add_icm(_icm(event_time))
    informational.add_iae(_iae(event_time))
    ready = informational.align(_auction(event_time), event_time)
    assert ready.all_required_inputs_ready
    assert "IMSI:IMSI_FULL_MODEL_DEFERRED_LIFT3" in ready.component_quality_flags
    assert ready.blocking_quality_flags == ()

    blocked = SnapshotAligner()
    blocked.add_imsi(
        _imsi(
            event_time,
            "blocked",
            quality_flags=("IMSI_COVARIANCE_UNSTABLE",),
            measurement_ready=False,
        )
    )
    blocked.add_icm(_icm(event_time))
    blocked.add_iae(_iae(event_time))
    not_ready = blocked.align(_auction(event_time), event_time)
    assert not not_ready.all_required_inputs_ready
    assert "IMSI:IMSI_COVARIANCE_UNSTABLE" in not_ready.component_quality_flags
    assert "IMSI:MEASUREMENT_NOT_READY" in not_ready.blocking_quality_flags
    event = CandidateEventGenerator().create(
        EventTrigger(
            event_type=CandidateEventType.IAE_RETEST_BULL,
            event_time_utc=event_time,
            available_at_utc=event_time,
            session_id="session-a",
            direction=1,
            parent_event_id="gap-a",
        ),
        _auction(event_time),
        not_ready,
    )
    assert event.research_ready
    assert event.readiness.base_event_ready
    assert not event.readiness.imsi_state_ready
    assert event.quality_flags == not_ready.quality_flags


def test_ablation_readiness_is_incremental_and_iae_score_is_optional() -> None:
    event_time = datetime(2024, 3, 4, 10, 5, tzinfo=UTC)
    auction = _auction(event_time)
    aligner = SnapshotAligner()

    auction_only = aligner.align(auction, event_time)
    assert not auction_only.imsi_ready
    assert not auction_only.icm_ready
    assert not auction_only.iae_structural_ready

    aligner.add_imsi(_imsi(event_time, "ablation"))
    with_imsi = aligner.align(auction, event_time)
    assert with_imsi.imsi_ready
    assert not with_imsi.icm_ready

    aligner.add_icm(_icm(event_time))
    with_icm = aligner.align(auction, event_time)
    assert with_icm.imsi_ready and with_icm.icm_ready
    assert not with_icm.iae_structural_ready

    aligner.add_iae(_iae(event_time))
    structural = aligner.align(auction, event_time)
    assert structural.iae_structural_ready
    assert not structural.iae_score_ready
    assert structural.all_required_inputs_ready

    scored_aligner = SnapshotAligner()
    scored_aligner.add_imsi(_imsi(event_time, "scored"))
    scored_aligner.add_icm(_icm(event_time))
    scored_aligner.add_iae(_iae(event_time, score_ready=True))
    scored = scored_aligner.align(auction, event_time)
    assert scored.iae_structural_ready and scored.iae_score_ready


def test_maintenance_candidate_is_retained_but_base_blocked() -> None:
    event_time = datetime(2024, 3, 4, 10, 5, tzinfo=UTC)
    auction = _auction(
        event_time,
        measurement_ready=False,
        quality_flags=("SESSION:MAINTENANCE",),
        session_id="maintenance-session",
    )
    synergy = SnapshotAligner().align(auction, event_time)
    event = CandidateEventGenerator().create(
        EventTrigger(
            event_type=CandidateEventType.VALUE_EXIT_UP,
            event_time_utc=event_time,
            available_at_utc=event_time,
            session_id="maintenance-session",
            direction=1,
            parent_event_id="maintenance-excursion",
        ),
        auction,
        synergy,
    )
    assert not event.readiness.base_event_ready
    assert "SESSION:MAINTENANCE" in event.quality_flags
    coverage = candidate_coverage(
        (event,),
        {synergy.snapshot_id: synergy},
        {"maintenance-session": SessionType.MAINTENANCE},
    )
    assert coverage["candidate_events_base_not_ready"] == 1
    assert coverage["by_session_type"] == {"maintenance": 1}


def test_iae_override_binds_each_retest_to_its_exact_gap_snapshot() -> None:
    event_time = datetime(2024, 3, 4, 10, 5, tzinfo=UTC)
    aligner = SnapshotAligner()
    aligner.add_imsi(_imsi(event_time, "ready"))
    aligner.add_icm(_icm(event_time))
    latest = _iae(event_time)
    aligner.add_iae(latest)
    gap_a = IAEStateSnapshot(
        **{
            field.name: getattr(latest, field.name)
            for field in fields(IAEStateSnapshot)
            if field.name not in {"snapshot_id", "gap_id"}
        },
        snapshot_id="iae-gap-a",
        gap_id="gap-a",
    )
    gap_b = IAEStateSnapshot(
        **{
            field.name: getattr(latest, field.name)
            for field in fields(IAEStateSnapshot)
            if field.name not in {"snapshot_id", "gap_id"}
        },
        snapshot_id="iae-gap-b",
        gap_id="gap-b",
    )

    synergy_a = aligner.align(_auction(event_time), event_time, iae_override=gap_a)
    synergy_b = aligner.align(_auction(event_time), event_time, iae_override=gap_b)
    assert synergy_a.iae_snapshot_id == "iae-gap-a"
    assert synergy_b.iae_snapshot_id == "iae-gap-b"
    assert synergy_a.snapshot_id != synergy_b.snapshot_id

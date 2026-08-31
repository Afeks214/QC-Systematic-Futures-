"""Symbolic H2/H3 candidate generation from ASR transitions."""

from datetime import timedelta

from systematic_futures.domain.enums import (
    AuctionTransitionType,
    BookType,
    HorizonFamily,
)
from systematic_futures.domain.errors import DataQualityError
from systematic_futures.domain.serialization import sha256_hex
from systematic_futures.hypotheses.contracts import CandidateEvent, HypothesisTemplate
from systematic_futures.measurement.auction_state import AuctionPhaseSnapshot

H2_HYPOTHESIS_ID = "H2_PROFILE_ACCEPTANCE"
H3_HYPOTHESIS_ID = "H3_FAILED_AUCTION"


def build_h2_template(
    *,
    eligible_markets: tuple[str, ...],
    preregistration_hash: str,
    policy_version: str,
    candidate_validity_minutes: int,
) -> HypothesisTemplate:
    """Build the H2 accepted-migration template without outcome-derived parameters."""

    return HypothesisTemplate(
        hypothesis_id=H2_HYPOTHESIS_ID,
        version=f"h2_accepted_auction_{policy_version}",
        book=BookType.TACTICAL_ALPHA,
        archetype="accepted_auction_migration",
        economic_mechanism=(
            "An initiative excursion that accumulates time, participation, persistence, "
            "and value-migration evidence may continue in the initiative direction."
        ),
        eligible_markets=eligible_markets,
        horizon_family=HorizonFamily.INTRADAY,
        forecast_horizons_minutes=(15, 30, 60),
        candidate_validity_minutes=candidate_validity_minutes,
        transition_name=AuctionTransitionType.INITIATIVE_TO_ACCEPTANCE.value,
        side_rule_id="candidate_side_equals_excursion_side",
        invalidation_rule_id="accepted_state_lost_or_reference_value_reentered",
        dedup_rule_id="one_candidate_per_hypothesis_excursion_transition",
        target_family_ids=("signed_forward_return", "mae_mfe", "acceptance_survival"),
        cost_policy_id="research_cost_unavailable_until_certified",
        risk_policy_id="no_capital_authority",
        preregistration_hash=preregistration_hash,
    )


def build_h3_template(
    *,
    eligible_markets: tuple[str, ...],
    preregistration_hash: str,
    policy_version: str,
    candidate_validity_minutes: int,
) -> HypothesisTemplate:
    """Build the H3 failed-auction template without outcome-derived parameters."""

    return HypothesisTemplate(
        hypothesis_id=H3_HYPOTHESIS_ID,
        version=f"h3_failed_auction_{policy_version}",
        book=BookType.TACTICAL_ALPHA,
        archetype="failed_auction_rejection",
        economic_mechanism=(
            "An initiative excursion that fails to mature acceptance and re-enters "
            "reference value may move back toward the prior distribution."
        ),
        eligible_markets=eligible_markets,
        horizon_family=HorizonFamily.INTRADAY,
        forecast_horizons_minutes=(15, 30, 60),
        candidate_validity_minutes=candidate_validity_minutes,
        transition_name=AuctionTransitionType.INITIATIVE_TO_FAILURE.value,
        side_rule_id="candidate_side_opposes_excursion_side",
        invalidation_rule_id="failed_auction_reestablishes_acceptance_outside_value",
        dedup_rule_id="one_candidate_per_hypothesis_excursion_transition",
        target_family_ids=("return_toward_prior_value", "mae_mfe", "time_to_prior_value"),
        cost_policy_id="research_cost_unavailable_until_certified",
        risk_policy_id="no_capital_authority",
        preregistration_hash=preregistration_hash,
    )


class H2H3HypothesisEngine:
    """Create append-once H2/H3 candidates from causal ASR transitions."""

    def __init__(
        self,
        h2_template: HypothesisTemplate,
        h3_template: HypothesisTemplate,
    ) -> None:
        if h2_template.hypothesis_id != H2_HYPOTHESIS_ID:
            raise DataQualityError("h2_template has the wrong hypothesis identity")
        if h3_template.hypothesis_id != H3_HYPOTHESIS_ID:
            raise DataQualityError("h3_template has the wrong hypothesis identity")
        if h2_template.eligible_markets != h3_template.eligible_markets:
            raise DataQualityError("H2 and H3 market universes must match")
        self._h2 = h2_template
        self._h3 = h3_template
        self._session_id: str | None = None
        self._seen: set[tuple[str, str, str]] = set()

    def evaluate(
        self,
        snapshot: AuctionPhaseSnapshot,
        structural_snapshot_id: str | None = None,
    ) -> tuple[CandidateEvent, ...]:
        """Create a candidate only on the first matching ASR transition.

        H1 structural state is attached for later conditioning but is never an H2/H3
        eligibility gate in this engine.
        """

        if snapshot.session_id != self._session_id:
            self._session_id = snapshot.session_id
            self._seen.clear()
        if not snapshot.measurement_ready or snapshot.evidence is None:
            return ()
        if snapshot.transition is AuctionTransitionType.INITIATIVE_TO_ACCEPTANCE:
            template = self._h2
            candidate_side = snapshot.side
        elif snapshot.transition is AuctionTransitionType.INITIATIVE_TO_FAILURE:
            template = self._h3
            candidate_side = -snapshot.side
        else:
            return ()
        if snapshot.root not in template.eligible_markets:
            return ()
        if snapshot.excursion_id is None or snapshot.excursion_start_utc is None:
            raise DataQualityError("candidate transition is missing excursion identity")

        dedup_key = (
            template.hypothesis_id,
            snapshot.excursion_id,
            snapshot.transition.value,
        )
        if dedup_key in self._seen:
            return ()
        self._seen.add(dedup_key)

        event_cluster_id = "cluster_" + sha256_hex(
            (
                snapshot.root,
                snapshot.contract_symbol,
                snapshot.session_id,
                snapshot.excursion_id,
                snapshot.side,
            )
        )
        candidate_id = "candidate_" + sha256_hex(
            (
                template.hypothesis_id,
                template.version,
                event_cluster_id,
                snapshot.as_of_utc,
                candidate_side,
            )
        )
        state_ids = {
            "asr_evidence": snapshot.evidence.evidence_id,
            "asr_state": snapshot.snapshot_id,
        }
        if structural_snapshot_id is not None:
            if not structural_snapshot_id.strip():
                raise DataQualityError("structural_snapshot_id must be non-blank")
            state_ids["structural"] = structural_snapshot_id
        hard_gates = dict(snapshot.gate_results)
        hard_gates["asr_measurement_ready"] = snapshot.measurement_ready
        hard_gates["transition_match"] = True
        hard_gates["roll_clear"] = snapshot.transition is not AuctionTransitionType.ROLL_TRANSITION
        lineage = {
            "candidate_id": candidate_id,
            "event_cluster_id": event_cluster_id,
            "hard_gate_results": tuple(sorted(hard_gates.items())),
            "hypothesis_id": template.hypothesis_id,
            "hypothesis_version": template.version,
            "state_snapshot_ids": tuple(sorted(state_ids.items())),
        }
        return (
            CandidateEvent(
                candidate_id=candidate_id,
                parent_event_id=snapshot.excursion_id,
                event_cluster_id=event_cluster_id,
                hypothesis_id=template.hypothesis_id,
                hypothesis_version=template.version,
                book=template.book,
                archetype=template.archetype,
                root=snapshot.root,
                actual_contract=snapshot.contract_symbol,
                session_id=snapshot.session_id,
                excursion_start_time_utc=snapshot.excursion_start_utc,
                candidate_time_utc=snapshot.as_of_utc,
                available_at_utc=snapshot.available_at_utc,
                excursion_side=snapshot.side,
                side=candidate_side,
                horizon_family=template.horizon_family,
                forecast_horizons_minutes=template.forecast_horizons_minutes,
                expires_at_utc=(
                    snapshot.available_at_utc
                    + timedelta(minutes=template.candidate_validity_minutes)
                ),
                state_snapshot_ids=tuple(sorted(state_ids.items())),
                hard_gate_results=tuple(sorted(hard_gates.items())),
                invalidation_rule_id=template.invalidation_rule_id,
                quality_flags=snapshot.quality_flags,
                lineage_hash=sha256_hex(lineage),
            ),
        )


__all__ = (
    "H2_HYPOTHESIS_ID",
    "H3_HYPOTHESIS_ID",
    "H2H3HypothesisEngine",
    "build_h2_template",
    "build_h3_template",
)

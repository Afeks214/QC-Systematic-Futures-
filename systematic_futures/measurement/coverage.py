from collections import Counter
from collections.abc import Callable, Mapping, Sequence

from systematic_futures.data.quality import measurement_quality_severity
from systematic_futures.domain.enums import MeasurementQualitySeverity, SessionType
from systematic_futures.domain.errors import DataQualityError, DuplicateIdentifierError
from systematic_futures.measurement.state_models import (
    CandidateEventObservation,
    IndicatorSynergySnapshot,
)


def candidate_coverage(
    events: Sequence[CandidateEventObservation],
    synergies: Mapping[str, IndicatorSynergySnapshot],
    session_types: Mapping[str, SessionType],
    *,
    raw_event_count: int | None = None,
) -> Mapping[str, object]:
    """Aggregate event breadth without price performance or repeated-row inflation.

    Units: counts and events per unique session. Time semantics: calendar month uses
    event UTC month; the report does not join later data. Missingness: an unknown
    session type is reported as `unknown`; missing synergy references do not drop an
    event. Raises: ``DataQualityError`` if the supplied raw count is smaller than the
    unique count.
    """

    records = tuple(events)
    unique_ids = {event.event_id for event in records}
    if len(unique_ids) != len(records):
        raise DuplicateIdentifierError("coverage input contains duplicate Event IDs")
    raw_count = len(records) if raw_event_count is None else raw_event_count
    if raw_count < len(records):
        raise DataQualityError("raw_event_count cannot be smaller than unique event count")
    by_root = Counter(event.root for event in records)
    by_type = Counter(event.event_type.value for event in records)
    by_contract = Counter(event.contract_symbol for event in records)
    by_month = Counter(event.event_time_utc.strftime("%Y-%m") for event in records)
    by_session_type = Counter(
        session_types.get(event.session_id, SessionType.UNKNOWN).value for event in records
    )
    unique_sessions = {event.session_id for event in records}
    resolved = [synergies.get(event.synergy_snapshot_id) for event in records]
    parent_ids = {event.parent_event_id for event in records if event.parent_event_id is not None}
    blocking_reasons: Counter[str] = Counter()
    informational_reasons: Counter[str] = Counter()
    warning_reasons: Counter[str] = Counter()
    blocking_by_root: dict[str, Counter[str]] = {}
    blocking_by_event_type: dict[str, Counter[str]] = {}
    for event in records:
        for flag in event.quality_flags:
            severity = measurement_quality_severity(flag)
            if severity is MeasurementQualitySeverity.BLOCKING:
                blocking_reasons[flag] += 1
                blocking_by_root.setdefault(event.root, Counter())[flag] += 1
                blocking_by_event_type.setdefault(event.event_type.value, Counter())[flag] += 1
            elif severity is MeasurementQualitySeverity.WARNING:
                warning_reasons[flag] += 1
            else:
                informational_reasons[flag] += 1

    readiness_by_contract: dict[str, dict[str, object]] = {}
    post_roll_contracts: set[str] = set()
    for contract_symbol in sorted(by_contract):
        contract_events = tuple(
            event for event in records if event.contract_symbol == contract_symbol
        )
        if any("ROLL:POST_ROLL" in event.quality_flags for event in contract_events):
            post_roll_contracts.add(contract_symbol)
        readiness_by_contract[contract_symbol] = {
            "first_event_utc": _first_event_time(contract_events, lambda event: True),
            "first_base_ready_event_utc": _first_event_time(
                contract_events, lambda event: event.readiness.base_event_ready
            ),
            "first_imsi_ready_event_utc": _first_event_time(
                contract_events, lambda event: event.readiness.imsi_state_ready
            ),
            "first_icm_ready_event_utc": _first_event_time(
                contract_events, lambda event: event.readiness.icm_state_ready
            ),
            "first_iae_structural_ready_event_utc": _first_event_time(
                contract_events, lambda event: event.readiness.iae_structural_ready
            ),
            "first_iae_score_ready_event_utc": _first_event_time(
                contract_events, lambda event: event.readiness.iae_score_ready
            ),
            "base_ready_count": sum(event.readiness.base_event_ready for event in contract_events),
            "imsi_ready_count": sum(event.readiness.imsi_state_ready for event in contract_events),
            "icm_ready_count": sum(event.readiness.icm_state_ready for event in contract_events),
            "iae_structural_ready_count": sum(
                event.readiness.iae_structural_ready for event in contract_events
            ),
            "iae_score_ready_count": sum(
                event.readiness.iae_score_ready for event in contract_events
            ),
        }
    return {
        "by_calendar_month": dict(sorted(by_month.items())),
        "by_contract": dict(sorted(by_contract.items())),
        "by_event_type": dict(sorted(by_type.items())),
        "by_root": dict(sorted(by_root.items())),
        "by_session_type": dict(sorted(by_session_type.items())),
        "events_per_session": len(records) / len(unique_sessions) if unique_sessions else 0.0,
        "events_with_IAE": sum(
            item is not None and item.iae_snapshot_id is not None for item in resolved
        ),
        "events_with_ICM": sum(
            item is not None and item.icm_snapshot_id is not None for item in resolved
        ),
        "events_with_IMSI": sum(
            item is not None and item.imsi_snapshot_id is not None for item in resolved
        ),
        "candidate_events_total": len(records),
        "candidate_events_inputs_present": sum(
            item is not None and item.all_required_inputs_present for item in resolved
        ),
        "candidate_events_inputs_ready": sum(
            item is not None and item.all_required_inputs_ready for item in resolved
        ),
        "candidate_events_not_ready": sum(not event.research_ready for event in records),
        "candidate_events_base_ready": sum(event.readiness.base_event_ready for event in records),
        "candidate_events_imsi_ready": sum(event.readiness.imsi_state_ready for event in records),
        "candidate_events_icm_ready": sum(event.readiness.icm_state_ready for event in records),
        "candidate_events_iae_structural_ready": sum(
            event.readiness.iae_structural_ready for event in records
        ),
        "candidate_events_iae_score_ready": sum(
            event.readiness.iae_score_ready for event in records
        ),
        "candidate_events_full_context_ready": sum(
            event.readiness.full_context_ready for event in records
        ),
        "candidate_events_base_not_ready": sum(
            not event.readiness.base_event_ready for event in records
        ),
        "candidate_events_missing_imsi": sum(
            item is None or item.imsi_snapshot_id is None for item in resolved
        ),
        "candidate_events_missing_icm": sum(
            item is None or item.icm_snapshot_id is None for item in resolved
        ),
        "candidate_events_missing_iae": sum(
            item is None or item.iae_snapshot_id is None for item in resolved
        ),
        "events_with_all_three": sum(
            item is not None and item.all_required_inputs_present for item in resolved
        ),
        "parent_excursion_count": len(parent_ids),
        "quality_blocked_events": sum(
            any(
                measurement_quality_severity(flag) is MeasurementQualitySeverity.BLOCKING
                for flag in event.quality_flags
            )
            for event in records
        ),
        "blocking_reason_counts": dict(sorted(blocking_reasons.items())),
        "informational_reason_counts": dict(sorted(informational_reasons.items())),
        "warning_reason_counts": dict(sorted(warning_reasons.items())),
        "blocking_reason_counts_by_root": {
            root: dict(sorted(counts.items())) for root, counts in sorted(blocking_by_root.items())
        },
        "blocking_reason_counts_by_event_type": {
            event_type: dict(sorted(counts.items()))
            for event_type, counts in sorted(blocking_by_event_type.items())
        },
        "readiness_by_contract": readiness_by_contract,
        "post_roll_contracts": sorted(post_roll_contracts),
        "raw_event_count": raw_count,
        "unique_event_count": len(records),
        "unique_session_count": len(unique_sessions),
    }


def _first_event_time(
    events: Sequence[CandidateEventObservation],
    predicate: Callable[[CandidateEventObservation], bool],
) -> str | None:
    matching = [event.event_time_utc for event in events if predicate(event)]
    if not matching:
        return None
    return min(matching).isoformat().replace("+00:00", "Z")


__all__ = ("candidate_coverage",)

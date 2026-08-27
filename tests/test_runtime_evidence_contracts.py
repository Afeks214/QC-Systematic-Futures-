from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from systematic_futures.data.rolls import RollManager
from systematic_futures.domain.enums import RollState
from systematic_futures.research_lib.certification import (
    QcFuturesRuntimeProbeArtifact,
    RuntimeMarketProbeEvidence,
    parse_roll_evidence,
    runtime_probe_content_hash,
    validate_qc_futures_runtime_probe_artifact,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _market(root: str) -> RuntimeMarketProbeEvidence:
    first = datetime(2024, 2, 15, 0, 0, tzinfo=UTC)
    last = datetime(2024, 3, 25, 23, 59, tzinfo=UTC)
    mapping_time = datetime(2024, 3, 13, 4, 0, tzinfo=UTC)
    return RuntimeMarketProbeEvidence(
        root=root,
        continuous_symbol=f"/{root}",
        first_data_time_utc=first,
        last_data_time_utc=last,
        rows_received=1,
        mapped_contracts_seen=(f"{root}H24", f"{root}M24"),
        mapped_contract_count=2,
        mapping_event_count=1,
        first_mapping_event_time_utc=mapping_time,
        last_mapping_event_time_utc=mapping_time,
        open_interest_observations=1,
        open_interest_non_null_observations=1,
        minimum_tick_observed=0.25,
        multiplier_observed=1.0,
        contract_expiries_seen=(datetime(2024, 3, 15, tzinfo=UTC),),
        missing_intervals_detected=0,
        session_ids_seen=("session_fixture",),
        roll_states_seen=(RollState.NORMAL, RollState.ROLL_TRANSITION),
        quality_flags=(),
    )


def test_real_probe_artifact_schema_requires_three_zero_trading_markets() -> None:
    artifact = QcFuturesRuntimeProbeArtifact(
        qc_project_id="synthetic-schema-fixture-project",
        qc_cloud_backtest_id="synthetic-schema-fixture-backtest",
        backtest_name="Lift 1 schema fixture",
        lean_version="synthetic-schema-fixture-version",
        compile_status="completed",
        backtest_status="completed",
        started_at_utc=datetime(2024, 3, 26, 0, 0, tzinfo=UTC),
        finished_at_utc=datetime(2024, 3, 26, 0, 1, tzinfo=UTC),
        markets=(_market("ES"), _market("ZN"), _market("6E")),
        orders_created=0,
        insights_created=0,
        portfolio_targets_created=0,
        probe_hash="0" * 64,
    )
    artifact = replace(artifact, probe_hash=runtime_probe_content_hash(artifact))

    validate_qc_futures_runtime_probe_artifact(artifact)


def test_roll_evidence_parser_preserves_future_visibility_boundary() -> None:
    rows = (
        {
            "root": "ES",
            "old_mapped_symbol": None,
            "new_mapped_symbol": "ESH24",
            "observed_at_utc": "2024-02-15T12:00:00Z",
            "effective_at_utc": "2024-02-15T12:00:00Z",
        },
        {
            "root": "ES",
            "old_mapped_symbol": "ESH24",
            "new_mapped_symbol": "ESM24",
            "observed_at_utc": "2024-03-01T12:00:00Z",
            "effective_at_utc": "2024-03-14T12:00:00Z",
        },
    )
    manager = RollManager()
    for observation in parse_roll_evidence(rows):
        manager.observe_mapping(observation)

    assert (
        manager.current_roll_state("ES", datetime(2024, 3, 13, 12, 0, tzinfo=UTC))
        is RollState.NORMAL
    )


def test_certified_qc_futures_artifact_has_three_observed_zero_action_markets() -> None:
    artifact = json.loads(
        (PROJECT_ROOT / "artifacts/certification/qc_futures_runtime_probe.json").read_text(
            encoding="utf-8"
        )
    )
    markets = {row["root"]: row for row in artifact["markets"]}

    assert artifact["certified_source_git_revision"] == ("cbfee265cbf5e94c7768667d469e2773f62e3080")
    assert artifact["execution"]["status"] == "COMPLETED"
    assert artifact["execution"]["orders_created"] == 0
    assert artifact["execution"]["insights_created"] == 0
    assert artifact["execution"]["portfolio_targets_created"] == 0
    assert set(markets) == {"ES", "ZN", "6E"}
    assert all(row["rows_received"] > 0 for row in markets.values())
    assert all(len(row["mapped_contracts_seen"]) == 2 for row in markets.values())
    assert all(row["mapping_event_count"] == 1 for row in markets.values())
    assert all(row["open_interest_non_null_observations"] > 0 for row in markets.values())
    assert all(
        row["roll_states_seen"] == ["normal", "post_roll", "roll_transition"]
        for row in markets.values()
    )
    assert (
        artifact["pythonnet_datetime_boundaries"]["symbol_changed_event_time"]["conversion_status"]
        == "WITHHELD_UNVERIFIED_SOURCE_TIMEZONE"
    )


def test_certified_cftc_artifact_preserves_early_delivery_and_official_gate() -> None:
    artifact = json.loads(
        (PROJECT_ROOT / "artifacts/certification/cftc_release_delivery_audit.json").read_text(
            encoding="utf-8"
        )
    )
    audits = {row["release_class"]: row for row in artifact["release_audits"]}

    assert artifact["certification_status"] == "CERTIFIED_CONTEXT"
    assert artifact["execution"]["orders_created"] == 0
    assert artifact["execution"]["insights_created"] == 0
    assert artifact["execution"]["portfolio_targets_created"] == 0
    assert [row["root"] for row in artifact["market_summaries"]] == ["ES", "ZN", "6E"]
    assert all(row["rows_received"] == 22 for row in artifact["market_summaries"])
    delayed = audits["HOLIDAY_DELAYED"]
    ordinary = audits["ORDINARY"]
    assert delayed["qc_delivery_precedes_official_release"] is True
    assert delayed["usable_from_utc"] == delayed["official_release_time_utc"]
    assert ordinary["qc_delivery_precedes_official_release"] is False
    assert ordinary["usable_from_utc"] == ordinary["official_release_time_utc"]
    assert len(delayed["deliveries"]) == len(ordinary["deliveries"]) == 3
    assert artifact["actual_qc_coverage"]["last_delivery_utc"].startswith("2026-05-29")

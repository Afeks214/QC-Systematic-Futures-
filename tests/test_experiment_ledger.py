from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from systematic_futures.domain.enums import ExperimentDecision
from systematic_futures.domain.errors import DuplicateIdentifierError
from systematic_futures.domain.identifiers import make_experiment_id
from systematic_futures.domain.schemas import ExperimentRecord
from systematic_futures.ledger.experiment_ledger import ExperimentLedger

_REGISTERED_AT = datetime(2024, 2, 1, 12, 0, tzinfo=UTC)


def _sample_experiment() -> ExperimentRecord:
    hypothesis_name = "Reference Futures Data Availability Audit"
    return ExperimentRecord(
        experiment_id=make_experiment_id(hypothesis_name, "1.0", _REGISTERED_AT),
        parent_experiment_id=None,
        hypothesis_name=hypothesis_name,
        hypothesis_version="1.0",
        registered_at_utc=_REGISTERED_AT,
        economic_rationale="Audit point-in-time data availability and contract identity.",
        expected_direction="No directional market claim.",
        target_definition="Data availability and mapping completeness only.",
        horizons_minutes=(),
        markets=("ES", "ZN", "6E"),
        exclusions=("Trading hypotheses",),
        development_period=("2024-02-15", "2024-03-01"),
        validation_period=("2024-03-02", "2024-03-15"),
        final_holdout_period=("2024-03-16", "2024-03-25"),
        planned_variants=1,
        decision=ExperimentDecision.PENDING,
        decision_reason="Pending completion of the reference data audit.",
    )


def test_duplicate_experiment_registration_is_rejected(tmp_path: Path) -> None:
    ledger = ExperimentLedger(tmp_path / "experiment_ledger.jsonl")
    record = _sample_experiment()

    ledger.pre_register(record)

    with pytest.raises(DuplicateIdentifierError):
        ledger.pre_register(record)


def test_mutating_historical_ledger_row_breaks_hash_chain(tmp_path: Path) -> None:
    path = tmp_path / "experiment_ledger.jsonl"
    ledger = ExperimentLedger(path)
    ledger.pre_register(_sample_experiment())
    row = json.loads(path.read_text(encoding="utf-8"))
    row["payload"]["economic_rationale"] = "Mutated after registration."
    path.write_text(json.dumps(row, separators=(",", ":")) + "\n", encoding="utf-8")

    assert ledger.verify_chain() is False

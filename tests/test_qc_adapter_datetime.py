from __future__ import annotations

from datetime import UTC, datetime

import pytest

from systematic_futures.domain.errors import TimeSemanticsError
from systematic_futures.qc_adapters.probe_recorder import qc_datetime_to_utc


def test_naive_qc_datetime_requires_explicit_source_timezone() -> None:
    value = datetime(2024, 3, 13, 0, 0)  # noqa: DTZ001 - boundary fixture is intentional

    with pytest.raises(TimeSemanticsError):
        qc_datetime_to_utc(value, "mapping_event_time")


def test_naive_qc_datetime_uses_documented_boundary_timezone() -> None:
    value = datetime(2024, 3, 13, 0, 0)  # noqa: DTZ001 - boundary fixture is intentional

    normalized = qc_datetime_to_utc(
        value,
        "mapping_event_time",
        naive_source_timezone="America/New_York",
    )

    assert normalized == datetime(2024, 3, 13, 4, 0, tzinfo=UTC)

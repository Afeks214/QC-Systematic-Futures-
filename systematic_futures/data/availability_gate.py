from __future__ import annotations

import heapq
from datetime import datetime

from systematic_futures.data.point_in_time import ensure_aware_utc
from systematic_futures.data.quality import ensure_quality_not_upgraded
from systematic_futures.domain.errors import DuplicateIdentifierError
from systematic_futures.domain.schemas import (
    CertifiedMarketEvent,
    PointInTimeDatum,
    validate_certified_market_event,
    validate_point_in_time_datum,
)

_TieKey = tuple[str, str, str, str, str, str]
_HeapEntry = tuple[datetime, _TieKey, PointInTimeDatum]


class AvailabilityGate:
    """Withhold normalized observations until their explicit usable time."""

    def __init__(self) -> None:
        """Create an empty gate with no global or shared state.

        Units: not applicable. Time semantics: no clock is read during
        construction. Missingness: not applicable. Raises: none.
        """
        self._pending: list[_HeapEntry] = []
        self._lineage_hashes: set[str] = set()
        self._released_hashes: set[str] = set()

    def submit(self, datum: PointInTimeDatum) -> None:
        """Submit one normalized datum to the release heap.

        Units: datum value units are unchanged. Time semantics: the gate stores
        the datum's existing usable timestamp and never rewrites it.
        Missingness: the datum's explicit status and missing reason are
        preserved. Raises: ``DuplicateIdentifierError`` for any reused lineage
        hash; schema validation exceptions propagate.
        """
        validate_point_in_time_datum(datum)
        if datum.lineage_hash in self._lineage_hashes:
            raise DuplicateIdentifierError(f"lineage hash already submitted: {datum.lineage_hash}")
        tie_key = _deterministic_tie_key(datum)
        heapq.heappush(self._pending, (datum.usable_from_utc, tie_key, datum))
        self._lineage_hashes.add(datum.lineage_hash)

    def release(self, now_utc: datetime) -> tuple[CertifiedMarketEvent, ...]:
        """Release all events whose usable time is at or before ``now_utc``.

        Units: UTC datetime. Time semantics: ``now_utc`` is explicit and aware;
        future items remain withheld; event timestamps are copied without
        backdating. Missingness: source quality and flags are retained exactly.
        Raises: ``TimeSemanticsError`` for a naive clock or
        ``DuplicateIdentifierError`` if internal re-release is detected.
        """
        now = ensure_aware_utc(now_utc, "now_utc")
        released: list[CertifiedMarketEvent] = []
        while self._pending and self._pending[0][0] <= now:
            _, _, datum = heapq.heappop(self._pending)
            if datum.lineage_hash in self._released_hashes:
                raise DuplicateIdentifierError(
                    f"lineage hash already released: {datum.lineage_hash}"
                )
            ensure_quality_not_upgraded(datum.quality_status, datum.quality_status)
            event = CertifiedMarketEvent(
                dataset_id=datum.dataset_id,
                series_id=datum.series_id,
                market=datum.market,
                instrument_id=datum.instrument_id,
                event_time_utc=datum.observation_time_utc,
                usable_from_utc=datum.usable_from_utc,
                released_at_utc=now,
                schema_version=datum.schema_version,
                quality_status=datum.quality_status,
                quality_flags=datum.quality_flags,
                value=datum.value,
                lineage_hash=datum.lineage_hash,
            )
            validate_certified_market_event(event)
            self._released_hashes.add(datum.lineage_hash)
            released.append(event)
        return tuple(released)

    def pending_count(self) -> int:
        """Return the number of currently withheld observations.

        Units: count. Time semantics: snapshot at call time. Missingness: not
        applicable. Raises: none.
        """
        return len(self._pending)

    def next_release_time(self) -> datetime | None:
        """Return the earliest pending usable time without removing it.

        Units: UTC datetime. Time semantics: the stored timestamp is returned
        unchanged. Missingness: returns ``None`` only when the gate is empty.
        Raises: none.
        """
        if not self._pending:
            return None
        return self._pending[0][0]


def _deterministic_tie_key(datum: PointInTimeDatum) -> _TieKey:
    return (
        datum.dataset_id,
        datum.series_id,
        datum.market or "",
        datum.instrument_id or "",
        datum.observation_time_utc.isoformat(),
        datum.lineage_hash,
    )

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from types import MappingProxyType
from typing import Any, cast
from zoneinfo import ZoneInfo

from systematic_futures.domain.errors import (
    ContractBoundaryError,
    MarketConfigurationError,
    UnverifiedQuantConnectApiError,
)
from systematic_futures.domain.serialization import canonical_json_bytes, sha256_hex
from systematic_futures.qc_adapters.probe_recorder import (
    qc_datetime_boundary_record,
    qc_datetime_to_utc,
    qc_symbol_text,
)

_REFERENCE_ROOTS = ("ES", "ZN", "6E")
_POSITION_FIELDS = (
    "asset_manager_long",
    "asset_manager_short",
    "asset_manager_spread",
    "dealer_long",
    "dealer_short",
    "dealer_spread",
    "leveraged_funds_long",
    "leveraged_funds_short",
    "leveraged_funds_spread",
    "non_reportable_long",
    "non_reportable_short",
    "open_interest",
    "other_reportable_long",
    "other_reportable_short",
    "other_reportable_spread",
)


@dataclass(slots=True)
class _CftcProbeState:
    root: str
    dataset_symbol: str
    rows_received: int = 0
    first_delivery_utc: datetime | None = None
    last_delivery_utc: datetime | None = None
    non_null_field_observations: int = 0
    nullable_field_names: set[str] = field(default_factory=set)


class CftcProbeRecorder:
    """Record sparse CFTC TFF delivery clocks and nullable-field coverage."""

    def __init__(self, subscriptions: Mapping[str, object]) -> None:
        """Bind exact reference roots to already-created CFTC dataset symbols.

        Units: CFTC contract counts. Time semantics: data clocks use the documented
        Eastern timezone; Slice delivery uses the UTC algorithm clock. Missingness:
        exactly ES, ZN, and 6E are required. Raises: market or contract errors.
        """

        if tuple(subscriptions) != _REFERENCE_ROOTS:
            raise MarketConfigurationError("CFTC probe requires ES, ZN, and 6E in order")
        self._states: dict[str, _CftcProbeState] = {}
        self._symbols: dict[str, object] = {}
        self._datetime_boundaries: dict[str, Mapping[str, object]] = {}
        self._delivery_rows: dict[tuple[str, str], Mapping[str, object]] = {}
        for root, symbol in subscriptions.items():
            symbol_text = qc_symbol_text(symbol, f"{root} CFTC dataset symbol")
            if symbol_text is None:
                raise ContractBoundaryError(f"{root} CFTC dataset symbol is missing")
            self._states[root] = _CftcProbeState(root, symbol_text)
            self._symbols[root] = symbol

    def observe_slice(self, slice_data: object) -> tuple[str, ...]:
        """Record each delivered CFTC TFF object in one Slice.

        Units: contract and field counts. Time semantics: Slice time is UTC; data
        time/end-time use ``America/New_York``. Missingness: nullable fields remain
        null and absent weekly rows emit nothing. Raises: boundary or timing errors.
        """

        qc_slice = cast(Any, slice_data)
        slice_time_value = getattr(qc_slice, "time", None)
        delivered_at = qc_datetime_to_utc(
            slice_time_value,
            "CFTC slice.time",
            naive_source_timezone="UTC",
        )
        self._datetime_boundaries.setdefault(
            "slice.time",
            qc_datetime_boundary_record(slice_time_value, "CFTC slice.time", "UTC"),
        )
        contains_key = getattr(qc_slice, "contains_key", None)
        if contains_key is None or not callable(contains_key):
            raise UnverifiedQuantConnectApiError("Slice lacks verified contains_key boundary")
        rows = [
            self._observe_point(root, qc_slice[symbol], delivered_at)
            for root, symbol in self._symbols.items()
            if contains_key(symbol)
        ]
        return tuple(rows)

    def _observe_point(self, root: str, point: Any, delivered_at: datetime) -> str:
        state = self._states[root]
        data_time_value = getattr(point, "time", None)
        end_time_value = getattr(point, "end_time", None)
        data_time = qc_datetime_to_utc(
            data_time_value,
            f"{root} CFTC data.time",
            naive_source_timezone="America/New_York",
        )
        end_time = qc_datetime_to_utc(
            end_time_value,
            f"{root} CFTC data.end_time",
            naive_source_timezone="America/New_York",
        )
        for name, value in (("time", data_time_value), ("end_time", end_time_value)):
            self._datetime_boundaries.setdefault(
                f"{root}.data.{name}",
                qc_datetime_boundary_record(
                    value,
                    f"{root} CFTC data.{name}",
                    "America/New_York",
                ),
            )
        non_null = tuple(
            name for name in _POSITION_FIELDS if getattr(point, name, None) is not None
        )
        nullable = tuple(sorted(set(_POSITION_FIELDS).difference(non_null)))
        state.rows_received += 1
        state.first_delivery_utc = min(delivered_at, state.first_delivery_utc or delivered_at)
        state.last_delivery_utc = max(delivered_at, state.last_delivery_utc or delivered_at)
        state.non_null_field_observations += len(non_null)
        state.nullable_field_names.update(nullable)
        row = {
            "root": root,
            "dataset_symbol": state.dataset_symbol,
            "qc_slice_time_utc": delivered_at,
            "data_time_utc": data_time,
            "data_end_time_utc": end_time,
            "non_null_field_count": len(non_null),
            "nullable_field_names": nullable,
            "report_type": "CFTCFinancialFutures",
        }
        release_date = end_time.astimezone(ZoneInfo("America/New_York")).date().isoformat()
        self._delivery_rows[(root, release_date)] = row
        return canonical_json_bytes({**row, "row_hash": sha256_hex(row)}).decode("utf-8")

    def build_delivery_audit_json(
        self,
        audit_releases: tuple[tuple[str, str], ...],
    ) -> tuple[str, ...]:
        """Return compact actual-delivery rows for official/QC release-date pairs.

        Units: CFTC contract and nullable-field counts. Time semantics: requested
        dates pair the official Eastern calendar with the QC historical end-time date;
        observed clocks retain UTC. Missingness: an unavailable root/date pair remains
        an explicit negative audit row. Raises: ``MarketConfigurationError`` for blank,
        duplicate, or invalid release-date pairs and canonical serialization errors.
        """

        if not audit_releases or len(audit_releases) != len(set(audit_releases)):
            raise MarketConfigurationError("CFTC audit release pairs must be unique")
        for official_release_date, qc_delivery_date in audit_releases:
            for field_name, value in (
                ("official release date", official_release_date),
                ("QC delivery date", qc_delivery_date),
            ):
                try:
                    date.fromisoformat(value)
                except ValueError as error:
                    raise MarketConfigurationError(
                        f"invalid CFTC {field_name}: {value!r}"
                    ) from error
        audit_rows: list[str] = []
        for official_release_date, qc_delivery_date in audit_releases:
            for root in _REFERENCE_ROOTS:
                observed = self._delivery_rows.get((root, qc_delivery_date))
                payload: dict[str, object] = {
                    "root": root,
                    "dataset_symbol": self._states[root].dataset_symbol,
                    "official_release_date": official_release_date,
                    "qc_delivery_key_date": qc_delivery_date,
                    "qc_delivery_precedes_official_release": (
                        qc_delivery_date < official_release_date
                    ),
                    "delivery_observed": observed is not None,
                    "quality_flags": (
                        () if observed is not None else ("NO_CFTC_DELIVERY_ON_AUDIT_DATE",)
                    ),
                }
                if observed is not None:
                    payload.update(observed)
                audit_rows.append(
                    canonical_json_bytes({**payload, "audit_hash": sha256_hex(payload)}).decode(
                        "utf-8"
                    )
                )
        return tuple(audit_rows)

    def delivery_audit_observed_count(
        self,
        audit_releases: tuple[tuple[str, str], ...],
    ) -> int:
        """Return the number of requested root/date pairs observed in QC delivery.

        Units: delivered root/date pairs. Time semantics: lookup dates are QC historical
        end-time dates paired to official releases. Missingness: missing pairs count as
        zero. Raises: none.
        """

        return sum(
            (root, qc_delivery_date) in self._delivery_rows
            for _, qc_delivery_date in audit_releases
            for root in _REFERENCE_ROOTS
        )

    def build_summary_json(self) -> tuple[str, ...]:
        """Return deterministic per-market delivery summaries.

        Units: row and field counts. Time semantics: first/last clocks are actual UTC
        Slice observations. Missingness: no-row markets retain null clocks and a flag.
        Raises: canonical serialization errors.
        """

        summaries: list[str] = []
        for root in _REFERENCE_ROOTS:
            state = self._states[root]
            summary = {
                "root": root,
                "dataset_symbol": state.dataset_symbol,
                "rows_received": state.rows_received,
                "first_delivery_utc": state.first_delivery_utc,
                "last_delivery_utc": state.last_delivery_utc,
                "non_null_field_observations": state.non_null_field_observations,
                "nullable_field_names": tuple(sorted(state.nullable_field_names)),
                "quality_flags": (
                    ("NO_CFTC_TFF_ROWS_RECEIVED",) if state.rows_received == 0 else ()
                ),
            }
            summaries.append(canonical_json_bytes(summary).decode("utf-8"))
        return tuple(summaries)

    def datetime_boundary_probe_json(self) -> str:
        """Return deterministic CFTC Python/Python.NET datetime observations.

        Units: microsecond precision. Time semantics: each conversion records its
        documented source timezone. Missingness: unobserved fields are absent. Raises:
        canonical serialization errors.
        """

        return canonical_json_bytes(
            {
                "schema_version": "lift1-cftc-pythonnet-datetime-probe-v1",
                "observations": dict(sorted(self._datetime_boundaries.items())),
            }
        ).decode("utf-8")

    def row_counts(self) -> Mapping[str, int]:
        """Return per-root delivered-row counts for QC summary statistics.

        Units: delivered CFTC objects. Time semantics: only observed Slices count.
        Missingness: absent markets return zero. Raises: none.
        """

        return MappingProxyType(
            {root: self._states[root].rows_received for root in _REFERENCE_ROOTS}
        )


__all__ = ("CftcProbeRecorder",)

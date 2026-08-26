from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path

from systematic_futures.domain.schemas import DataProbeResult, MarketDefinition
from systematic_futures.qc_adapters.futures_registration import (
    configure_quantbook_utc,
    register_reference_futures,
    request_quantbook_histories,
)
from systematic_futures.research_lib.coverage_report import build_data_probe_result
from systematic_futures.research_lib.export import export_probe_results_file


def add_reference_futures(
    quantbook: object,
    markets: Sequence[MarketDefinition],
) -> Mapping[str, object]:
    """Configure UTC and register exactly ES, ZN, and 6E on a QuantBook.

    Units: minute resolution with market-defined calendar-day contract filters.
    Time semantics: the notebook timezone is set explicitly to UTC; extended-hours,
    Open Interest mapping, and Backwards Ratio normalization are explicit. Missingness:
    all three verified reference definitions are mandatory. Raises: market, API, or QC
    runtime errors; no constant, mode, or market is inferred.
    """

    configure_quantbook_utc(quantbook)
    return register_reference_futures(quantbook, markets)


def request_reference_history(
    quantbook: object,
    subscriptions: Mapping[str, object],
    start_utc: datetime,
    end_utc: datetime,
) -> Mapping[str, object]:
    """Request each reference market's chain, continuous, mapping, and universe history.

    Units: minute chain/continuous rows and daily FutureUniverse rows. Time semantics:
    inputs must be aware; the verified adapter preserves UTC values in each result bundle
    and converts them to naive UTC only at the documented QuantBook overload boundary.
    Missingness: empty QC histories remain empty; every reference subscription is
    mandatory. Raises: time, configuration, API, or QC runtime errors.
    """

    return request_quantbook_histories(quantbook, subscriptions, start_utc, end_utc)


def summarize_contract_history(root: str, history: object) -> DataProbeResult:
    """Build a deterministic, lineage-bearing summary for one reference market.

    Units: native tick/multiplier and observed row/gap/mapping counts. Time semantics:
    QC DataFrame exchange-local indices are normalized to UTC; gaps are deliberately
    unadjudicated for holidays and maintenance. Missingness: absent observations remain
    explicit flags with a non-valid quality status. Raises: raw-boundary, time, market,
    or schema validation errors.
    """

    return build_data_probe_result(root, history)


def export_probe_results(
    results: Sequence[DataProbeResult],
    output_path: Path,
) -> str:
    """Atomically export sorted small probe summaries and return their content hash.

    Units: inherited from validated ``DataProbeResult`` records.
    Time semantics: aware datetimes serialize as UTC ISO-8601 ``Z``.
    Missingness: no raw bulk data is exported; optional observed metadata remains JSON
    ``null`` and an empty result set is rejected. Raises: duplicate/schema/canonical or
    filesystem errors. Returns the SHA-256 of the exact canonical bytes written.
    """

    return export_probe_results_file(results, output_path)


__all__ = (
    "add_reference_futures",
    "export_probe_results",
    "request_reference_history",
    "summarize_contract_history",
)

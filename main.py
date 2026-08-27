from __future__ import annotations

import platform
from datetime import UTC, datetime

from AlgorithmImports import QCAlgorithm, Slice, SymbolChangedEvents

from systematic_futures.config.markets import reference_market_definitions
from systematic_futures.domain.errors import MarketConfigurationError
from systematic_futures.domain.serialization import canonical_json_bytes, sha256_hex
from systematic_futures.qc_adapters.cftc_probe_recorder import CftcProbeRecorder
from systematic_futures.qc_adapters.futures_registration import (
    register_reference_cftc,
    register_reference_futures,
)
from systematic_futures.qc_adapters.probe_recorder import (
    FuturesProbeRecorder,
    runtime_market_evidence_json,
)

_CFTC_AUDIT_RELEASES = (
    ("2026-01-05", "2026-01-02"),
    ("2026-01-09", "2026-01-09"),
)


class InstitutionalFuturesDataProbe(QCAlgorithm):
    """Observe ES, ZN, and 6E data identity, mappings, metadata, and coverage."""

    def initialize(self) -> None:
        """Configure the fixed read-only probe and its three subscriptions.

        Units: minute resolution and calendar-day contract filters. Time semantics:
        the algorithm clock is UTC and the inclusive configured dates are 2024-02-15
        through 2024-03-25. Missingness: every reference subscription is mandatory.
        Raises: configuration, verified-API, metadata, or QC runtime exceptions.
        """

        self.set_time_zone("UTC")
        self._probe_mode = self.get_parameter("lift1_probe_mode", "futures")
        if self._probe_mode == "cftc":
            self.set_start_date(2026, 1, 1)
            self.set_end_date(2026, 8, 25)
            self._cftc_subscriptions = register_reference_cftc(self)
            self._cftc_recorder = CftcProbeRecorder(self._cftc_subscriptions)
            return
        if self._probe_mode != "futures":
            raise MarketConfigurationError("lift1_probe_mode must be 'futures' or 'cftc'")
        self.set_start_date(2024, 2, 15)
        self.set_end_date(2024, 3, 25)
        markets = reference_market_definitions()
        self._subscriptions = register_reference_futures(self, markets)
        self._recorder = FuturesProbeRecorder(
            markets,
            datetime(2024, 2, 15, tzinfo=UTC),
            datetime(2024, 3, 25, 23, 59, tzinfo=UTC),
        )
        for root, subscription in self._subscriptions.items():
            self._recorder.register_subscription(root, subscription)

    def on_data(self, slice: Slice) -> None:  # noqa: A002
        """Record continuous minute rows and explicitly observed mapped identities.

        Units: minute rows and native contract metadata. Time semantics: Slice time is
        interpreted under the UTC algorithm clock; gaps are not session adjudications.
        Missingness: absent bars remain absent and are never converted to zero.
        Raises: timing, identity, configuration, or verified-API boundary exceptions.
        """

        if self._probe_mode == "cftc":
            self._cftc_recorder.observe_slice(slice)
            return
        self._recorder.observe_slice(slice, self._subscriptions)

    def on_symbol_changed_events(
        self,
        symbols_changed: SymbolChangedEvents,
    ) -> None:
        """Record delivered old/new mapped-contract identities without inference.

        Units: one count per delivered mapping event. Time semantics: delivery time is
        the current UTC algorithm clock and is never backdated. Missingness: an absent
        old identity is allowed; a missing new or unknown continuous identity raises.
        Raises: timing, contract-boundary, or verified-API boundary exceptions.
        """

        if self._probe_mode == "futures":
            self._recorder.observe_mapping_events(symbols_changed, self.time)

    def on_end_of_algorithm(self) -> None:
        """Validate and log one small canonical summary per reference market.

        Units: observed row, gap, and mapping counts plus native tick and multiplier.
        Time semantics: summaries are finalized at the current UTC algorithm clock.
        Missingness: absent observations produce explicit flags and non-valid status.
        Raises: timing, schema, canonical-serialization, or QC logging exceptions.
        """

        if self._probe_mode == "cftc":
            summaries = self._cftc_recorder.build_summary_json()
            for root, summary in zip(self._cftc_subscriptions, summaries, strict=True):
                self.log(f"LIFT_1_CFTC_SUMMARY {summary}")
                self.set_summary_statistic(f"L1.CFTC.{root}.Summary", summary)
            audit_rows = self._cftc_recorder.build_delivery_audit_json(_CFTC_AUDIT_RELEASES)
            audit_keys = (
                (release_date, root)
                for release_date, _ in _CFTC_AUDIT_RELEASES
                for root in self._cftc_subscriptions
            )
            for (release_date, root), audit_row in zip(audit_keys, audit_rows, strict=True):
                self.log(f"LIFT_1_CFTC_DELIVERY_AUDIT {audit_row}")
                self.set_summary_statistic(
                    f"L1.CFTC.{root}.{release_date}.Audit",
                    audit_row,
                )
            for root, rows in self._cftc_recorder.row_counts().items():
                self.set_summary_statistic(f"L1.CFTC.{root}.Rows", rows)
            self.set_summary_statistic(
                "L1.CFTC.AuditObserved",
                self._cftc_recorder.delivery_audit_observed_count(_CFTC_AUDIT_RELEASES),
            )
            self.set_summary_statistic(
                "L1.CFTC.AuditExpected",
                len(_CFTC_AUDIT_RELEASES) * len(self._cftc_subscriptions),
            )
            probe_hash = sha256_hex((*summaries, *audit_rows))
            datetime_probe = self._cftc_recorder.datetime_boundary_probe_json()
        else:
            evidence_rows = self._recorder.build_runtime_market_evidence(self.time)
            for evidence in evidence_rows:
                evidence_json = runtime_market_evidence_json(evidence)
                self.log(f"LIFT_1_RUNTIME_MARKET {evidence_json}")
                prefix = f"L1.{evidence.root}"
                self.set_summary_statistic(f"{prefix}.Evidence", evidence_json)
                self.set_summary_statistic(f"{prefix}.Rows", evidence.rows_received)
                self.set_summary_statistic(f"{prefix}.MappedCount", evidence.mapped_contract_count)
                self.set_summary_statistic(f"{prefix}.MappingEvents", evidence.mapping_event_count)
                self.set_summary_statistic(
                    f"{prefix}.OINonNull",
                    evidence.open_interest_non_null_observations,
                )
                if evidence.minimum_tick_observed is not None:
                    self.set_summary_statistic(f"{prefix}.TickSize", evidence.minimum_tick_observed)
                if evidence.multiplier_observed is not None:
                    self.set_summary_statistic(f"{prefix}.Multiplier", evidence.multiplier_observed)
            probe_hash = sha256_hex(evidence_rows)
            datetime_probe = self._recorder.datetime_boundary_probe_json()
        self.set_summary_statistic("L1.NoOrders", 0)
        self.set_summary_statistic("L1.NoInsights", 0)
        self.set_summary_statistic("L1.NoPortfolioTargets", 0)
        self.set_summary_statistic("L1.ProbeHash", probe_hash)
        runtime_identity = {
            "machine": platform.machine(),
            "platform": platform.platform(),
            "python_implementation": platform.python_implementation(),
            "python_version": platform.python_version(),
        }
        self.set_summary_statistic("L1.Machine", runtime_identity["machine"])
        self.set_summary_statistic("L1.Platform", runtime_identity["platform"])
        self.set_summary_statistic(
            "L1.PythonImplementation", runtime_identity["python_implementation"]
        )
        self.set_summary_statistic("L1.PythonVersion", runtime_identity["python_version"])
        self.set_summary_statistic("L1.DateTimeProbe", datetime_probe)
        self.log(
            f"LIFT_1_RUNTIME_IDENTITY {canonical_json_bytes(runtime_identity).decode('utf-8')}"
        )
        self.log(f"LIFT_1_PYTHONNET_DATETIMES {datetime_probe}")

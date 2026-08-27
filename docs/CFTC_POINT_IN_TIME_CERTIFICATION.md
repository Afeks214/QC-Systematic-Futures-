# CFTC Point-in-Time Certification

Status: **CERTIFIED_CONTEXT**
Policy: `lift1.cftc-release-timing.v1`
Certified: **2026-08-27**

## Decision

Real QuantConnect `CFTCFinancialFutures` data was observed for the exact TFF markets
`E_MINI_SP_500`, `UST_10_Y_NOTE`, and `EURO_FX`. The official CFTC schedule remains
the release-side authority. The resulting context is suitable for research-state
gating only; it is not a signal certification.

## Evidence

- QC project: `35697180`
- Cloud build: `67d2fc-f0a27f`
- Cloud backtest: `a7ba4f84937fb19bc3f6f63bc773e3c3`
- LEAN runtime: `2.5.0.0.18036`
- Artifact: `artifacts/certification/cftc_release_delivery_audit.json`
- Artifact content hash: `fb1456ab3d3e34b815a0ed5f2bd171c9528909dc1ba035e5e8fb83bb4ae8a4d6`
- Probe hash: `908cb750ec8e5133a01710ac0b8fc74c16e82e0a36ccd8b9ed429e3be6f63fd7`

Each reference market delivered 22 rows, with 330 non-null field observations and no
nullable field names encountered in this sample. The configured audit window was
2026-01-01 through 2026-08-25; actual QC delivery ran from 2026-01-02 20:30 UTC
through 2026-05-29 19:30 UTC and processed 788 total data points.

## Release audit

| Class | Official release | Observed QC Slice/EndTime | Gate usable from | Result |
|---|---|---|---|---|
| Holiday-delayed | 2026-01-05 20:30 UTC | 2026-01-02 20:30 UTC | 2026-01-05 20:30 UTC | 3/3 roots observed; early historical QC clock withheld |
| Ordinary | 2026-01-09 20:30 UTC | 2026-01-09 20:30 UTC | 2026-01-09 20:30 UTC | 3/3 roots observed; clocks match |

The official [CFTC release schedule](https://www.cftc.gov/MarketReports/CommitmentsofTraders/ReleaseSchedule/index.htm)
sets 3:30 PM Eastern and marks 2026-01-05 as holiday delayed. Raw QC timestamps are
never rewritten. Availability is:

```text
usable_from_utc = max(
    official_release_timestamp_utc,
    observed_qc_delivery_timestamp_utc,
    documented_manual_exception_timestamp_utc when present,
)
```

The ordinary and delayed AvailabilityGate tests prove no earlier release. Missing
observations are withheld, never interpolated or replaced with zero.

## Limitations

- QC delivered no rows after 2026-05-29 in the configured window. No later-tail
  completeness claim is made.
- QC `data_time` values are preserved and not relabeled as CFTC Tuesday observation
  dates.
- No revision-history or live/backtest delivery-parity claim is made.
- Certification is `CERTIFIED_CONTEXT`, not `CERTIFIED_SIGNAL`; no COT feature,
  forecast, alpha, order, or trading behavior exists.

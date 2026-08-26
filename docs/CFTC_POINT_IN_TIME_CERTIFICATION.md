# CFTC Point-in-Time Certification

Status: **UNDER_REVIEW — QC DELIVERY NOT CERTIFIED**
Policy version: `lift1.cftc-release-timing.v1`
Reviewed: **2026-08-26**

## Official schedule evidence

The official [CFTC COT release schedule](https://www.cftc.gov/MarketReports/CommitmentsofTraders/ReleaseSchedule/index.htm)
states that COT reports are released at 3:30 PM Eastern Time, usually on Friday,
usually for data from the preceding Tuesday, and that federal holidays can delay a
release by one or two days. The CFTC describes the same ordinary Tuesday/Friday
relationship in its [COT report FAQ](https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm).

The schedule is expressly tentative. Within the requested 2026-01-01 through
2026-08-25 QC audit window, its marked delayed release dates are:

| Official release date | Eastern release time | UTC release time | Schedule mark |
|---|---:|---:|---|
| 2026-01-05 | 15:30 EST | 2026-01-05T20:30:00Z | Federal-holiday delay |
| 2026-06-22 | 15:30 EDT | 2026-06-22T19:30:00Z | Federal-holiday delay |
| 2026-07-06 | 15:30 EDT | 2026-07-06T19:30:00Z | Federal-holiday delay |

These rows identify publication dates only. The tentative schedule alone does not
establish the observation/report date represented by each delivered QC object, nor
does it prove when QuantConnect made the object available.

Source metadata for a future immutable schedule fixture:

- source owner: U.S. Commodity Futures Trading Commission;
- source URL: `https://www.cftc.gov/MarketReports/CommitmentsofTraders/ReleaseSchedule/index.htm`;
- retrieved/verified date: `2026-08-26`;
- timezone interpretation: `America/New_York`, converted with date-specific UTC offset;
- calendar label: `CFTC tentative 2026 release schedule`;
- immutable source-byte hash: `NOT_CAPTURED`; no byte hash is invented in this document.

## Point-in-time rule

The repository's conservative rule is:

```text
usable_from_utc = max(
    official_release_timestamp_utc,
    observed_qc_delivery_timestamp_utc,
    documented_manual_exception_timestamp_utc when present,
)
```

An observation date must match an explicit schedule entry. A delayed release is an
explicit later timestamp, never an inferred weekday offset. An unlisted observation,
missing official release, timestamp mismatch, or unavailable QC delivery timestamp is
withheld rather than interpolated. No missing report is replaced with zero. Retaining a
previous report later in time requires explicit age/staleness metadata; this repository
does not create synthetic intermediate reports.

## Evidence actually obtained

| Evidence | Result | Meaning |
|---|---|---|
| Official CFTC ordinary and delayed publication rules | `VERIFIED_DOCUMENTATION` | Establishes the official release-side lower bound |
| `UnderReviewCftcReleaseTimingPolicy` max-timestamp rule | `IMPLEMENTED_STATIC` | Enforces an explicit schedule and observed delivery field at the domain boundary |
| Ordinary-release AvailabilityGate test | `PASS_SYNTHETIC_ONLY` | Proves a synthetic record is withheld until its supplied release timestamp |
| Delayed-release AvailabilityGate test | `PASS_SYNTHETIC_ONLY` | Proves a synthetic delayed record is not released on an earlier ordinary Friday |
| QC `CFTCFinancialFutures` observations for 2026-01-01 through 2026-08-25 | `NOT_EXECUTED` | LEAN CLI exists, but no authenticated QC account/session is available |
| ES QC CFTC delivery timing | `NOT_EXECUTED` | The verified `CFTC.Markets.E_MINI_SP_500` name does not prove delivery |
| ZN and 6E TFF constants | `VERIFIED_API` | Current official stubs expose `UST_10_Y_NOTE` and `EURO_FX`; delivered coverage remains unobserved |
| Ordinary and delayed QC Slice/data time comparison | `NOT_EXECUTED` | No real delivery audit exists |
| `artifacts/certification/cftc_release_delivery_audit.json` | `ABSENT` | A synthetic fixture is not written under this empirical artifact name |

QuantConnect documents `CFTCFinancialFutures` and the ES example constant in its
[Commitments of Traders dataset documentation](https://www.quantconnect.com/docs/v2/writing-algorithms/datasets/commodity-futures-trading-commission/commitments-of-traders).
Current official `quantconnect-stubs==18032` additionally resolves the exact ZN/6E
constants, nullable TFF fields, Eastern data timezone, and `end_time` API. The single
read-only root algorithm has a `cftc` parameter mode that logs Slice/data clocks and
null coverage. These establish a statically checked execution path, not account
entitlement, actual reference-market coverage, delivery clocks, or point-in-time
certification.

## Certification decision

The official release-side lower bound and the gate invariant are established. Actual
QC delivery semantics, real ordinary/delayed objects, delivered ZN/6E coverage,
nullable-field behavior, and sufficient observation counts are not established.
Therefore CFTC remains `UNDER_REVIEW`; it is not `CERTIFIED_CONTEXT` or
`CERTIFIED_SIGNAL`. The CFTC timing gate remains a blocking Lift 1 closure item.

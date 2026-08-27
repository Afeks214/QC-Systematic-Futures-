# Roll Timing Certification

Status: **CERTIFIED_BACKTEST_CONTEXT**
Policy: `lift1.roll-availability.v1`
Certified: **2026-08-27**

QuantConnect documents that a continuous future has a distinct continuous `symbol`
and a current actual `mapped` contract. It also documents that backtest and live
`SymbolChangedEvent` delivery times differ. Therefore this certification covers the
observed backtest context only; it does not infer live timing.

## Causal policy

```text
visible_at_utc = max(observed_at_utc, effective_at_utc)
```

Before visibility, the prior contract remains current. At visibility, an explicit
identity change is `ROLL_TRANSITION`; afterward it is `POST_ROLL`. No pre-roll window,
transition duration, blackout, future volume, or future mapping is inferred. Actual
old/new contracts remain separate from adjusted continuous prices.

## Evidence

| Root | Mapped identities | Delivered mapping event | Observed states |
|---|---:|---:|---|
| ES | 2 | 2024-03-13 04:00 UTC | normal, roll_transition, post_roll |
| ZN | 2 | 2024-02-26 06:00 UTC | normal, roll_transition, post_roll |
| 6E | 2 | 2024-03-18 05:00 UTC | normal, roll_transition, post_roll |

QC project `35697180`, build `67d2fc-f0a27f`, and backtest
`b22d565d649c5b31650fd033cdc89cf3` produced the evidence in
`artifacts/certification/qc_futures_runtime_probe.json`. Local causal tests also prove
that a future-effective observation cannot change an earlier query.

The raw `SymbolChangedEvent.time` representation was observed, but its source timezone
was not independently established. Its UTC conversion is therefore withheld instead
of guessed. This limitation does not affect the recorder's algorithm-clock observation
used for causal roll state.

Empirical live mapping delivery remains unexecuted and must be separately certified
before any later live-timing claim.

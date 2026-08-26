# Roll Timing Certification

Status: **BLOCKED_EMPIRICAL**
Policy version: `lift1.roll-availability.v1`
Reviewed: **2026-08-26**

## Official documented behavior

QuantConnect documents that a continuous future has a distinct continuous `symbol`,
while its `mapped` property identifies the current actual contract. It also documents
a real environment difference: a futures `SymbolChangedEvent` occurs at midnight
Eastern Time in backtests, whereas live continuous-mapping data arrives at about 6/7
AM Eastern Time and the live event occurs then. Sources:
[Futures universes](https://www.quantconnect.com/docs/v2/writing-algorithms/universes/futures)
and [Futures handling data](https://www.quantconnect.com/docs/v2/writing-algorithms/securities/asset-classes/futures/handling-data).

These statements establish documented non-parity. They do not prove when an event was
delivered to this repository, because no QC run occurred here.

## Conservative availability policy

For each environment, a mapping change becomes visible only at:

```text
visible_at_utc = max(observed_at_utc, effective_at_utc)
```

The adapter must record the timestamp delivered by that environment. A backtest event
timestamp must not be relabeled as a live delivery timestamp, and the documented live
window must not be synthesized into backtest data. Before `visible_at_utc`, the old
contract remains the visible identity. At and after visibility, old and new contracts
remain separate immutable identities; no adjusted continuous price is substituted for
an actual-contract price.

`RollManager` implements only causal, event-instant state:

- an initial explicit observation is `NORMAL`;
- an explicit identity change is `ROLL_TRANSITION` only at its visibility instant;
- it is `POST_ROLL` afterward;
- no `PRE_ROLL`, transition duration, or `BLACKOUT` is inferred;
- no future volume or future mapping may alter earlier state.

This is a conservative research-foundation rule, not a forecast of exchange behavior.

## Evidence status

| Evidence | Result | Interpretation |
|---|---|---|
| Official QC backtest/live timing documentation | `VERIFIED_DOCUMENTATION` | Establishes that the two environments are not time-identical |
| Static causal roll test | `PASS_LOCAL_STATIC` | `test_future_mapping_observation_does_not_change_earlier_roll_state` proves a supplied future observation cannot change an earlier query |
| Real ES/ZN/6E backtest mapping events, 2024-02-15 through 2024-03-25 | `NOT_EXECUTED` | LEAN CLI is installed; authenticated QC project access is unavailable |
| Empirical live mapping delivery | `NOT_EXECUTED` | No paper/live observation path was authorized or run |
| `qc_futures_runtime_probe.json` mapping evidence | `ABSENT` | Synthetic identities are not accepted as runtime evidence |

## Certification decision

Static causality is verified, but actual backtest events and actual live delivery were
not observed. Therefore contract-mapping and roll timing are **not empirically
certified**. The documented non-parity is modeled conservatively and may later support
conditional readiness only after the required real backtest evidence exists. It does
not support `READY_FOR_LIFT_2` in the current state.

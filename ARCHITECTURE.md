# Architecture

## Purpose

The system is a causal, read-only futures measurement pipeline. It observes market data,
maintains explicit contract/session/roll state, and emits descriptive measurements and
candidate events. There is no strategy, forecast, sizing, risk, or execution layer.

## Runtime flow

```text
QuantConnect Slice
  -> MeasurementRuntime
     -> mapped actual-contract trade ticks only
        -> MeasurementStream
           -> 1-minute buckets
           -> completed 5-minute bars and Profiles
           -> completed 30-minute state bars
           -> IMSI / ICM / IAE snapshots
           -> descriptive candidate events
     -> deterministic summary hashes and zero-action counters
```

`main.py` delegates to `systematic_futures/qc_adapters/runtime.py`. This is the only
active composition path. QuantConnect objects do not cross into the framework-independent
core.

## Ownership

| Concern | Source of truth |
| --- | --- |
| Eight market definitions and QC identities | `systematic_futures/config/markets.py` |
| Measurement clocks and bounded replay windows | `systematic_futures/config/measurement.py` |
| Source/revision lineage identity | `systematic_futures/domain/identifiers.py` |
| Continuous/mapped/actual mapping identity | `systematic_futures/data/rolls.py` |
| External usable-from and revision truth | `systematic_futures/data/point_in_time.py` |
| Session windows, holidays, early closes, DST | `systematic_futures/data/sessions.py` |
| Mapping observations and roll isolation | `systematic_futures/data/rolls.py` |
| Actual-contract integer-tick Profile, POC, VA | `systematic_futures/measurement/volume_profile.py` |
| IMSI prior-state measurement | `systematic_futures/measurement/imsi.py` |
| ICM completed-bar measurement | `systematic_futures/measurement/icm.py` |
| IAE signed descriptive gap state | `systematic_futures/measurement/iae.py` |
| Stream coordination and causal finalization | `systematic_futures/measurement/stream.py` |

## Data truth

- Domain time is aware UTC. QC naive datetimes are accepted only with an explicit source zone.
- `usable_from_utc` is the earliest admissible decision frontier; equality is usable.
- A later revision cannot alter an earlier as-known result.
- Continuous symbols select mappings; the actual mapped contract owns trades and Profile state.
- A roll finalizes the old stream and creates a new contract-isolated stream.
- Pre-roll, transition, and blackout ticks are excluded from the active runtime stream,
  preventing one completed bar or Profile from mixing roll eligibility states.
- Session classification is exchange-local and uses explicit bounded reference
  holiday/early-close exceptions; it is not a claim of a complete live exchange calendar.
- Profile prices are integer tick indices; POC and value-area tie rules are deterministic.
- IMSI seasonal/history inputs are prior-only; ICM consumes completed medium bars; IAE keeps
  signed volume surprise and symmetric bullish/bearish geometry.
- Missing or unready inputs produce explicit flags, never fabricated values.

## Runtime modes

`measurement_mode=reference` runs the fixed ES/ZN/6E reference window.
`measurement_mode=smoke` runs a bounded window for any supported root. The root is selected
with `measurement_root`. Invalid values fail closed.

## Explicitly absent

The repository has no outcome labels, backtest strategy, H1 implementation, alpha model,
machine learning, forecast packets, position objects, portfolio/risk engine, broker adapter,
or order-producing API. Historical reports and generated evidence are recoverable from Git
history rather than retained as active architecture.

## Proof surface

Tests cover point-in-time release and revisions, all eight identities, sessions/DST/holidays,
roll causality, Profile arithmetic, IMSI/ICM/IAE causality, event identity, the actual-contract
QC boundary, and static absence of trading/ML calls. These checks prove tested software
invariants only; they do not prove alpha or external runtime qualification. Mathematical
lookbacks and minute buckets are bounded, but deduplication identities and emitted evidence
collections grow with observed input. Cross-platform NumPy/BLAS bit identity and external QC
ordering for equal-time ticks are not established by the local suite.

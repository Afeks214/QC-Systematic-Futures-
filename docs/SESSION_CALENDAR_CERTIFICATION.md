# Session Calendar Certification

Status: **CERTIFIED_FOR_PINNED_LEAN_CALENDAR_VERSION**
Semantic policy: `lift1-semantic-v1`
LEAN source commit: `07fb0182bfe229edd9445cf675ac6509d0069539`
Market-hours database SHA-256:
`d93f0b417cc9df618da4548f78157fd2b49515e0999f16e83ffddcffd54eef41`
Verified: **2026-08-27**

## Scope

LEAN's official
[`market-hours-database.json`](https://github.com/QuantConnect/Lean/blob/07fb0182bfe229edd9445cf675ac6509d0069539/Data/market-hours/market-hours-database.json)
is the exchange-hours authority. `SessionEngine` only adds stable semantic labels; it
does not replace LEAN's calendar. The compact fixtures below pin facts from that exact
database version so local UTC/local-time behavior is deterministic.

## Verified matrix

| Root | LEAN key | Zone | Ordinary/DST | Holiday | 2024-05-27 close / reopen | Cross-midnight |
|---|---|---|---|---|---|---|
| ES | `Future-cme-ES` | `America/New_York` | PASS | 2026-12-25 PASS | 13:00 / 18:00 PASS | PASS |
| ZN | `Future-cbot-ZN` | `America/Chicago` | PASS | 2026-12-25 PASS | 12:00 / 17:00 PASS | PASS |
| 6E | `Future-cme-6E` | `America/Chicago` | PASS | 2026-12-25 PASS | 16:00 / 17:00 PASS | PASS |

The parameterized tests cover an ordinary local instant, both sides of the 2024 spring
and fall US DST transitions, one all-day closure, one early-close/reopen interval, and
one cross-midnight session ID for every reference root. The existing causal roll test
also proves that session classification cannot make a future mapping effective early.

## Runtime boundary

This certification establishes the semantic engine against the pinned current LEAN
calendar file. The fixed-window QC cloud probe subsequently observed 111 ES, 110 ZN,
and 113 6E semantic session IDs and roll-adjacent states under LEAN 2.5.0.0.18036 in
backtest `b22d565d649c5b31650fd033cdc89cf3`. It does not claim that all future calendars
are permanently certified or that every exchange-hours object was separately audited.

# Assumptions and Blockers

This is the exhaustive current register. Documentation and synthetic fixtures never
substitute for empirical QuantConnect delivery evidence.

## VERIFIED

- Both private specifications were reviewed from the authorized workspace. SHA-256:
  Master `ef19e4242a48747ef13b235e38f9c9fa0c09a7ed07085b5bb689be39a8786747`;
  Intraday Extension `bdebaf3e0ec38c3cb13d605b1fdc289db0a6316218756d0264ed23856f3195b2`.
- CPython 3.11.15 is installed in the project environment. LEAN CLI 1.0.228 is
  installed separately and executes.
- The official `quantconnect-stubs==18032` surface was used for an explicit
  stub-backed basic check of `main.py` and the QC adapters; the core has the separate
  strict gate and no stub package is retained as a project dependency.
- Current official LEAN source commit is
  `07fb0182bfe229edd9445cf675ac6509d0069539`. Its market-hours database SHA-256 is
  `d93f0b417cc9df618da4548f78157fd2b49515e0999f16e83ffddcffd54eef41`.
- ES, ZN, and 6E ordinary/DST/cross-midnight/holiday/early-close fixtures are pinned to
  that database and pass. This certifies the versioned semantic engine/fixture matrix,
  not every future exchange calendar.
- Exact CFTC TFF constants are `E_MINI_SP_500`, `UST_10_Y_NOTE`, and `EURO_FX` in the
  current official stubs. The read-only probe can select futures or CFTC mode without a
  second source tree.
- The Master Definition-of-Ready contracts exist: point-in-time normalizer/gate,
  ExperimentLedger, feature names/units marked unimplemented, ForecastPacket schema,
  number-free BASE/STRESS/SEVERE cost contract, and OBSERVE_ONLY hard-safety contract.
- The target GitHub repository was empty at task start. The connected GitHub integration
  published the certified source tree to `main` at
  `3f1bb4294d26acbe7f4977f65b7a69483a6f124a` without force-push. The private
  specifications and all credentials, raw data, caches, and bulk outputs are excluded.

## ASSUMED_FOR_LOCAL_TEST_ONLY

- Synthetic timestamps, payloads, symbols, expiry values, ticks, and multipliers are
  used only to test invariants and schemas. They are never certification evidence.
- Event-instant roll semantics are conservative: a delivered mapping change is
  `ROLL_TRANSITION` only at its observed/effective visibility instant and `POST_ROLL`
  afterward. No pre-roll window or future-volume inference exists.
- The 182-day contract filter is bounded inspection configuration, not an exchange or
  institutional threshold.
- The random seed `20240826` is manifest metadata; Lift 1 performs no random research.

## NOT_VERIFIED

- QuantConnect account identity, organization tier, cloud-project access, futures/CFTC
  entitlements, and whether any local data request would incur QCC.
- Actual QC cloud Python/LEAN/Python.NET versions and runtime architecture.
- Real ES/ZN/6E rows, mapped paths, mapping events, expiries, OI coverage, ticks,
  multipliers, missing intervals, and QC exchange objects for the fixed 2024 window.
- Actual CFTC TFF coverage, nullable fields, Slice/data clocks, ordinary releases, and
  holiday-delayed releases in the 2026 audit window.
- Notebook 01 execution in QC Research. Its structural thin-client parity is verified;
  no execution claim is made.
- Empirical live mapping delivery. Official QC documents the backtest/live timing
  difference; the adapter changes identity only when its own environment delivers the
  observation.
- Backwards-Ratio values as executable or point-in-time signal prices. They are
  deliberately restricted to continuous research/identity use.

## BLOCKED

- **Authenticated QuantConnect execution is the sole external blocker.** No authorized
  QC environment variables or existing CLI session were present. `lean whoami` could
  not use the protected default CLI home, and the authorized official browser login
  route reached a secure authentication request that was declined. The request was not
  retried and no credentials were searched for elsewhere.
- Consequently no QC project/backtest ID, empirical futures artifact, empirical CFTC
  delivery artifact, QC runtime datetime artifact, executed Notebook 01 output, or
  qualified closure manifest can truthfully be produced. No other vendor or synthetic
  data may close these gates.

## DEFERRED_TO_LIFT_2

- Volume/Market Profile, Auction State, IMSI, ICM, IAE, L2, candidate events, labels,
  event studies, returns, P&L, forecasts, ML, portfolio/risk behavior, execution,
  orders, paper trading, and live trading.
- Numerical feature, forecast, cost, or safety behavior. Lift 1 contains contracts only.

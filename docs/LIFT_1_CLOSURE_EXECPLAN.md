# Lift 1 Closure ExecPlan

Status: `RECONCILED_EXTERNAL_SECRET_OR_ENTITLEMENT_REQUIRED`
Updated: 2026-08-27
Boundary: Lift 1 research/data readiness only; no Lift 2 behavior.

## Purpose

Close every reachable Lift 1 gate with deterministic evidence and leave only a
credential, entitlement, or paid-resource dependency as an external blocker. No
documentation or synthetic fixture may substitute for a real QuantConnect observation.

## Current state

- Both specifications were read from the supplied private workspace and retain SHA-256
  `ef19e4242a48747ef13b235e38f9c9fa0c09a7ed07085b5bb689be39a8786747` and
  `bdebaf3e0ec38c3cb13d605b1fdc289db0a6316218756d0264ed23856f3195b2`.
- The public target repository was verified empty and cloned to the writable canonical
  workspace `/workspace/QC-Systematic-Futures-`. The specifications are mounted under
  ignored `upload/` and will not be pushed.
- GitHub integration reports admin/push permission for
  `Afeks214/QC-Systematic-Futures-`.
- CPython 3.11.15 is installed through `uv`; the project and LEAN CLI use separate
  environments. Official LEAN CLI 1.0.228 is installed and executes.
- QuantConnect access path 1 (`lean whoami`) could not inspect credentials because the
  default CLI home is read-only. No authorized QuantConnect environment variables or
  existing CLI session were present.
- QuantConnect access path 2 reached the official cloud login in the authorized browser;
  the secure authentication request was declined. It will not be retried without a new
  user authorization event.
- No QC project, cloud backtest, market-data observation, CFTC observation, or notebook
  runtime output exists. Those gates remain external-access dependent.

## Closure matrix

| Gate | Evidence required | Command or test | Expected artifact | Pass | Fail | Status |
|---|---|---|---|---|---|---|
| Writable Git and push | Local and remote `main` resolve to the same SHA | Git commit; GitHub write API; fetch/verify | closure report/evidence index | SHA equality | write auth absent | PASS — final delivery verification pending |
| Python 3.11 | Full mandated suite under 3.11.x | exact quality sequence | `python311_quality_gate.json` | every exit 0 | any failure | PASS — CPython 3.11.15 |
| LEAN CLI | Current official executable | `lean --version` | quality/evidence index | 1.0.228 observed | unavailable | PASS |
| QC authentication/tier | Authenticated account status | `lean whoami` or official browser/cloud session | QC IDs/status | account and tier observed | no secret/session | EXTERNAL SECRET REQUIRED |
| ES/ZN/6E runtime | Fixed-window read-only cloud probe | `lean cloud backtest ... --push` | futures probe evidence | all roots and zero actions | missing data/run | BLOCKED BY QC ACCESS |
| Mapping/OI/metadata/datetime | Empirical fields from the same run | cloud result/API | futures and datetime evidence | required fields present | inferred/static only | BLOCKED BY QC ACCESS |
| Sessions/calendar | Current official LEAN market-hours database plus semantic tests | parameterized pytest | session matrix | ordinary/DST/holiday/early-close/cross-midnight pass | guessed date/rule | PASS — pinned version |
| Notebook 01 | Actual execution or documented thin-client runtime parity | QC Research or certified shared probe | data-probe summary | real QC outputs | structural-only | BLOCKED BY QC ACCESS |
| CFTC timing | Official clock plus actual QC ordinary/delayed delivery | CFTC cloud probe | CFTC timing evidence | gate never early | synthetic-only | BLOCKED BY QC ACCESS |
| PIT/ledger/contracts | Deterministic local tests | pytest | quality record | invariant tests pass | any failure | PASS |
| Qualified closure manifest | Non-null Git, LEAN, QC IDs, and empirical hashes | manifest builder | closure manifest | all evidence real | placeholder/null | BLOCKED BY QC ACCESS |

## Exact remaining work

1. Commit and publish the final evidence/report tree; verify local and remote SHA equality.
2. If a new authorized QC session becomes available, synchronize the exact Git revision,
   run futures and CFTC cloud probes, retrieve results through official APIs, execute or
   establish thin-client parity for Notebook 01, and build the qualified manifest.
3. Otherwise issue `EXTERNAL_SECRET_OR_ENTITLEMENT_REQUIRED` with QuantConnect access as
   the sole unresolved dependency and no synthetic runtime claims.

## Verification commands

```bash
.venv/bin/python -m compileall systematic_futures main.py
.venv/bin/ruff format --check .
.venv/bin/ruff check .
.venv/bin/pyright
.venv/bin/pytest -q
.venv/bin/python scripts/validate_notebooks.py
.venv/bin/python scripts/build_manifest.py
bash -n scripts/bootstrap_mac_m4.sh scripts/run_quality_checks.sh
```

Cloud commands are permitted only after authenticated account status is established and
must never use a nonzero data-purchase limit.

## Progress

- [x] Re-read the Master Definition of Ready and Intraday Lift boundary.
- [x] Inspect the existing implementation, reports, notebooks, manifest, and tests.
- [x] Recover a writable clone of the empty target repository without force-push.
- [x] Install CPython 3.11.15 and LEAN CLI 1.0.228 through official supported paths.
- [x] Exhaust the existing CLI-session and authorized browser-session access paths.
- [x] Verify the current official LEAN market-hours database at commit
  `07fb0182bfe229edd9445cf675ac6509d0069539`.
- [x] Finish session fixtures, cleanup, and Python 3.11 evidence.
- [x] Publish the exact certified source tree to canonical remote `main`.
- [x] Reconcile the closure report and evidence index.
- [ ] Publish the final evidence commit and verify local/remote SHA equality.

## Decision log

- Docker is not required for cloud certification and is not a blocker.
- The private specifications are mounted for hashing but excluded from the public Git
  tree.
- A declined secure QuantConnect authentication request is treated as unavailable
  authorization, not as permission to seek credentials elsewhere.
- Real QC evidence remains absent; no status promotion or runtime artifact will be
  fabricated.

## Final reconciliation

All locally executable milestones reconcile. The final delivery commit and remote-SHA
check are the remaining mechanical handoff operations. Authenticated QC execution is
the sole external dependency; without it, the required result is
`EXTERNAL_SECRET_OR_ENTITLEMENT_REQUIRED` and no qualified closure manifest is built.

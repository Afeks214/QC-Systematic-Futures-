# Mac M4 and QuantConnect/LEAN Bootstrap

Verified against current official material on 2026-08-26. The canonical CLI
version reviewed was `1.0.228`; the current LEAN source baseline was commit
`185c691b89f28bd68e48d53c02147415134975f0`. Re-verify commands and images before
changing these pins.

## 1. Install Docker Desktop for Apple Silicon

Install the Apple Silicon build from the official [Docker Desktop for Mac](https://docs.docker.com/desktop/setup/install/mac-install/)
page, start Docker Desktop, and verify:

```bash
docker version
docker info
```

Docker documents Apple Silicon separately from Intel Mac and recommends at least
4 GB of memory. Docker Desktop licensing depends on the organization; review its
current terms rather than assuming eligibility.

## 2. Create the Python 3.11 environment

LEAN's pinned Docker definitions use Python 3.11.11. Install a current supported
Python 3.11 patch release and run the idempotent local bootstrap:

```bash
bash scripts/bootstrap_mac_m4.sh
source .venv/bin/activate
python --version
```

The script installs only the pinned development dependencies in
`requirements.txt`. It never logs in, asks for secrets, buys data, or creates cloud
resources.

## 3. Install VS Code

Install [Visual Studio Code](https://code.visualstudio.com/) and its official Python
extension. Open the repository directory and select `.venv/bin/python` as the
interpreter. `quantconnect-stubs` is intentionally omitted: no immutable mapping
between a current package version, the pinned LEAN commit, and Python 3.11.11 was
verified for this Lift.

## 4. Install the LEAN CLI

Inside the activated environment, install the reviewed CLI version explicitly:

```bash
python -m pip install lean==1.0.228
lean --version
```

The official [lean-cli repository](https://github.com/QuantConnect/lean-cli) notes
that local research and backtesting use Docker. Re-verify the pinned version before
upgrading it.

## 5. Authenticate manually

Run the interactive command yourself:

```bash
lean login
```

Do not put user IDs, API tokens, `.env` files, global CLI credentials, or copied
authentication output in this repository. The bootstrap script never runs login.

## 6. Initialize a LEAN workspace

The repository is a project, while LEAN CLI operates from an organization workspace.
Create a separate parent workspace so the generated workspace files do not obscure
the audited repository tree:

```bash
mkdir InstitutionalFuturesWorkspace
cd InstitutionalFuturesWorkspace
lean init --language python
```

Initialization creates configuration and sample data; it does not validate futures
entitlements or execute the probe.

## 7. Create the project with the current command

The canonical command is `project-create`; `create-project` is only an alias:

```bash
lean project-create --language python "InstitutionalFuturesLift1"
```

Official source: [lean project-create API](https://www.quantconnect.com/docs/v2/lean-cli/api-reference/lean-project-create).

## 8. Use this repository as the QC project

Copy the repository contents into the generated
`InstitutionalFuturesLift1/` directory while preserving the CLI-generated
`config.json` and editor files required by that workspace. Do not copy `.venv`,
credentials, artifacts, caches, or the outer workspace configuration. Review the
result before running anything; `main.py` must still define only
`InstitutionalFuturesDataProbe`.

An alternative is to place a checkout of this repository directly at the generated
project path, then restore only the officially generated `config.json` locally.
Generated LEAN workspace files are environment scaffolding, not research evidence.

## 9. Open the local Research Environment

From the organization workspace:

```bash
lean research "InstitutionalFuturesLift1"
```

This starts JupyterLab in Docker. Open
`research_notebooks/01_data_state_research.ipynb`. QuantBook is interactive: it can
request arbitrary history, so the fixed end date and explicit UTC boundary must not
be relaxed silently.

## 10. Run a local backtest

With required futures files already available locally:

```bash
lean backtest "InstitutionalFuturesLift1" --data-provider-historical Local
```

This executes only the read-only data probe because `main.py` contains that class.
It is called a backtest by LEAN, but this project neither places orders nor evaluates
a strategy.

## 11. Run a cloud backtest

After you have intentionally reviewed the cloud project and upload, run:

```bash
lean cloud backtest "InstitutionalFuturesLift1" --push --open
```

The official [workflow documentation](https://www.quantconnect.com/docs/v2/lean-cli/projects/workflows)
states that `--push` uploads local modifications before execution. This task did not
run the command. Cloud use requires credentials, an eligible organization, and data
access.

## 12. Run the probe algorithm only

Confirm the class name and prohibited-token scan before either execution path:

```bash
python -m compileall systematic_futures main.py
rg -n "market_order|limit_order|stop_market_order|set_holdings|liquidate|emit_insights|Insight\\(|PortfolioTarget\\(" main.py
lean backtest "InstitutionalFuturesLift1" --data-provider-historical Local
```

The expected `rg` result is no matches. The fixed algorithm period is 2024-02-15
through 2024-03-25 and subscriptions are only ES, ZN, and 6E.

## 13. Avoid unnecessary bulk futures downloads

Prefer the credentialed cloud probe when the necessary data is available there.
For local work, first use the Local provider and obtain only files required by the
three-market, fixed-period probe. Do not run `--download-data` automatically.

QuantConnect documents that its API data provider can download requested files and
that no spending limit is applied by default. If you deliberately select that
provider, set and approve a finite `--data-purchase-limit` appropriate to the
organization before running. The [local backtesting documentation](https://www.quantconnect.com/docs/v2/lean-cli/backtesting/deployment)
is authoritative for the current options.

## 14. Record the LEAN version

`lean --version` records the CLI version, not the exact engine build. Retain all of:

```bash
lean --version
docker image inspect quantconnect/lean:latest --format '{{json .RepoDigests}}'
docker image inspect quantconnect/research:latest --format '{{json .RepoDigests}}'
```

Also retain the LEAN engine version line from the actual run log. Populate
`ResearchRunManifest.lean_version` only from that direct evidence; otherwise keep
it `None`.

## 15. ARM versus cloud differences

- Apple M4 is arm64; Docker Desktop selects an Apple Silicon virtualization path.
  An amd64-only image or dependency may require emulation and behave differently.
- LEAN maintains an ARM foundation Dockerfile, but the exact locally pulled image
  digest still must be recorded.
- Local execution uses local hardware, the configured Docker image, and local or
  explicitly selected data. Cloud execution uses QuantConnect infrastructure,
  entitlements, data, and a potentially different engine image.
- Performance, timestamps, mapping-event delivery, and available files must be
  compared from artifacts; parity is not assumed.

## 16. Credential warning

Never commit credentials, `.env` files, CLI global configuration, Docker registry
tokens, copied notebook API variables, or cloud logs containing secrets. If a
credential appears in repository output, stop, revoke it through the official
provider workflow, and remove it from history before continuing.

## Local prerequisite status for this task

The Codex workspace used to build Lift 1 had Python 3.12 rather than Python 3.11,
and it did not expose LEAN CLI, a verified LEAN image, QC credentials, or futures
data. Core checks may be executed locally, but QC runtime checks remain
`NOT_EXECUTED` until the steps above are completed in an authorized environment.

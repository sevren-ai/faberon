# Faberon CLI reference

The `faberon` command is installed with the brain (see [install.md](install.md)). Two commands work locally (`faberon init` and `faberon serve`). The other commands post to the brain's HTTP API for managing campaigns.

## faberon init

```bash
faberon init
```

Setup wizard. Generates the API token, asks for the LLM model and, on a Slurm cluster, the account, then writes the config file with mode `0600`. Requires a running Postgres and creates the `faberon` database. Re-run it after every upgrade: it shows every current value as the prompt default and fills in keys the new version added. The full settings reference lives in [configure-faberon.md](configure-faberon.md).

## faberon serve

```bash
faberon serve [--no-recover]
```

Starts the API server, binding to the `host` and `port` from the config file. The executor comes from the config's `executor` key, defaulting to `slurm` when `sbatch` is on `PATH` and to `local` otherwise. At startup it checks the configuration and probes Postgres, then resumes every pending campaign workflow (DBOS recovery).

- `--no-recover`: do not resume pending workflows at startup. Use it to break a crash loop, then act on campaigns one by one with `faberon resume` or `faberon cancel` (see [troubleshooting.md](troubleshooting.md)).

Run it inside `tmux` or `screen` so it survives your SSH session.

## faberon create

```bash
faberon create <plan.json> [repo] [--poll SECONDS] [--branch NAME]
```

Submits a research plan and starts a campaign. The plan file is validated before submission; invalid JSON and plan-schema violations are reported one field per line. `repo` defaults to the current directory and must be a clean git working tree. Prints the campaign ID and the workflow ID.

- `--poll, -p`: poll interval in seconds for job status checks (default 30).
- `--branch, -b`: working branch to adopt or create. Defaults to a fresh `faberon/<short-id>` branch.

## faberon successor

```bash
faberon successor <campaign-id> --budget-gpu-hours N --max-experiments M [--branch NAME]
```

Starts a successor from a finished campaign's best kept commit. The successor runs the exact same research plan as the predecessor's. To change the plan itself, use `faberon create` instead.

- `--budget-gpu-hours`: fresh GPU-hour budget (required).
- `--max-experiments`: fresh experiment cap (required).
- `--branch, -b`: working branch for the successor. Defaults to a fresh `faberon/<short-id>` branch.

## faberon list

```bash
faberon list [--json]
```

Lists all campaigns, oldest first, with live progress derived from the ledger: status, metric, experiments done vs. cap, GPU-hours burned vs. budget, and baseline to current best.

- `--json, -j`: emit machine-readable JSON instead of the table.

## faberon show

```bash
faberon show <campaign-id> [--json]
```

Shows one campaign: status, plan details, live progress (experiments done, GPU-hours burned, baseline to current best), and the stop reason when the campaign has ended.

- `--json, -j`: emit machine-readable JSON.

## faberon events

```bash
faberon events <campaign-id> [--follow] [--after SEQ] [--verbose] [--json]
```

Prints the campaign's ledger, one event per line.

- `--follow, -f`: stream new events live instead of printing a bounded snapshot.
- `--after`: skip events with sequence numbers up to this one.
- `--verbose, -v`: show full event payloads.
- `--json, -j`: emit raw events as JSONL, one per line.

## faberon cancel

```bash
faberon cancel <campaign-id> [--reason TEXT]
```

Requests cancellation of an active campaign. The reason is recorded in the ledger and must not be empty.
Note that cancellation might not happen immediately.

- `--reason, -r`: why the campaign is cancelled. Prompted interactively when omitted.

## faberon resume

```bash
faberon resume <campaign-id>
```

Resumes a pending campaign's workflow from its last checkpoint. Does not resubmit a job that was already submitted. A campaign whose workflow ended or died cannot be resumed. In those cases, you should start a successor instead.

## faberon chat

```bash
faberon chat [extra args...]
```

Starts the chat interface: hands over to plain `pi` when it is on `PATH` (which auto-loads the extension once installed), falling back to the `faberon-chat` npm shim. Extra arguments are passed through to Pi. When neither is found, it prints install guidance and exits. See [chat.md](chat.md).

## faberon --version

```bash
faberon --version
```

Prints the installed brain version and exits.

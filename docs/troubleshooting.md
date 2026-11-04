# Troubleshooting

Procedures for when a running Faberon misbehaves.

## `faberon init` cannot connect, but Postgres is running

On a no-sudo (login node) install, `FABERON_PG_URL` in `~/.config/faberon/postgres.env` may be missing the database password. 

Repair by re-running the installer while Postgres is up. It detects the missing password, resets it over the trust-authenticated unix socket, and rewrites the env file:

```bash
bash ~/.local/bin/start-postgres.sh   # if Postgres is not already running
bash install-postgres-no-sudo.sh      # re-run: repairs FABERON_PG_URL
```

Then re-run `faberon init`.

## Safe restart and recovery

By default Faberon resumes every pending campaign workflow at startup (DBOS recovery). If a recovered workflow is what destabilized the cluster, that becomes a crash loop: recover, resubmit, kill, repeat. To break it, start in no-recover mode so no workflow resumes at boot, then act on campaigns one by one:

```bash
faberon serve --no-recover
faberon list                          # live status: active / ended / died
faberon resume <id>                   # resume one from its last checkpoint
faberon cancel <id>                   # or cancel one you do not want to run again
```

`resume` replays from the last checkpoint; it does not resubmit a job already submitted. A campaign whose workflow ended or died cannot be resumed in place: start a new campaign seeded from its best metric and head sha, which are recorded in the ledger.

## Upgrading Faberon

Upgrade the brain the same way you installed it. From PyPI:

```bash
uv tool upgrade faberon
```

From a source checkout: `uv tool install` builds a snapshot of the source, so `git pull` alone does not update the installed `faberon` command. Reinstall after every pull:

```bash
uv tool install --force packages/brain
```

After every upgrade, re-run `faberon init` to review your settings: it shows every current value as the prompt default, fills in keys the new version added, and re-checks the database.

Be careful when upgrading Faberon while you have an active campaign running. DBOS won't be able to recover the old workflow, and the campaign won't resume after starting the new version of Faberon.

Instead, such outdated campaigns will be forcefully ended with a stop reason `error`, naming the upgrade as the reason. The repo is then free for a new campaign right away: you can continue the research with a follow-up or a re-seed/resume from the campaign's best metric and head sha.

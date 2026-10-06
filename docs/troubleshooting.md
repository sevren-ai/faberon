# Troubleshooting

Procedures for when a running Faberon misbehaves.

## Safe restart and recovery

By default Faberon resumes every pending campaign workflow at startup (DBOS recovery). If a recovered workflow is what destabilized the cluster, that becomes a crash loop: recover, resubmit, kill, repeat. To break it, start in no-recover mode so no workflow resumes at boot, then act on campaigns one by one:

```bash
FABERON_NO_RECOVER=1 faberon serve    # ensure the environment is correctly set up before running 'serve'
faberon list                          # live status: active / ended / died
faberon resume <id>                   # resume one from its last checkpoint
faberon cancel <id>                   # or cancel one you do not want to run again
```

`resume` replays from the last checkpoint; it does not resubmit a job already submitted. A campaign whose workflow ended or died cannot be resumed in place: start a new campaign seeded from its best metric and head sha, which are recorded in the ledger.

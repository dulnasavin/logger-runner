# Crypto Logger runner

This public repository contains the orchestration workflows only. Production
Python source stays in the private repository and is executed from the exact
40-character commit recorded in the `PRIVATE_CODE_SHA` repository variable.
Mutable CSV and incident state is isolated on the private `runtime-data` branch.

## Safe first deployment

1. Pause the external five-minute dispatcher for the short deployment window.
   This prevents the old runner from loading partially deployed private code or
   applying a schema before the reviewed workflow rollout is in place.
2. Merge and test the private source changes, then set `PRIVATE_CODE_SHA` in
   this repository to that exact private commit SHA.
3. Merge the public runner workflow changes while the dispatcher remains paused.
4. Run **CSV Maintenance | Controlled** on public `main`, select
   `seed-runtime-data`, and enter `CREATE_RUNTIME_DATA`. The action refuses to
   replace an existing branch.
5. Run **CSV Maintenance | Controlled** with `validate`.
6. Only after the schema migration has passed on an isolated Neon branch and
   received explicit production approval, run **Neon Schema | Controlled
   Migration** once with `APPLY_NEON_SCHEMA`, then run **Neon Sync | Manual
   Catch-up**.
7. Run **Make Outlook Alert Test**, then manually run **Crypto Logger | Main**.
8. Resume the single external five-minute dispatcher only after the complete
   manual run (including the dependent Neon job) succeeds.
9. Enable `ENABLE_NEON_WEEKLY_AUDIT=true` only after the audit has passed
   against an isolated Neon branch.

The established external five-minute dispatcher is the only production
scheduler. The main workflow intentionally has no second GitHub cron.

## Controlled CSV deletion

Never delete `price_log.csv` or its rows by hand. Missing or damaged files are
treated as accidental and restored from the active Git generation.

- For a complete clean start, run **CSV Maintenance | Controlled**, choose
  `intentional-reset`, enter `RESET_PRICE_LOG`, and supply a non-sensitive
  reason. This starts a new generation; older Neon generations are archived
  and cannot repopulate the new CSV.
- For wrong historical data, first choose `preview-selected-batches`, then
  choose `delete-selected-batches`, enter one or more exact `timestamp_nz`
  values, supply a reason, and confirm with `DELETE_PRICE_BATCHES`.
- For batches already removed manually, first choose
  `preview-existing-deletions`, then choose `register-existing-deletions`, enter
  the exact missing `timestamp_nz` values, supply a reason, and confirm with
  `REGISTER_DELETED_BATCHES`. This records tombstones without changing the
  current CSV, allowing the weekly audit to remove the matching Neon rows.

Selected deletion always removes the complete eleven-symbol run. It records an
atomic tombstone in `csv_state.json`; Git restoration will continue excluding
that run, normal Neon Sync remains insert-only, and the controlled weekly audit
deletes only exact tombstoned rows from the active Neon generation. Arbitrary
single-symbol deletion is intentionally rejected because it would create an
incomplete trading-data batch.

## Repository secrets and variables

Existing `PRIVATE_REPO_TOKEN` remains supported. For least privilege, replace it
later with both of these fine-grained secrets:

- `PRIVATE_CODE_READ_TOKEN`: private repository Contents **read-only**.
- `PRIVATE_DATA_WRITE_TOKEN`: private repository Contents **read/write**, scoped
  to the runtime-data repository/branch as tightly as GitHub allows.

When a split token is absent, workflows fall back to `PRIVATE_REPO_TOKEN` for
compatibility. Never remove the legacy secret until one complete manual run has
passed with both split tokens.

`PRIVATE_CODE_SHA` is required and must be a full commit SHA. The only files a
normal production run may commit to `runtime-data` are `price_log.csv`,
`csv_state.json`, `provider_incident_state.json`, and `runtime_manifest.json`.

## Protection model

Protect public `main` and private source `main` after the rollout PRs merge.
Runtime writes must target only `runtime-data`; do not point
`PRIVATE_DATA_BRANCH` back to source `main`. GitHub branch rules, fine-grained
token creation, and the external scheduler are account settings and are not
changed by repository code.

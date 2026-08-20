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

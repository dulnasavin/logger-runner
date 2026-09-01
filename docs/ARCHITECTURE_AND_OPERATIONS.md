# Architecture and operations

## Trust boundaries

The system separates orchestration, immutable code and mutable data so a workflow error cannot silently become a historical-data rewrite.

| Plane | Repository and branch | Allowed content |
|---|---|---|
| Control | public `logger-runner/main` | Approved production workflows |
| Verification | public `logger-runner/staging` | Offline staging gates and proposed workflows |
| Code | private `main` and `staging` | Python, tests, schemas and dependency locks |
| Data | private `runtime-data` | `price_log.csv`, `csv_state.json`, `provider_incident_state.json`, `runtime_manifest.json` |
| Database | Neon | Generation-aware relational copy and reconciliation records |

The protected public `config/production-release.json` manifest bridges the
control and code planes. It selects exactly one private commit and carries
separate fail-closed capability switches for logger execution, runtime
maintenance and Neon operations.

## Non-negotiable invariants

1. Production executes only public `main` and one full private source SHA.
2. Staging never writes `runtime-data`, Neon, production CSV history or GitHub VPN secrets.
3. Runtime commits contain only the four allowlisted data/provenance files.
4. CSV writes are lock-protected, validated and atomic.
5. Every accepted batch contains exactly 11 unique symbols.
6. Missing CSV rows are not interpreted as intentional deletion.
7. Intentional deletion requires an active-generation tombstone created by controlled maintenance.
8. Neon reconciliation is previewed before apply and the approved plan ID must match the current CSV and Neon state.
9. Same-key financial conflicts and incomplete batches fail closed.
10. All third-party GitHub Actions use full commit SHAs.
11. Production code selection comes only from the protected public release manifest, never a mutable repository variable.
12. Every production-capable workflow validates its own capability as enabled before accessing private runtime data or Neon.

## Intentional row deletion

1. Run `CSV Maintenance | Controlled` with `preview-selected-batches`.
2. Confirm the exact timestamps, 11-row batches and non-sensitive reason.
3. Run `delete-selected-batches` with `DELETE_PRICE_BATCHES`.
4. Run `Neon Reconciliation | Controlled` in `preview` mode.
5. Review its sanitized counters and copy the exact `nrp-v1-*` plan ID.
6. Run `apply-approved-plan` with that plan ID, `APPLY_NEON_RECONCILIATION`, and the reason.

If either CSV or Neon changes between steps 4 and 6, the content-addressed plan ID changes and apply is rejected.

## Promotion protocol

1. Rebase or merge the current `main` baseline into both staging branches.
2. Pass private security CI and the public provider-resilience gate.
3. Review complete `main...staging` diffs and remove temporary artifacts.
4. Open private and public pull requests; never merge `runtime-data`.
5. Merge only after explicit approval and passing required checks.
6. Update the protected release manifest to the approved full private production commit while all capabilities remain disabled.
7. Enable only the logger capability in a separate approved public pull request for the canary.
8. Keep runtime maintenance and Neon disabled until separately approved.
9. Enable each remaining capability through its own reviewable public manifest change.

## Recovery policy

- Network error: one reconnect of the current route; a failed VPN1 reconnect may consume the one VPN2-switch budget.
- Rate limit: bounded `Retry-After`, then the one VPN2-switch budget when eligible.
- Provider server error: bounded backoff without changing network routes.
- VPN authentication error: dedicated VPNBook credential recovery, not ordinary provider failover.
- Exhausted recovery: fail closed without persisting an incomplete price batch.

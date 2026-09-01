# Crypto Logger Control Plane

This public repository contains the GitHub Actions control plane for the private crypto logger. It contains orchestration and security workflows only; application source, credentials, price history, and mutable runtime state remain private.

## Branch contract

| Branch | Responsibility | Mutable data |
|---|---|---|
| `main` | Approved production orchestration | Never stored here |
| `staging` | Offline verification and proposed workflow changes | Never stored here |

The private repository supplies the corresponding code plane:

- private `main`: approved immutable application source;
- private `staging`: S2 development and regression testing;
- private `runtime-data`: isolated mutable CSV/state plane with unrelated Git history.

`runtime-data` must never be merged into `main` or `staging`.

## Zero-cost production release authority

`config/production-release.json` is the only production release authority. It
pins one full private source commit and independently disables or enables the
logger, runtime maintenance and Neon capabilities. Production-capable
workflows validate it with `scripts/validate_release_manifest.py` and fail
closed. A mutable repository variable cannot select production code.

Because the authority lives on protected public `main`, changing a private
production pin or enabling a capability remains reviewable even when private
branch-protection enforcement is unavailable on the free GitHub plan.

## Permanent workflows

- `Crypto Logger | Main` — production logger, manual dispatch entry point, protected `main` only.
- `Provider Resilience | Staging Verification Gate` — offline staging regression and S2 fault tests.
- `CSV Maintenance | Controlled` — validated reset, restoration and exact-batch deletion controls.
- `Neon Sync | Manual Catch-up` — insert-only catch-up; it never infers database deletion from a missing CSV row.
- `Neon Reconciliation | Controlled` — read-only preview followed by content-addressed approved apply.
- `Neon Schema | Controlled Migration` — explicit schema changes only.
- `Workflow Security` and `CodeQL` — supply-chain and source security gates.

See [Architecture and operations](docs/ARCHITECTURE_AND_OPERATIONS.md) for invariants, promotion rules and recovery procedures.

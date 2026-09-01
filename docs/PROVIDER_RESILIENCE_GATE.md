# Provider Resilience verification gate

This is the permanent offline staging gate for the S2 provider-network recovery milestone.

## Isolation contract

- Public source: `staging`, read-only.
- Private source: `staging`, read-only.
- Production `main`: never executed by this gate.
- `runtime-data`: never checked out or modified.
- Neon credentials: never loaded.
- Live VPN and provider calls: never made.

## Recovery invariants

1. VPN1 is the primary route and VPN2 is cold standby.
2. A network failure may reconnect the active route once.
3. A failed VPN1 reconnect may activate VPN2 once.
4. A rate limit may use bounded `Retry-After`, then the one VPN2 switch budget.
5. Provider server errors use bounded backoff without changing VPN routes.
6. VPN authentication failures use the dedicated credential-recovery controller.
7. Provider clients and pooled connections are recreated after route changes.
8. One logger run may perform at most one successful VPN2 switch.
9. Exhausted recovery fails closed before runtime data is persisted.

This gate remains offline after S2 promotion and continues as a regression boundary.


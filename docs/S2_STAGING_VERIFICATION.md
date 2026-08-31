# S2 staging verification

This document records the temporary staging gate for the S2 network-recovery rollout.

## Safety boundary

- Public branch: `staging` only.
- Private code: read-only checkout of private `staging`.
- Production `main`: not executed or modified by the staging verification workflow.
- Private `runtime-data`: not checked out or written.
- Neon credentials and writes: not used.
- GitHub VPN secret persistence: disabled during staging verification.

## Network policy under test

1. Validate VPN1 and VPN2 runtime profiles without opening both tunnels.
2. Normalize only safe OpenVPN TCP client aliases in protected runtime copies.
3. Connect and verify VPN1 as the primary route.
4. Verify the root-owned OpenVPN process with controlled read-only `sudo` `/proc` inspection when the runner cannot read it directly.
5. Keep VPN2 as cold standby while VPN1 is healthy.
6. For a network failure, reconnect the current VPN once.
7. If VPN1 cannot recover, activate VPN2 once and verify the new route.
8. Recreate provider HTTP/SDK clients after a route change.
9. Do not switch VPN for authentication or provider server errors.
10. Enforce one global VPN2-switch budget for the logger run.
11. If both routes fail, fail closed and preserve production data.

The temporary live staging workflow should be removed or made manual-only before S2 is promoted to production.

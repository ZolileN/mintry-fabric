# Release Notes — Mintry Fabric v1.1.0 (Phase 2)

Enterprise Phase 2 gate on top of the v1.0.0 closed enforce loop.

## What's new

| ID | Capability |
| --- | --- |
| E0 | Fleet Option A — static sub-budget partitioning |
| E1 | Agent-grouped ledger UI |
| E2 | Org hierarchy compile → flat agent caps |
| E3 | Go `mintry-proxy` sidecar scaffold (Alpine / k8s) |
| E4 | OPA-shaped bundles materialize at sync; no CLI on hot path |
| E5 | Vault alias-only secret references |

## Architecture reminder

Authorize still evaluates only local numbers. Org inheritance, fleet partitions, and OPA envelopes all compile **before** the hot path.

## Follow-ups

- Sidecar HTTPS MITM
- Sidecar built-in policy poller

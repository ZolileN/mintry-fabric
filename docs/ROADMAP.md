# Mintry Fabric Roadmap

This roadmap reflects the code currently present in the repository.

> [!IMPORTANT]
> **Architectural Alignment:** All items on this roadmap, including "Ideas Under Consideration", are strictly subject to validation against the [Six Architecture Principles](ARCHITECTURE.md). Any feature that compromises deterministic, zero-latency local enforcement will be removed from the roadmap.

## Repository Status

**Current release: `v1.1.1`** (Phase 2 enterprise gate + promise-alignment tighten).

See [PHASE2_PLAN.md](./PHASE2_PLAN.md), [PRODUCTION_READINESS_PLAN.md](./PRODUCTION_READINESS_PLAN.md),
[RELEASE_NOTES_v1.1.0.md](./RELEASE_NOTES_v1.1.0.md), and [CHANGELOG.md](../CHANGELOG.md).

### Supported product path

| Layer | Status |
| --- | --- |
| Python SDK + local SQLite WAL | **Supported** — enforce locally, zero CP I/O on allow/block |
| Dashboard Sign & Push → Supabase | **Supported** — central authoring source of truth |
| Fleet Option A / Org compile → flat caps | **Supported** — compiled before the hot path |
| Go `mintry-proxy` sidecar | **Scaffold** — HTTP metering works; HTTPS MITM TBD |
| Node SDK (`mintry-node`) | **Prototype** — private `0.1.0` |
| Legacy `apps/sync-api` | **Demo stub only** — not the control plane |

### Promise alignment (v1.1.1)

- With `MINTRY_CONTROL_PLANE_URL` set, local mandate upsert/revoke requires `MINTRY_LOCAL_GOVERNANCE=1`
- Dashboard leads with Sign & Push / Fleet / Org; local ledger edits are gated
- README / SECURITY honestly label supported vs scaffold paths

## Completed Milestones

### v0.1.1 – v0.5.0

Prior milestones (interception, async, multi-provider, lifecycle, dashboard) — see git history / CHANGELOG.

### v1.0.0 — Phase 1 production gate (2026-07-28)

- [x] Canonical ES256 policy contract (Python + dashboard)
- [x] PolicyCache wired into `PolicyEngine.authorize()`
- [x] Dashboard admin token / login cookie; Python API bearer
- [x] Spend reservations + durable flush/`close()`
- [x] TelemetryBatcher from `init()`
- [x] Idempotent `init()`; DoD test suites
- [x] Legacy sync-api / Node SDK honesty labels
- [x] Dashboard credibility (§10): demo mode, KPIs, audit feed, brand palette
- [x] Closed control-plane loop: sign → poll → verify → enforce; LKG on failure

### v1.1.0 — Phase 2 enterprise gate (2026-07-28)

See [PHASE2_PLAN.md](./PHASE2_PLAN.md).

- [x] **E0** Fleet Option A static sub-budget partitioning
- [x] **E1** Agent-grouped ledger (UI)
- [x] **E2** Org hierarchy compile → flat agent caps
- [x] **E3** Go sidecar scaffold (`apps/sidecar` / `mintry-proxy`)
- [x] **E4** OPA compile-at-sync materialization (no CLI on hot path)
- [x] **E5** Vault alias-only secret references

### v1.1.1 — Promise alignment (2026-07-28)

- [x] Central Sign & Push default when control plane configured
- [x] Local ledger mutations opt-in (`MINTRY_LOCAL_GOVERNANCE`)
- [x] Dashboard authoring UX reordered; docs honesty pass

## Next (post–Phase 2)

Ordered by leverage for the stated promise ("init once / author centrally / enforce locally / any language"):

1. **Sidecar HTTPS MITM** — inspect/meter TLS LLM traffic through `HTTP(S)_PROXY` without uninspected tunnels
2. **Sidecar policy poller** — same verify → LKG → flat-cap loop as the Python SDK (today Python syncs; sidecar reads ledger)
3. **Full Supabase Auth UI** — replace shared admin token for multi-user dashboard access
4. **Configurable intent blocklists** — move built-in phrases into signed policy (still deterministic allow/block)
5. **Option B fleet hard cap** — Redis/Upstash atomic counter only if Option A partitions prove insufficient

## Explicitly Deferred

From [CONTROL_PLANE_SPEC.md](./CONTROL_PLANE_SPEC.md) §8 — do not pull onto the hot path:

- Automatic model rerouting
- Anomaly / recommendation engine (analytics layer only)
- Push-based policy propagation (until enterprise SLA requires it)

## Ideas Under Consideration

- Shared ledger mode beyond a single local SQLite file (per-pod emptyDir + Option A remains preferred)
- VS Code spend visibility
- Automated Stripe-triggered top-ups (control plane only; never on authorize)
- Publishable Node SDK subset once it matches Python’s closed enforce loop

## Notes

- Docs in this folder track code under `src/mintry`, `apps/dashboard`, and `apps/sidecar`.
- Phase 1 = `1.0.0`. Phase 2 = `1.1.0`. Promise tighten = `1.1.1`.
- Next work must preserve: no network on authorize; fail to last-known-good; deterministic allow / block / configured number.

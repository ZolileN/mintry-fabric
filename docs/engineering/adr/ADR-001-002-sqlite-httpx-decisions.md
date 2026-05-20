# ADR-001: SQLite over Postgres for the Local Mandate Ledger

**Date:** 2026-04-30  
**Status:** Accepted  
**Author:** Engineering Lead

---

## Context

Mintry Fabric needs a persistent store to track mandate budgets (`max_usd`) and cumulative spend (`spent_usd`) in real time. The store must be:

- **Fast** — every LLM request triggers a read and a write before and after flight.
- **Reliable** — a partial write to `spent_usd` would create an "attribution leak" (the core problem Mintry exists to prevent).
- **Zero-dependency** — developers should be able to `uv add mintry-fabric` and have the full ledger working immediately, without running a separate database server.
- **Thread-safe** — Python 3.14+ free-threaded environments run multiple threads concurrently.

---

## Decision

We use **SQLite with Write-Ahead Logging (WAL)** as the local mandate ledger.

---

## Rationale

### Why not Postgres?

Postgres requires a running server, credentials, and network connectivity. This violates the "zero-dependency" goal. A developer working offline or in a restricted network environment would be blocked from using Mintry at all.

### Why not a plain file or in-memory dict?

A plain JSON file has no atomicity guarantees — a crash mid-write can corrupt `spent_usd`. An in-memory dict does not survive process restarts, losing all attribution history.

### Why SQLite?

- **Atomic writes:** SQLite's WAL mode ensures that `UPDATE mandates SET spent_usd = spent_usd + ?` is atomic. There is no race condition between the pre-flight check and the post-flight write.
- **Zero server:** Ships as a single file (`vouchers.db`). No daemon, no port, no credentials.
- **Concurrent reads:** WAL mode allows multiple readers to operate concurrently without blocking, which matters in free-threaded Python 3.14+.
- **Standard library:** `sqlite3` is part of the Python standard library. No additional dependency.

---

## Consequences

- **Accepted limitation:** SQLite does not support multiple writers from separate *processes* well. If Mintry is deployed across multiple concurrent processes writing to the same `vouchers.db`, locking contention may occur. A shared ledger mode (networked server) is tracked in the roadmap for v1.0.0.
- **Local only:** The SQLite ledger is a local cache. It does not automatically sync to the Mintry monitoring plane. Remote sync is a planned feature.
- **Migration:** If schema changes are needed in future versions, SQLite migrations must be handled explicitly (no ORM is used).

---

## Alternatives Considered

| Option | Rejected Reason |
|---|---|
| PostgreSQL | Requires server; violates zero-dependency goal |
| Redis | Requires server; no persistent durability by default |
| Plain JSON file | No atomicity; risk of attribution leakage on crash |
| In-memory dict | Lost on process restart; no audit trail |

---

# ADR-002: HTTPX Transport Patching over a Proxy Architecture

**Date:** 2026-04-30  
**Status:** Accepted  
**Author:** Engineering Lead

---

## Context

Mintry needs to intercept every outbound LLM API call to perform pre-flight budget checks and post-flight token metering. There are two main architectural approaches:

1. **Proxy architecture** — Run a local HTTP proxy that all traffic is routed through.
2. **Transport patching** — Monkey-patch the HTTP client library used by LLM SDKs.

---

## Decision

We use **HTTPX transport patching** — specifically monkey-patching `httpx.Client.send`.

---

## Rationale

### Why not a local proxy?

A proxy requires the developer to configure their environment to route LLM SDK traffic through `localhost:<port>`. This means:
- Every developer must change their network or SDK config.
- Certificate handling becomes complex (TLS inspection requires a local CA cert).
- The proxy must stay running as a separate process.

This significantly increases the operational burden and breaks the "one-line integration" design goal.

### Why HTTPX transport patching?

The OpenAI Python SDK (and most modern LLM SDKs) use `httpx` as their underlying HTTP client. By patching `httpx.Client.send` once at startup, **every** call made by any library using `httpx` is automatically intercepted — without any changes to agent code or SDK configuration.

- **One-line integration:** `mintry.init()` at startup is sufficient.
- **No config changes:** Developers do not need to set proxy env vars or trust a local CA.
- **Transparent:** Agent code continues to call `client.chat.completions.create()` as normal.

---

## Consequences

- **Historical note:** the original `v0.1.0` implementation only patched `httpx.Client.send`. The current codebase now patches both `httpx.Client.send` and `httpx.AsyncClient.send`.
- **Library coupling:** If an LLM SDK switches away from `httpx`, the interceptor will stop working. This is monitored as a dependency risk.
- **Global side effect:** `mintry.init()` has a global side effect on all `httpx.Client` instances in the process. This is intentional but must be documented clearly.

---

## Alternatives Considered

| Option | Rejected Reason |
|---|---|
| Local HTTP proxy | High setup burden; breaks one-line integration goal |
| SDK wrapper classes | Requires wrapping every SDK independently; not scalable |
| eBPF / kernel-level tracing | Too complex; requires elevated permissions |

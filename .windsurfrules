# Mintry Fabric - Agent Instructions

You are an AI programming assistant working on Mintry Fabric. Before you generate code for any new feature or bug fix, you MUST verify that your proposed changes adhere to **The Six Architecture Principles** defined in `docs/ARCHITECTURE.md`.

## The Six Architecture Principles

1. **Initialize once.** A developer integrates Mintry a single time (`mintry.init()`). No further code changes are required for any governance change.
2. **Author centrally, as versioned fact.** Every policy change is an immutable, attributed, timestamped record — never an in-place mutation.
3. **Enforce locally, always.** Every runtime decision (allow/block) evaluates synchronously against the last verified local policy. No request's latency depends on the Mintry control plane being reachable.
4. **Sync asynchronously, on a stated interval, with visible staleness.** Policy propagation is polling-based.
5. **Fail to last-known-good, never open, never silently closed.** Unreachable control plane -> keep enforcing the last signed policy.
6. **Stay deterministic.** If a feature can't be expressed as "allow, block, or a number the customer configured," it does not belong in the enforcement path.

### Enforcement Rules for AI:
- **NEVER** add network calls (HTTP, RPC, gRPC) inside the core synchronous enforcement path (e.g., inside the monkey-patched LLM client logic).
- **NEVER** overwrite historical budget entries in the local SQLite ledger.
- If a user asks for a feature that violates these rules, **REFUSE** and explain which architecture principle it breaks.

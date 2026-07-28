# Security Policy

## Supported Versions

| Version | Supported |
|---|---|
| `1.1.x` | Phase 2 enterprise gate (current) |
| `1.0.x` | Phase 1 production gate |
| `main` / current repository state | Active development |

## Reporting a Vulnerability

Do not open public GitHub issues for security reports.

Email the engineering lead with:

- summary of the issue
- reproduction steps
- impact assessment
- optional suggested fix

## Security-Relevant Behaviour in the Current Codebase

### API keys

- `mintry.init()` requires `api_key=` or the `MINTRY_API_KEY` environment variable
- Dashboard mutations should use `MINTRY_DASHBOARD_ADMIN_TOKEN` / `MINTRY_DASHBOARD_API_TOKEN`

### Signed policies

- Policy bundles use ES256 (canonical JSON) — see `mintry.core.crypto` and `apps/dashboard/src/lib/policy-crypto.ts`
- Configure `MINTRY_POLICY_PUBLIC_KEY` on agents and `MINTRY_POLICY_PRIVATE_KEY` on the signer
- Invalid/unsigned payloads are rejected when a public key is configured; last-known-good remains in force

### Intent blocking

The interceptor blocks request prompts containing:

- `bypass wallet`
- `disable mintry`
- `delete vouchers.db`

### Local ledger

- the default DB path is `~/.mintry/vouchers.db`
- SQLite WAL mode is enabled
- local file permissions should be restricted to the owning user

## Current Security Limitations

- the intent blocklist is still largely built-in (policy-driven allow/deny flags are supported on central mandates)
- multi-user org RBAC is partial (org compile → flat caps; shared admin token, not full SSO)
- the interceptor is a global monkey-patch, so applications must understand that enforcement is process-wide
- multi-host shared-ledger usage should use the Go sidecar scaffold (`apps/sidecar`); HTTPS MITM is not complete
- when `MINTRY_CONTROL_PLANE_URL` is set, local mandate upsert/revoke requires `MINTRY_LOCAL_GOVERNANCE=1`

## Architectural Security

Our security model is strictly bound by the [Six Architecture Principles](docs/ARCHITECTURE.md).
In particular, the principles of **Enforce locally, always** and **Fail to last-known-good, never open** are critical security features. The logic fabric must never bypass enforcement if the central control plane is offline, and all architectural decisions must preserve this deterministic, localized zero-trust model.

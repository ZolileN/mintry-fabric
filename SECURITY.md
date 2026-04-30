# Security Policy

## Supported Versions

| Version | Supported |
|---|---|
| 0.1.x | ✅ Active |
| < 0.1.0 | ❌ Not supported |

---

## Reporting a Vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

If you discover a security vulnerability in Mintry Fabric, please report it privately. We take security seriously — Mintry Fabric handles API keys, cryptographic mandate signatures, and financial spend data.

### How to Report

Email the engineering lead directly with the subject line:

```
[SECURITY] mintry-fabric — <brief description>
```

Include:
- A description of the vulnerability
- Steps to reproduce
- Potential impact
- Your suggested fix (optional but appreciated)

We will acknowledge receipt within **24 hours** and aim to issue a patch within **7 business days** for critical issues.

---

## Security Design Principles

Mintry Fabric is built with the following security constraints:

### API Keys
- `MINTRY_API_KEY` must be passed at runtime and must **never** be hardcoded in source files.
- API keys must never be committed to version control. The `.gitignore` excludes `.env` files by default.

### Cryptographic Mandates
- `AP2IntentMandate` payloads are signed using BBS+ or ES256 signatures.
- Unsigned or malformed mandate payloads must be rejected before any budget is allocated.

### Intent Filtering
- The `GlobalHTTPInterceptor` actively scans prompt payloads for prohibited patterns (e.g., attempts to disable the Fabric or delete the ledger).
- Any prompt matching a prohibited pattern raises a `PermissionError` before the request leaves the server.

### Local Ledger
- `vouchers.db` is stored at `~/.mintry/vouchers.db` by default — outside the project directory and not committed to version control.
- Write-Ahead Logging (WAL) ensures ledger atomicity; `spent_usd` is never partially written.
- The database file should have permissions restricted to the owner (`chmod 600`).

### Dependency Trust
- All dependencies are pinned in `uv.lock`. Do not add new dependencies without team review.
- Do not use `--no-verify` when installing packages.

---

## Known Security Limitations (v0.1.0)

- The `mandate_id` is currently hardcoded to `mt_task_882x` in the interceptor. Dynamic per-request mandate routing via `X-Mintry-Mandate` is planned for a future release. Until then, all intercepted traffic is billed against the same mandate.
- Only `httpx.Client` (synchronous) is patched. Async clients using `httpx.AsyncClient` are not yet intercepted and bypass the Fabric.

---

## Disclosure Policy

Once a fix is released, we will:
1. Publish a patch release with a `SECURITY` tag in the changelog.
2. Credit the reporter (unless they prefer anonymity).
3. Disclose the CVE details publicly 30 days after the patch is available.

---

Copyright © 2026, MLK Computer Consulting. Licensed under the MIT License.

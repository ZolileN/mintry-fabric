# Security Policy

## Supported Versions

| Version | Supported |
|---|---|
| `main` / current repository state | Active development |
| `0.5.x` | Current release |
| `0.1.x` | Initial baseline release |
| older than `0.1.0` | Not supported |

## Reporting a Vulnerability

Do not open public GitHub issues for security reports.

Email the engineering lead with:

- summary of the issue
- reproduction steps
- impact assessment
- optional suggested fix

## Security-Relevant Behaviour in the Current Codebase

### API keys

- `api_key` is required by `mintry.init()`
- the library does not auto-read `MINTRY_API_KEY`; applications must pass it explicitly

### Signed mandates

- `AP2IntentMandate` supports ES256 verification helpers
- malformed signatures raise errors
- invalid signatures return `False`

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

- the intent blocklist is hardcoded rather than policy-driven
- the dashboard is a local operational tool and does not provide authentication or multi-user authorization
- the interceptor is a global monkey-patch, so applications must understand that enforcement is process-wide
- the repo does not yet ship a hardened deployment model for multi-host shared-ledger usage

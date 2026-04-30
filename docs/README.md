# Mintry Fabric — Documentation

Welcome to the Mintry Fabric documentation. Use the index below to find what you need.

---

## Getting Started

| Document | Description |
|---|---|
| [Developer Guide](DEVELOPER_GUIDE.md) | End-to-end workflow: onboarding, integration, mandate lifecycle, and architecture overview |
| [Configuration Reference](CONFIGURATION.md) | Environment variables, database path, SQLite settings, intent filter, and token pricing |
| [API Reference](API_REFERENCE.md) | Full reference for every public class and method (`mintry.init`, `MintryWallet`, `PolicyEngine`, `GlobalHTTPInterceptor`) |

---

## Operations

| Document | Description |
|---|---|
| [Troubleshooting](TROUBLESHOOTING.md) | Common errors with root causes and step-by-step fixes |
| [Roadmap](ROADMAP.md) | Planned features and milestones from v0.1.1 through v1.0.0 |

---

## Engineering Standards

| Document | Description |
|---|---|
| [PR Review Standard](engineering/PR_REVIEW_STANDARD.md) | How pull requests are created, reviewed, approved, and merged |
| [ADR-001: SQLite over Postgres](engineering/adr/ADR-001-002-sqlite-httpx-decisions.md#adr-001-sqlite-over-postgres-for-the-local-mandate-ledger) | Why SQLite was chosen for the mandate ledger |
| [ADR-002: HTTPX Transport Patching](engineering/adr/ADR-001-002-sqlite-httpx-decisions.md#adr-002-httpx-transport-patching-over-a-proxy-architecture) | Why transport patching was chosen over a proxy architecture |

---

## Repository Root

These files live at the repository root for GitHub integration:

| Document | Description |
|---|---|
| [CONTRIBUTING.md](../CONTRIBUTING.md) | How to set up, branch, test, and submit pull requests |
| [CHANGELOG.md](../CHANGELOG.md) | Version history and release notes |
| [SECURITY.md](../SECURITY.md) | How to report vulnerabilities and security design principles |
| [README.md](../README.md) | Project overview, quick start, and feature summary |

---

> **Copyright © 2026, MLK Computer Consulting.** Licensed under the MIT License.

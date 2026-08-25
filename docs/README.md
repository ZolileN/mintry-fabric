# Mintry Fabric Documentation

This documentation set is aligned to the current code in `src/mintry` (**v1.3.0**).

> [!IMPORTANT]
> **Read This First:** All development and feature design must strictly adhere to the [Six Architecture Principles](ARCHITECTURE.md). Features that violate these principles will be rejected.

## Architecture

| Document | Description |
|---|---|
| [Architecture Map](ARCHITECTURE.md) | Control plane / data plane topology and the Six Principles |
| [Control Plane Spec](CONTROL_PLANE_SPEC.md) | Full implementation spec — policy model, phased roadmap, recorded decisions |
| [App Analysis](APP_ANALYSIS.md) | Current-state analysis of apps, SDKs, and architecture gaps |
| [Production Readiness Plan](PRODUCTION_READINESS_PLAN.md) | Workstreams to close analysis gaps and ship Phase 1 production |

## Getting Started

| Document | Description |
|---|---|
| [Run Locally](RUN_LOCAL.md) | Local setup, dashboard startup, CLI usage, and test commands |
| [Developer Guide](DEVELOPER_GUIDE.md) | End-to-end architecture and workflow through the SDK and dashboard |
| [Configuration Reference](CONFIGURATION.md) | Supported init parameters, environment variables, SQLite behaviour, pricing, and safety defaults |
| [API Reference](API_REFERENCE.md) | Current Python API surface implemented by the repo |

## Operations

| Document | Description |
|---|---|
| [Deployment Guide](DEPLOYMENT.md) | **Vercel + Supabase + Python agent** production deploy |
| [Troubleshooting](TROUBLESHOOTING.md) | Common local setup and runtime issues |
| [Roadmap](ROADMAP.md) | Current release status and next work |
| [Sprint Plan](SPRINT_PLAN.md) | Current planning snapshot and next release priorities |

## Engineering

| Document | Description |
|---|---|
| [PR Review Standard](engineering/PR_REVIEW_STANDARD.md) | Review expectations and merge standards |
| [ADR-001 / ADR-002](engineering/adr/ADR-001-002-sqlite-httpx-decisions.md) | Rationale for SQLite and HTTPX interception |

## Repository Root References

| Document | Description |
|---|---|
| [README.md](../README.md) | Project overview and quick start |
| [CHANGELOG.md](../CHANGELOG.md) | Release history and unreleased implementation snapshot |
| [CONTRIBUTING.md](../CONTRIBUTING.md) | Contributor workflow |
| [SECURITY.md](../SECURITY.md) | Security reporting and current constraints |

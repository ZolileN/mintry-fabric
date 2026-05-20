# Mintry Fabric — Sprint Plan

**Created:** 2026-05-20  
**Version Under Review:** 0.1.0  
**Sprint Goal:** Stabilize the core platform, fix all failing tests, and close critical gaps before any feature work begins.

---

## Platform Health Summary

### Current Test Suite: 3/4 Failing

| Test                            | File                          | Result  | Root Cause                                                                               |
| ------------------------------- | ----------------------------- | ------- | ---------------------------------------------------------------------------------------- |
| `test_real_time_metering`       | `tests/test_metering.py`      | ❌ FAIL | Delta is `0.02` instead of expected `0.01` — double-counting from stacked monkey-patches |
| `test_logic_fabric_enforcement` | `tests/test_mintry_fabric.py` | ✅ PASS | —                                                                                        |
| `test_intent_blocking`          | `tests/test_intent_fabric.py` | ❌ FAIL | Missing `import pytest`; intent filter not wired into `install()`                        |
| `test_mpp_resurrection`         | `tests/test_mpp_bridge.py`    | ❌ FAIL | `e.__cause__` is `None` — unhandled in exception check                                   |

### Critical Issues Identified

| #   | Severity    | Issue                                                                            | Location                      |
| --- | ----------- | -------------------------------------------------------------------------------- | ----------------------------- |
| 1   | 🔴 Critical | Intent filtering not wired into `install()` — prohibited prompts bypass security | `interceptors/global_http.py` |
| 2   | 🔴 Critical | Multiple `init()` calls stack monkey-patches, causing double metering            | `interceptors/global_http.py` |
| 3   | 🔴 Critical | `Decimal` not imported in `wallet.py` — `add_funds()` raises `NameError`         | `core/wallet.py`              |
| 4   | 🟡 Design   | Hardcoded `mt_task_882x` mandate ID everywhere — no dynamic routing              | `global_http.py`, `engine.py` |
| 5   | 🟡 Design   | `create_mandate()` referenced in docs but doesn't exist on `MintryWallet`        | `core/wallet.py`              |
| 6   | 🟡 Design   | `shield()` is a stub returning a mock — never creates a real mandate             | `core/engine.py`              |
| 7   | 🟢 Minor    | CI only runs `test_metering.py`, not the full suite                              | `.github/workflows/test.yaml` |
| 8   | 🟢 Minor    | `docs` branch not merged to `master`                                             | Git                           |

---

## Sprint 1 — Stabilization (v0.1.1 Patch)

> **Objective:** Fix all broken tests, resolve critical bugs, and ensure the existing feature set works as documented.

### Task 1: Fix `Decimal` Import in Wallet

- **File:** `src/mintry/core/wallet.py`
- **Change:** Add `from decimal import Decimal` at the top of the file.
- **Effort:** 5 min
- **Status:** `[x]` ✅ Completed

### Task 2: Wire Intent Filtering into `install()`

- **File:** `src/mintry/interceptors/global_http.py`
- **Change:** The `patched_send` function inside `install()` currently only performs a fiscal check. It must also scan the request body for prohibited patterns (the logic already exists in `sync_intercept()` but is not called from `install()`). Extract the intent check into a shared method and call it from both paths.
- **Effort:** 30 min
- **Status:** `[x]` ✅ Completed

### Task 3: Make `install()` Idempotent

- **File:** `src/mintry/interceptors/global_http.py`
- **Change:** Guard against multiple patches stacking on `httpx.Client.send`. Save the original `send` reference once (e.g., as a class attribute `_original_send`), and skip re-patching if already installed. This eliminates the double-counting bug.
- **Effort:** 30 min
- **Status:** `[x]` ✅ Completed

### Task 4: Fix Test Suite

- **Files:** All test files
- **Changes:**
  - `test_intent_fabric.py` — Add missing `import pytest`.
  - `test_mpp_bridge.py` — Guard against `e.__cause__` being `None` on line 16.
  - All tests — Use temporary database paths (e.g., `tmp_path` fixture) to prevent cross-test state contamination.
- **Effort:** 1 hr
- **Status:** `[x]` ✅ Completed

### Task 5: Add `create_mandate()` and `exhaust_mandate()`

- **File:** `src/mintry/core/wallet.py`
- **Change:** Add two public methods:
  - `create_mandate(mandate_id: str, max_usd: float)` — Inserts a new mandate row.
  - `exhaust_mandate(mandate_id: str)` — Sets mandate status to `"exhausted"`.
- **Effort:** 30 min
- **Status:** `[x]` ✅ Completed

### Task 6: Update CI to Run Full Test Suite

- **File:** `.github/workflows/test.yaml`
- **Change:** Change `uv run pytest -s tests/test_metering.py` → `uv run pytest -s tests/`
- **Effort:** 5 min
- **Status:** `[x]` ✅ Completed

### Task 7: Merge `docs` Branch into `master`

- **Action:** Merge the `docs` branch (which contains all project documentation, governance templates, and license) into `master`.
- **Effort:** 5 min
- **Status:** `[x]` ✅ Completed

### Sprint 1 Acceptance Criteria

- [x] All 4 tests pass — `4 passed in 41.01s`
- [x] `wallet.add_funds()` works without `NameError`
- [x] Prohibited prompts are blocked by the installed interceptor (not just `sync_intercept`)
- [x] Multiple `mintry.init()` calls don't stack patches
- [x] CI runs the complete test suite
- [x] `docs` merged into `master`

---

## Sprint 2 — Dynamic Mandate Routing (v0.1.1 → v0.2.0)

> **Objective:** Replace all hardcoded mandate references with dynamic routing, enabling multi-task budget enforcement.

### Task 8: Read `X-Mintry-Mandate` Header in Interceptor

- **File:** `src/mintry/interceptors/global_http.py`
- **Change:** Extract mandate ID from `request.headers.get("X-Mintry-Mandate", "mt_task_882x")` instead of hardcoding. Fall back to a default mandate for backward compatibility.
- **Effort:** 1 hr
- **Status:** `[x]` ✅ Completed (done in Sprint 1)

### Task 9: Implement Real `shield()` Context Manager

- **File:** `src/mintry/core/engine.py`
- **Change:** Generate a UUID-based mandate ID, call `wallet.create_mandate()` on entry, yield a mandate object with the `.id`, and optionally mark it exhausted on exit.
- **Effort:** 1 hr
- **Status:** `[x]` ✅ Completed

### Task 10: Validate `api_key` on Init

- **File:** `src/mintry/__init__.py`
- **Change:** At minimum, validate that `api_key` is a non-empty string. Store it on the engine for future remote-sync use.
- **Effort:** 15 min
- **Status:** `[x]` ✅ Completed (done in Sprint 1)

### Task 11: Improve `PermissionError` Messages

- **File:** `src/mintry/interceptors/global_http.py`, `src/mintry/core/engine.py`
- **Change:** Include `mandate_id`, `budget_usd`, `spent_usd`, and remaining headroom in all `PermissionError` messages.
- **Effort:** 30 min
- **Status:** `[x]` ✅ Completed

### Sprint 2 Acceptance Criteria

- [x] Requests with `X-Mintry-Mandate` header are billed to the correct mandate
- [x] `engine.shield()` creates a real mandate and returns a usable context manager
- [x] `mintry.init()` rejects empty/missing API keys
- [x] Error messages include actionable budget details

---

## Sprint 3 — Async & Multi-Provider (v0.2.0 → v0.3.0)

> **Objective:** Extend the Logic Fabric to cover async frameworks and non-OpenAI providers.

### Task 12: Patch `httpx.AsyncClient.send`

- **File:** `src/mintry/interceptors/global_http.py`
- **Change:** Add an async counterpart to `patched_send` that intercepts `httpx.AsyncClient.send`. Use `aiosqlite` or connection-per-thread for safe async SQLite writes.
- **Effort:** 3–4 hrs
- **Status:** `[x]` ✅ Completed

### Task 13: Add Per-Model / Per-Provider Pricing Table

- **File:** New file `src/mintry/core/pricing.py`
- **Change:** Create a configurable pricing registry with rates per model (GPT-4o, Claude, Gemini, Mistral, etc.). The interceptor should look up the model from the request body and apply the correct rate.
- **Effort:** 2 hrs
- **Status:** `[x]` ✅ Completed

### Task 14: Mandate Expiry Enforcement

- **Files:** `src/mintry/core/wallet.py`, `src/mintry/core/engine.py`
- **Change:** Check `AP2IntentMandate.expires_at` during authorization. Reject expired mandates with a clear error.
- **Effort:** 1 hr
- **Status:** `[x]` ✅ Completed

### Task 15: AP2IntentMandate Signature Verification

- **Files:** `src/mintry/models/mandates.py`
- **Change:** Implement BBS+ / ES256 signature verification using the `cryptography` dependency (already declared). Reject unsigned or malformed payloads.
- **Effort:** 3–4 hrs
- **Status:** `[x]` ✅ Completed

### Sprint 3 Acceptance Criteria

- [x] Async agent code is intercepted and metered
- [x] Token costs are calculated using per-model pricing
- [x] Expired mandates are rejected at authorization time
- [x] Mandate signatures are cryptographically verified

---

## Backlog (Unscheduled)

These items are tracked on the [ROADMAP](ROADMAP.md) but are not scheduled for immediate sprints:

| Item                                                    | Target Version |
| ------------------------------------------------------- | -------------- |
| Local web dashboard (spend charts, mandate health)      | v0.5.0         |
| Webhook support for mandate exhaustion events           | v0.5.0         |
| Remote sync to Mintry monitoring plane                  | v0.5.0         |
| CLI: `mintry mandates list` / `mintry mandates inspect` | v0.4.0         |
| Docker-based shared team ledger                         | v1.0.0         |
| TypeScript/JavaScript SDK                               | v1.0.0         |
| VS Code extension for inline spend display              | Exploratory    |
| Stripe auto-top-up automation                           | Exploratory    |

---

## Risk Register

| Risk                                                 | Impact                               | Mitigation                                                                 |
| ---------------------------------------------------- | ------------------------------------ | -------------------------------------------------------------------------- |
| SQLite write contention in multi-process deployments | Metering data loss or locking errors | Document single-process constraint; plan shared ledger mode for v1.0       |
| LLM SDKs migrate away from `httpx`                   | Interceptor stops working silently   | Monitor OpenAI/Anthropic SDK changelogs; add transport-layer detection     |
| Global monkey-patch conflicts with other libraries   | Unpredictable request behavior       | Make `install()` idempotent; store and restore original `send` on teardown |
| Test contamination from shared SQLite state          | False passes/failures in CI          | Enforce per-test temp database paths in Sprint 1                           |

---

_This sprint plan is a living document. Update task statuses as work progresses._

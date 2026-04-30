# Mintry Fabric: Developer Journey & Technical Guide

Mintry Fabric is a high-performance infrastructure layer designed to eliminate the "Attribution Void" in AI agent ecosystems. It acts as a transparent "Logic Fabric" that intercepts LLM traffic at the transport layer to provide real-time metering, spend attribution, and proactive budget enforcement.

---

## 🌑 The Problem: The Attribution Void

In the 2026 AI landscape, organizations often suffer from "Agent-Blindness". While total API spend is visible on provider dashboards, it is nearly impossible to attribute specific costs to individual background tasks or autonomous agents until the invoice arrives. This delay creates a "Void" where rogue loops can burn through quarterly budgets in hours.

Mintry Fabric closes this void by moving enforcement from reactive billing to **proactive interception**.

---

## 🚀 Developer Journey: End-to-End Workflow

The workflow of Mintry Fabric is designed to be a "set-and-forget" infrastructure layer. It moves the complexity of AI financial governance out of your application code and into the transport layer.

Here is the end-to-end journey from signup to real-time enforcement:

### 1. Developer Onboarding & Provisioning

When a developer signs up, the primary goal is to establish the "Source of Truth" for their AI budget.

- **Wallet Creation:** Upon signup, a `MintryWallet` is automatically provisioned for the developer.
- **Local Ledger Initialization:** A persistent SQLite database is initialized (typically in a `.mintry/` directory) to act as a high-speed, local cache of all mandates and spend.
- **API Key Issuance:** The developer receives a `MINTRY_API_KEY`, which acts as the handshake between their local environment and the Mintry monitoring plane.

### 2. The "One-Line" Integration

Instead of wrapping every single OpenAI call in custom logic, the developer initializes the Logic Fabric at the start of their main application script.

- **Transport Patching:** By calling `mintry.init()`, Mintry hooks into the HTTPX transport layer.
- **Global Interception:** This ensures that any library using `httpx` (like the OpenAI or Anthropic Python SDKs) is automatically "Fabric-aware" without requiring changes to individual function calls.

### 3. Defining a "Mandate" (The Budget)

Before an agent performs a task, the developer (or the system) creates a **Mandate**. This is a specific permission set for a single job.

- **Budget Allocation:** A mandate is defined with a `max_usd` limit (e.g., "Analyze this 500mb log file; budget: $2.00").
- **Task Binding:** This mandate ID is passed into the agent's context, signaling to the Fabric which budget "bucket" to bill against.

### 4. The Pre-Flight Check (Authorization)

As soon as the agent attempts to call an LLM (e.g., `client.chat.completions.create`):

- **Interception:** The Logic Fabric catches the request at the transport layer before it leaves the server.
- **Policy Engine Verification:** The `PolicyEngine` queries the local SQLite ledger to check if the specific `mandate_id` has remaining funds.
- **Gatekeeping:**
  - **If Budget Exists:** The request is allowed to proceed to the provider (OpenAI/Anthropic).
  - **If Budget Exhausted:** The Fabric returns a `403 Forbidden` error locally, killing the request before it costs a single cent.

### 5. Post-Flight Metering & Attribution

Once the LLM provider responds:

- **Token Capture:** The Fabric intercepts the response and extracts the usage metadata (prompt tokens, completion tokens, and model type).
- **Cost Calculation:** It calculates the exact USD cost based on real-time model pricing.
- **Ledger Update:** The `spent_usd` column in the SQLite database is updated atomically.
- **Closing the Void:** The developer can now query the ledger to see exactly which task spent what, solving the Attribution Void instantly.

### 6. Automated Governance

If an agent enters a recursive loop or a "hallucination spiral":

- The Fabric continues to deduct costs after every call.
- The moment the next request would exceed the `max_usd` defined in Step 3, the Fabric shuts down the connection.
- **Result:** Your system stays live, but the "rogue" agent is safely neutralized.

---

## 🛠️ Development Setup

Mintry is architected for Ubuntu Linux environments.

- **Python Environment:** We utilize `uv` for high-concurrency dependency management and virtual environment orchestration.
- **Version Requirements:** Systems must run **Python 3.14+** to leverage free-threaded (No-GIL) performance models.
- **Persistence Layer:** The local ledger uses SQLite with Write-Ahead Logging (WAL) for thread-safe attribution.

---

## ✨ Features

- **Logic Fabric Interception:** Hooks into the HTTPX transport layer to monitor traffic without requiring changes to agent logic.
- **Real-Time Metering:** Calculates exact token costs post-flight and updates a persistent ledger instantly.
- **Mandate-Based Budgeting:** Define specific `max_usd` limits (Mandates) for every task to prevent runaway costs.
- **No-GIL Ready:** Optimized for Python 3.14+ free-threaded environments.
- **SQLite Persistence:** Uses a robust SQLite backend with Write-Ahead Logging (WAL) for thread-safe, high-concurrency transaction logging.

---

## 🏗️ Architecture

The system consists of three core components:

| Component | Responsibility |
|---|---|
| **MintryWallet** | Manages the local SQLite database (`vouchers.db`) and the mandate ledger. |
| **PolicyEngine** | The gatekeeper that authorizes or denies requests based on remaining mandate budget. |
| **Global Interceptor** | A patched transport layer that coordinates authorization and post-flight metering. |

---

## 🛡️ The Kill-Switch: Stopping Runaway Agents

Mintry Fabric acts as a circuit breaker. If an agent enters a recursive loop, the Fabric kills the connection the moment the next request would exceed the assigned budget.

```python
import mintry
from openai import OpenAI

# Initialize the Logic Fabric
fabric = mintry.init(api_key="your_key")

# Define a $0.05 "Hard Cap" Mandate
MANDATE_ID = "research_task_001"
fabric.wallet.create_mandate(MANDATE_ID, max_usd=0.05)

client = OpenAI()

try:
    while True:
        # Every call is metered against the MANDATE_ID
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": "Analyze and recurse."}],
            extra_headers={"X-Mintry-Mandate": MANDATE_ID}
        )
except PermissionError as e:
    # Mintry intercepts and kills the loop locally before the next cent is spent
    print(f"🛑 [MINTY SHIELD ACTIVE]: {e}")
```

---

## 🧪 Testing & Quality Assurance

We maintain high standards for technical accuracy. Before pushing any changes to GitHub:

- Ensure the surname in any documentation or code comments is correctly spelled as **Nonzapa**.
- Run the full suite of metering tests to ensure your changes don't introduce "attribution leakage."
- Verify that SQLite transactions remain atomic, especially under the high-concurrency conditions common in our full-stack environments.

---

## 🚀 Quick Start

### Installation

```bash
uv add mintry-fabric
```

### Development Setup

Mintry is designed for Ubuntu Linux environments using Python 3.14+.

```bash
# Sync dependencies
uv sync --all-extras --dev

# Run metering validation tests
uv run pytest -s tests/test_metering.py
```

---

## 📂 Database Schema

The `vouchers.db` maintains the following state for high-speed local attribution:

| Column | Type | Description |
|---|---|---|
| `id` | TEXT | Unique ID for the mandate (e.g., `mt_task_882x`). |
| `max_usd` | REAL | The maximum budget allocated for this task. |
| `spent_usd` | REAL | Cumulative spend tracked in real-time. |
| `status` | TEXT | Mandate status (e.g., `active` or `exhausted`). |

---

Welcome to the team — we are excited to have you onboard as we build the future of agentic finance!

---

## 📄 License

Copyright © 2026, MLK Computer Consulting.  
Licensed under the MIT License.

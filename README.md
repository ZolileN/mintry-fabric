![Logic Fabric CI](https://github.com/ZolileN/mintry-fabric/actions/workflows/tests.yml/badge.svg)
# Mintry Fabric 🚀

**Mintry Fabric** is a high-performance, real-time AI metering and policy enforcement layer designed for the 2026 AI ecosystem. It acts as a "Logic Fabric" that sits between your AI agents and their LLM providers, ensuring fiscal responsibility through granular budget mandates and SQLite-backed usage tracking.

## ✨ Features

*   **Logic Fabric Interception**: Hooks directly into the `HTTPX` transport layer to monitor OpenAI (and other provider) traffic without modifying agent code.
*   **Real-Time Metering**: Calculates exact token costs post-flight and updates a persistent ledger.
*   **Mandate-Based Budgeting**: Define `max_usd` limits for specific tasks to prevent runaway costs.
*   **No-GIL Ready**: Optimized for Python 3.14+ free-threaded environments.
*   **SQLite Persistence**: Uses a robust SQLite backend with Write-Ahead Logging (WAL) for thread-safe transaction logging.

## 🛠️ Architecture

The system consists of three core components:
1.  **MintryWallet**: Manages the SQLite database and mandate ledger[cite: 1].
2.  **PolicyEngine**: Authorizes requests based on available budget before they are fired[cite: 1].
3.  **Global Interceptor**: A patched `HTTPX` transport that coordinates the authorization and metering flow[cite: 1].

## 🚀 Quick Start

### Installation
```bash
uv add git+https://github.com/your-username/mintry-fabric.git
```

### Usage
Initialize the fabric at the entry point of your application:

```python
import mintry
from openai import OpenAI

# Initialize the Logic Fabric
mintry.init(api_key="your_mintry_key")

# Standard OpenAI calls are now automatically metered
client = OpenAI()
response = client.chat.completions.create(
    model="gpt-5-preview",
    messages=[{"role": "user", "content": "Analyze these logs."}]
)
```

## 🧪 Testing

The project includes a suite of metering tests that validate the delta between initial and final spend using `pytest-httpx`.

```bash
uv run pytest -s tests/test_metering.py
```

**Successful Output:**
```text
--- Phase 1: Executing Metered Request ---
[TEST] Initial Spent: $0.060000
[TEST] Final Spent: $0.070000
[TEST] Calculated Delta: $0.010000
[SUCCESS] Logic Fabric Metered the exact token cost.
```

## 📂 Database Schema

The `vouchers.db` maintains the following state[cite: 1]:
| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | TEXT | Primary key for the mandate (e.g., `mt_task_882x`)[cite: 1]. |
| `max_usd` | REAL | The maximum budget allocated[cite: 1]. |
| `spent_usd` | REAL | Cumulative spend tracked in real-time[cite: 1]. |
| `status` | TEXT | Mandate status (active/exhausted)[cite: 1]. |

---

## 📄 License
MIT

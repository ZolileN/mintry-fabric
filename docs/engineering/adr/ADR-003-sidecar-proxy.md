# ADR 003: Language-Agnostic Sidecar Proxy

**Date:** 2026-05-20
**Status:** Approved
**Context:** Mintry Fabric currently relies on library-level monkey-patching (`httpx` in Python, `fetch` in Node.js) to intercept LLM traffic, enforce budgets, and meter usage. While effective for initial environments, this approach scales poorly across multiple programming languages (Java, Swift, Rust) and is vulnerable to internal client updates or complex transport pipelines.

## Decision

We will build a **standalone local proxy daemon** (the "Sidecar Proxy") to handle all HTTP interception, replacing the need for language-specific interceptor logic.

### 1. Language Choice
The proxy will be written in **Go**.
- **Reasoning**: Go's `net/http/httputil` provides robust, production-ready reverse/forward proxy capabilities out of the box. Go's concurrency model (goroutines) is perfectly suited for handling high-throughput asynchronous proxy requests with minimal overhead. It compiles to a single static binary, making distribution trivial.

### 2. Proxy Architecture
The sidecar will operate as an **Explicit HTTP Forward Proxy**.
- **Reasoning**: By running as a forward proxy on `localhost:8820`, language SDKs can remain incredibly thin. `mintry.init()` will simply set the `HTTP_PROXY` and `HTTPS_PROXY` environment variables for the host process. This allows existing LLM libraries (like the official OpenAI or Anthropic SDKs) to automatically route traffic through Mintry without any code changes or URL rewriting by the user, preserving our "Three Lines" marketing promise.

### 3. State Management
The sidecar will connect directly to the existing `vouchers.db` SQLite ledger.
- **Reasoning**: Thanks to SQLite's WAL mode, the Go daemon can concurrently read and write to the database alongside the Python observability dashboard and CLI. This ensures real-time spend visibility remains unbroken. We will use `mattn/go-sqlite3` for database access.

### 4. The Request Lifecycle
1. **Intercept**: The proxy intercepts requests targeting known LLM hosts.
2. **Pre-flight Check**: Extracts the `X-Mintry-Mandate` header. Queries `vouchers.db` to verify the mandate is active and has >$0.01 headroom.
3. **Intent Check**: Parses the JSON body to block prohibited phrases.
4. **Flight**: Forwards the request upstream.
5. **Post-flight Metering**: Reads the upstream JSON response, extracts `usage` (prompt/completion tokens), calculates the cost against the pricing registry, and records the spend in SQLite.
6. **Return**: Streams the response back to the client.

## Consequences

**Positive:**
- "One Fabric. Any Language." becomes fully realized. We can release Java, Swift, and Rust SDKs that consist of literally three lines of code (setting env vars and headers).
- Interception logic is unified in one codebase, reducing maintenance burden.
- Solves edge cases where complex HTTP clients bypass monkey-patching.

**Negative:**
- Introduces an additional binary dependency for deployment.
- Requires orchestrating the daemon lifecycle (starting/stopping the proxy alongside the application). We will mitigate this by providing a `mintry proxy start` CLI command and Docker sidecar configurations.

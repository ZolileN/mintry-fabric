# Mintry Fabric v1.0.0 Release Notes

We are thrilled to announce the official **v1.0.0** production-ready release of Mintry Fabric!

Mintry Fabric is the universal logic fabric for the agentic economy. It provides programmatic budget controls, observability, and security interceptors directly at the transport layer, ensuring your AI agents never exceed their fiscal mandates.

## Key Features in v1.0.0

### The "Three Lines" Promise Delivered
Both our Python and Node.js SDKs have been officially unified around our beautiful "three lines of code" ergonomics. By securely tracking state via `contextvars` in Python and `AsyncLocalStorage` in Node.js, your AI agents are protected without requiring any complex architectural changes.

**Python:**
```python
import mintry
mintry.init()
with mintry.mandate("task:nightly_summarizer", cap=50.00):
    openai.chat.completions.create(...) # Fully protected & metered
```

**TypeScript/Node.js:**
```typescript
import mintry from 'mintry-node';
mintry.init();
await mintry.mandate("task:nightly_summarizer", 50.00, async () => {
    await fetch("https://api.openai.com/v1/chat/completions", { ... });
});
```

### Universal Observability Dashboard
Run `mintry dashboard` locally to instantly visualize real-time AI spend, manage mandate lifecycles, and view your append-only audit feed. The dashboard shares a synchronous SQLite WAL connection with the SDKs, providing zero-latency telemetry.

### Multi-Provider Interception
Mintry Fabric v1.0.0 silently intercepts traffic to the big four LLM providers out of the box:
- OpenAI (`api.openai.com`)
- Anthropic (`api.anthropic.com`)
- Google Gemini (`generativelanguage.googleapis.com`)
- Mistral (`api.mistral.ai`)

### Programmable Exception Handling
Budget exhaustion and mandate expiry now throw structured `MintryMandateExceeded` errors. This empowers developers to programmatically catch failures and fall back to cheaper models or alert administrators, rather than dealing with generic permission exceptions.

### Docker "Shared Ledger" Support
We've officially published our Docker deployment blueprint, demonstrating how your application containers and the Mintry Observability Dashboard can safely coordinate and share fiscal state via Docker volumes.

## What's Next? (The Sidecar Proxy)
With v1.0.0 out the door, we have formally adopted **ADR-003**, establishing our path towards a language-agnostic Go daemon. This standalone Sidecar Proxy will eventually replace the SDK monkey-patching approach, allowing any language (Java, Swift, Rust) to interface with Mintry by simply setting the `HTTP_PROXY` environment variable.

## Getting Started
- Python: `uv add mintry-fabric` or `pip install mintry-fabric`
- Node.js: `npm install mintry-node`

For full API documentation, see `docs/API_REFERENCE.md`.

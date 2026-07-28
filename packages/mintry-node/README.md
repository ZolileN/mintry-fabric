# mintry-node (experimental)

**Status:** prototype / not production-ready. Version `0.1.0`.

The supported enforcement SDK is the **Python** package (`src/mintry`).
This package sketches the same ergonomics (`init`, `mandate`, `fetch` patch,
SQLite wallet) for Node.js but does **not** yet implement:

- control-plane polling
- ES256 policy verification / last-known-good
- telemetry batching
- dashboard / CLI parity
- publishable `dist` / `exports` layout

Do not treat `1.0.0` release notes or older package versions as a claim of
parity with Python.

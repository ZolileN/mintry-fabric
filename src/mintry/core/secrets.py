"""Vault alias resolution for provider secrets (Phase 2 E5).

Mintry never stores customer provider API keys. The control plane and
dashboard may author **alias references** only (e.g. ``OPENAI_PROD_KEY``).
The SDK / sidecar resolves aliases from the customer environment or an
optional local Vault agent endpoint — never from Mintry servers.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import Mapping, Optional
from urllib.error import URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

# Alias names: uppercase, digits, underscore; must look like env var names.
_ALIAS_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,127}$")


@dataclass(frozen=True)
class SecretRef:
    """Alias-only reference to a customer-held secret."""

    alias: str
    provider: str = ""  # openai | anthropic | gemini | mistral | ...
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "alias": self.alias,
            "provider": self.provider,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: Mapping) -> "SecretRef":
        return cls(
            alias=str(data.get("alias", "")),
            provider=str(data.get("provider", "")),
            description=str(data.get("description", "")),
        )


class SecretResolutionError(Exception):
    """Raised when an alias cannot be resolved from the customer environment."""


def validate_alias(alias: str) -> Optional[str]:
    """Return an error message if alias is invalid, else None."""
    if not alias or not isinstance(alias, str):
        return "alias must be a non-empty string"
    if not _ALIAS_RE.match(alias):
        return (
            "alias must match env-var form: start with A-Z, then A-Z0-9_ "
            "(e.g. OPENAI_PROD_KEY)"
        )
    # Reject values that look like raw secrets being smuggled as aliases.
    if alias.startswith("sk-") or "BEGIN" in alias or len(alias) > 128:
        return "alias looks like a raw secret; store only the reference name"
    return None


def resolve_secret(
    alias: str,
    *,
    environ: Optional[Mapping[str, str]] = None,
    vault_addr: Optional[str] = None,
    vault_token: Optional[str] = None,
) -> str:
    """Resolve an alias to a secret value from the customer environment.

    Resolution order:
    1. Process environment (or provided ``environ`` mapping)
    2. Optional local Vault agent at ``vault_addr`` (customer-operated)

    Never contacts the Mintry control plane.
    """
    err = validate_alias(alias)
    if err:
        raise SecretResolutionError(err)

    env = environ if environ is not None else os.environ
    if alias in env and env[alias]:
        return env[alias]

    addr = vault_addr if vault_addr is not None else os.environ.get("VAULT_ADDR")
    token = vault_token if vault_token is not None else os.environ.get("VAULT_TOKEN")
    if addr and token:
        # Customer Vault agent only — not Mintry infrastructure.
        # Path convention: secret/data/mintry/<alias>
        url = addr.rstrip("/") + f"/v1/secret/data/mintry/{alias}"
        req = Request(url, headers={"X-Vault-Token": token})
        try:
            with urlopen(req, timeout=2.0) as resp:  # noqa: S310 — customer-configured URL
                import json

                payload = json.loads(resp.read().decode("utf-8"))
                value = (
                    payload.get("data", {}).get("data", {}).get("value")
                    or payload.get("data", {}).get("value")
                )
                if value:
                    return str(value)
        except (URLError, TimeoutError, ValueError, KeyError) as exc:
            logger.warning("Vault resolve failed for %s: %s", alias, exc)

    raise SecretResolutionError(
        f"alias {alias!r} not found in customer environment"
        + (" or Vault" if addr else "")
    )


def resolve_provider_key(
    provider: str,
    *,
    aliases: Optional[Mapping[str, str]] = None,
    environ: Optional[Mapping[str, str]] = None,
) -> str:
    """Resolve a provider API key via alias map or conventional env names.

    ``aliases`` maps provider → alias (e.g. ``{"openai": "OPENAI_PROD_KEY"}``).
    Falls back to conventional ``OPENAI_API_KEY`` / ``ANTHROPIC_API_KEY`` etc.
    """
    conventional = {
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "gemini": "GOOGLE_API_KEY",
        "google": "GOOGLE_API_KEY",
        "mistral": "MISTRAL_API_KEY",
    }
    env = environ if environ is not None else os.environ
    alias_map = aliases or {}
    alias = alias_map.get(provider) or conventional.get(provider.lower())
    if not alias:
        raise SecretResolutionError(f"no alias configured for provider {provider!r}")
    # Conventional keys may not match alias regex (still env vars) — allow direct env read.
    if alias in env and env[alias]:
        return env[alias]
    return resolve_secret(alias, environ=env)

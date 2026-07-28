"""OPA bundle compile-at-sync (Phase 2 E4).

OPA may structure/distribute policy, but budget math stays in the custom
evaluator. Bundles are **materialized at sync/apply time** into a flat
``mandate_id → {max_usd, allow, expires_at}`` map for ``PolicyCache``.

Never spawn the OPA CLI from the authorize hot path.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Mapping, Optional

logger = logging.getLogger(__name__)


def materialize_flat_rules(
    mandates: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    """Compile mandate map into flat hot-path rules.

    Accepts either:
    - Already-flat ``{mandate_id: {max_usd, allow?, expires_at?}}``
    - OPA-shaped ``{"mandate": {mandate_id: {...}}}`` or nested data.mintry

    Returns only allow / max_usd / expires_at — deterministic numbers & booleans.
    """
    if not isinstance(mandates, Mapping):
        return {}

    source: Mapping[str, Any] = mandates
    if "mandate" in mandates and isinstance(mandates["mandate"], Mapping):
        source = mandates["mandate"]  # type: ignore[assignment]
    elif "mintry" in mandates and isinstance(mandates["mintry"], Mapping):
        inner = mandates["mintry"]
        if "mandate" in inner and isinstance(inner["mandate"], Mapping):
            source = inner["mandate"]  # type: ignore[assignment]
        else:
            source = inner  # type: ignore[assignment]

    flat: dict[str, dict[str, Any]] = {}
    for mandate_id, raw in source.items():
        if not isinstance(raw, Mapping):
            continue
        rule: dict[str, Any] = {}
        if "allow" in raw:
            rule["allow"] = bool(raw["allow"])
        if "max_usd" in raw:
            try:
                rule["max_usd"] = float(raw["max_usd"])
            except (TypeError, ValueError):
                logger.warning("Skipping non-numeric max_usd for %s", mandate_id)
                continue
        if "expires_at" in raw and raw["expires_at"]:
            rule["expires_at"] = str(raw["expires_at"])
        if "fleet_id" in raw:
            rule["fleet_id"] = str(raw["fleet_id"])
        if "fleet_total_usd" in raw:
            try:
                rule["fleet_total_usd"] = float(raw["fleet_total_usd"])
            except (TypeError, ValueError):
                pass
        if rule:
            flat[str(mandate_id)] = rule
    return flat


class OPABundleEvaluator:
    """Load and materialize OPA-shaped bundles at sync time only."""

    def __init__(self, bundle_path: Optional[Path | str] = None):
        self.bundle_path = Path(bundle_path) if bundle_path else (
            Path.home() / ".mintry" / "opa_bundle.json"
        )
        self._bundle_cache: Optional[dict] = None
        self._flat_rules: dict[str, dict[str, Any]] = {}

    def load_bundle(self) -> bool:
        if not self.bundle_path.exists():
            logger.debug("OPA bundle not found at %s", self.bundle_path)
            return False
        try:
            with open(self.bundle_path, "r") as f:
                self._bundle_cache = json.load(f)
            self._flat_rules = self.materialize()
            logger.info(
                "Loaded OPA bundle from %s (%d rules)",
                self.bundle_path,
                len(self._flat_rules),
            )
            return True
        except Exception as exc:
            logger.error("Failed to load OPA bundle: %s", exc)
            return False

    def set_bundle_data(self, data: dict[str, Any]) -> dict[str, dict[str, Any]]:
        """Set in-memory bundle (e.g. from PolicyCache apply) and materialize."""
        if "data" in data or "metadata" in data:
            self._bundle_cache = data
        else:
            self._bundle_cache = {
                "metadata": {"source": "policy_cache"},
                "data": {"mintry": {"mandate": data}},
            }
        self._flat_rules = self.materialize()
        return self._flat_rules

    def materialize(self) -> dict[str, dict[str, Any]]:
        """Materialize flat rules from the loaded bundle (sync-time only)."""
        if not self._bundle_cache:
            return {}
        data = self._bundle_cache.get("data", self._bundle_cache)
        if isinstance(data, Mapping):
            mintry = data.get("mintry", data)
            return materialize_flat_rules(mintry if isinstance(mintry, Mapping) else {})
        return {}

    @property
    def flat_rules(self) -> dict[str, dict[str, Any]]:
        return dict(self._flat_rules)

    def evaluate(
        self,
        query: str,
        input_data: dict[str, Any],
    ) -> Optional[Any]:
        """Lookup against already-materialized flat rules.

        Does **not** spawn the OPA CLI. Returns rule dict, False if allow=false,
        or None if missing.
        """
        del input_data  # reserved for future pure in-process predicates
        if not self._flat_rules and self._bundle_cache:
            self._flat_rules = self.materialize()

        if not query.startswith("data."):
            return None
        parts = query.replace("data.", "").split(".")
        mandate_id = None
        if len(parts) >= 3 and parts[0] == "mintry" and parts[1] == "mandate":
            mandate_id = parts[2]
        elif len(parts) >= 2 and parts[0] == "mintry":
            mandate_id = parts[1]

        if mandate_id and mandate_id in self._flat_rules:
            rule = self._flat_rules[mandate_id]
            if rule.get("allow") is False:
                return False
            return rule

        return self._lookup_nested(parts)

    def _evaluate_in_process(self, query: str, input_data: dict) -> Optional[Any]:
        """Backward-compatible alias used by existing tests."""
        return self.evaluate(query, input_data)

    def _lookup_nested(self, path_parts: list[str]) -> Optional[Any]:
        if not self._bundle_cache:
            return None
        result: Any = self._bundle_cache.get("data", {})
        for part in path_parts:
            if isinstance(result, dict):
                result = result.get(part)
            else:
                return None
        return result

    def validate_bundle(self) -> bool:
        if not self._bundle_cache:
            return False
        required_fields = ["metadata", "data"]
        if not all(field in self._bundle_cache for field in required_fields):
            logger.warning("OPA bundle missing required fields")
            return False
        logger.info("OPA bundle validation passed")
        return True

"""OPA (Open Policy Agent) bundle evaluation for advanced policy logic.

OPA bundles are Rego policies compiled to JSON. Used for complex enforcement rules
beyond simple budget allows/blocks.

Never called from the enforcement hot path for Phase 1.
Phase 1 focus: structure only. Phase 2: integrate OPA evaluation.
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class OPABundleEvaluator:
    """Evaluate OPA (Rego) policies compiled to bundles."""

    def __init__(self, bundle_path: Optional[Path | str] = None):
        """Initialize the OPA evaluator.

        Args:
            bundle_path: Path to OPA bundle JSON file.
                        Falls back to ~/.mintry/opa_bundle.json if not provided.
        """
        self.bundle_path = Path(bundle_path) if bundle_path else (
            Path.home() / ".mintry" / "opa_bundle.json"
        )
        self._bundle_cache: Optional[dict] = None

    def load_bundle(self) -> bool:
        """Load OPA bundle from disk.

        Returns:
            True if bundle loaded successfully, False otherwise.
        """
        if not self.bundle_path.exists():
            logger.debug("OPA bundle not found at %s", self.bundle_path)
            return False

        try:
            with open(self.bundle_path, "r") as f:
                self._bundle_cache = json.load(f)
            logger.info("Loaded OPA bundle from %s", self.bundle_path)
            return True
        except Exception as exc:
            logger.error("Failed to load OPA bundle: %s", exc)
            return False

    def evaluate(
        self,
        query: str,
        input_data: dict[str, Any],
    ) -> Optional[Any]:
        """Evaluate an OPA query against input data.

        Phase 1: Requires local `opa` CLI binary for evaluation.
        Phase 2: Will integrate with embedded OPA runtime (no CLI dependency).

        Args:
            query: OPA query path (e.g. "data.mintry.allow_request")
            input_data: Input context for the query

        Returns:
            The query result, or None if evaluation fails or OPA not available.
        """
        if not self._bundle_cache:
            logger.debug("OPA bundle not loaded; skipping evaluation")
            return None

        try:
            # Phase 1: Use CLI if available (for testing)
            result = self._evaluate_with_cli(query, input_data)
            if result is not None:
                return result

            # Phase 1: Fallback to simple in-process evaluation
            logger.debug("OPA CLI not available; using fallback evaluation")
            return self._evaluate_in_process(query, input_data)

        except Exception as exc:
            logger.warning("OPA evaluation failed: %s", exc)
            return None

    def _evaluate_with_cli(self, query: str, input_data: dict) -> Optional[Any]:
        """Evaluate query using local OPA CLI (if available).

        Returns:
            Query result, or None if OPA not installed/available.
        """
        try:
            # Check if OPA binary is available
            subprocess.run(["opa", "version"], capture_output=True, timeout=1, check=True)
        except (FileNotFoundError, subprocess.CalledProcessError):
            return None

        try:
            cmd = ["opa", "eval", "-d", str(self.bundle_path), "-i", "-", query]
            result = subprocess.run(
                cmd,
                input=json.dumps(input_data).encode(),
                capture_output=True,
                timeout=5,
                check=True,
            )

            output = json.loads(result.stdout.decode())
            if output.get("result"):
                return output["result"][0].get("expressions", [{}])[0].get("value")

            return None
        except Exception as exc:
            logger.debug("OPA CLI evaluation failed: %s", exc)
            return None

    def _evaluate_in_process(self, query: str, input_data: dict) -> Optional[Any]:
        """Fallback: Simple in-process policy evaluation (Phase 1).

        This is a placeholder for Phase 2 when we integrate a full OPA runtime.
        Phase 1: Only supports basic queries like "data.mintry.mandate[<id>]"

        Returns:
            Query result, or None.
        """
        if not query.startswith("data."):
            return None

        try:
            path_parts = query.replace("data.", "").split(".")
            result = self._bundle_cache.get("data", {})

            for part in path_parts:
                if isinstance(result, dict):
                    result = result.get(part)
                else:
                    return None

            return result
        except Exception as exc:
            logger.debug("Fallback in-process evaluation failed: %s", exc)
            return None

    def validate_bundle(self) -> bool:
        """Validate OPA bundle structure.

        Returns:
            True if bundle is valid, False otherwise.
        """
        if not self._bundle_cache:
            return False

        required_fields = ["metadata", "data"]
        if not all(field in self._bundle_cache for field in required_fields):
            logger.warning("OPA bundle missing required fields")
            return False

        logger.info("OPA bundle validation passed")
        return True

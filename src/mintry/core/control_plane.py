"""Supabase control plane client for fetching policies and posting telemetry.

Runs only during async policy sync and telemetry batch uploads.
Never called from the enforcement hot path.

HTTP transport: uses urllib.request (stdlib) intentionally — httpx is
monkey-patched by Mintry's GlobalHTTPInterceptor and must not be used
here. Control plane calls are internal infrastructure, not customer LLM
traffic, and must never pass through the enforcement interceptor.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.request
import urllib.error
from typing import Optional

logger = logging.getLogger(__name__)


def _http_get(url: str, headers: dict, timeout: float = 5.0) -> tuple[int, bytes]:
    """Perform a GET request using stdlib urllib. Returns (status_code, body)."""
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def _http_post(url: str, headers: dict, body: bytes, timeout: float = 5.0) -> tuple[int, bytes]:
    """Perform a POST request using stdlib urllib. Returns (status_code, body)."""
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


class SupabaseControlPlaneClient:
    """Client for Supabase-hosted control plane API."""

    def __init__(
        self,
        control_plane_url: Optional[str] = None,
        api_key: Optional[str] = None,
        service_role_key: Optional[str] = None,
        timeout: float = 5.0,
    ):
        """Initialize the control plane client.

        Args:
            control_plane_url: Base URL for control plane (e.g. https://project.supabase.co)
                             Falls back to MINTRY_CONTROL_PLANE_URL env var
            api_key: Supabase anon key. Falls back to MINTRY_CONTROL_PLANE_KEY env var
            service_role_key: Supabase service role key (bypasses RLS for writes).
                             Falls back to MINTRY_SERVICE_ROLE_KEY env var.
            timeout: HTTP request timeout in seconds
        """
        self.url = control_plane_url or os.environ.get("MINTRY_CONTROL_PLANE_URL", "")
        self.api_key = api_key or os.environ.get("MINTRY_CONTROL_PLANE_KEY", "")
        # Service role key bypasses RLS — used for write operations only
        self.service_role_key = (
            service_role_key
            or os.environ.get("MINTRY_SERVICE_ROLE_KEY", "")
            or self.api_key  # fall back to anon key if service key not set
        )
        self.timeout = timeout

        if not self.url or not self.api_key:
            logger.warning(
                "Control plane not configured. "
                "Set MINTRY_CONTROL_PLANE_URL and MINTRY_CONTROL_PLANE_KEY to enable policy sync."
            )

    def _read_headers(self) -> dict:
        """Headers for read-only (anon key) requests."""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "apikey": self.api_key,
            "Content-Type": "application/json",
        }

    def _write_headers(self) -> dict:
        """Headers for write (service role key) requests — bypasses Supabase RLS."""
        return {
            "Authorization": f"Bearer {self.service_role_key}",
            "apikey": self.service_role_key,
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        }

    def fetch_policy_bundle(self, agent_id: str, current_version: Optional[int] = None) -> Optional[dict]:
        """Fetch the latest signed policy bundle for an agent.

        Args:
            agent_id: The agent ID to fetch policy for
            current_version: Current version the client has (for conditional fetch)

        Returns:
            The signed policy bundle dict, or None if fetch fails or no update available.
        """
        if not self.url or not self.api_key:
            logger.debug("Control plane not configured; skipping policy fetch")
            return None

        try:
            params = f"agent_id=eq.{agent_id}&order=version.desc&limit=1"
            if current_version is not None:
                params += f"&version=gt.{current_version}"
            url = f"{self.url}/rest/v1/policy_bundles?{params}"

            status, body = _http_get(url, self._read_headers(), timeout=self.timeout)

            if status != 200:
                logger.warning("Failed to fetch policy bundle: HTTP %s", status)
                return None

            bundles = json.loads(body)
            if not bundles:
                logger.debug("No policy updates for agent %s", agent_id)
                return None

            latest = bundles[0] if isinstance(bundles, list) else bundles
            logger.info("Fetched policy v%s for agent %s", latest.get("version"), agent_id)
            return latest

        except Exception as exc:
            logger.error("Control plane fetch error: %s", exc)
            return None

    def push_policy_bundle(self, bundle: dict, agent_id: str = "default_agent") -> bool:
        """Push a signed policy bundle to the Supabase policy_bundles table.

        Args:
            bundle: Policy bundle dict (must include version, policy_json, signature)
            agent_id: The agent this bundle is for

        Returns:
            True if successful, False otherwise.
        """
        if not self.url or not self.api_key:
            logger.debug("Control plane not configured; skipping bundle push")
            return False

        try:
            policy_json = bundle.get("policy_json") or {
                k: v for k, v in bundle.items()
                if k not in ("signature", "agent_id", "issued_at", "issued_by", "version")
            }

            record = {
                "agent_id": agent_id,
                "version": bundle["version"],
                "policy_json": policy_json if isinstance(policy_json, dict) else json.loads(policy_json),
                "signature": bundle.get("signature", ""),
                "issued_at": bundle.get("issued_at"),
                "issued_by": bundle.get("issued_by"),
            }

            # Supabase upsert: requires both Prefer header AND on_conflict query param
            url = f"{self.url}/rest/v1/policy_bundles?on_conflict=agent_id,version"
            headers = {**self._write_headers(), "Prefer": "resolution=merge-duplicates,return=minimal"}
            body = json.dumps(record).encode("utf-8")

            status, resp_body = _http_post(url, headers, body, timeout=self.timeout)

            if status not in (200, 201, 204):
                logger.warning("Failed to push policy bundle: HTTP %s — %s", status, resp_body[:200])
                return False

            logger.info("Pushed policy bundle v%s for agent %s", bundle["version"], agent_id)
            return True

        except Exception as exc:
            logger.error("Policy bundle push error: %s", exc)
            return False

    def post_telemetry_batch(self, records: list[dict]) -> bool:
        """Post a batch of telemetry records to the control plane.

        Args:
            records: List of telemetry records (mandate decisions, spend events)

        Returns:
            True if successful, False otherwise.
        """
        if not records:
            return True

        if not self.url or not self.api_key:
            logger.debug("Control plane not configured; telemetry not uploaded")
            return False

        try:
            url = f"{self.url}/rest/v1/telemetry_events"
            body = json.dumps(records).encode("utf-8")

            status, resp_body = _http_post(url, self._write_headers(), body, timeout=self.timeout)

            if status not in (200, 201, 204):
                logger.warning("Failed to post telemetry: HTTP %s — %s", status, resp_body[:200])
                return False

            logger.info("Uploaded %d telemetry records to control plane", len(records))
            return True

        except Exception as exc:
            logger.error("Telemetry POST error: %s", exc)
            return False

    def health_check(self) -> bool:
        """Check if control plane is reachable and credentials are valid.

        Queries policy_bundles with limit=0 using the anon key — returns 200
        when credentials are valid and the table exists. Intentionally uses
        urllib (not httpx) to bypass the Mintry enforcement interceptor.

        Returns:
            True if healthy, False otherwise.
        """
        if not self.url or not self.api_key:
            return False

        try:
            url = f"{self.url}/rest/v1/policy_bundles?limit=0"
            status, _ = _http_get(url, self._read_headers(), timeout=2.0)
            return status == 200
        except Exception as exc:
            logger.debug("Control plane health check failed: %s", exc)
            return False

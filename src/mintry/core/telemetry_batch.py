"""Batched telemetry collection and async posting to Supabase.

Never blocks the enforcement hot path.
Collects decisions asynchronously and uploads in batches every N seconds.
"""

from __future__ import annotations

import json
import logging
import queue
import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 100
DEFAULT_BATCH_INTERVAL_SEC = 30


@dataclass
class TelemetryEvent:
    """A single telemetry event (decision or spend)."""

    timestamp: str
    mandate_id: str
    action: str  # "allow", "block", "throttle", "spend"
    amount: float
    details: str
    agent_id: Optional[str] = None


class TelemetryBatcher:
    """Collects and batches telemetry events for async upload to control plane."""

    def __init__(
        self,
        wallet,
        control_plane_client,
        *,
        batch_size: int = DEFAULT_BATCH_SIZE,
        batch_interval_sec: float = DEFAULT_BATCH_INTERVAL_SEC,
    ):
        """Initialize the telemetry batcher.

        Args:
            wallet: MintryWallet instance
            control_plane_client: SupabaseControlPlaneClient instance
            batch_size: Upload when this many events are queued
            batch_interval_sec: Upload at most every N seconds
        """
        self._wallet = wallet
        self._control_plane = control_plane_client
        self._batch_size = batch_size
        self._batch_interval_sec = batch_interval_sec
        self._queue: queue.Queue[TelemetryEvent] = queue.Queue()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_upload_at = time.time()

    def start(self) -> None:
        """Start the background batch upload thread."""
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="mintry-telemetry")
        self._thread.start()
        logger.info("Telemetry batcher started (batch_size=%d, interval=%ds)", self._batch_size, self._batch_interval_sec)

    def stop(self) -> None:
        """Stop the background thread and flush pending events."""
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def record_decision(
        self,
        mandate_id: str,
        action: str,
        amount: float,
        details: str,
        agent_id: Optional[str] = None,
    ) -> None:
        """Queue a decision event for batch upload.

        Args:
            mandate_id: The mandate ID
            action: "allow", "block", or "throttle"
            amount: Cost/amount involved
            details: Human-readable event details
            agent_id: Optional agent ID
        """
        event = TelemetryEvent(
            timestamp=datetime.now(timezone.utc).isoformat(),
            mandate_id=mandate_id,
            action=action,
            amount=amount,
            details=details,
            agent_id=agent_id,
        )
        self._queue.put_nowait(event)

    def _run_loop(self) -> None:
        """Background loop: collect and upload batches."""
        batch: list[TelemetryEvent] = []

        while not self._stop.is_set():
            try:
                # Wait for either a batch to fill or the interval to elapse
                timeout = max(0.1, self._batch_interval_sec - (time.time() - self._last_upload_at))

                try:
                    event = self._queue.get(timeout=timeout)
                    batch.append(event)
                except queue.Empty:
                    pass

                # Upload if batch is full or interval elapsed
                should_upload = (
                    len(batch) >= self._batch_size
                    or (time.time() - self._last_upload_at) >= self._batch_interval_sec
                )

                if should_upload and batch:
                    self._upload_batch(batch)
                    batch = []
                    self._last_upload_at = time.time()

            except Exception as exc:
                logger.error("Telemetry loop error: %s", exc)

        # Flush any remaining events on shutdown
        if batch:
            self._upload_batch(batch)

    def _upload_batch(self, batch: list[TelemetryEvent]) -> None:
        """Upload a batch of events to the control plane."""
        try:
            records = [
                {
                    "agent_id": event.agent_id or "unknown",
                    "mandate_id": event.mandate_id,
                    "action": event.action,
                    "amount": event.amount,
                    # 'details' is jsonb in Supabase — must be a dict
                    "details": {"message": event.details} if isinstance(event.details, str) else event.details,
                    # Actual Supabase column name is 'timestamp'
                    "timestamp": event.timestamp,
                }
                for event in batch
            ]

            success = self._control_plane.post_telemetry_batch(records)
            if success:
                logger.info("Uploaded telemetry batch: %d events", len(batch))
            else:
                logger.warning("Telemetry batch upload failed; events queued locally")
                # Re-queue failed events
                for event in batch:
                    self._queue.put_nowait(event)

        except Exception as exc:
            logger.error("Batch upload error: %s", exc)

    def get_queue_size(self) -> int:
        """Get current queue size (for monitoring)."""
        return self._queue.qsize()

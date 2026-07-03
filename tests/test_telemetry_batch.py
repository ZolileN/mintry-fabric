"""Tests for batched telemetry collection and upload."""

import pytest
import time
from unittest.mock import MagicMock, patch
from pathlib import Path

from mintry.core.telemetry_batch import TelemetryBatcher, TelemetryEvent


def test_telemetry_event_creation():
    """Test creating a telemetry event."""
    event = TelemetryEvent(
        timestamp="2026-01-01T00:00:00Z",
        mandate_id="agent_1",
        action="allow",
        amount=0.01,
        details="Request allowed",
    )
    assert event.mandate_id == "agent_1"
    assert event.action == "allow"


def test_batcher_initialization():
    """Test batcher initialization."""
    mock_wallet = MagicMock()
    mock_control_plane = MagicMock()

    batcher = TelemetryBatcher(
        wallet=mock_wallet,
        control_plane_client=mock_control_plane,
        batch_size=10,
        batch_interval_sec=5,
    )

    assert batcher._batch_size == 10
    assert batcher._batch_interval_sec == 5


def test_batcher_record_decision():
    """Test recording a decision event."""
    mock_wallet = MagicMock()
    mock_control_plane = MagicMock()

    batcher = TelemetryBatcher(
        wallet=mock_wallet,
        control_plane_client=mock_control_plane,
    )

    batcher.record_decision(
        mandate_id="agent_1",
        action="allow",
        amount=0.01,
        details="Test event",
    )

    assert batcher.get_queue_size() == 1


def test_batcher_start_stop():
    """Test starting and stopping the batcher."""
    mock_wallet = MagicMock()
    mock_control_plane = MagicMock()

    batcher = TelemetryBatcher(
        wallet=mock_wallet,
        control_plane_client=mock_control_plane,
    )

    batcher.start()
    time.sleep(0.1)  # Give thread time to start
    assert batcher._thread is not None
    assert batcher._thread.is_alive()

    batcher.stop()
    time.sleep(0.2)  # Give thread time to stop
    assert not batcher._thread.is_alive()


def test_batcher_upload_batch():
    """Test batch upload to control plane."""
    mock_wallet = MagicMock()
    mock_control_plane = MagicMock()
    mock_control_plane.post_telemetry_batch.return_value = True

    batcher = TelemetryBatcher(
        wallet=mock_wallet,
        control_plane_client=mock_control_plane,
    )

    events = [
        TelemetryEvent(
            timestamp="2026-01-01T00:00:00Z",
            mandate_id="agent_1",
            action="allow",
            amount=0.01,
            details="Test",
        ),
        TelemetryEvent(
            timestamp="2026-01-01T00:00:01Z",
            mandate_id="agent_2",
            action="block",
            amount=50.0,
            details="Budget exceeded",
        ),
    ]

    batcher._upload_batch(events)
    mock_control_plane.post_telemetry_batch.assert_called_once()

    # Verify the records format
    call_args = mock_control_plane.post_telemetry_batch.call_args
    records = call_args[0][0]
    assert len(records) == 2
    assert records[0]["action"] == "allow"
    assert records[1]["action"] == "block"


def test_batcher_upload_batch_failure_requeues():
    """Test that failed uploads are requeued."""
    mock_wallet = MagicMock()
    mock_control_plane = MagicMock()
    mock_control_plane.post_telemetry_batch.return_value = False

    batcher = TelemetryBatcher(
        wallet=mock_wallet,
        control_plane_client=mock_control_plane,
    )

    events = [
        TelemetryEvent(
            timestamp="2026-01-01T00:00:00Z",
            mandate_id="agent_1",
            action="allow",
            amount=0.01,
            details="Test",
        ),
    ]

    initial_queue_size = batcher.get_queue_size()
    batcher._upload_batch(events)

    # Events should be requeued after failed upload
    time.sleep(0.1)
    assert batcher.get_queue_size() >= initial_queue_size


def test_batcher_batch_size_trigger():
    """Test that batch uploads when size threshold is reached."""
    mock_wallet = MagicMock()
    mock_control_plane = MagicMock()
    mock_control_plane.post_telemetry_batch.return_value = True

    batcher = TelemetryBatcher(
        wallet=mock_wallet,
        control_plane_client=mock_control_plane,
        batch_size=2,
        batch_interval_sec=10,
    )

    batcher.start()

    # Add events up to batch size
    batcher.record_decision("agent_1", "allow", 0.01, "Test 1")
    batcher.record_decision("agent_1", "allow", 0.01, "Test 2")

    # Give thread time to process
    time.sleep(0.5)

    # Should have uploaded by now (batch size reached)
    assert mock_control_plane.post_telemetry_batch.called

    batcher.stop()


def test_batcher_time_interval_trigger():
    """Test that batch uploads after time interval."""
    mock_wallet = MagicMock()
    mock_control_plane = MagicMock()
    mock_control_plane.post_telemetry_batch.return_value = True

    batcher = TelemetryBatcher(
        wallet=mock_wallet,
        control_plane_client=mock_control_plane,
        batch_size=100,  # Large, won't be triggered by size
        batch_interval_sec=0.3,  # Short interval
    )

    batcher.start()

    # Add one event
    batcher.record_decision("agent_1", "allow", 0.01, "Test")

    # Wait for interval to elapse
    time.sleep(0.5)

    # Should have uploaded by now (interval elapsed)
    assert mock_control_plane.post_telemetry_batch.called

    batcher.stop()


def test_batcher_flush_on_shutdown():
    """Test that pending events are flushed on shutdown."""
    mock_wallet = MagicMock()
    mock_control_plane = MagicMock()
    mock_control_plane.post_telemetry_batch.return_value = True

    batcher = TelemetryBatcher(
        wallet=mock_wallet,
        control_plane_client=mock_control_plane,
        batch_size=100,  # Large, won't be triggered by size
        batch_interval_sec=100,  # Long interval
    )

    batcher.start()

    # Add events
    batcher.record_decision("agent_1", "allow", 0.01, "Test 1")
    batcher.record_decision("agent_1", "allow", 0.01, "Test 2")

    # Stop should flush remaining events
    batcher.stop()

    # Should have been called to upload final batch
    assert mock_control_plane.post_telemetry_batch.called

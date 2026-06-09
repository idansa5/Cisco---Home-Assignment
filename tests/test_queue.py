from unittest.mock import MagicMock, patch

import fakeredis
import pytest
from rq import Queue

from app.queue import CapacityError, enqueue_scan, is_at_capacity
from app.config import settings


def make_fake_queue() -> Queue:
    conn = fakeredis.FakeRedis()
    return Queue("scans", connection=conn)


def mock_queue(running: int, queued: int) -> MagicMock:
    q = MagicMock(spec=Queue)
    q.count = queued
    with patch("app.queue.StartedJobRegistry") as mock_reg:
        mock_reg.return_value.__len__ = MagicMock(return_value=running)
        q._mock_reg = mock_reg
    return q


# --- is_at_capacity ---

def test_not_at_capacity_when_below_limit():
    q = make_fake_queue()
    with patch("app.queue.StartedJobRegistry") as mock_reg:
        mock_reg.return_value.__len__ = MagicMock(return_value=2)
        assert is_at_capacity(q) is False


def test_at_capacity_when_running_equals_max():
    q = make_fake_queue()
    with patch("app.queue.StartedJobRegistry") as mock_reg:
        mock_reg.return_value.__len__ = MagicMock(return_value=settings.max_parallel_scans)
        assert is_at_capacity(q) is True


def test_at_capacity_when_combined_equals_max():
    conn = fakeredis.FakeRedis()
    q = Queue("scans", connection=conn)
    # Pre-fill queue with (max - 1) jobs so running(1) + queued(max-1) = max
    for i in range(settings.max_parallel_scans - 1):
        q.enqueue("time.sleep", 0)
    with patch("app.queue.StartedJobRegistry") as mock_reg:
        mock_reg.return_value.__len__ = MagicMock(return_value=1)
        assert is_at_capacity(q) is True


def test_at_capacity_when_combined_exceeds_max():
    conn = fakeredis.FakeRedis()
    q = Queue("scans", connection=conn)
    for i in range(settings.max_parallel_scans):
        q.enqueue("time.sleep", 0)
    with patch("app.queue.StartedJobRegistry") as mock_reg:
        mock_reg.return_value.__len__ = MagicMock(return_value=1)
        assert is_at_capacity(q) is True


def test_not_at_capacity_when_one_below_limit():
    conn = fakeredis.FakeRedis()
    q = Queue("scans", connection=conn)
    for i in range(settings.max_parallel_scans - 1):
        q.enqueue("time.sleep", 0)
    with patch("app.queue.StartedJobRegistry") as mock_reg:
        mock_reg.return_value.__len__ = MagicMock(return_value=0)
        assert is_at_capacity(q) is False


# --- enqueue_scan ---

def test_enqueue_raises_capacity_error_when_full():
    q = make_fake_queue()
    with patch("app.queue.is_at_capacity", return_value=True):
        with pytest.raises(CapacityError):
            enqueue_scan("scan-1", "code", "rv-1", q=q)


def test_enqueue_returns_job_id_when_under_capacity():
    q = make_fake_queue()
    with patch("app.queue.is_at_capacity", return_value=False):
        job_id = enqueue_scan("scan-1", "code", "rv-1", q=q)
    assert isinstance(job_id, str)


def test_enqueue_does_not_raise_when_under_capacity():
    q = make_fake_queue()
    with patch("app.queue.is_at_capacity", return_value=False):
        enqueue_scan("scan-1", "code", "rv-1", q=q)
    assert q.count == 1

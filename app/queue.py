from __future__ import annotations

import time
import uuid
from contextlib import contextmanager

import redis
from rq import Callback, Queue
from rq.registry import StartedJobRegistry

from app.config import settings


class CapacityError(Exception):
    pass


def make_queue() -> Queue:
    conn = redis.from_url(settings.redis_url, db=0)
    return Queue("scans", connection=conn)


def is_at_capacity(q: Queue) -> bool:
    """True when running + queued jobs have reached the configured limit."""
    running = len(StartedJobRegistry(queue=q))
    return (running + q.count) >= settings.max_parallel_scans


@contextmanager
def _redis_lock(conn: redis.Redis, name: str, timeout: int = 10, blocking_timeout: int = 5):
    """Simple SET-NX based lock (avoids redis-py's Lua-script-based Lock,
    which fakeredis can't run without the optional `lupa` dependency)."""
    token = uuid.uuid4().hex
    deadline = time.monotonic() + blocking_timeout
    while not conn.set(name, token, nx=True, px=timeout * 1000):
        if time.monotonic() >= deadline:
            raise CapacityError("System at capacity, please try again later")
        time.sleep(0.05)
    try:
        yield
    finally:
        if conn.get(name) == token.encode():
            conn.delete(name)


def enqueue_scan(scan_id: str, code: str, ruleset_version: str, q: Queue | None = None) -> str:
    """Enqueue a scan job; raises CapacityError if the system is full."""
    if q is None:
        q = make_queue()
    # Atomic check-and-enqueue: prevents concurrent requests from all
    # passing the capacity check before any of their jobs are registered.
    with _redis_lock(q.connection, "scan_capacity_lock", timeout=10, blocking_timeout=5):
        if is_at_capacity(q):
            raise CapacityError("System at capacity, please try again later")
        # Pass the job function as a string so workers import it lazily (no circular deps)
        job = q.enqueue(
            "app.worker.run_scan",
            scan_id,
            code,
            ruleset_version,
            job_timeout=settings.scan_job_timeout_seconds,
            on_failure=Callback("app.worker.on_scan_failure"),
        )
        return job.id

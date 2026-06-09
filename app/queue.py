from __future__ import annotations

import redis
from rq import Queue
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


def enqueue_scan(scan_id: str, code: str, ruleset_version: str, q: Queue | None = None) -> str:
    """Enqueue a scan job; raises CapacityError if the system is full."""
    if q is None:
        q = make_queue()
    if is_at_capacity(q):
        raise CapacityError("System at capacity, please try again later")
    # Pass the job function as a string so workers import it lazily (no circular deps)
    job = q.enqueue("app.worker.run_scan", scan_id, code, ruleset_version)
    return job.id

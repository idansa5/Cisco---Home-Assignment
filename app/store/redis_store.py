from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

import redis

from app.models import RuleResult, ScanRecord, ScanStatus


# Results live in logical DB 1; RQ uses DB 0 by default.
_SCAN_KEY = "scan:{scan_id}"
_HASH_KEY = "hash:{code_hash}"


class RedisResultStore:
    def __init__(self, client: redis.Redis) -> None:
        self._r = client

    # ------------------------------------------------------------------
    # Public interface (matches store/base.py ResultStore protocol)
    # ------------------------------------------------------------------

    def create(self, scan_id: str, code_hash: str, ttl_seconds: int) -> None:
        record = ScanRecord(
            scan_id=scan_id,
            code_hash=code_hash,
            status=ScanStatus.queued,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        scan_key = _SCAN_KEY.format(scan_id=scan_id)
        self._r.setex(scan_key, ttl_seconds, record.model_dump_json())

    def update(
        self,
        scan_id: str,
        *,
        status: str,
        results: Optional[list[RuleResult]] = None,
        error: Optional[str] = None,
    ) -> None:
        scan_key = _SCAN_KEY.format(scan_id=scan_id)

        raw = self._r.get(scan_key)
        if raw is None:
            return  # scan expired or never existed; silently drop

        remaining_ttl = self._r.ttl(scan_key)
        data = json.loads(raw)
        data["status"] = status
        if results is not None:
            data["results"] = [r.model_dump() for r in results]
        if error is not None:
            data["error"] = error

        # keepttl=True (Redis 6+) preserves the remaining expiry without resetting it
        self._r.set(scan_key, json.dumps(data), keepttl=True)

        # When a scan completes successfully, index it by code_hash so future
        # submissions of the same file can be reused without re-running.
        if status == ScanStatus.done and remaining_ttl > 0:
            hash_key = _HASH_KEY.format(code_hash=data["code_hash"])
            self._r.setex(hash_key, remaining_ttl, scan_id)

    def get_by_id(self, scan_id: str) -> Optional[ScanRecord]:
        raw = self._r.get(_SCAN_KEY.format(scan_id=scan_id))
        if raw is None:
            return None
        return ScanRecord.model_validate_json(raw)

    def find_by_hash(self, code_hash: str) -> Optional[str]:
        """Return a completed scan_id for this code_hash, or None."""
        return self._r.get(_HASH_KEY.format(code_hash=code_hash))


def make_store(redis_url: str) -> RedisResultStore:
    """Factory used by both the API and the worker."""
    client = redis.from_url(redis_url, db=1, decode_responses=True)
    return RedisResultStore(client)

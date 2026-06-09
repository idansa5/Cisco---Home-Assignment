from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable

from app.models import RuleResult, ScanRecord


@runtime_checkable
class ResultStore(Protocol):
    def create(self, scan_id: str, code_hash: str, ruleset_version: str, ttl_seconds: int) -> None:
        """Persist a new scan record in the queued state."""
        ...

    def update(
        self,
        scan_id: str,
        *,
        status: str,
        results: Optional[list[RuleResult]] = None,
        error: Optional[str] = None,
    ) -> None:
        """Update status (and optionally results/error) without resetting the TTL."""
        ...

    def get_by_id(self, scan_id: str) -> Optional[ScanRecord]:
        """Return the scan record, or None if not found / expired."""
        ...

    def find_by_hash(self, code_hash: str) -> Optional[str]:
        """Return the scan_id of a completed scan with this code_hash, or None."""
        ...

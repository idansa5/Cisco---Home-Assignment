from __future__ import annotations

from enum import Enum
from typing import Optional
from pydantic import BaseModel


class ScanStatus(str, Enum):
    queued = "queued"
    running = "running"
    done = "done"
    failed = "failed"


class RuleResult(BaseModel):
    rule_id: str
    name: str
    passed: bool


class ScanRecord(BaseModel):
    scan_id: str
    code_hash: str
    status: ScanStatus
    created_at: str
    results: Optional[list[RuleResult]] = None
    error: Optional[str] = None

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
    ruleset_version: str
    status: ScanStatus
    created_at: str
    results: Optional[list[RuleResult]] = None
    error: Optional[str] = None


class ScanSubmitResponse(BaseModel):
    scan_id: str
    status: ScanStatus
    reused: bool = False


class ScanStatusResponse(BaseModel):
    scan_id: str
    status: ScanStatus
    results: Optional[list[RuleResult]] = None
    error: Optional[str] = None

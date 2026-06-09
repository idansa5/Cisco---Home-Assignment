from __future__ import annotations

import logging
from typing import Optional

from app.config import settings
from app.models import RuleResult, ScanStatus
from app.reviewer.engine import LLMClient, review
from app.reviewer.ollama_client import OllamaClient
from app.reviewer.rules import Rule, load_rules
from app.store.base import ResultStore
from app.store.redis_store import make_store

logger = logging.getLogger(__name__)


def run_scan(scan_id: str, code: str) -> None:
    """RQ job entrypoint — called by the worker process."""
    store = make_store(settings.redis_url)
    client = OllamaClient(settings.ollama_base_url, settings.ollama_model)
    _process_scan(scan_id, code, store, client)


def _process_scan(
    scan_id: str,
    code: str,
    store: ResultStore,
    client: LLMClient,
    rules: Optional[list[Rule]] = None,
) -> None:
    """Core scan logic — separated from run_scan so it can be unit-tested."""
    if rules is None:
        rules = load_rules()

    store.update(scan_id, status=ScanStatus.running)
    try:
        results: list[RuleResult] = review(code, rules, client)
        store.update(scan_id, status=ScanStatus.done, results=results)
    except Exception as exc:
        logger.error("Scan %s failed: %s", scan_id, exc)
        store.update(scan_id, status=ScanStatus.failed, error=str(exc))

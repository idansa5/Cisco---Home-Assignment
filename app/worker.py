from __future__ import annotations

import logging
from typing import Optional

from app.config import settings
from app.models import RuleResult, ScanStatus
from app.reviewer.engine import LLMClient, review
from app.reviewer.ollama_client import OllamaClient
from app.reviewer.rules import Rule, load_rules, ruleset_version
from app.store.base import ResultStore
from app.store.redis_store import make_store

logger = logging.getLogger(__name__)


def on_scan_failure(job, connection, exc_type, exc_value, exc_traceback) -> None:
    """RQ failure callback. _process_scan catches and records its own errors
    without re-raising, so this only fires when RQ itself abandons the job —
    i.e. the worker that picked it up died or it exceeded job_timeout."""
    scan_id = job.args[0]
    store = make_store(settings.redis_url)
    store.update(scan_id, status=ScanStatus.failed, error="Worker crashed or job timed out before completing")


def run_scan(scan_id: str, code: str, ruleset_version: str) -> None:
    """RQ job entrypoint — called by the worker process."""
    store = make_store(settings.redis_url)
    client = OllamaClient(settings.ollama_base_url, settings.ollama_model)
    _process_scan(scan_id, code, store, client, ruleset_version)


def _process_scan(
    scan_id: str,
    code: str,
    store: ResultStore,
    client: LLMClient,
    submitted_ruleset_version: str,
    rules: Optional[list[Rule]] = None,
    current_ruleset_version: Optional[str] = None,
) -> None:
    """Core scan logic — separated from run_scan so it can be unit-tested."""
    if rules is None:
        rules = load_rules()
    if current_ruleset_version is None:
        current_ruleset_version = ruleset_version()

    store.update(scan_id, status=ScanStatus.running)

    if submitted_ruleset_version != current_ruleset_version:
        store.update(
            scan_id,
            status=ScanStatus.failed,
            error="Rules changed since submission, please resubmit",
        )
        return

    try:
        results: list[RuleResult] = review(code, rules, client)
        store.update(scan_id, status=ScanStatus.done, results=results)
    except Exception as exc:
        logger.error("Scan %s failed: %s", scan_id, exc)
        store.update(scan_id, status=ScanStatus.failed, error=str(exc))

from unittest.mock import MagicMock, call, patch

from app.models import RuleResult, ScanStatus
from app.reviewer.rules import Rule
from app.worker import _process_scan

RULES = [
    Rule(id="rule_a", name="Meaningful names", prompt="Check names."),
    Rule(id="rule_b", name="Docstring matches", prompt="Check docstrings."),
]

RESULTS = [
    RuleResult(rule_id="rule_a", name="Meaningful names", passed=True),
    RuleResult(rule_id="rule_b", name="Docstring matches", passed=False),
]

CODE = "def f(x): return x"


def make_mock_store() -> MagicMock:
    return MagicMock()


def make_mock_client(results: list[RuleResult] = RESULTS) -> MagicMock:
    client = MagicMock()
    # review() is called with (code, rules, client) in engine — client.generate per rule
    client.generate.return_value = '{"passed": true}'
    return client


# --- status transitions ---

def test_process_scan_marks_running_before_review():
    store = make_mock_store()
    client = make_mock_client()
    _process_scan("scan-1", CODE, store, client, rules=RULES)
    first_call = store.update.call_args_list[0]
    assert first_call == call("scan-1", status=ScanStatus.running)


def test_process_scan_marks_done_on_success():
    store = make_mock_store()
    client = make_mock_client()
    _process_scan("scan-1", CODE, store, client, rules=RULES)
    last_call = store.update.call_args_list[-1]
    assert last_call.kwargs["status"] == ScanStatus.done


def test_process_scan_stores_results_on_success():
    store = make_mock_store()
    client = make_mock_client()
    _process_scan("scan-1", CODE, store, client, rules=RULES)
    last_call = store.update.call_args_list[-1]
    assert last_call.kwargs["results"] is not None


def test_process_scan_result_count_matches_rules():
    store = make_mock_store()
    client = make_mock_client()
    _process_scan("scan-1", CODE, store, client, rules=RULES)
    last_call = store.update.call_args_list[-1]
    assert len(last_call.kwargs["results"]) == len(RULES)


def test_process_scan_marks_failed_on_review_error():
    # The engine absorbs per-rule LLM errors; failed fires only if review() itself raises
    store = make_mock_store()
    client = make_mock_client()
    with patch("app.worker.review", side_effect=RuntimeError("review crashed")):
        _process_scan("scan-1", CODE, store, client, rules=RULES)
    last_call = store.update.call_args_list[-1]
    assert last_call.kwargs["status"] == ScanStatus.failed


def test_process_scan_stores_error_message_on_failure():
    store = make_mock_store()
    client = make_mock_client()
    with patch("app.worker.review", side_effect=RuntimeError("review crashed")):
        _process_scan("scan-1", CODE, store, client, rules=RULES)
    last_call = store.update.call_args_list[-1]
    assert last_call.kwargs["error"] is not None


def test_process_scan_updates_store_twice_on_success():
    store = make_mock_store()
    client = make_mock_client()
    _process_scan("scan-1", CODE, store, client, rules=RULES)
    assert store.update.call_count == 2


def test_process_scan_updates_store_twice_on_failure():
    store = make_mock_store()
    client = MagicMock()
    client.generate.side_effect = RuntimeError("boom")
    _process_scan("scan-1", CODE, store, client, rules=RULES)
    assert store.update.call_count == 2

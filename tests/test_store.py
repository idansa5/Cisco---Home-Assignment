import pytest
import fakeredis

from app.models import RuleResult, ScanStatus
from app.store.base import ResultStore
from app.store.redis_store import RedisResultStore

TTL = 86400

RESULTS = [
    RuleResult(rule_id="rule_1", name="Meaningful names", passed=True),
    RuleResult(rule_id="rule_2", name="Docstring matches", passed=False),
]


@pytest.fixture()
def store() -> RedisResultStore:
    client = fakeredis.FakeRedis(decode_responses=True)
    return RedisResultStore(client)


# --- Protocol compliance ---

def test_implements_result_store_protocol(store):
    assert isinstance(store, ResultStore)


# --- create + get_by_id ---

def test_create_sets_scan_id(store):
    store.create("scan-1", "hash-abc", "rv-1", TTL)
    assert store.get_by_id("scan-1").scan_id == "scan-1"


def test_create_sets_code_hash(store):
    store.create("scan-1", "hash-abc", "rv-1", TTL)
    assert store.get_by_id("scan-1").code_hash == "hash-abc"


def test_create_initial_status_is_queued(store):
    store.create("scan-1", "hash-abc", "rv-1", TTL)
    assert store.get_by_id("scan-1").status == ScanStatus.queued


def test_create_results_initially_none(store):
    store.create("scan-1", "hash-abc", "rv-1", TTL)
    assert store.get_by_id("scan-1").results is None


def test_get_by_id_returns_none_for_unknown(store):
    assert store.get_by_id("nonexistent") is None


# --- TTL ---

def test_ttl_is_set_on_create(store):
    store.create("scan-1", "hash-abc", "rv-1", TTL)
    assert 0 < store._r.ttl("scan:scan-1") <= TTL


# --- update: running ---

def test_update_to_running_sets_status(store):
    store.create("scan-1", "hash-abc", "rv-1", TTL)
    store.update("scan-1", status=ScanStatus.running)
    assert store.get_by_id("scan-1").status == ScanStatus.running


# --- update: done ---

def test_update_to_done_sets_status(store):
    store.create("scan-1", "hash-abc", "rv-1", TTL)
    store.update("scan-1", status=ScanStatus.done, results=RESULTS)
    assert store.get_by_id("scan-1").status == ScanStatus.done


def test_update_to_done_stores_result_count(store):
    store.create("scan-1", "hash-abc", "rv-1", TTL)
    store.update("scan-1", status=ScanStatus.done, results=RESULTS)
    assert len(store.get_by_id("scan-1").results) == 2


def test_update_to_done_first_rule_passed(store):
    store.create("scan-1", "hash-abc", "rv-1", TTL)
    store.update("scan-1", status=ScanStatus.done, results=RESULTS)
    assert store.get_by_id("scan-1").results[0].passed is True


def test_update_to_done_second_rule_failed(store):
    store.create("scan-1", "hash-abc", "rv-1", TTL)
    store.update("scan-1", status=ScanStatus.done, results=RESULTS)
    assert store.get_by_id("scan-1").results[1].passed is False


# --- update: failed ---

def test_update_to_failed_sets_status(store):
    store.create("scan-1", "hash-err", "rv-1", TTL)
    store.update("scan-1", status=ScanStatus.failed, error="LLM timeout")
    assert store.get_by_id("scan-1").status == ScanStatus.failed


def test_update_to_failed_stores_error_message(store):
    store.create("scan-1", "hash-err", "rv-1", TTL)
    store.update("scan-1", status=ScanStatus.failed, error="LLM timeout")
    assert store.get_by_id("scan-1").error == "LLM timeout"


# --- find_by_hash (reuse) ---

def test_find_by_hash_returns_none_before_done(store):
    store.create("scan-1", "hash-pending", "rv-1", TTL)
    assert store.find_by_hash("hash-pending") is None


def test_find_by_hash_returns_scan_id_after_done(store):
    store.create("scan-1", "hash-done", "rv-1", TTL)
    store.update("scan-1", status=ScanStatus.done, results=[])
    assert store.find_by_hash("hash-done") == "scan-1"


# --- edge cases ---

def test_update_on_missing_scan_does_not_raise(store):
    store.update("ghost", status=ScanStatus.running)
    assert store.get_by_id("ghost") is None

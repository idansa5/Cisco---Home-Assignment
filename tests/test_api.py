from __future__ import annotations

import hashlib
from unittest.mock import patch

import fakeredis
import pytest
from fastapi.testclient import TestClient
from rq import Queue

from app.api.main import app, get_rq_queue, get_store
from app.models import RuleResult, ScanStatus
from app.store.redis_store import RedisResultStore

SAMPLE_PY = b"def add(a, b):\n    return a + b\n"
FIXED_RV = "test-ruleset-v1"


@pytest.fixture()
def fake_store():
    return RedisResultStore(fakeredis.FakeRedis(decode_responses=True))


@pytest.fixture()
def fake_queue():
    return Queue("scans", connection=fakeredis.FakeRedis())


@pytest.fixture()
def api_client(fake_store, fake_queue):
    app.dependency_overrides[get_store] = lambda: fake_store
    app.dependency_overrides[get_rq_queue] = lambda: fake_queue
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _post_scan(client, content=SAMPLE_PY, filename="test.py"):
    return client.post("/scans", files={"file": (filename, content, "text/plain")})


def _seed_done_scan(store, content=SAMPLE_PY, rv=FIXED_RV, scan_id="existing-scan"):
    code_hash = hashlib.sha256(content + rv.encode()).hexdigest()
    store.create(scan_id, code_hash, rv, 86400)
    store.update(scan_id, status=ScanStatus.done, results=[
        RuleResult(rule_id="rule_a", name="Meaningful names", passed=True),
    ])
    return scan_id, code_hash


# --- GET /health ---

def test_health_returns_200(api_client):
    assert api_client.get("/health").status_code == 200


# --- POST /scans: validation ---

def test_submit_valid_py_returns_202(api_client):
    with patch("app.api.main.ruleset_version", return_value=FIXED_RV):
        assert _post_scan(api_client).status_code == 202


def test_submit_non_py_returns_400(api_client):
    assert _post_scan(api_client, filename="test.txt").status_code == 400


def test_submit_empty_file_returns_400(api_client):
    with patch("app.api.main.ruleset_version", return_value=FIXED_RV):
        assert _post_scan(api_client, content=b"   ").status_code == 400


# --- POST /scans: new scan ---

def test_submit_returns_scan_id(api_client):
    with patch("app.api.main.ruleset_version", return_value=FIXED_RV):
        resp = _post_scan(api_client)
    assert "scan_id" in resp.json()


def test_submit_returns_queued_status(api_client):
    with patch("app.api.main.ruleset_version", return_value=FIXED_RV):
        resp = _post_scan(api_client)
    assert resp.json()["status"] == ScanStatus.queued


def test_submit_returns_reused_false(api_client):
    with patch("app.api.main.ruleset_version", return_value=FIXED_RV):
        resp = _post_scan(api_client)
    assert resp.json()["reused"] is False


def test_submit_creates_record_in_store(api_client, fake_store):
    with patch("app.api.main.ruleset_version", return_value=FIXED_RV):
        resp = _post_scan(api_client)
    assert fake_store.get_by_id(resp.json()["scan_id"]) is not None


def test_submit_enqueues_job(api_client, fake_queue):
    with patch("app.api.main.ruleset_version", return_value=FIXED_RV):
        _post_scan(api_client)
    assert fake_queue.count == 1


# --- POST /scans: capacity ---

def test_submit_at_capacity_returns_429(api_client):
    with patch("app.api.main.is_at_capacity", return_value=True):
        assert _post_scan(api_client).status_code == 429


# --- POST /scans: reuse ---

def test_submit_reused_returns_200(api_client, fake_store):
    _seed_done_scan(fake_store)
    with patch("app.api.main.ruleset_version", return_value=FIXED_RV):
        resp = _post_scan(api_client)
    assert resp.status_code == 200


def test_submit_reused_returns_existing_scan_id(api_client, fake_store):
    existing_id, _ = _seed_done_scan(fake_store)
    with patch("app.api.main.ruleset_version", return_value=FIXED_RV):
        resp = _post_scan(api_client)
    assert resp.json()["scan_id"] == existing_id


def test_submit_reused_has_reused_flag_true(api_client, fake_store):
    _seed_done_scan(fake_store)
    with patch("app.api.main.ruleset_version", return_value=FIXED_RV):
        resp = _post_scan(api_client)
    assert resp.json()["reused"] is True


def test_submit_reused_does_not_enqueue_new_job(api_client, fake_store, fake_queue):
    _seed_done_scan(fake_store)
    with patch("app.api.main.ruleset_version", return_value=FIXED_RV):
        _post_scan(api_client)
    assert fake_queue.count == 0


# --- GET /scans/{id} ---

def test_get_unknown_scan_returns_404(api_client):
    assert api_client.get("/scans/nonexistent").status_code == 404


def test_get_existing_scan_returns_200(api_client, fake_store):
    fake_store.create("scan-abc", "hash-1", FIXED_RV, 86400)
    assert api_client.get("/scans/scan-abc").status_code == 200


def test_get_scan_returns_correct_scan_id(api_client, fake_store):
    fake_store.create("scan-abc", "hash-1", FIXED_RV, 86400)
    assert api_client.get("/scans/scan-abc").json()["scan_id"] == "scan-abc"


def test_get_scan_returns_status(api_client, fake_store):
    fake_store.create("scan-abc", "hash-1", FIXED_RV, 86400)
    assert api_client.get("/scans/scan-abc").json()["status"] == ScanStatus.queued


def test_get_done_scan_includes_results(api_client, fake_store):
    scan_id, _ = _seed_done_scan(fake_store)
    assert api_client.get(f"/scans/{scan_id}").json()["results"] is not None


def test_get_queued_scan_has_no_results(api_client, fake_store):
    fake_store.create("scan-abc", "hash-1", FIXED_RV, 86400)
    assert api_client.get("/scans/scan-abc").json()["results"] is None

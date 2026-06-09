from __future__ import annotations

import hashlib
import uuid

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from rq import Queue

from app.config import settings
from app.models import ScanStatusResponse, ScanSubmitResponse, ScanStatus
from app.queue import CapacityError, enqueue_scan, is_at_capacity, make_queue
from app.reviewer.rules import ruleset_version
from app.store.base import ResultStore
from app.store.redis_store import make_store

app = FastAPI(title="Code Review Platform", version="0.1.0")


# --- dependencies (overridable in tests) ---

def get_store() -> ResultStore:
    return make_store(settings.redis_url)


def get_rq_queue() -> Queue:
    return make_queue()


# --- endpoints ---

@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/scans", status_code=202, response_model=ScanSubmitResponse)
async def submit_scan(
    file: UploadFile = File(...),
    store: ResultStore = Depends(get_store),
    q: Queue = Depends(get_rq_queue),
) -> JSONResponse | ScanSubmitResponse:
    if not file.filename.endswith(".py"):
        raise HTTPException(status_code=400, detail="Only .py files are accepted")

    code_bytes = await file.read()
    if not code_bytes.strip():
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    rv = ruleset_version()
    code_hash = hashlib.sha256(code_bytes + rv.encode()).hexdigest()

    # Reuse: return the existing scan immediately without re-running
    existing_id = store.find_by_hash(code_hash)
    if existing_id:
        return JSONResponse(
            status_code=200,
            content={"scan_id": existing_id, "status": ScanStatus.done, "reused": True},
        )

    # Capacity gate — checked before creating the record to avoid orphans
    if is_at_capacity(q):
        raise HTTPException(status_code=429, detail="System at capacity, please try again later")

    scan_id = str(uuid.uuid4())
    code_str = code_bytes.decode("utf-8", errors="replace")

    store.create(scan_id, code_hash, rv, settings.result_ttl_seconds)
    enqueue_scan(scan_id, code_str, rv, q=q)

    return ScanSubmitResponse(scan_id=scan_id, status=ScanStatus.queued, reused=False)


@app.get("/scans/{scan_id}", response_model=ScanStatusResponse)
def get_scan(
    scan_id: str,
    store: ResultStore = Depends(get_store),
) -> ScanStatusResponse:
    record = store.get_by_id(scan_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Scan not found or has expired")
    return ScanStatusResponse(
        scan_id=record.scan_id,
        status=record.status,
        results=record.results,
        error=record.error,
    )

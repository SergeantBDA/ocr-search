# app/web/admin_jobs.py
from __future__ import annotations
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
import json, html
from app.broker.config import r, NS, KEY_JOB  # готовые объекты/функции из вашего config.py
from app.broker.workers import process_upload   # актёр для “повтора” задачи
from app.config import settings

from fastapi.templating import Jinja2Templates
templates = Jinja2Templates(directory="app/web/templates")

router = APIRouter(prefix="/admin/jobs", tags=["admin"])

def _scan_jobs():
    # безопасно сканим все job-ключи
    for key in r.scan_iter(f"{NS}:job:*"):
        raw = r.get(key)
        if not raw:
            continue
        job = json.loads(raw)
        job_id = key.decode().split(":")[-1] if isinstance(key, bytes) else str(key).split(":")[-1]
        job["job_id"] = job_id
        yield job

@router.get("", response_class=HTMLResponse)
def jobs_page(request: Request):
    jobs = list(_scan_jobs())
    return templates.TemplateResponse("admin_jobs.html", {"request": request, "jobs": jobs})

# app/web/admin_jobs.py
@router.post("/{job_id}/abort")
def job_abort(request: Request, job_id: str):
    r.setex(f"{NS}:job-cancel:{job_id}", 3600, b"1")
    data = r.get(KEY_JOB(job_id))
    if data:
        job = json.loads(data); job["status"] = "aborting"
        r.set(KEY_JOB(job_id), json.dumps(job, ensure_ascii=False))
    return jobs_page(request)
 
@router.delete("/{job_id}/del")
def job_delete(request: Request, job_id: str):
    r.setex(f"{NS}:job-cancel:{job_id}", 3600, b"1")
    r.setex(f"{NS}:job-deleted:{job_id}", 3600, b"1")
    r.delete(KEY_JOB(job_id))
    return jobs_page(request)
 
@router.post("/{job_id}/retry")
def job_retry(request: Request, job_id: str):
    data = r.get(KEY_JOB(job_id))
    if not data:
        return HTMLResponse("<div>job not found</div>", status_code=404)
    job = json.loads(data)
    payload = job.get("payload")
    if not payload:
        return HTMLResponse("<div>no payload to retry</div>", status_code=400)
    import uuid, datetime
    new_id = uuid.uuid4().hex
    process_upload.send(new_id, payload["files"], payload["texts_dir"], payload["user_email"])
    from app.broker.config import job_set
    job_set(new_id, {
        "status": "queued",
        "created_at": datetime.datetime.utcnow().isoformat(),
        "total": len(payload["files"]),
        "done": 0, "progress": 0, "items": [],
        "error": None,
        "payload": payload,
    })
    return jobs_page(request)

# app/web/admin_jobs.py
from __future__ import annotations
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
import json, html
from app.broker.config import r, NS, KEY_JOB  # готовые объекты/функции из вашего config.py
from app.broker.workers import process_upload   # актёр для “повтора” задачи
from app.config import settings

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
    rows = []
    for job in _scan_jobs():
        rows.append(f"""
        <tr>
          <td>{html.escape(job.get('job_id',''))}</td>
          <td>{html.escape(job.get('status',''))}</td>
          <td>{job.get('progress',0)}%</td>
          <td>{html.escape(job.get('created_at',''))}</td>
          <td>
            <button hx-post="/admin/jobs/{job['job_id']}/abort" hx-target="closest tr"  hx-swap="outerHTML">Прервать</button>
            <button hx-post="/admin/jobs/{job['job_id']}/retry" hx-target="#jobs-table" hx-swap="outerHTML">Повторить</button>
            <button hx-delete="/admin/jobs/{job['job_id']}/del" hx-target="closest tr"  hx-swap="outerHTML">Удалить</button>
          </td>
        </tr>""")
    table = f"""
    <table id="jobs-table" class="table">
      <thead><tr><th>Job</th><th>Статус</th><th>Прогресс</th><th>Создан</th><th></th></tr></thead>
      <tbody>{"".join(rows) or "<tr><td colspan=5>Нет заданий</td></tr>"}</tbody>
    </table>"""
    # простой HTML (можете вставить в ваш layout)
    return HTMLResponse(f"<h1>Задания</h1>{table}")

# app/web/admin_jobs.py
@router.delete("/{job_id}/del")
def job_delete(job_id: str):
    # 1) отменяем текущую работу
    r.setex(f"{NS}:job-cancel:{job_id}", 3600, b"1")
    # 2) ставим tombstone на час
    r.setex(f"{NS}:job-deleted:{job_id}", 3600, b"1")
    # 3) удаляем ключ статуса
    r.delete(KEY_JOB(job_id))
    return HTMLResponse("")


@router.post("/{job_id}/abort")
def job_abort(job_id: str):
    # ставим флаг отмены и меняем статус (см. хук в воркере ниже)
    r.setex(f"{NS}:job-cancel:{job_id}", 3600, b"1")
    data = r.get(KEY_JOB(job_id))
    if data:
        job = json.loads(data)
        job["status"] = "aborting"
        r.set(KEY_JOB(job_id), json.dumps(job, ensure_ascii=False))
    return HTMLResponse("")

@router.post("/{job_id}/retry")
def job_retry(job_id: str):
    # Простой способ: переотправить задачу, если вы сохраняете исходный payload в job (files, texts_dir, email).
    data = r.get(KEY_JOB(job_id))
    if not data:
        return JSONResponse({"ok": False, "error": "job not found"}, status_code=404)
    job = json.loads(data)
    payload = job.get("payload")  # СМОТРИТЕ ниже: как положить payload в job_set из вашего места постановки задач
    if not payload:
        return JSONResponse({"ok": False, "error": "no payload to retry"}, status_code=400)

    # создаём новый job_id и шлём в actor
    import uuid, datetime
    new_id = uuid.uuid4().hex
    process_upload.send(new_id, payload["files"], payload["texts_dir"], payload["user_email"])
    # и сразу создаём ключ статуса нового задания
    from app.broker.config import job_set
    job_set(new_id, {
        "status": "queued",
        "created_at": datetime.datetime.utcnow().isoformat(),
        "total": len(payload["files"]),
        "done": 0, "progress": 0, "items": [],
        "error": None,
        "payload": payload,
    })
    return jobs_page(request=None)  # перерисуем таблицу
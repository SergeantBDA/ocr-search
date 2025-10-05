from app.infra.broker import broker
import uuid
import shutil
import asyncio
import logging
from urllib.parse import quote
from typing import Optional, List, Dict, Annotated, Any
from pathlib import Path
from datetime import datetime

import dramatiq
from fastapi import APIRouter, Request, UploadFile, File, Depends, Query
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session

from app import search as search_module
from app.db import get_session, SessionLocal
from app.models import Document, User
from app.schemas import UserRead
#from app.services.ocr_dispatch import extract_text
from app.services import save_outputs
from app.settings_store import get_documents_dir as store_get_documents_dir
from app.config import settings
from app.logger import logger as app_logger, attach_to_logger_names
from app.services import bytes_xtractor as bx

from concurrent.futures import ThreadPoolExecutor

attach_to_logger_names(["app.web.routes"])

# import auth dependency
from app.services.auth import get_current_user

# защитить все эндпоинты этого роутера
router = APIRouter(
    prefix="",
    tags=["web"],
    dependencies=[Depends(get_current_user)],
)
CurrentUser = Annotated[User, Depends(get_current_user)]
templates = Jinja2Templates(directory="app/web/templates")

# В test: in-memory. В проде — используйте Redis/БД.
JOBS: dict[str, dict] = {}

def get_current_user_login_proxy(request: Request) -> str:
    # заголовок выставляет обратный прокси
    user = request.headers.get("X-Remote-User")
    return user or "anonymous"

@router.get("/whoami")
def whoami(request: Request, user: str = Depends(get_current_user_login_proxy)):
    return {"user": user}

@router.get("/", include_in_schema=True)
def index(request: Request, current_user: CurrentUser = None):
    """
    Рендерит главную страницу (index.html) с пустым блоком результатов.
    """
    user = UserRead.model_validate(current_user, from_attributes=True)
    context = {
        "request": request,
        "q": "",
        "items": [],
        "total": 0,
        "limit": 25,
        "offset": 0,
        "current_user":user
    }
    return templates.TemplateResponse("index.html", context)

@router.get("/search", include_in_schema=True)
async def search(
    request: Request,
    q: str = Query("", description="строка поиска"),
    ocr_user: Optional[str] = Query(None, description="email/user"),
    ocr_from: Optional[str] = Query(None, description="filter от"),
    ocr_to  : Optional[str] = Query(None, description="filter до"),
    limit: int = 25,
    offset: int = 0,
    db: Session = Depends(get_session),
):
    """
    HTMX: возвращает partial со списком результатов (_results.html).
    """
    print(q, ocr_user, ocr_from, ocr_to)

    result = search_module.search_documents(db, q=q, ocr_user=ocr_user, ocr_from=ocr_from, ocr_to=ocr_to, limit=limit, offset=offset)
    context = {
        "request": request,
        "q": q,
        "ocr_user":ocr_user,
        "ocr_from":ocr_from,
        "ocr_to":ocr_to,
        "items": result.get("items", []),
        "total": result.get("total", 0),
        "limit": limit,
        "offset": offset,
    }
    return templates.TemplateResponse("_results.html", context)


@router.post("/scan", name="scan_now", include_in_schema=True)
def scan_now(request: Request, db: Session = Depends(get_session)):
    """
    Запускает сканирование каталога (scan_folder) и возвращает partial-отчёт (_scan_report.html).
    (Остаётся для API/админов — UI выбора каталога отключён в пользу загрузки директорий клиентом)
    """
    try:
        report = ingest_folder.scan_folder(db, recursive=True)
    except Exception as exc:
        app_logger.exception("Scan failed: %s", exc)
        return HTMLResponse(f'<div class="muted">Ошибка запуска сканирования: {exc}</div>', status_code=500)

    successes = [r for r in report if r.get("status") == "ok"]
    failures = [r for r in report if r.get("status") != "ok"]

    res = search_module.search_documents(db, "", limit=25, offset=0)
    items = res.get("items", [])

    context = {
        "request": request,
        "report": report,
        "success_count": len(successes),
        "failure_count": len(failures),
        "items": items,
    }
    return templates.TemplateResponse("_scan_report.html", context)

# ================
# POST /upload
# ================
@router.post("/upload", name="upload", include_in_schema=True)
async def upload_file(
    request: Request,
    files: List[UploadFile] = File(...),
    current_user: CurrentUser = None,
):
    """
    Только загрузка файлов в "пользовательский" каталог и постановка задания в Dramatiq.
    Возвращает 202 Accepted + {"job_id": "..."}.
    """
    user = UserRead.model_validate(current_user, from_attributes=True)

    # Каталог для оригиналов: <output_originals_dir>/<YYYYMMDDHH>_<login>
    prefix = f"{datetime.now().strftime('%Y%m%d%H')}_{user.email.split('@')[0]}"
    upload_dir = Path(settings.output_originals_dir) / prefix
    upload_dir.mkdir(parents=True, exist_ok=True)

    saved_paths: list[dict] = []  # [{path, filename, mime}]
    for f in files:
        filename = f.filename or "uploaded"
        mime = (f.content_type or "").lower() or None
        dst = upload_dir / filename
        with dst.open("wb") as w:
            shutil.copyfileobj(f.file, w)
        saved_paths.append({"path": str(dst), "filename": filename, "mime": mime})

    if not saved_paths:
        return HTMLResponse('<div class="muted">Файлы не были загружены.</div>', status_code=400)

    # Каталог для текстов (по той же сигнатуре)
    texts_dir = Path(settings.output_texts_dir) / prefix
    texts_dir.mkdir(parents=True, exist_ok=True)

    # Создаем job и кидаем в Dramatiq
    job_id = str(uuid.uuid4())
    JOBS[job_id] = {
        "status": "queued",
        "created_at": datetime.utcnow().isoformat(),
        "total": len(saved_paths),
        "done": 0,
        "items": [],
        "error": None,
    }

    process_upload.send(job_id, saved_paths, str(texts_dir), user.email)

    # Возвращаем JSON — удобно для JS/HTMX
    return JSONResponse({"job_id": job_id}, status_code=202)


# ================
# GET /jobs/{id} — partial для HTMX
# ================
@router.get("/jobs/{job_id}", include_in_schema=False)
def job_status(job_id: str, request: Request):
    job = JOBS.get(job_id)
    if not job:
        return HTMLResponse(f'<div class="text-danger">Задание {job_id} не найдено</div>', status_code=404)

    if job["status"] in ("queued", "running"):
        # отдаём маленький partial с прогрессом
        return templates.TemplateResponse(
            "_job_progress.html",
            {"request": request, "job": job, "job_id": job_id},
            status_code=200,
        )

    if job["status"] == "error":
        return HTMLResponse(f'<div class="text-danger">Ошибка: {job["error"]}</div>', status_code=500)

    # status == done — вернём список результатов тем же шаблоном, что и раньше
    return templates.TemplateResponse(
        "_results.html",
        {"request": request, "items": job.get("items") or []},
        status_code=200,
    )


# =======================
# Dramatiq actor
# =======================
# 1) ЯВНОЕ имя очереди — так проще не промахнуться при запуске
@dramatiq.actor(queue_name="upload", max_retries=0)
def process_upload(job_id: str, files: list[dict], texts_dir: str, user_email: str):
    app_logger.info("process_upload START job_id=%s files=%d texts_dir=%s", job_id, len(files), texts_dir)
    try:
        if job_id in JOBS:
            JOBS[job_id] = {'status':'started', "progress":0, "items":[]}
        else:
            JOBS[job_id].update({'status':'started', "progress":0, "items":[]})

    except Exception as e:
        app_logger.warning("job_update(running) failed: %s", e)
    done = 0
    for f in files:
        path = f["path"]
        filename = f["filename"]
        mime = f.get("mime")
        app_logger.info("process_upload file=%s mime=%s", path, mime)
        try:
            text = bx.extract_text_file(path, filename=filename, mime=mime) or ""
            try:
                save_outputs.save_text(filename, text, Path(texts_dir))
            except Exception as e:
                app_logger.exception("save_text failed for %s: %s", filename, e)
 
            db = SessionLocal()
            try:
                p = Path(path)
                path_origin = Path(*(settings.hostfs, *p.parts[1:])) if settings.hostfs else p
                doc = Document(
                    filename=filename,
                    content=text,
                    mime=mime,
                    size_bytes=p.stat().st_size if p.exists() else 0,
                    meta={},
                    path_origin=str(path_origin),
                    email=user_email,
                )
                db.add(doc)
                db.commit()
                db.refresh(doc)
                link = f'http://{settings.httpfs}/{doc.path_origin.replace("\\\\", "/")}' if settings.httpfs and doc.path_origin else None
                JOBS[job_id]["items"].append(
                    {
                        "id": doc.id,
                        "filename": doc.filename,
                        "link": link,
                        "snippet": (doc.content or "")[:100]
                    })
            finally:
                db.close()
 
            done += 1
            if job_id in JOBS:
                JOBS[job_id]["done"] = done
        except Exception as exc:
            app_logger.exception("process_upload failed for %s: %s", filename, exc)
            JOBS[job_id]["status"] = "error"
            JOBS[job_id]["error"] = str(exc)
            return
    if job_id in JOBS:
        JOBS[job_id]["status"] = "done"
        app_logger.info("process_upload DONE job_id=%s", job_id)

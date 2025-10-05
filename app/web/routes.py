
from __future__ import annotations

import uuid
import shutil
from typing import Optional, List, Annotated
from pathlib import Path
from datetime import datetime

from fastapi import APIRouter, Request, UploadFile, File, Depends, Query
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session

from app import search as search_module
from app.db import get_session
from app.schemas import UserRead
from app.services.auth import get_current_user
from app.config import settings
from app.logger import logger as app_logger, attach_to_logger_names

# Redis/Memurai helpers + actor
from app.broker.config import job_set, job_get
from app.broker.workers import process_upload

attach_to_logger_names(["app.web.routes"])

router = APIRouter(prefix="", tags=["web"], dependencies=[Depends(get_current_user)])
CurrentUser = Annotated[UserRead, Depends(get_current_user)]
templates = Jinja2Templates(directory="app/web/templates")

@router.get("/", include_in_schema=True)
def index(request: Request, current_user: CurrentUser = None):
    user = UserRead.model_validate(current_user, from_attributes=True)
    context = {"request": request, "q": "", "items": [], "total": 0, "limit": 25, "offset": 0, "current_user": user}
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
    result = search_module.search_documents(db, q=q, ocr_user=ocr_user, ocr_from=ocr_from, ocr_to=ocr_to, limit=limit, offset=offset)
    context = {"request": request, "q": q, "ocr_user": ocr_user, "ocr_from": ocr_from, "ocr_to": ocr_to,
               "items": result.get("items", []), "total": result.get("total", 0), "limit": limit, "offset": offset}
    return templates.TemplateResponse("_results.html", context)

@router.post("/upload", name="upload", include_in_schema=True)
async def upload_file(request: Request, files: List[UploadFile] = File(...), current_user: CurrentUser = None):
    user = UserRead.model_validate(current_user, from_attributes=True)

    # Каталог для оригиналов: <output_originals_dir>/<YYYYMMDDHH>_<login>
    prefix = f"{datetime.now().strftime('%Y%m%d%H')}_{user.email.split('@')[0]}"
    upload_dir = Path(settings.output_originals_dir) / prefix
    upload_dir.mkdir(parents=True, exist_ok=True)

    saved_paths = []
    for f in files:
        filename = f.filename or "uploaded"
        mime = (f.content_type or "").lower() or None
        dst = upload_dir / filename
        with dst.open("wb") as w:
            shutil.copyfileobj(f.file, w)
        saved_paths.append({"path": str(dst), "filename": filename, "mime": mime})

    if not saved_paths:
        return HTMLResponse('<div class="muted">Файлы не были загружены.</div>', status_code=400)

    # Каталог для текстов
    texts_dir = Path(settings.output_texts_dir) / prefix
    texts_dir.mkdir(parents=True, exist_ok=True)

    # Создаём запись задачки в Redis/Memurai
    job_id = uuid.uuid4().hex
    job_set(job_id, {
        "status": "queued",
        "created_at": datetime.utcnow().isoformat(),
        "total": len(saved_paths),
        "done": 0,
        "items": [],
        "error": None,
    })

    # Отправляем в очередь Dramatiq (Memurai/Redis как брокер)
    process_upload.send(job_id, saved_paths, str(texts_dir), user.email)
    return JSONResponse({"job_id": job_id}, status_code=202)

@router.get("/jobs/{job_id}", include_in_schema=False)
def job_status(job_id: str, request: Request):
    job = job_get(job_id)
    if not job:
        return HTMLResponse(f'<div class="text-danger">Задание {job_id} не найдено</div>', status_code=404)

    status = job.get("status")
    if status in ("queued", "running"):
        return templates.TemplateResponse("_job_progress.html", {"request": request, "job": job, "job_id": job_id}, status_code=200)
    if status == "error":
        return HTMLResponse(f'<div class="text-danger">Ошибка: {job.get('error')}</div>', status_code=500)

    # done
    return templates.TemplateResponse("_results.html", {"request": request, "items": job.get("items") or []}, status_code=200)

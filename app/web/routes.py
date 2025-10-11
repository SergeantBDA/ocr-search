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
from app.services.uploads import save_files, enqueue_job
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
    def _parse_dt(val: Optional[str]) -> Optional[datetime]:
        if not val:
            return None
        try:
            # 'YYYY-MM-DDTHH:MM' или 'YYYY-MM-DDTHH:MM:SS'
            return datetime.fromisoformat(val)
        except ValueError:
            return None
    _ocr_from = _parse_dt(ocr_from)
    _ocr_to   = _parse_dt(ocr_from)
    print(f"Поиск: {q}, {ocr_user}, {ocr_from}, {ocr_to}")
    result = search_module.search_documents(db, q=q, ocr_user=ocr_user, ocr_from=_ocr_from, ocr_to=_ocr_to, limit=limit, offset=offset)
    context = {"request": request, "q": q, "ocr_user": ocr_user, "ocr_from": ocr_from, "ocr_to": ocr_to,
               "items": result.get("items", []), "total": result.get("total", 0), "limit": limit, "offset": offset}
    return templates.TemplateResponse("_results.html", context)

@router.post("/upload", name="upload", include_in_schema=True)
async def upload_file(request: Request, files: List[UploadFile] = File(...), current_user: CurrentUser = None):
    user = UserRead.model_validate(current_user, from_attributes=True)
    
    if not files:
        return HTMLResponse('<div class="muted">Файлы не были загружены.</div>', status_code=400)
    
    try:
        # Use shared upload service
        owner_label = user.email.split('@')[0]
        prefix, saved_files, texts_dir, upload_dir = save_files(files, owner_label)
        
        # Enqueue job using shared service
        job_id = enqueue_job(saved_files, texts_dir, user.email)
        
        return templates.TemplateResponse("_job_started.html", {"request": request, "job_id": job_id}, status_code=202)
        
    except Exception as e:
        app_logger.exception("Upload failed: %s", e)
        return HTMLResponse(f'<div class="muted">Ошибка загрузки: {e}</div>', status_code=500)

@router.get("/jobs/{job_id}", include_in_schema=False)
def job_status(request: Request, job_id: str):
    info = job_get(job_id) or {}
    # Прогресс должен быть целым 0..100, без «None» и строк с мусором
    try:
        progress = int(float(info.get("progress", 0)))
    except (TypeError, ValueError):
        progress = 0
    status = info.get("status") or ("done" if progress >= 100 else "started")
    error = info.get("error")
    return templates.TemplateResponse("_job_status.html", {
        "request": request,
        "job_id": job_id,
        "status": status,
        "progress": progress,
        "error": error,
    })

from typing import Optional, Dict, Any
import json
import logging

from fastapi import APIRouter, Request, UploadFile, File, Form, Depends
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.db import get_session, SessionLocal
from app.models import Document
from app.services.ocr_dispatch import extract_text
from app import search as search_module
from app.services import ingest_folder
from app.settings_store import get_documents_dir as store_get_documents_dir

router = APIRouter()
templates = Jinja2Templates(directory="app/web/templates")
logger = logging.getLogger(__name__)


@router.get("/", include_in_schema=True)
def index(request: Request):
    """
    Рендерит главную страницу (index.html) с информацией о текущем каталоге.
    """
    current_dir = store_get_documents_dir()
    context = {
        "request": request,
        "q": "",
        "items": [],
        "total": 0,
        "limit": 25,
        "offset": 0,
        "documents_dir": current_dir,
    }
    return templates.TemplateResponse("index.html", context)


@router.get("/settings", include_in_schema=True)
def settings_panel(request: Request):
    """
    Возвращает partial-шаблон с формой настройки каталога (для HTMX).
    """
    current_dir = store_get_documents_dir()
    context = {"request": request, "documents_dir": current_dir, "message": None}
    return templates.TemplateResponse("_settings.html", context)


@router.post("/settings/documents-dir", name="set_documents_dir", include_in_schema=True)
def set_documents_dir(request: Request, documents_dir: str = Form(...)):
    """
    Устанавливает documents_dir через ingest_folder.set_documents_dir_path и возвращает partial с результатом.
    """
    try:
        ingest_folder.set_documents_dir_path(documents_dir)
        message = f"Каталог сохранён: {documents_dir}"
    except Exception as exc:
        logger.exception("Failed to set documents_dir: %s", exc)
        message = f"Ошибка: {exc}"
    current_dir = store_get_documents_dir()
    context = {"request": request, "documents_dir": current_dir, "message": message}
    return templates.TemplateResponse("_settings.html", context)


@router.get("/search", include_in_schema=True)
def search(
    request: Request,
    q: Optional[str] = "",
    limit: int = 25,
    offset: int = 0,
    db: Session = Depends(get_session),
):
    """
    HTMX: возвращает partial со списком результатов (_results.html).
    """
    q = (q or "").strip()
    result = search_module.search_documents(db, q, limit=limit, offset=offset)
    context = {
        "request": request,
        "q": q,
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
    """
    try:
        report = ingest_folder.scan_folder(db, recursive=True)
    except Exception as exc:
        logger.exception("Scan failed: %s", exc)
        return HTMLResponse(f'<div class="muted">Ошибка запуска сканирования: {exc}</div>', status_code=500)

    # формируем краткий отчёт: успехи/ошибки и последние N документов
    successes = [r for r in report if r.get("status") == "ok"]
    failures = [r for r in report if r.get("status") != "ok"]

    # Получим последние 25 документов для отображения
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


# Оставляем существующий /upload (HTMX будет принимать HTML partial)
@router.post("/upload", name="upload", include_in_schema=True)
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    filename: Optional[str] = Form(None),
    meta: Optional[str] = Form(None),
):
    """
    Обрабатывает загрузку файла (вызывается из HTMX form hx-post), возвращает фрагмент с добавленным документом.
    """
    data = await file.read()
    mime = (file.content_type or "").lower()
    orig_name = file.filename or filename or "uploaded"

    parsed_meta = {}
    if meta:
        try:
            parsed_meta = json.loads(meta)
        except Exception:
            parsed_meta = {"raw": meta}

    try:
        # Сохраняем синхронно как раньше
        text = extract_text(orig_name, data, mime)
        db = SessionLocal()
        try:
            doc = Document(
                filename=(filename or orig_name),
                content=text,
                mime=mime,
                size_bytes=len(data),
                meta=parsed_meta,
            )
            db.add(doc)
            db.commit()
            db.refresh(doc)
            # Возвращаем фрагмент с одним документом (вставляется в начало #results)
            context = {"request": request, "items": [{"id": doc.id, "filename": doc.filename, "snippet": (doc.content or "")[:800]}]}
            return templates.TemplateResponse("_results.html", context, status_code=201)
        finally:
            db.close()
    except Exception as exc:
        logger.exception("Upload processing failed: %s", exc)
        return HTMLResponse(f'<div class="muted">Ошибка при обработке загрузки: {exc}</div>', status_code=500)

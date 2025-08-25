from typing import Optional, List, Dict, Any
import logging

from fastapi import APIRouter, Request, UploadFile, File, Depends
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.db import get_session, SessionLocal
from app.models import Document
from app.services.ocr_dispatch import extract_text
from app import search as search_module
from app.services import ingest_folder
from app.settings_store import get_documents_dir as store_get_documents_dir
from app.services import save_outputs
from app.config import settings

router = APIRouter()
templates = Jinja2Templates(directory="app/web/templates")
logger = logging.getLogger(__name__)


@router.get("/", include_in_schema=True)
def index(request: Request):
    """
    Рендерит главную страницу (index.html) с пустым блоком результатов.
    """
    context = {
        "request": request,
        "q": "",
        "items": [],
        "total": 0,
        "limit": 25,
        "offset": 0,
    }
    return templates.TemplateResponse("index.html", context)


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
    (Остаётся для API/админов — UI выбора каталога отключён в пользу загрузки директорий клиентом)
    """
    try:
        report = ingest_folder.scan_folder(db, recursive=True)
    except Exception as exc:
        logger.exception("Scan failed: %s", exc)
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

@router.post("/upload", name="upload", include_in_schema=True)
async def upload_file(
    request: Request,
    files: List[UploadFile] = File(...),
):
    """
    Обрабатывает загрузку файлов (HTMX form hx-post with multiple files).
    - Берём только UploadFile.filename and UploadFile.content_type
    - extract_text -> (text, meta)
    - meta сохраняется из extract_text
    - сохраняем оригинал/text в папки из settings (необязательно)
    """
    created_items = []

    for upload in files:
        try:
            data = await upload.read()
            orig_name = upload.filename or "uploaded"
            mime = (upload.content_type or "").lower()

            # extract_text returns (text, meta)
            text, meta = extract_text(orig_name, data, mime)

            # Save to DB
            db = SessionLocal()
            try:
                doc = Document(
                    filename=orig_name,
                    content=text,
                    mime=mime,
                    size_bytes=len(data),
                    meta=meta or {},
                )
                db.add(doc)
                db.commit()
                db.refresh(doc)
                created_items.append({"id": doc.id, "filename": doc.filename, "snippet": (doc.content or "")[:800]})
            finally:
                db.close()

            # Save outputs if configured (errors logged but do not break processing)
            try:
                if settings.output_originals_dir:
                    save_outputs.save_original(orig_name, data, settings.output_originals_dir)
            except Exception as e:
                logger.exception("Failed to save original for %s: %s", orig_name, e)

            try:
                if settings.output_texts_dir:
                    save_outputs.save_text(orig_name, text or "", settings.output_texts_dir)
            except Exception as e:
                logger.exception("Failed to save text for %s: %s", orig_name, e)

        except Exception as exc:
            logger.exception("Upload processing failed for %s: %s", getattr(upload, "filename", "<unknown>"), exc)
            return HTMLResponse(f'<div class="muted">Ошибка при обработке файла {getattr(upload, "filename", "")}: {exc}</div>', status_code=500)

    if created_items:
        context = {"request": request, "items": created_items}
        return templates.TemplateResponse("_results.html", context, status_code=201)

    return HTMLResponse('<div class="muted">Файлы не были загружены.</div>', status_code=400)
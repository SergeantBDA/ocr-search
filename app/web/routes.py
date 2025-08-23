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

router = APIRouter()
templates = Jinja2Templates(directory="app/web/templates")
logger = logging.getLogger(__name__)


def _save_document_sync(
    data: bytes,
    original_filename: str,
    stored_filename: Optional[str],
    mime: Optional[str],
    meta: Optional[Dict[str, Any]],
) -> Document:
    """
    Синхронно выполняет OCR и сохраняет документ в БД, возвращает сохранённый объект Document.
    """
    text = extract_text(original_filename, data, mime)
    db: Session = SessionLocal()
    try:
        doc = Document(
            filename=(stored_filename or original_filename),
            content=text,
            mime=mime,
            size_bytes=len(data),
            meta=meta or {},
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
        return doc
    finally:
        db.close()


@router.get("/", include_in_schema=True)
def index(request: Request):
    """
    Рендерит главную страницу (index.html) с пустым блоком результатов.
    """
    context = {"request": request, "q": "", "items": [], "total": 0, "limit": 25, "offset": 0}
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
    Возвращает partial-шаблон с результатами поиска (только блок items).
    Поддерживает HTMX: вызывается hx-get и обновляет div#results.
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
    return templates.TemplateResponse("_results.html", context, status_code=200)


@router.post("/upload", name="upload", include_in_schema=True)
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    filename: Optional[str] = Form(None),
    meta: Optional[str] = Form(None),
):
    """
    Синхронная обработка загруженного файла: выполняем OCR, сохраняем в БД и
    возвращаем partial-шаблон с обновлённым списком документов.
    Возвращаем HTML, чтобы HTMX вставил блок в div#results (hx-swap="afterbegin").
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
        # Сохраняем документ синхронно
        _save_document_sync(data, orig_name, filename, mime, parsed_meta)
    except Exception as exc:
        logger.exception("Failed to process uploaded file: %s", exc)
        # Вернём сообщение об ошибке как HTML фрагмент
        return HTMLResponse(f'<div class="muted">Ошибка при обработке файла: {exc}</div>', status_code=500)

    # После сохранения вернём актуальный список — используем короткий список последних документов
    db: Session = SessionLocal()
    try:
        # Получаем последние 25 документов для отображения (пустой q => последние)
        res = search_module.search_documents(db, "", limit=25, offset=0)
        context = {"request": request, "items": res.get("items", []), "total": res.get("total", 0)}
        # Возвращаем partial (_results.html) — HTMX вставит его в #results
        return templates.TemplateResponse("_results.html", context, status_code=200)
    finally:
        db.close()

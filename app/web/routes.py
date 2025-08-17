from typing import Optional, Dict, Any
import json
import logging
from io import BytesIO

from fastapi import APIRouter, Request, UploadFile, File, Form, BackgroundTasks, Depends, HTTPException
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db import get_session, SessionLocal
from app.models import Document
from app.services.ocr_dispatch import extract_text
from app import search as search_module

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
logger = logging.getLogger(__name__)


def _save_document_to_db_bytes(
    data: bytes,
    original_filename: str,
    stored_filename: Optional[str],
    mime: Optional[str],
    meta: Optional[Dict[str, Any]],
) -> None:
    """
    Background worker: выполняет OCR (через extract_text) и сохраняет результат в БД.
    Создаём собственный SessionLocal, т.к. исходный Session может быть закрыт.
    """
    try:
        # Получаем текст (может быть тяжёлой операцией)
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
        finally:
            db.close()
    except Exception as exc:
        logger.exception("Background processing failed for %s: %s", original_filename, exc)


@router.get("/", include_in_schema=True)
def index(request: Request):
    """
    Рендерит главную страницу (index.html). По умолчанию без результатов.
    """
    context = {"request": request, "q": "", "items": [], "total": 0, "limit": 25, "offset": 0}
    return templates.TemplateResponse("index.html", context)


@router.get("/search", include_in_schema=True)
def search(request: Request, q: Optional[str] = "", limit: int = 25, offset: int = 0, db: Session = Depends(get_session)):
    """
    Поиск документов. Использует app.search.search_documents и рендерит results.html.
    Если results.html отсутствует, можно изменить на index.html.
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
    # Рендерим results.html как просил пользователь; при необходимости заменить на index.html
    return templates.TemplateResponse("results.html", context)


@router.post("/upload", name="upload", include_in_schema=True)
async def upload_file(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    filename: Optional[str] = Form(None),
    meta: Optional[str] = Form(None),
):
    """
    Загрузка файла: читаем байты и ставим BackgroundTask, который выполнит OCR и сохранит Document.
    Возвращаем 202 Accepted сразу.
    """
    data = await file.read()
    mime = (file.content_type or "").lower()
    orig_name = file.filename or filename or "uploaded"

    parsed_meta = {}
    if meta:
        try:
            parsed_meta = json.loads(meta)
        except Exception:
            # Если не JSON — просто сохраним как строка в поле meta
            parsed_meta = {"raw": meta}

    # Планируем фоновые задачи: выполняют OCR и сохраняют документ
    background_tasks.add_task(_save_document_to_db_bytes, data, orig_name, filename, mime, parsed_meta)

    return JSONResponse({"status": "accepted", "filename": orig_name}, status_code=202)

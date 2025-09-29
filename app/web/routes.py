import asyncio
import logging
from urllib.parse import quote
from typing import Optional, List, Dict, Annotated, Any
from pathlib import Path
from datetime import datetime

from fastapi import APIRouter, Request, UploadFile, File, Depends
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app import search as search_module
from app.db import get_session, SessionLocal
from app.models import Document, User
from app.schemas import UserRead
from app.services.ocr_dispatch import extract_text
from app.services import ingest_folder, save_outputs
from app.settings_store import get_documents_dir as store_get_documents_dir
from app.config import settings
from app.logger import logger as app_logger, attach_to_logger_names
from app.services import bytes_xtractor as bx

from concurrent.futures import ThreadPoolExecutor

attach_to_logger_names(["app.service.bytes_xtractor","app.services.ingest_folder", "app.search", "app.services.ocr_dispatch", "app.services.save_outputs"])

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

@router.post("/upload", name="upload", include_in_schema=True)
async def upload_file(
    request: Request,
    files: List[UploadFile] = File(...),
    current_user: CurrentUser = None,
):
    """
    Обрабатывает загрузку файлов (HTMX form hx-post with multiple files).
    - Берём только UploadFile.filename and UploadFile.content_type
    - extract_text -> (text, meta)
    - meta сохраняется из extract_text
    - сохраняем оригинал/text в папки из settings (необязательно)
    """
    created_items = []
    user = UserRead.model_validate(current_user, from_attributes=True)
    _prefix_dir = f'{datetime.now().strftime('%Y%m%d%H')}_{user.email.split('@')[0]}'
    _output_originals_dir = f'{settings.output_originals_dir}/{_prefix_dir}'
    _output_texts_dir     = f'{settings.output_texts_dir}/{_prefix_dir}'

    # 1) асинхронно считываем все файлы -> получаем bytes
    payloads: list[tuple[str | None, str | None, bytes]] = []
    for f in files:
        _data = await f.read()                      # ВАЖНО: тут await!
        _filename = f.filename or "uploaded"
        _mime = (f.content_type or "").lower() or None
        payloads.append((_filename, _mime, _data))

    # 2) синхронная функция для пула
    def run_sync(args: tuple[str | None, str | None, bytes]):
        _filename, _mime, _data = args
        _text = bx.extract_text_bytes(_data, filename=_filename, mime=_mime)
        return _filename, _mime, _data, _text

    # 3) параллельно обрабатываем bytes
    max_workers = 4 #settings.max_workers or 4
    with ThreadPoolExecutor(max_workers=max_workers) as tp:
        for orig_name, mime, data, text in tp.map(run_sync, payloads):
            try:
                # Save outputs if configured (errors logged but do not break processing)
                path_origin = ""
                try:
                    if settings.output_originals_dir:
                        path_origin = save_outputs.save_original(orig_name, data, _output_originals_dir)
                        path_origin = Path( *(settings.hostfs, *path_origin.parts[1:]) )
                except Exception as e:
                    app_logger.exception("Failed to save original for %s: %s", orig_name, e)

                try:
                    if settings.output_texts_dir:
                        save_outputs.save_text(orig_name, text or "", _output_texts_dir)
                except Exception as e:
                    app_logger.exception("Failed to save text for %s: %s", orig_name, e)

                # Save to DB
                db = SessionLocal()
                try:
                    doc = Document(
                        filename=orig_name,
                        content=text,
                        mime=mime,
                        size_bytes=len(data),
                        meta={},
                        path_origin=str(path_origin),
                        email=user.email
                    )
                    db.add(doc)
                    db.commit()
                    db.refresh(doc)
                    created_items.append({"id": doc.id, 
                                        "filename": doc.filename, 
                                        "link": f'http://{settings.httpfs}/{doc.path_origin.replace("\\", "/")}' if settings.httpfs and doc.path_origin else None, 
                                        "snippet": (doc.content or "")[:800]})
                finally:
                    db.close()

            except Exception as exc:
                #app_logger.exception("Upload processing failed for %s: %s", getattr(upload, "filename", "<unknown>"), exc)
                app_logger.exception("Upload processing failed for %s", exc)
                return HTMLResponse(f'<div class="muted">Ошибка при обработке файлов: {exc}</div>', status_code=500)

    if created_items:
        context = {"request": request, "items": created_items}
        return templates.TemplateResponse("_results.html", context, status_code=201)

    return HTMLResponse('<div class="muted">Файлы не были загружены.</div>', status_code=400)

from __future__ import annotations

from pathlib import Path
from datetime import datetime
from typing import Sequence

import dramatiq

from app.broker.config import redis_broker, result_backend, job_update, job_set
from app.config import settings
from app.logger import logger as app_logger, attach_to_logger_names
from app.services import bytes_xtractor as bx
from app.services import save_outputs
from app.db import SessionLocal
from app.models import Document

attach_to_logger_names(["app.broker.workers"])

@dramatiq.actor(queue_name="upload", max_retries=0, store_results=True)
def process_upload(job_id: str, files: list[dict], texts_dir: str, user_email: str) -> dict:
    """
    Актёр обработки загрузки:
      - OCR/извлечение текста
      - сохранение текстов на диск
      - запись в БД
      - обновление статуса в Redis (Memurai)
    Возвращает короткий отчёт.
    """
    app_logger.info("process_upload START job_id=%s files=%d texts_dir=%s", job_id, len(files), texts_dir)

    # Инициализируем статус
    job_set(job_id, {
        "status": "running",
        "created_at": datetime.utcnow().isoformat(),
        "total": len(files),
        "done": 0,
        "items": [],
        "error": None,
    })

    done = 0
    items: list[dict] = []

    for f in files:
        path = f["path"]
        filename = f["filename"]
        mime = f.get("mime")
        app_logger.info("process_upload file=%s mime=%s", path, mime)
        try:
            text = bx.extract_text_file(path, filename=filename, mime=mime) or ""

            # сохранить текстовый файл (best-effort)
            try:
                save_outputs.save_text(filename, text, Path(texts_dir))
            except Exception as e:
                app_logger.exception("save_text failed for %s: %s", filename, e)

            # сохранить в БД
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

                link = f"http://{settings.httpfs}/{doc.path_origin.replace('\\', '/')}" if settings.httpfs and doc.path_origin else None
                items.append({
                    "id": doc.id,
                    "filename": doc.filename,
                    "link": link,
                    "snippet": (doc.content or "")[:100]
                })
            finally:
                db.close()

            done += 1
            # обновляем прогресс
            job_update(job_id, done=done, items=items)
        except Exception as exc:
            app_logger.exception("process_upload failed for %s: %s", filename, exc)
            job_update(job_id, status="error", error=str(exc))
            return {"ok": False, "error": str(exc), "processed": done, "items": items}

    job_update(job_id, status="done", done=done, items=items)
    app_logger.info("process_upload DONE job_id=%s", job_id)
    return {"ok": True, "processed": done, "items": items}

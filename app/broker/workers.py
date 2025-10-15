# app/broker/workers.py
from __future__ import annotations

import os
os.environ["RUN_CONTEXT"] = "worker"   # <-- важно: до импортов extractors!

from pathlib import Path
from datetime import datetime

import dramatiq

from app.broker.config import redis_broker, result_backend, job_update, job_set
from app.config import settings
from app.services import bytes_xtractor as bx
from app.services import save_outputs
from app.db import SessionLocal
from app.models import Document

from app.logger_worker import worker_log

@dramatiq.actor(queue_name="upload", max_retries=0, store_results=True)
def process_upload(job_id: str, files: list[dict], texts_dir: str, user_email: str) -> dict:
    """
    Обработка загруженных файлов:
      - OCR/извлечение текста
      - сохранение текстов на диск (best-effort)
      - запись документа в БД
      - обновление статуса/прогресса в сторе (Redis/Memurai)

    Параметры:
      job_id: идентификатор задания (str)
      files: список словарей {'path': str, 'filename': str, 'mime': Optional[str]}
      texts_dir: каталог для сохранения извлечённых текстов
      user_email: email пользователя (для записи в БД)

    Возвращает краткий отчёт для result backend.
    """
    total = max(1, len(files))
    worker_log.info(
        "process_upload START job_id=%s files=%d texts_dir=%s",
        job_id, len(files), texts_dir
    )

    # Инициализируем статус задания — прогресс в процентах
    job_set(job_id, {
        "status": "started",
        "created_at": datetime.utcnow().isoformat(),
        "total": len(files),
        "done": 0,
        "progress": 0,
        "items": [],
        "error": None,
    })

    done = 0
    items: list[dict] = []

    for f in files:
        # перед началом тяжёлой работы проверяем, не нажали ли “Прервать”
        if r.get(f"{NS}:job-cancel:{job_id}"):
            job_update(job_id, status="aborted")
            worker_log.info("process_upload ABORTED job_id=%s", job_id)
            return {"ok": False, "processed": done, "progress": int(done*100/max(1,len(files))), "items": items} 
            
        path = f["path"]
        filename = f["filename"]
        mime = f.get("mime")
        worker_log.info("process_upload file=%s mime=%s", path, mime)

        try:
            # 1) OCR
            print(path)
            text = bx.extract_text_file(path, filename=filename, mime=mime) or ""

            # 2) Сохранить извлечённый текст (best-effort)
            try:
                save_outputs.save_text(filename, text, Path(texts_dir))
            except Exception as e:
                worker_log.exception("save_text failed for %s: %s", filename, e)

            # 3) Записать документ в БД
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

                link = (
                    f"http://{settings.httpfs}/{doc.path_origin.replace('\\', '/')}"
                    if settings.httpfs and doc.path_origin else None
                )
                items.append({
                    "id": doc.id,
                    "filename": doc.filename,
                    "link": link,
                    "snippet": (doc.content or "")[:100],
                })
            finally:
                db.close()

            # 4) Обновить прогресс
            done += 1
            pct = int(done * 100 / total)
            job_update(job_id, status="started", done=done, progress=pct, items=items)

        except Exception as exc:
            # Ошибка на конкретном файле — фиксируем и завершаем задание как failed
            worker_log.exception("process_upload failed for %s: %s", filename, exc)
            pct = int(done * 100 / total)
            job_update(job_id, status="failed", done=done, progress=pct, error=str(exc), items=items)
            return {"ok": False, "error": str(exc), "processed": done, "progress": pct, "items": items}

    # Финальное обновление: 100%
    job_update(job_id, status="done", done=done, progress=100, items=items)
    worker_log.info("process_upload DONE job_id=%s", job_id)
    return {"ok": True, "processed": done, "progress": 100, "items": items}

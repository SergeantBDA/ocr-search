from typing import List, Dict, Any, Tuple
import uuid
import shutil
from pathlib import Path
from datetime import datetime

from fastapi import UploadFile

from app.config import settings
from app.broker.config import job_set, job_get
from app.broker.workers import process_upload


def save_files(
    files: List[UploadFile], 
    owner_label: str
) -> Tuple[str, List[Dict[str, Any]], Path, Path]:
    """
    Save uploaded files to originals directory and prepare texts directory.
    
    Returns:
        tuple: (prefix, saved_files_metadata, texts_dir, upload_dir)
    """
    if not settings.output_originals_dir:
        raise ValueError("OUTPUT_ORIGINALS_DIR not configured")
    
    if not settings.output_texts_dir:
        raise ValueError("OUTPUT_TEXTS_DIR not configured")
    
    # Create prefix with timestamp and owner
    prefix = f"{datetime.now().strftime('%Y%m%d%H')}_{owner_label}"
    upload_dir = Path(settings.output_originals_dir) / prefix
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    texts_dir = Path(settings.output_texts_dir) / prefix
    texts_dir.mkdir(parents=True, exist_ok=True)
    
    saved_files = []
    for f in files:
        if not f.filename:
            continue
            
        filename = f.filename
        mime = (f.content_type or "").lower() or None
        dst = upload_dir / filename
        
        # Save file
        with dst.open("wb") as w:
            shutil.copyfileobj(f.file, w)
        
        saved_files.append({
            "path": str(dst),
            "filename": filename,
            "mime": mime
        })
    
    return prefix, saved_files, texts_dir, upload_dir


def enqueue_job(
    saved_paths: List[Dict[str, Any]], 
    texts_dir: Path, 
    owner_email: str
) -> str:
    """
    Create job entry in Redis/Memurai and enqueue processing task.
    Includes full payload to allow 'retry' functionality later.
    
    Returns:
        str: job_id
    """
    job_id = uuid.uuid4().hex

    # Формируем полезную нагрузку (payload) для возможного повтора
    payload = {
        "files": saved_paths,          # [{'path':..., 'filename':..., 'mime':...}, ...]
        "texts_dir": str(texts_dir),
        "user_email": owner_email,
    }

    # Сохраняем всё в Redis (для статуса + payload)
    job_set(job_id, {
        "status": "queued",
        "created_at": datetime.utcnow().isoformat(),
        "total": len(saved_paths),
        "done": 0,
        "progress": 0,
        "items": [],
        "error": None,
        "payload": payload,             # 🟢 добавляем сюда весь контекст задачи
    })

    # Отправляем задачу в Dramatiq
    process_upload.send(job_id, saved_paths, str(texts_dir), owner_email)

    return job_id



def get_job_status(job_id: str) -> Dict[str, Any]:
    """
    Get job status from Redis/Memurai storage.
    
    Returns:
        dict: {"job_id", "status", "progress", "error", "total", "done"}
    """
    info = job_get(job_id) or {}
    
    # Ensure progress is valid integer 0-100
    try:
        progress = int(float(info.get("progress", 0)))
        progress = max(0, min(100, progress))
    except (TypeError, ValueError):
        progress = 0
    
    # Determine status
    status = info.get("status", "unknown")
    if progress >= 100 and status not in ["error", "failed"]:
        status = "completed"
    elif status == "queued" and progress > 0:
        status = "processing"
    
    return {
        "job_id": job_id,
        "status": status,
        "progress": progress,
        "total": info.get("total", 0),
        "done": info.get("done", 0),
        "error": info.get("error"),
        "created_at": info.get("created_at"),
    }
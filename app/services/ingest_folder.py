from pathlib import Path
from typing import Optional, Set, List, Dict, Any
import mimetypes
import os

from sqlalchemy.orm import Session

from app.settings_store import set_documents_dir, get_documents_dir
from app.services.ocr_dispatch import extract_text
from app.models import Document


def set_documents_dir_path(path: str) -> None:
    """
    Нормализует путь, проверяет существование и права на чтение, затем сохраняет в settings_store.
    """
    p = Path(path).expanduser()
    if not p.exists():
        raise FileNotFoundError(f"Path does not exist: {p}")
    if not p.is_dir():
        raise NotADirectoryError(f"Not a directory: {p}")
    if not os.access(str(p), os.R_OK):
        raise PermissionError(f"Directory is not readable: {p}")
    # сохраняем как строку
    set_documents_dir(str(p.resolve()))


def get_documents_dir_path() -> Optional[str]:
    return get_documents_dir()


def _is_temp_or_hidden(p: Path) -> bool:
    name = p.name
    return name.startswith(".") or name.startswith("~$") or name.endswith(".tmp") or name.endswith(".TMP")


def scan_folder(
    session: Session,
    *,
    recursive: bool = True,
    allowed_ext: Optional[Set[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Обходит каталог documents_dir и загружает найденные файлы в БД.
    Возвращает список словарей с результатами для каждого файла:
      {"path": str, "status": "ok"|"error", "id": int|None, "error": <message>|None}
    session: SQLAlchemy Session (передаётся извне).
    """
    if allowed_ext is None:
        allowed_ext = {".pdf", ".png", ".jpg", ".jpeg", ".docx", ".xlsx"}

    base = get_documents_dir()
    if not base:
        raise ValueError("Documents directory is not configured")

    base_path = Path(base)
    if not base_path.exists() or not base_path.is_dir():
        raise FileNotFoundError(f"Documents directory not found: {base_path}")

    results: List[Dict[str, Any]] = []

    pattern = "**/*" if recursive else "*"
    for p in base_path.glob(pattern):
        try:
            if not p.is_file():
                continue
            if _is_temp_or_hidden(p):
                continue
            if p.suffix.lower() not in allowed_ext:
                continue

            try:
                # читаем содержимое — безопасно для небольших файлов
                data = p.read_bytes()
            except MemoryError as me:
                results.append({"path": str(p), "status": "error", "id": None, "error": "MemoryError reading file"})
                continue
            except Exception as e:
                results.append({"path": str(p), "status": "error", "id": None, "error": f"IO error: {e}"})
                continue

            mime, _ = mimetypes.guess_type(str(p))
            try:
                text, meta = extract_text(p.name, data, mime)
            except Exception as e:
                # OCR error — record and continue
                results.append({"path": str(p), "status": "error", "id": None, "error": f"OCR error: {e}"})
                continue

            # сохраняем в БД (каждый файл в своей транзакции)
            try:
                doc = Document(
                    filename=p.name,
                    content=text,
                    mime=mime or "",
                    size_bytes=len(data),
                    meta=meta or {"source_path": str(p)},
                )
                session.add(doc)
                session.commit()
                session.refresh(doc)
                results.append({"path": str(p), "status": "ok", "id": doc.id, "error": None})
            except Exception as e:
                try:
                    session.rollback()
                except Exception:
                    pass
                results.append({"path": str(p), "status": "error", "id": None, "error": f"DB error: {e}"})
        except Exception as e:
            results.append({"path": str(p), "status": "error", "id": None, "error": f"Unhandled error: {e}"})

    return results

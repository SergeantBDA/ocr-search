from pathlib import Path
from typing import Optional, Set, List, Dict, Any
import mimetypes
import os

from sqlalchemy.orm import Session

from app.settings_store import set_documents_dir, get_documents_dir
from app.services.ocr_dispatch import extract_text
from app.models import Document
from app.services import save_outputs
from app.config import settings


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
    После успешной обработки сохраняет оригиналы и тексты в выходные папки (если настроены).
    Возвращает список результатов для каждого файла.
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
                data = p.read_bytes()
            except MemoryError:
                results.append({"path": str(p), "status": "error", "id": None, "error": "MemoryError reading file"})
                continue
            except Exception as e:
                results.append({"path": str(p), "status": "error", "id": None, "error": f"IO error: {e}"})
                continue

            mime, _ = mimetypes.guess_type(str(p))
            try:
                text, meta = extract_text(p.name, data, mime)
            except Exception as e:
                results.append({"path": str(p), "status": "error", "id": None, "error": f"OCR error: {e}"})
                continue

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
                continue

            # Save outputs if configured: try to preserve relative path under base (preferred)
            try:
                if settings.output_originals_dir:
                    # destination dir may include subfolders as relative path
                    try:
                        rel = p.relative_to(base_path)
                        dst_dir = Path(settings.output_originals_dir) / rel.parent
                    except Exception:
                        dst_dir = Path(settings.output_originals_dir)
                    save_outputs.save_original(p.name, data, dst_dir)
            except Exception as e:
                logger.exception("Failed to save original for %s: %s", p, e)

            try:
                if settings.output_texts_dir:
                    try:
                        rel = p.relative_to(base_path)
                        dst_dir = Path(settings.output_texts_dir) / rel.parent
                    except Exception:
                        dst_dir = Path(settings.output_texts_dir)
                    save_outputs.save_text(p.name, text or "", dst_dir)
            except Exception as e:
                logger.exception("Failed to save text for %s: %s", p, e)

        except Exception as e:
            results.append({"path": str(p), "status": "error", "id": None, "error": f"Unhandled error: {e}"})

    return results
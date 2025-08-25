from __future__ import annotations
import re
import unicodedata
from pathlib import Path
from typing import Union
import logging

logger = logging.getLogger(__name__)

INVALID_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_filename(name: str, max_len: int = 255) -> str:
    """
    Normalize filename: remove invalid Windows chars, collapse spaces, normalize unicode,
    and trim to max_len.
    """
    if not name:
        return "file"
    # Normalize unicode
    name = unicodedata.normalize("NFKC", name)
    # Remove path components
    name = Path(name).name
    # Remove invalid characters
    name = INVALID_CHARS_RE.sub("_", name)
    # Collapse repeated dots and spaces
    name = re.sub(r"\s+", " ", name).strip()
    # Trim length, preserve suffix if exists
    if len(name) <= max_len:
        return name
    # try to keep extension
    stem = Path(name).stem
    suffix = Path(name).suffix
    keep = max_len - len(suffix)
    stem = stem[:max(1, keep)]
    return f"{stem}{suffix}"


def ensure_dir(path: Union[str, Path]) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _unique_path(dst: Path) -> Path:
    """
    If dst exists, add suffix _1, _2 ... before extension.
    """
    if not dst.exists():
        return dst
    parent = dst.parent
    stem = dst.stem
    suffix = dst.suffix
    i = 1
    while True:
        candidate = parent / f"{stem}_{i}{suffix}"
        if not candidate.exists():
            return candidate
        i += 1


def save_original(filename: str, data: bytes, dst_dir: Union[str, Path]) -> Path:
    """
    Save binary original file into dst_dir with safe filename.
    Do not overwrite existing file; add suffix _1, _2... if needed.
    Returns Path to saved file.
    """
    dst_root = ensure_dir(dst_dir)
    safe_name = safe_filename(filename)
    dst = dst_root / safe_name
    dst = _unique_path(dst)
    # write in binary mode
    try:
        with open(dst, "wb") as fh:
            fh.write(data)
    except Exception:
        logger.exception("Failed to save original file %s to %s", filename, dst)
        raise
    return dst


def save_text(filename: str, text: str, dst_dir: Union[str, Path]) -> Path:
    """
    Save extracted text as .txt file into dst_dir using same base name.
    For example: report.pdf -> report.txt
    No overwrite: add suffixes if needed.
    """
    dst_root = ensure_dir(dst_dir)
    txt_name = Path(safe_filename(filename))
    
    dst = dst_root / txt_name
    dst = _unique_path(dst)
    try:
        with open(dst, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text or "")
    except Exception:
        logger.exception("Failed to save text for %s to %s", filename, dst)
        raise
    return dst
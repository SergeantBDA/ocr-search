# bytes_xtractor.py
"""
Извлечение текста из файлов, переданных как bytes.
Учитывает ориентацию страниц при OCR (pytesseract.image_to_osd).

Приоритет стратегии: MIME (если передан) → mimetypes по filename → расширение → plain text.

Опциональные зависимости:
- PyMuPDF (fitz)                 — PDF (текстовый слой + OCR-фоллбек)
- pytesseract + Tesseract OCR    — OCR (изображения, PDF-фоллбек)
- Pillow (PIL)                   — изображения для OCR
- python-docx                    — DOCX
- pandas + openpyxl/xlrd         — Excel
- beautifulsoup4 + lxml          — HTML/XML
- striprtf                       — RTF
"""

from __future__ import annotations
import re
import io
import logging
import mimetypes
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Dict, Type



# ------------------------- logging --------------------------------------
from app.logger import logger as app_logger, attach_to_logger_names
attach_to_logger_names(["app.services.bytes_xtractor2"])
# ----------------------- helpers ----------------------------------------
RUSSIAN_CHARS = set(r".:,-+=()!0123456789абвгдеёжзийклмнопрстуфхцчшщъыьэюяАБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ")



def _guess_ext(filename: Optional[str], mime: Optional[str]) -> str:
    name = (filename or "").lower()
    if name.endswith(".pdf") or mime == "application/pdf":
        return "pdf"
    if any(name.endswith(x) for x in (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp")) or (
        mime and mime.startswith("image/")
    ):
        return "image"
    if name.endswith(".docx") or mime in {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"}:
        return "docx"
    if name.endswith(".xlsx") or mime in {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}:
        return "xlsx"
    return "txt"

# -------------------------- concrete extractors -------------------------


class UnsupportedExtractor(BytesExtractor):
    def extract_text(self) -> str:
        app_logger.info("Неподдерживаемый тип: %s / %s",
                    self.payload.mime, self.payload.filename)
        return ""

# --------------------------- factory ------------------------------------

_MIME_MAP: Dict[str, Type[BytesExtractor]] = {
    "application/pdf": PDFExtractor,
    "image/png": ImageExtractor,
    "image/jpeg": ImageExtractor,
    "image/bmp": ImageExtractor,
    "image/gif": ImageExtractor,
    "text/html": HTMLExtractor,
    "application/xhtml+xml": HTMLExtractor,
    "text/xml": XMLExtractor,
    "application/xml": XMLExtractor,
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": DOCXExtractor,
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ExcelExtractor,
    "text/plain": PlainTextExtractor,
    "message/rfc822": EMLExtractor,
}

_EXT_MAP: Dict[str, Type[BytesExtractor]] = {
    "pdf": PDFExtractor,
    "png": ImageExtractor,
    "jpg": ImageExtractor,
    "jpeg": ImageExtractor,
    "bmp": ImageExtractor,
    "gif": ImageExtractor,
    "html": HTMLExtractor,
    "htm": HTMLExtractor,
    "xml": XMLExtractor,
    "docx": DOCXExtractor,
    "xlsx": ExcelExtractor,
    "xls": ExcelExtractor,
    "xlsm": ExcelExtractor,
    "rtf": RTFExtractor,
    "txt": PlainTextExtractor,
    "eml": EMLExtractor,
}

def get_extractor(payload: BytesPayload, *, ocr_lang: str = "rus+eng") -> BytesExtractor:
    """
    Выбор экстрактора:
      1) MIME из payload.mime,
      2) MIME по mimetypes.guess_type(filename),
      3) расширение из filename,
      4) fallback: UnsupportedExtractor.
    """
    mime = normalized_mime(payload.mime) or normalized_mime(_guess_mime_from_name(payload.filename))
    if mime and mime in _MIME_MAP:
        return _MIME_MAP[mime](payload, ocr_lang=ocr_lang)

    ext = ext_from_filename(payload.filename)
    if ext and ext in _EXT_MAP:
        return _EXT_MAP[ext](payload, ocr_lang=ocr_lang)

    return UnsupportedExtractor(payload, ocr_lang=ocr_lang)

# --------------------------- public API ----------------------------------

def extract_text_bytes(
    content: bytes,
    filename: Optional[str] = None,
    mime: Optional[str] = None,
    *,
    ocr_lang: str = "rus+eng",
) -> str:
    """
    Удобная функция «в один вызов». Потокобезопасна.

    Пример с ThreadPoolExecutor:

        with ThreadPoolExecutor(max_workers=4) as tp:
            futs = [tp.submit(extract_text_bytes, b, name, mime) for (b,name,mime) in items]
            results = [f.result() for f in futs]
    """
    payload = BytesPayload(content=content, filename=filename, mime=mime)
    extractor = get_extractor(payload, ocr_lang=ocr_lang)
    return extractor.extract_text()

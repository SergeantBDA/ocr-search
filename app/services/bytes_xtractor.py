from __future__ import annotations
#import logging
import re
from pathlib import Path
from typing import Optional, Type
 
from .extractors import (
    BytesPayload, BytesExtractor,
    DOCXExtractor, EMLMSGExtractor, HTMLExtractor, 
    PDFExtractor, PDFExtractorFast, ImageExtractor, RTFExtractor, 
    PlainTextExtractor, UnsupportedExtractor, ExcelExtractor,
)

from app.logger import logger as app_logger, attach_to_logger_names
attach_to_logger_names(["app.services.extractors.byte_xtractor"])

_ws_re        = re.compile(r"[ \t\u00A0]+")
_hyphen_re    = re.compile(r"(\w)-\s*\n(\w)")
_single_nl_re = re.compile(r"(?<!\n)\n(?!\n)")   # одиночный \n, не часть \n\n
_multi_nl_re  = re.compile(r"\n{3,}")            # 3+ переводов → 2
_ctrl_re      = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F]")

def _preprocess_text_layer(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _hyphen_re.sub(r"\1\2", text)        # убираем переносы по дефису
    text = _single_nl_re.sub(" ", text)         # одиночный \n превращаем в пробел
    text = _ws_re.sub(" ", text)                # сжимаем пробелы (вкл. NBSP)
    text = _multi_nl_re.sub("\n", text)         # абзацы нормализуем к \n
    text = _ctrl_re.sub("", text)               # убрать NUL и «плохие» управляющие
    text = text.replace("\u0000", "")           # на всякий случай явно
    # нормализация юникода – снижает «мусор» из PDF
    try:
        text = unicodedata.normalize("NFC", text)
    except Exception:
        pass

    return text.strip()

def normalized_mime(mime: Optional[str]) -> Optional[str]:
    return mime.lower().strip() if mime else None

def ext_from_filename(filename: Optional[str]) -> Optional[str]:
    if not filename or "." not in filename:
        return None
    return filename.rsplit(".", 1)[-1].lower()

# --------- распознавание типа (расширение/ MIME) ---------
def _guess_ext(filename: Optional[str], mime: Optional[str]) -> str:
    name = ext_from_filename(filename)
    mime = normalized_mime(mime)

    if name.endswith("docx") or mime == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        return "docx"
    if name.endswith(("eml","msg")) or mime in {"message/rfc822","application/eml"}:
        return "email"
    if name.endswith(("htm","html","xhtml","xml")) or mime in {"text/html","application/xhtml+xml"}:
        return "html"
    if name.endswith("pdf") or mime == "application/pdf":
        return "pdf"
    if any(name.endswith(x) for x in ("png","jpg","jpeg","tif","tiff","bmp")) or mime in {"image/"}:
        return "image"
    if name.endswith("rtf") or mime in {"application/rtf", "text/rtf"}:
        return "rtf"           
    if name.endswith(("txt","csv")) or mime in {"text"}:
        return "txt"
    if name.endswith(("xlsx","xls")) or mime == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":
        return "xls"
    return 'uns'
 
# --------- реестр экстракторов ---------
EXTRACTOR_BY_KIND: dict[str, Type[BytesExtractor]] = {
    "docx": DOCXExtractor,
    "email": EMLMSGExtractor,
    "html": HTMLExtractor,
    "pdf": PDFExtractorFast,
    "image": ImageExtractor,
    "rtf":RTFExtractor,
    "txt": PlainTextExtractor,
    "uns": UnsupportedExtractor,
    "xls": ExcelExtractor,
}
 
def get_extractor(payload: BytesPayload, *, ocr_lang: str = "rus+eng") -> BytesExtractor:
    kind = _guess_ext(payload.filename, payload.mime)
    cls = EXTRACTOR_BY_KIND[kind]
    return cls(payload, ocr_lang=ocr_lang)
 
# --------- публичный API ---------
def extract_text_bytes(
    content: bytes,
    filename: Optional[str] = None,
    mime: Optional[str] = None,
    *,
    ocr_lang: str = "rus+eng",
) -> str:
    payload = BytesPayload(content=content, path=None, filename=filename, mime=mime)
    return get_extractor(payload, ocr_lang=ocr_lang).extract_text()
 
def extract_text_file(
    path: str,
    filename: Optional[str] = None,
    mime: Optional[str] = None,
    *,
    ocr_lang: str = "rus+eng",
) -> str:
    payload = BytesPayload(content=None, path=path, filename=filename or Path(path).name, mime=mime)
    return _preprocess_text_layer( get_extractor(payload, ocr_lang=ocr_lang).extract_text() )

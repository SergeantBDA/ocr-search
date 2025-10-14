from __future__ import annotations
from pathlib import Path 
from .base import BytesExtractor
import logging
# ------------------------- logging --------------------------------------
from app.logger_worker import worker_log as app_logger
 
class PlainTextExtractor(BytesExtractor):
    def extract_text(self) -> str:
        if self.payload.path:
            p = Path(self.payload.path)
            try:
                return p.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                return p.read_text(encoding="cp1251", errors="ignore")
            except Exception as e:
                app_logger.exception("Ошибка чтения TXT: %s", e)
                return ""
        content = self.payload.content or b""
        for enc in ("utf-8", "cp1251", "koi8-r", "utf-16", "iso-8859-5", "mac-cyrillic"):
            try:
                return content.decode(enc)
            except UnicodeDecodeError:
                continue
        return content.decode("utf-8", errors="ignore")

class UnsupportedExtractor(BytesExtractor):
    def extract_text(self) -> str:
        app_logger.info("Неподдерживаемый тип: %s / %s",
                    self.payload.mime, self.payload.filename)
        return ""

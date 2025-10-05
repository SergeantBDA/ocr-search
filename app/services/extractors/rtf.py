from __future__ import annotations
import logging
from pathlib import Path
from .base import BytesExtractor
 
# ------------------------- logging --------------------------------------
from app.logger import logger as app_logger, attach_to_logger_names
attach_to_logger_names(["app.services.extractors.rtf"])

# Поддержка обеих форм импорта из striprtf
try:
    from striprtf.striprtf import rtf_to_text as _rtf_to_text
except Exception:
    try:
        from striprtf import rtf_to_text as _rtf_to_text  # некоторые форки
    except Exception:
        _rtf_to_text = None
 
class RTFExtractor(BytesExtractor):
    """
    Извлечение текста из RTF:
    - Поддерживает payload.path и payload.content (bytes).
    - Авто-подбор кодировки (utf-8 → cp1251 → latin-1 → utf-8 ignore).
    """
    def extract_text(self) -> str:
        if _rtf_to_text is None:
            app_logger.warning("striprtf не установлен — пропускаю RTF.")
            return ""
 
        try:
            if self.payload.path:
                data = Path(self.payload.path).read_bytes()
            else:
                data = self.payload.content or b""
 
            rtf_text = None
            for enc in ("utf-8", "cp1251", "latin-1"):
                try:
                    rtf_text = data.decode(enc)
                    break
                except UnicodeDecodeError:
                    continue
            if rtf_text is None:
                rtf_text = data.decode("utf-8", errors="ignore")
 
            return _rtf_to_text(rtf_text) if rtf_text else ""
        except Exception as e:
            app_logger.exception("Ошибка чтения RTF: %s", e)
            return ""

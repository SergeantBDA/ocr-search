from __future__ import annotations
import io
import logging
from pathlib import Path
from .base import BytesExtractor

# ------------------------- logging --------------------------------------
from app.logger import logger as app_logger, attach_to_logger_names
attach_to_logger_names(["app.services.extractors.xls"])

try:
    import pandas as pd
except Exception:  # pragma: no cover
    pd = None

class ExcelExtractor(BytesExtractor):
    def extract_text(self) -> str:
        if pd is None:
            app_logger.warning("pandas не установлен — пропускаю Excel.")
            return ""        
        try:
            if self.payload.path:
                frames: Dict[str, "pd.DataFrame"] = pd.read_excel(self.payload.path, sheet_name=None, header=None)
            else:
                bio = io.BytesIO(self.payload.content or b"")
                frames: Dict[str, "pd.DataFrame"] = pd.read_excel(bio, sheet_name=None, header=None)
        except Exception as e:
            app_logger.exception("Ошибка чтения Excel: %s", e)
            return ""
        parts = []
        for sheet, df in frames.items():
            parts.append(f"=== Лист: {sheet} ===")
            parts.append(df.to_csv(sep="\t", index=False, header=False))

        return "\n\n".join(parts).strip()
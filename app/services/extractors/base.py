from __future__ import annotations
import logging
from abc import abstractmethod
from dataclasses import dataclass
from typing import Optional
from abc import ABC, abstractmethod
# ------------------------- logging --------------------------------------
from app.logger_worker import worker_log as app_logger

# --------------------------- base ---------------------------------------
@dataclass(frozen=True)
class BytesPayload:
    """
    Универсальный payload: либо content (bytes), либо path (путь к файлу).
    Достаточно одного из них. filename/mime используются как подсказки.
    """
    content : Optional[bytes] = None
    path    : Optional[str]   = None
    filename: Optional[str]   = None
    mime    : Optional[str]   = None

class BytesExtractor(ABC):
    """Базовый класс для экстракторов, работающих с bytes."""    
    def __init__(self, payload: BytesPayload, *, ocr_lang: str = "rus+eng"):
        self.payload  = payload
        self.ocr_lang = ocr_lang

    @abstractmethod
    def extract_text(self) -> str: ...
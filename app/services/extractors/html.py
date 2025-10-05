from __future__ import annotations
import logging
from pathlib import Path
 
from .base import BytesExtractor
 
# ------------------------- logging --------------------------------------
from app.logger import logger as app_logger, attach_to_logger_names
attach_to_logger_names(["app.services.extractors.html"])

try:
    # BeautifulSoup умеет детектировать кодировку через UnicodeDammit
    from bs4 import BeautifulSoup, UnicodeDammit
    try:
        from bs4 import Comment  # для удаления HTML-комментариев
    except Exception:
        Comment = None
except Exception:
    BeautifulSoup = None
    UnicodeDammit = None
    Comment = None
 
class HTMLExtractor(BytesExtractor):
    """
    Извлекает «видимый» текст из HTML.
    Поддерживает: payload.path (файл на диске) и payload.content (bytes).
    """
 
    DROP_TAGS = ("script", "style", "nav", "header", "footer", "aside",
                 "noscript", "link", "meta", "form", "svg", "canvas", "iframe")
 
    def extract_text(self) -> str:
        if BeautifulSoup is None:
            app_logger.warning("beautifulsoup4 не установлен — пропускаю HTML.")
            return ""
 
        data = self._read_html_bytes()
        if not data:
            return ""
 
        html = self._decode_html(data)
 
        # Пытаемся парсить lxml, при отсутствии — stdlib html.parser
        soup = None
        try:
            soup = BeautifulSoup(html, "lxml")
        except Exception:
            try:
                soup = BeautifulSoup(html, "html.parser")
            except Exception as e:
                app_logger.exception("Ошибка парсинга HTML: %s", e)
                return ""
 
        if not soup:
            return ""
 
        # Удаляем «шумные» теги
        for tag in soup(self.DROP_TAGS):
            try:
                tag.decompose()
            except Exception:
                pass
 
        # Сносим комментарии
        if Comment is not None:
            try:
                for c in soup.find_all(string=lambda s: isinstance(s, Comment)):
                    c.extract()
            except Exception:
                pass
 
        # Возвращаем видимый текст
        try:
            return soup.get_text(separator=" ", strip=True)
        except Exception as e:
            app_logger.exception("Ошибка извлечения текста из HTML: %s", e)
            return ""
 
    # ------- helpers -------
 
    def _read_html_bytes(self) -> bytes:
        if self.payload.path:
            try:
                return Path(self.payload.path).read_bytes()
            except Exception as e:
                app_logger.exception("Не удалось прочитать HTML-файл %s: %s", self.payload.path, e)
                return b""
        return self.payload.content or b""
 
    def _decode_html(self, data: bytes) -> str:
        # 1) пробуем детектор кодировки BeautifulSoup
        if UnicodeDammit is not None:
            try:
                ud = UnicodeDammit(data, is_html=True)
                if ud.unicode_markup:
                    return ud.unicode_markup
            except Exception:
                pass
        # 2) «ручной» перебор популярных кодировок
        for enc in ("utf-8", "cp1251", "koi8-r", "utf-16", "iso-8859-5", "mac-cyrillic", "latin-1"):
            try:
                return data.decode(enc)
            except UnicodeDecodeError:
                continue
        # 3) последний шанс
        return data.decode("utf-8", errors="ignore")

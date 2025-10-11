from __future__ import annotations
import io
import re
import concurrent.futures
from .base import BytesExtractor
# ------------------------- logging --------------------------------------
from app.logger import logger as app_logger, attach_to_logger_names
attach_to_logger_names(["app.services.extractors.pdf"])
RUSSIAN_CHARS = set(r".:,-+=()!0123456789абвгдеёжзийклмнопрстуфхцчшщъыьэюяАБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ")
# -------- optional imports (защищены) ----------
try:
    import fitz  # PyMuPDF
except Exception as e:  # pragma: no cover
    fitz = None
    app_logger.warning("PyMuPDF не загрузился: %s", e)

try:
    from PIL import Image
except Exception:  # pragma: no cover
    Image = None

try:
    import pytesseract
except Exception:  # pragma: no cover
    pytesseract = None

def _looks_like_russian(text: str, threshold: float = 0.40) -> bool:
    if not text:
        return False
    ru = sum(1 for ch in text if ch in RUSSIAN_CHARS)
    return (ru / max(1, len(text))) >= threshold

def _prepare_img(page: "fitz.Page", dpi: int = 300):
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    img = Image.open(io.BytesIO(pix.tobytes("png")))
    return(img)

def _rotate_by_osd(
    page: "fitz.Page",
    *,
    logger: logging.Logger = app_logger,
) -> int:
    """
    Пытается определить ориентацию через Tesseract OSD и повернуть изображение.
    Возвращает (возможно повернутое) изображение и метаданные:
      {"method": "osd"|"trial"|"skip", "angle": int, "confidence": float, "reason": str}

    НИКОГДА тихо не молчит: всегда пишет в лог на уровне INFO/WARNING/ERROR.
    """
    img = _prepare_img(page)
    osd_text = pytesseract.image_to_osd(img, config="--psm 0 -l osd")
    # Пример:
    # Orientation in degrees: 270
    # Rotate: 90
    # Orientation confidence: 12.34
    # Script: Cyrillic
    # Script confidence: 9.87

    # Парсим angle
    angle = None
    m = re.search(r"(?i)Rotate:\s*(\d+)", osd_text)
    if m:
        angle = int(m.group(1))
    else:
        m2 = re.search(r"(?i)Orientation in degrees:\s*(\d+)", osd_text)
        if m2:
            # В некоторых сборках «Orientation in degrees» = фактический угол страницы.
            # Для Pillow поворачиваем на -angle (против часовой, чтобы выровнять).
            angle = (-int(m2.group(1))) % 360

    if angle is None or angle in (0, 360, -360):
        logger.info("OSD не смог распознать угол — пропускаю поворот.")
        return 0

    return angle

_ws_re        = re.compile(r"[ \t\u00A0]+")
_hyphen_re    = re.compile(r"(\w)-\s*\n(\w)")
_single_nl_re = re.compile(r"(?<!\n)\n(?!\n)")   # одиночный \n, не часть \n\n
_multi_nl_re  = re.compile(r"\n{3,}")            # 3+ переводов → 2

def _preprocess_text_layer(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _hyphen_re.sub(r"\1\2", text)        # убираем переносы по дефису
    text = _single_nl_re.sub(" ", text)         # одиночный \n превращаем в пробел
    text = _ws_re.sub(" ", text)                # сжимаем пробелы (вкл. NBSP)
    text = _multi_nl_re.sub("\n", text)       # абзацы нормализуем к \n
    return text.strip()


def _page_has_text(page: "fitz.Page", min_chars: int = 16) -> bool:
    txt = page.get_text("text", sort=True)
    if len(re.sub(r"\s+", "", txt)) >= min_chars:
        return True
    d = page.get_text("rawdict")
    for b in d.get("blocks", []):
        if b.get("type") == 0:
            for line in b.get("lines", []):
                for span in line.get("spans", []):
                    if span.get("text") and len(span["text"].strip()) > 0:
                        return True
    return False

def _extract_from_text_page(page) -> str:
    parts = []
    # blocks: (x0, y0, x1, y1, text, block_no, block_type)
    for x0, y0, x1, y1, txt, bno, btype in page.get_text("blocks", sort=True):
        if btype != 0:      # 0 = текст
            continue
        parts.append(_preprocess_text_layer(txt))
    # Между блоками оставляем пустую строку
    return "\n\n".join([p for p in parts if p])

def _extract_from_image_page(num: int, page: "fitz.Page", angle: int = 0) -> tuple[int, str]:
    img = _prepare_img(page)
    if angle != 0:
        img = img.rotate(-angle, expand=True)
    txt = pytesseract.image_to_string(img, lang="rus+eng", config="--psm 6")
    return num, txt  

class PDFExtractorFast(BytesExtractor):
    """PDF: сперва текстовый слой, затем OCR-фоллбек с учётом ориентации."""
    def extract_text(self) -> str:
        if fitz is None:
            app_logger.warning("PyMuPDF не установлен — пропускаю PDF.")
            return ""
        
        try:
            if self.payload.path:
                doc = fitz.open(self.payload.path)
            else:
                doc = fitz.open(stream=(self.payload.content or b""), filetype="pdf")            
        except Exception as e:
            app_logger.exception("Ошибка открытия PDF: %s", e)
            return ""

        page_count = doc.page_count
        app_logger.info(f"PDF pages: {page_count}")
        angle = _rotate_by_osd(doc[0])

        text_per_page: List[Optional[str]] = [None] * page_count
        is_scan_page: List[bool] = [False] * page_count
        for n in range(page_count):
            p = doc.load_page(n)
            if _page_has_text(p):
                text_per_page[n] = _extract_from_text_page(p)
                is_scan_page[n] = False
            else:
                is_scan_page[n] = True  # позже сделаем OCR        

        # 2) OCR только скан-страниц (параллельно)
        ocr_results: dict[int, Tuple[str, bytes]] = {}
        scan_indices = [i for i, flag in enumerate(is_scan_page) if flag]
        if scan_indices:
            app_logger.info(f"Кол-во стр. на распознавании: {len(scan_indices)}")              

            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                futures = [pool.submit(_extract_from_image_page, n, doc[n], angle) for n in scan_indices]
                for fut in concurrent.futures.as_completed(futures):
                    npage, txt       = fut.result()
                    text_per_page[npage] = _preprocess_text_layer(txt)
        if text_per_page:
            result = ''.join(text_per_page)
        return result
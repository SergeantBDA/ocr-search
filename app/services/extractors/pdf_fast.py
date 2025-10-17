from __future__ import annotations

import io
import re
import unicodedata
import concurrent.futures
import logging
from typing import List, Optional, Tuple

# ------------------------- logging --------------------------------------
from app.logger_worker import worker_log as app_logger

# -------- optional imports (защищены) ----------
try:
    import fitz  # PyMuPDF
except Exception as e:  # pragma: no cover
    fitz = None
    app_logger.warning("PyMuPDF не загрузился: %s", e)

try:
    from PIL import Image, ImageOps
    Image.MAX_IMAGE_PIXELS = 500_000_000  # «страховка», основной контроль делаем zoom-ом
except Exception:  # pragma: no cover
    Image = None
    ImageOps = None

try:
    import pytesseract
except Exception:  # pragma: no cover
    pytesseract = None

from .base import BytesExtractor

# ------------------------- константы --------------------------------------
RUSSIAN_CHARS = set(r".:,-+=()!0123456789абвгдеёжзийклмнопрстуфхцчшщъыьэюяАБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ")

TARGET_DPI      = 300           # контролируемая растеризация страниц PDF
MAX_OSD_PIXELS  = 8_000_000     # даунскейл для OSD (~8 Мп, ускоряет и гасит DecompressionBombWarning)
SAFE_MAX_PIXELS = 100_000_000   # не более 100 Мп на страницу (подберите под RAM)
MAX_SIDE_PX     = 3500          # ограничение длинной стороны (ускоряет OCR)

# ------------------------- утилиты текста ---------------------------------
def _looks_like_russian(text: str, threshold: float = 0.40) -> bool:
    if not text:
        return False
    ru = sum(1 for ch in text if ch in RUSSIAN_CHARS)
    return (ru / max(1, len(text))) >= threshold

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


# ------------------------- растеризация/OSD -------------------------------
def _compute_zoom(page: "fitz.Page", target_dpi: int, max_pixels: int, max_side_px: int) -> float:
    """
    Возвращает коэффициент zoom для fitz.Matrix так, чтобы итог:
      - не превышал max_pixels,
      - и длинная сторона была <= max_side_px.
    """
    base = target_dpi / 72.0
    w_pt, h_pt = float(page.rect.width), float(page.rect.height)
    w_px_base, h_px_base = w_pt * base, h_pt * base
    total_base = w_px_base * h_px_base
 
    zoom = base
    if total_base > max_pixels:
        zoom *= (max_pixels / total_base) ** 0.5  # равномерно ужимаем
 
    # контроль длинной стороны
    long_side_after = max(w_px_base, h_px_base) * (zoom / base)
    if long_side_after > max_side_px:
        zoom *= (max_side_px / long_side_after)
 
    return max(0.1, zoom)
 
def _rasterize_page_to_pil(page: "fitz.Page", dpi: int = TARGET_DPI) -> "Image.Image":
    """
    Безопасная растеризация: ограничиваем размер, и создаём PIL.Image напрямую из Pixmap.samples.
    """
    if Image is None:
        raise RuntimeError("Pillow (PIL) не установлен.")
    if fitz is None:
        raise RuntimeError("PyMuPDF не установлен.")
 
    # Подбираем zoom под ограничения
    zoom = _compute_zoom(page, dpi, SAFE_MAX_PIXELS, MAX_SIDE_PX)
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, alpha=False)  # alpha=False → RGB или GRAY
 
    # Собираем PIL.Image без PNG-декомпрессии
    # pix.n: 1=GRAY, 3=RGB, 4=CMYK(?) или RGBA при alpha=True; тут alpha=False, поэтому 1 или 3
    if pix.n == 1:
        mode = "L"
    elif pix.n == 3:
        mode = "RGB"
    else:
        # на всякий случай (бывает палитра/прочее) — конвертнём в RGB
        pix = fitz.Pixmap(fitz.csRGB, pix)
        mode = "RGB"
 
    img = Image.frombytes(mode, (pix.width, pix.height), pix.samples)
 
    # Пропишем реальный DPI, соответствующий zoom
    eff_dpi = int(72.0 * zoom)
    img.info["dpi"] = (eff_dpi, eff_dpi)
    return img

def _downscale_for_osd(img: "Image.Image", max_pixels: int = MAX_OSD_PIXELS) -> "Image.Image":
    w, h = img.size
    total = w * h
    if total <= max_pixels:
        return img
    k = (max_pixels / total) ** 0.5
    new_size = (max(1, int(w * k)), max(1, int(h * k)))
    return img.resize(new_size, Image.LANCZOS)


def _rotate_by_osd(page: "fitz.Page") -> int:
    """
    Безопасное определение угла ориентации через Tesseract OSD.
    Возвращает угол (0|90|180|270). При любой проблеме — 0.
    Всегда пишет в лог о результате или причине пропуска.
    """
    if pytesseract is None:
        app_logger.info("OSD пропущен: pytesseract не установлен.")
        return 0
    try:
        img = _rasterize_page_to_pil(page, dpi=TARGET_DPI)

        # Учитываем возможный EXIF-поворот от сканера/камеры
        if ImageOps is not None:
            img = ImageOps.exif_transpose(img)

        # Даунскейл и перевод в L для устойчивого OSD
        img_osd = _downscale_for_osd(img).convert("L")

        # ВАЖНО: язык задаём отдельным аргументом, а не -l в config
        osd_text = pytesseract.image_to_osd(img_osd, config="--psm 0", lang="osd")

        # В osd_text обычно есть "Orientation in degrees: N" и/или "Rotate: N"
        angle: Optional[int] = None
        m = re.search(r"(?i)Rotate:\s*(\d+)", osd_text)
        if m:
            angle = int(m.group(1))
        else:
            m2 = re.search(r"(?i)Orientation in degrees:\s*(\d+)", osd_text)
            if m2:
                # Для Pillow поворот делаем на -angle (чтобы выровнять)
                angle = (-int(m2.group(1))) % 360

        if angle not in (0, 90, 180, 270):
            app_logger.info("OSD не смог распознать угол — пропускаю поворот.")
            return 0

        app_logger.info("OSD угол: %s°", angle)
        return angle
    except pytesseract.TesseractError as e:
        # Типично: "Too few characters. Skipping this page"
        app_logger.info("OSD пропущен: %s", getattr(e, "message", e))
        return 0
    except Exception as e:
        app_logger.warning("OSD не удался: %r", e)
        return 0


# ------------------------- извлечение текста ------------------------------
def _extract_from_text_page(page: "fitz.Page") -> str:
    parts: List[str] = []
    # blocks: (x0, y0, x1, y1, text, block_no, block_type)
    for x0, y0, x1, y1, txt, bno, btype in page.get_text("blocks", sort=True):
        if btype != 0:      # 0 = текст
            continue
        parts.append(txt)
    # Между блоками оставляем пустую строку
    return "\n\n".join([p for p in parts if p])


def _extract_from_image_page(num: int, page: "fitz.Page", angle: int = 0) -> Tuple[int, str]:
    try:
        if pytesseract is None:
            return num, ""
        img = _rasterize_page_to_pil(page, dpi=TARGET_DPI)
        if angle:
            # поворачиваем в читаемый вид
            img = img.rotate(-angle, expand=True)
        # Базовая конфигурация: смешанный русский/английский документ
        txt = pytesseract.image_to_string(img, lang="rus+eng", config="--psm 6")
    except Exception as e:
        print(e)
        return num, ''
    return num, txt


# ------------------------- основной класс ---------------------------------
class PDFExtractorFast(BytesExtractor):
    """PDF: сперва текстовый слой, затем OCR-фоллбек с учётом ориентации."""
    def extract_text(self) -> str:
        if fitz is None:
            app_logger.warning("PyMuPDF не установлен — пропускаю PDF.")
            return ""

        # 1) открываем документ
        try:
            if self.payload.path:
                doc = fitz.open(self.payload.path)
            else:
                doc = fitz.open(stream=(self.payload.content or b""), filetype="pdf")
        except Exception as e:
            app_logger.exception("Ошибка открытия PDF: %s", e)
            return ""

        page_count = doc.page_count
        app_logger.info("PDF pages: %s", page_count)

        # 2) определяем общий угол ориентации по первой странице (безопасно)
        angle = 0
        try:
            if page_count > 0:
                angle = _rotate_by_osd(doc[0])
        except Exception as e:
            app_logger.warning("Определение ориентации пропущено: %r", e)
            angle = 0

        # 3) пробуем извлечь текстовый слой там, где он есть
        text_per_page: List[Optional[str]] = [None] * page_count
        is_scan_page: List[bool] = [False] * page_count

        for n in range(page_count):
            p = doc.load_page(n)
            if _page_has_text(p):
                text_per_page[n] = _extract_from_text_page(p)
                is_scan_page[n] = False
            else:
                is_scan_page[n] = True  # позже сделаем OCR

        # 4) OCR только скан-страниц (параллельно)
        scan_indices = [i for i, flag in enumerate(is_scan_page) if flag]
        if scan_indices and pytesseract is not None:
            app_logger.info("Кол-во стр. на распознавании: %s", len(scan_indices))
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                futures = [pool.submit(_extract_from_image_page, n, doc[n], angle) for n in scan_indices]
                for fut in concurrent.futures.as_completed(futures):
                    npage, txt = fut.result()
                    text_per_page[npage] = txt

        # 5) склеиваем
        if text_per_page:
            return "".join(s or "" for s in text_per_page)
        return ""

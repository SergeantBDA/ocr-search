from __future__ import annotations
import re
from .base import BytesExtractor
# ------------------------- logging --------------------------------------
from app.logger import logger as app_logger, attach_to_logger_names
attach_to_logger_names(["app.services.extractors.pdf"])
RUSSIAN_CHARS = set(r".:,-+=()!0123456789абвгдеёжзийклмнопрстуфхцчшщъыьэюяАБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ")
# -------- optional imports (защищены) ----------
try:
    import fitz  # PyMuPDF
except Exception:  # pragma: no cover
    fitz = None

try:
    from PIL import Image
except Exception:  # pragma: no cover
    Image = None

try:
    import pytesseract
except Exception:  # pragma: no cover
    pytesseract = None

def looks_like_russian(text: str, threshold: float = 0.40) -> bool:
    if not text:
        return False
    ru = sum(1 for ch in text if ch in RUSSIAN_CHARS)
    return (ru / max(1, len(text))) >= threshold

def _rotate_by_osd(
    img: "Image.Image",
    *,
    enable_trials: bool = False,           # можно включить дешёвую эвристику «перебор углов», если OSD упал
    trial_angles: tuple[int, ...] = (0, 90, 180, 270),
    osd_conf_threshold: float = 3.0,       # ниже — считаем, что OSD не уверен
    logger: logging.Logger = app_logger,
) -> tuple["Image.Image", dict]:
    """
    Пытается определить ориентацию через Tesseract OSD и повернуть изображение.
    Возвращает (возможно повернутое) изображение и метаданные:
      {"method": "osd"|"trial"|"skip", "angle": int, "confidence": float, "reason": str}

    НИКОГДА тихо не молчит: всегда пишет в лог на уровне INFO/WARNING/ERROR.
    """
    meta = {"method": "skip", "angle": 0, "confidence": -1.0, "reason": ""}

    if pytesseract is None:
        msg = "pytesseract не установлен — пропускаю OSD."
        logger.info(msg)
        meta["reason"] = msg
        return img, meta

    # Pillow: нормализуем режим — OSD иногда капризничает на 'P', 'LA', 'RGBA'
    try:
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
    except Exception as e:
        logger.warning("Не удалось сконвертировать изображение к RGB для OSD: %s", e)

    w, h = getattr(img, "size", (0, 0))
    if min(w, h) < 50:
        msg = f"слишком маленькое изображение для OSD: {w}x{h}"
        logger.info(msg)
        meta["reason"] = msg
        return img, meta

    # Явная конфигурация OSD
    try:
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

        # Парсим confidence
        conf = -1.0
        c = re.search(r"(?i)Orientation confidence:\s*([0-9]+(?:\.[0-9]+)?)", osd_text)
        if c:
            conf = float(c.group(1))

        logger.info("OSD результат: angle=%s, confidence=%.2f (size=%dx%d)", angle, conf, w, h)

        if angle is None:
            meta.update({"method": "osd", "angle": 0, "confidence": conf, "reason": "angle not parsed"})
            logger.info("OSD не смог распознать угол — пропускаю поворот.")
            return img, meta

        if conf < osd_conf_threshold:
            logger.info("OSD низкая уверенность (%.2f < %.2f)", conf, osd_conf_threshold)

        # Приводим угол к {0,90,180,270}
        angle = int(angle) % 360
        if angle in (0, 360):
            meta.update({"method": "osd", "angle": 0, "confidence": conf, "reason": "no rotation needed"})
            return img, meta

        # Pillow: положительный угол — поворот против часовой стрелки.
        # OSD «Rotate: 90» обычно означает «поверни по часовой на 90», значит надо повернуть на -90.
        # Мы уже нормализовали выше, здесь просто -angle:
        rotated = img.rotate(-angle, expand=True)
        meta.update({"method": "osd", "angle": angle, "confidence": conf, "reason": "rotated by OSD"})
        logger.info("Повернул по OSD на %d°", angle)
        return rotated, meta

    except Exception as e:
        # Логируем ПРИЧИНУ (например, TesseractNotFoundError, отсутствие osd.traineddata)
        logger.error("OSD упал: %s", e)
        meta["reason"] = f"osd failed: {e}"

    # === Fallback (опционально): перебор углов, если OSD не сработал ===
    if enable_trials:
        best_angle = 0
        best_score = -1
        best_img = img
        logger.info("Пробую эвристику углов: %s", trial_angles)

        for a in trial_angles:
            try:
                candidate = img if a in (0, 360) else img.rotate(-a, expand=True)
                txt = pytesseract.image_to_string(candidate, lang="rus+eng", config="--psm 6")
                # Простейший скорер «сколько букв/цифр»:
                letters = sum(ch.isalnum() for ch in txt)
                # Можно усилить: штрафовать за «слишком мало» или «слишком много» пробелов/непечатаемых
                score = letters
                logger.info("trial angle=%d → score=%d, len=%d", a, score, len(txt))
                if score > best_score:
                    best_score = score
                    best_angle = a
                    best_img = candidate
            except Exception as e:
                logger.warning("trial angle=%d упал: %s", a, e)

        meta.update({"method": "trial", "angle": best_angle, "confidence": -1.0, "reason": "trial best angle"})
        if best_angle not in (0, 360):
            logger.info("Выбрал эвристический угол %d° (score=%d)", best_angle, best_score)
        return best_img, meta

    return img, meta

class PDFExtractor(BytesExtractor):
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

        # 1) прямой текст
        txt_parts = []
        for page in doc:
            try:
                t = page.get_text().strip()
            except Exception:
                t = ""
            if t:
                txt_parts.append(t)
        whole_text = "\n".join(txt_parts).strip()

        # 2) OCR fallback при отсутствии/скупости текста
        need_ocr = not whole_text or (not looks_like_russian(whole_text[:300]) and pytesseract and Image)
        if need_ocr and Image is not None and pytesseract is not None:
            ocr_parts = []
            for page in doc:
                try:                    
                    pix = page.get_pixmap(dpi=300, alpha=False)
                    img = Image.open(io.BytesIO(pix.tobytes("png")))
                    img = _rotate_by_osd(img)[0]                    
                    ocr_parts.append(pytesseract.image_to_string(img, lang=self.ocr_lang))
                except Exception:
                    # продолжаем собирать со следующих страниц
                    continue            
            ocr_text = "\n".join(ocr_parts).strip()
            if len(ocr_text) > len(whole_text):
                return ocr_text

        return whole_text

class ImageExtractor(BytesExtractor):
    """OCR изображений с определением ориентации (OSD)."""
    def extract_text(self) -> str:
        if Image is None or pytesseract is None:
            app_logger.warning("Pillow/pytesseract не установлены — пропускаю изображение.")
            return ""
        try:
            if self.payload.path:
                img = Image.open(self.payload.path)
            else:
                img = Image.open(io.BytesIO(self.payload.content or b""))
        except Exception as e:
            app_logger.exception("Ошибка открытия изображения: %s", e)
            return ""
        img = _rotate_by_osd(img)[0]
        try:
            return pytesseract.image_to_string(img, lang=self.ocr_lang)
        except Exception as e:
            app_logger.exception("Ошибка OCR изображения: %s", e)
            return ""
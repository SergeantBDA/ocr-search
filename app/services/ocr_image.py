from io import BytesIO
from typing import Tuple

from PIL import Image, ImageOps, ImageFilter, ImageEnhance, ImageStat
import pytesseract


def _preprocess_image(img: Image.Image, target_width: int = 1800) -> Image.Image:
    """
    Простая предобработка для улучшения качества OCR:
    - конвертация в RGB
    - увеличение размера до target_width (сохранение соотношения)
    - преобразование в grayscale
    - повышение контраста
    - лёгкая бинаризация и шумоподавление
    """
    if img.mode != "RGB":
        img = img.convert("RGB")

    # Увеличим изображение если оно маленькое (чтобы улучшить распознавание)
    w, h = img.size
    if w < target_width:
        ratio = target_width / float(w)
        new_size = (int(w * ratio), int(h * ratio))
        img = img.resize(new_size, Image.LANCZOS)

    # Перевод в градации серого
    img = ImageOps.grayscale(img)

    # Повышение контраста
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(1.4)

    # Лёгкое размытие для снижения мелкого шума, затем резкая бинаризация
    img = img.filter(ImageFilter.MedianFilter(size=3))

    # Бинаризация по порогу, адаптация порога под яркость
    # Рассчитываем среднюю яркость и ставим порог чуть ниже средней
    stat = ImageStat.Stat(img)
    mean = stat.mean[0] if stat.mean else 128
    threshold = max(80, min(140, int(mean * 0.9)))
    img = img.point(lambda p: 255 if p > threshold else 0)

    return img


def extract_text_from_image(data: bytes) -> str:
    """
    Извлекает текст из картинки (байты) используя Pillow + pytesseract.
    Возвращает распознанный текст (строка). При ошибке возвращает пустую строку.
    """
    try:
        buf = BytesIO(data)
        with Image.open(buf) as img:
            processed = _preprocess_image(img)
            # Конфиг можно менять: psm 3/6 в зависимости от типа изображения
            text = pytesseract.image_to_string(processed,lang="rus+eng", config="--oem 3 --psm 3")
            return text.strip()
    except Exception:
        return ""

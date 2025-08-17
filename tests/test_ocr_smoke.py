import io
import pytest

# пропускаем тест если отсутствуют зависимости
pytest.importorskip("PIL")
pytesseract = pytest.importorskip("pytesseract")

from PIL import Image, ImageDraw, ImageFont
from pytesseract import get_tesseract_version
from app.services.ocr_image import extract_text_from_image

# пропускаем если бинарь tesseract не установлен/не доступен
try:
    get_tesseract_version()
except Exception:
    pytest.skip("Tesseract binary is not available, skipping OCR smoke test")


def test_extract_text_from_generated_png_contains_ocr():
    # Создаём простое изображение с текстом "Hello OCR"
    img = Image.new("RGB", (520, 120), color="white")
    draw = ImageDraw.Draw(img)
    try:
        # Попытка использовать системный truetype шрифт для лучшего результата
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 48)
    except Exception:
        font = ImageFont.load_default()

    draw.text((10, 20), "Hello OCR", fill="black", font=font)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    data = buf.getvalue()

    text = extract_text_from_image(data)
    assert "OCR" in (text or "").upper()

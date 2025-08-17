import io
from typing import List

import pdfplumber
from pdf2image import convert_from_bytes
import pytesseract


MIN_TOTAL_CHARS = 200  # если извлечённый текст меньше этого — запускаем OCR


def extract_text_from_pdf(data: bytes) -> str:
	"""
	Попробовать извлечь текст через pdfplumber; если текста мало — отрисовать страницы и выполнить OCR через pytesseract.
	Возвращает объединённый текст (pdfplumber + OCR при необходимости).
	"""
	plumber_text_parts: List[str] = []
	try:
		with pdfplumber.open(io.BytesIO(data)) as pdf:
			for page in pdf.pages:
				try:
					text = page.extract_text()
				except Exception:
					text = None
				if text:
					plumber_text_parts.append(text)
	except Exception:
		# Если pdfplumber упал — оставим plumber_text_parts пустым и продолжим с OCR
		plumber_text_parts = []

	plumber_text = "\n\n".join(plumber_text_parts).strip()

	# Если достаточно текста, возвращаем результат pdfplumber
	if len(plumber_text) >= MIN_TOTAL_CHARS:
		return plumber_text

	# Иначе — делаем OCR по изображениям страниц
	ocr_parts: List[str] = []
	try:
		images = convert_from_bytes(data, dpi=300)
		for img in images:
			# Можно добавить дополнительные параметры в конфиг, например '--psm 3'
			try:
				text = pytesseract.image_to_string(img)
			except Exception:
				text = ""
			if text:
				ocr_parts.append(text)
	except Exception:
		# Если и OCR упал — возвращаем то, что есть от pdfplumber (возможно пустую строку)
		ocr_parts = []

	ocr_text = "\n\n".join(ocr_parts).strip()

	# Если pdfplumber дал хоть что-то, объединим оба результата, иначе вернём только OCR
	if plumber_text and ocr_text:
		return plumber_text + "\n\n" + ocr_text
	if ocr_text:
		return ocr_text
	return plumber_text

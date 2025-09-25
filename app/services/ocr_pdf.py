import io
from typing import List

import pymupdf
from pdf2image import convert_from_bytes
import pytesseract


MIN_TOTAL_CHARS = 200  # если извлечённый текст меньше этого — запускаем OCR


def extract_text_from_pdf(data: bytes) -> str:
	"""
	Попробовать извлечь текст через pdfplumber; если текста мало — отрисовать страницы и выполнить OCR через pytesseract.
	Возвращает объединённый текст (pdfplumber + OCR при необходимости).
	"""
	text_parts: List[str] = []
	try:
		doc = pymupdf.Document(stream=data)
		with doc as pdf:			
			for page in pdf:
				try:
					text = page.get_text().strip()
				except Exception:
					text = None
				if text:
					text_parts.append(text)
	except Exception as e:
		print(e)
		# Если pdfplumber упал — оставим plumber_text_parts пустым и продолжим с OCR
		text_parts = []

	soft_text = "\n".join(text_parts).strip()

	# Если достаточно текста, возвращаем результат pdfplumber
	if len(soft_text) >= MIN_TOTAL_CHARS:
		return soft_text

	# Иначе — делаем OCR по изображениям страниц
	ocr_parts: List[str] = []
	try:
		images = convert_from_bytes(data, dpi=300)
		for img in images:
			# Можно добавить дополнительные параметры в конфиг, например '--psm 3'
			try:
				text = pytesseract.image_to_string(img, lang="rus+eng", config="--oem 3 --psm 3")
			except Exception:
				text = ""
			if text:
				ocr_parts.append(text)
	except Exception:
		# Если и OCR упал — возвращаем то, что есть от pdfplumber (возможно пустую строку)
		ocr_parts = []

	ocr_text = "\n\n".join(ocr_parts).strip()

	# Если pdfplumber дал хоть что-то, объединим оба результата, иначе вернём только OCR
	if soft_text and ocr_text:
		return soft_text + "\n\n" + ocr_text
	if ocr_text:
		return ocr_text
	return soft_text

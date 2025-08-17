from sqlalchemy import Column, BigInteger, String, Text, JSON, DateTime, func
from .db import Base

class Document(Base):
	__tablename__ = "documents"

	# Первичный ключ
	id = Column(BigInteger, primary_key=True, autoincrement=True)

	# Имя файла
	filename = Column(String, nullable=False)

	# Содержимое (текст/OCR)
	content = Column(Text, nullable=True)

	# MIME-тип
	mime = Column(String, nullable=True)

	# Размер в байтах
	size_bytes = Column(BigInteger, nullable=True)

	# Дополнительные метаданные в JSON
	meta = Column(JSON, nullable=True)

	# Время создания (по умолчанию текущее)
	created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

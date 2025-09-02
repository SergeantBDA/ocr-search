from sqlalchemy import Column, BigInteger, String, Text, JSON, DateTime, func
from .db import Base
from sqlalchemy.dialects.postgresql import TSVECTOR


class Document(Base):
    __tablename__ = "documents"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    filename = Column(String, nullable=False)
    content = Column(Text, nullable=True)
    mime = Column(String, nullable=True)
    size_bytes = Column(BigInteger, nullable=True)
    meta = Column(JSON, nullable=True, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    search_vector = Column(TSVECTOR, nullable=True)
    #полный путь до загруженного файла ORIGIN
    path_origin = Column(String, nullable=False)

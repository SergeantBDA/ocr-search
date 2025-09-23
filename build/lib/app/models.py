from sqlalchemy import Column, BigInteger, String, Text, JSON, DateTime, func, Boolean, Index
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

# GIN индекс по search_vector
Index(
    "ix_documents_search_vector",
    Document.search_vector,
    postgresql_using="gin"
)
 
# Триграммный GIN-индекс по content
Index(
    "ix_documents_content_trgm",
    Document.content,
    postgresql_using="gin",
    postgresql_ops={"content": "gin_trgm_ops"}
)


class User(Base):
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    email = Column(String(320), nullable=False, unique=True, index=True)  # RFC-compatible length
    password_hash = Column(String(255), nullable=False)
    is_active = Column(Boolean, nullable=False, server_default="true")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email}>"
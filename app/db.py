# filepath: app/db.py
from typing import Generator

from fastapi import Depends
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings

# SQLAlchemy engine (synchronous)
engine = create_engine(settings.database_url, future=True)

# Session factory
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

# Declarative base for models
class Base(DeclarativeBase):
    pass

# Dependency for FastAPI endpoints
def get_session() -> Generator[Session, None, None]:
    """
    Yields a SQLAlchemy Session and ensures it is closed after use.
    Use in FastAPI endpoints as: db: Session = Depends(get_session)
    """
    session: Session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
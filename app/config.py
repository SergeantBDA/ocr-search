from typing import Optional
from pathlib import Path
from pydantic import SecretStr, Field, IPvAnyAddress
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[1]  # корень проекта рядом с app/

class Settings(BaseSettings):
    database_url: SecretStr = Field(..., env="DATABASE_URL")
    env: str = Field("dev", env="ENV")

    app_host: IPvAnyAddress = Field("0.0.0.0", env="APP_HOST")
    app_port: int = Field(8000, env="APP_PORT")

    # Новое поле: каталог с документами (может быть пустым)
    # documents_dir: Optional[str] = Field(None, env="DOCUMENTS_DIR")

    # выходные каталоги для сохранения оригиналов и текстов (опционально)
    output_originals_dir: Optional[str] = Field(None, env="OUTPUT_ORIGINALS_DIR")
    output_texts_dir: Optional[str] = Field(None, env="OUTPUT_TEXTS_DIR")
    hostfs: Optional[str] = Field(None, env="HOSTFS")
    httpfs: Optional[str] = Field(None, env="HTTPFS")

    # JWT settings
    jwt_secret: SecretStr = Field(..., env="JWT_SECRET")
    jwt_expire_minutes: int = Field(60, env="JWT_EXPIRE_MINUTES")
    # BROKER
    redis_url: Optional[str] = Field(None, env="REDIS_URL")
    dramatiq_ns: Optional[str] = Field(None, env="DRAMATIQ_NS")

    # жёстко указываем .env в корне проекта
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
    )
settings = Settings()


import os
from typing import Optional
from pydantic import SecretStr, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    database_url: SecretStr = Field(..., env="DATABASE_URL")
    env: str = Field("dev", env="ENV")
    documents_dir: Optional[str] = Field(None, env="DOCUMENTS_DIR")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    APP_PORT: int = Field(8000, env="APP_PORT")

    # Новое поле: каталог с документами (может быть пустым)
    documents_dir: Optional[str] = Field(None, env="DOCUMENTS_DIR")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

settings = Settings()

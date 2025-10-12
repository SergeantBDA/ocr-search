# app/config.py
from __future__ import annotations
import os, json
from pathlib import Path
from typing import Optional, List
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# ── 1) найдём .env ────────────────────────────────────────────────────────────
def _find_env_file() -> Optional[str]:
    # сначала текущая директория запуска
    cwd = Path.cwd() / ".env"
    if cwd.exists():
        return str(cwd)
    # затем рядом с этим файлом (до 3 уровней вверх)
    here = Path(__file__).resolve()
    for up in (1, 2, 3):
        p = here.parents[up] / ".env"
        if p.exists():
            return str(p)
    # явный путь через переменную окружения
    x = os.getenv("APP_ENV_FILE")
    return x if x and Path(x).exists() else None

ENV_FILE = _find_env_file()
'''
# ── 2) Загрузим .env в окружение "жёстко" ─────────────────────────────────────
try:
    from dotenv import load_dotenv  # pip install python-dotenv
except Exception:
    load_dotenv = None

if ENV_FILE and load_dotenv:
    # override=True — перезапишет уже установленные, чтобы не тащить "старые" пустые значения
    load_dotenv(ENV_FILE, override=True)
    print(f"[config] Loaded .env into os.environ: {ENV_FILE}")
else:
    print(f"[config] .env not auto-loaded (ENV_FILE={ENV_FILE!r}, have_dotenv={bool(load_dotenv)})")
'''
# ── 3) Модель настроек ────────────────────────────────────────────────────────
class Settings(BaseSettings):
    # базовые
    database_url: Optional[SecretStr] = Field(None, env="DATABASE_URL")

    jwt_secret:   Optional[SecretStr] = Field(None, env="JWT_SECRET")
    jwt_expire_minutes: int = Field(60, env="JWT_EXPIRE_MINUTES")

    env: str  = Field("dev", env="ENV")
    app_host: str = Field("0.0.0.0", env="APP_HOST")
    app_port: int = Field(8000, env="APP_PORT")

    output_originals_dir: Optional[str] = Field(None, env="OUTPUT_ORIGINALS_DIR")
    output_texts_dir: Optional[str]     = Field(None, env="OUTPUT_TEXTS_DIR")
    
    hostfs: Optional[str] = Field(None, env="HOSTFS")
    httpfs: Optional[str] = Field(None, env="HTTPFS")

    redis_url: Optional[str] = Field(None, env="REDIS_URL")
    dramatiq_ns: Optional[str] = Field(None, env="DRAMATIQ_NS")
    api_secret: Optional[str] = Field(None, env="API_SECRET")

    # ЛАКОНИЧНАЯ конфигурация: берём только окружение (мы его уже заполнили load_dotenv)
    model_config = SettingsConfigDict(
        extra="ignore",
        case_sensitive=False,   # безопаснее на Win/PwSh
    )

    @property
    def api_keys(self) -> List[str]:
        v = (self.api_secret or "").strip()
        if not v:
            return []
        if v.startswith("[") and v.endswith("]"):
            try:
                arr = json.loads(v)
                return [str(x).strip() for x in arr if str(x).strip()]
            except Exception:
                pass
        return [x.strip() for x in v.split(",") if x.strip()]

settings = Settings(_env_file=ENV_FILE)

# В прод-окружении требуем обязательные поля
if settings.env != "dev":
    if not settings.database_url or not settings.jwt_secret:
        raise RuntimeError(f"Missing DATABASE_URL / JWT_SECRET (env={settings.env}, file={ENV_FILE!r})")

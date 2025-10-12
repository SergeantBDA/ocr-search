# app/api/deps.py
from fastapi import HTTPException, Security, status, Request
from fastapi.security import APIKeyHeader
from app.config import settings

# Разрешим оба варианта имени — обычно APIKeyHeader и так case-insensitive,
# но так явно и читаемо:
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def require_api_key(request: Request, key: str = Security(api_key_header)) -> str:
    # Дополнительно попробуем из Authorization: ApiKey <key>
    if not key:
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("apikey "):
            key = auth.split(" ", 1)[1].strip()

    # Диагностика (на время): покажем, что пришло на сервер
    # print("X-API-Key:", key, "configured keys:", settings.api_keys)

    if not key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing API key")

    if key not in set(settings.api_keys):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")

    return key

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

from app.web.routes import router as web_router
from app.config import settings

import logging

logger = logging.getLogger("uvicorn.error")
logger.setLevel(logging.INFO)

fh = logging.FileHandler("uvicorn.log", encoding="utf-8")
formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
fh.setFormatter(formatter)
logger.addHandler(fh)

app = FastAPI(title="OCR Service")

# Простая CORS-конфигурация — при необходимости ограничьте origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Регистрируем веб-маршруты (index, search, upload)
app.include_router(web_router)

# Простой лог на старте
@app.on_event("startup")
async def on_startup():
    logger.info("Starting OCR Service (env=%s)", settings.env)


@app.on_event("shutdown")
async def on_shutdown():
    logger.info("Shutting down OCR Service")

@app.get("/healthz")
def healthz():
    return {"ok": True}

if __name__ == "__main__":
    # Запуск через `python -m app.main` (опционально); обычно запускается через uvicorn
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=str(settings.app_host),
        port=settings.app_port,
        log_level="info",
        reload=(settings.env == "dev"),
    )

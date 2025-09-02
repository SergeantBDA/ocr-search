from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.openapi.docs import get_swagger_ui_html
from swagger_ui_bundle import swagger_ui_path


from app.web.routes import router as web_router
from app.config import settings

import logging

logger = logging.getLogger("uvicorn.error")
logger.setLevel(logging.INFO)

fh = logging.FileHandler("uvicorn.log", encoding="utf-8")
formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
fh.setFormatter(formatter)
logger.addHandler(fh)

app = FastAPI(
    title="OCR Search",
    version="0.1.0",
    docs_url=None,                 # отключаем дефолтные /docs
    openapi_url="/openapi.json",
    openapi_version="3.0.3",       # <<< важная строка: откат на 3.0.x
)

# раздаём локальные файлы Swagger UI
app.mount("/swagger-ui", StaticFiles(directory=swagger_ui_path), name="swagger_ui")

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
 
@app.get("/docs", include_in_schema=False)
def custom_swagger_ui_html():
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title="API Docs",
        swagger_js_url="/swagger-ui/swagger-ui-bundle.js",
        swagger_css_url="/swagger-ui/swagger-ui.css",
    )

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


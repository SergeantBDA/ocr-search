from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import logging
import uvicorn

from app.web.routes import router as web_router
from app.config import settings
from app.logger import logger as app_logger, attach_to_logger_names
from swagger_ui_bundle import swagger_ui_path

# ensure uvicorn/fastapi use same handlers
attach_to_logger_names()

app = FastAPI(
    title="OCR Search",
    version="0.1.0",
    docs_url=None,
    openapi_url="/openapi.json",
    openapi_version="3.0.3",
)

# CORS (allow all for dev; restrict in prod)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# mount swagger static files (optional)
app.mount("/swagger-ui", StaticFiles(directory=swagger_ui_path), name="swagger_ui")

# include routes
app.include_router(web_router)

@app.on_event("startup")
async def on_startup():
    app_logger.info("START")

@app.on_event("shutdown")
async def on_shutdown():
    app_logger.info("STOP")

if __name__ == "__main__":
    # ensure uvicorn uses our logger handlers/level
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"):
        lg = logging.getLogger(name)
        lg.handlers = app_logger.handlers[:]
        lg.setLevel(app_logger.level)
        lg.propagate = False

    uvicorn.run(
        "app.main:app",
        host=str(settings.app_host),
        port=int(settings.app_port),
        log_level="info",
        reload=(getattr(settings, "env") == "dev"),
    )


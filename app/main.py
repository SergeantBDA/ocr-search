from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request
from starlette.status import HTTP_401_UNAUTHORIZED
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.responses import RedirectResponse, JSONResponse

import logging
import uvicorn

from app.web.public import router as public_router
from app.api.upload import router as api_router
from app.routers import auth as auth_router_module
from app.web.routes import router as web_router
from app.web.admin_jobs import router as admin_jobs_router

from app.config import settings
from app.logger import logger as app_logger, attach_to_logger_names

from datetime import datetime, timedelta
from app.broker.config import r, NS
import json

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

#from starlette.middleware.proxy_headers import ProxyHeadersMiddleware
#app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")

# mount static dir if exists
try:
    app.mount("/static", StaticFiles(directory="app/static"), name="static")
except Exception:
    pass

# public pages (login/register)
app.include_router(public_router)
# API endpoints
app.include_router(api_router, dependencies=[])
# include auth router (public API endpoints)
app.include_router(auth_router_module.router, prefix="/auth")
# protected web router
app.include_router(web_router)
# admin jobs
app.include_router(admin_jobs_router)

# 401 handler: redirect browsers to /login (except whitelist)
WHITELIST_PREFIXES = ("/auth", "/login", "/register", "/openapi.json", "/docs", "/swagger-ui", "/static")
STALE_AFTER_MIN = 360

@app.on_event("startup")
async def sweep_stale_jobs():
    now = datetime.utcnow()
    for key in r.scan_iter(f"{NS}:job:*"):
        raw = r.get(key)
        if not raw: continue
        try:
            job = json.loads(raw)
            created = datetime.fromisoformat(job.get("created_at", "1970-01-01T00:00:00"))
            if job.get("status") in (None, "started", "queued") and now - created > timedelta(minutes=STALE_AFTER_MIN):
                r.delete(key)
        except Exception:
            r.delete(key)

@app.exception_handler(HTTP_401_UNAUTHORIZED)
async def on_401(request: Request, exc: StarletteHTTPException):
    accept = request.headers.get("accept", "")
    path = request.url.path or ""
    # Для API — не перетирать detail, показывать, что именно не так
    if path.startswith("/api"):
        return JSONResponse({"detail": getattr(exc, "detail", "Unauthorized")}, status_code=401)

    # Для браузера — редирект на логин (как было)
    if "text/html" in accept and not any(path.startswith(p) for p in WHITELIST_PREFIXES):
        return RedirectResponse(url="/auth/login-web")
    return JSONResponse({"detail": "Not authenticated"}, status_code=401)


@app.on_event("startup")
async def on_startup():
    app_logger.info("🚀 OCR-SEARCH запущен")


@app.on_event("shutdown")
async def on_shutdown():
    app_logger.info("🛑 OCR-SEARCH остановлен")


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
        reload=(getattr(settings, "env", "dev") == "dev"),
        proxy_headers=True,
        forwarded_allow_ips="*"
    )


from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/web/templates")
router = APIRouter(tags=["public"])


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})


@router.post("/logout")
def logout():
    # Клиент должен очистить localStorage.token; серверный выход — no-op
    return JSONResponse({"ok": True})
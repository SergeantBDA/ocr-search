from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/web/templates")
router = APIRouter(tags=["public"])


@router.get("/login-web", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})


@router.post("/logout")
def logout():
    """
    Server-side logout: remove HttpOnly cookie (if установлен) and return JSON.
    Client should also clear localStorage token and redirect.
    """
    resp = JSONResponse({"ok": True})
    # remove cookie on client (sets Set-Cookie with expired value)
    resp.delete_cookie("access_token", path="/")
    return resp
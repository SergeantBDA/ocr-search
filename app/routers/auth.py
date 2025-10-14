from fastapi import APIRouter, Depends, HTTPException, status, Request, Form
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_session, SessionLocal
from app.models import User
from app.schemas import UserCreate, UserRead, Token
from app.services.auth import get_password_hash, verify_password, create_access_token, get_current_user, _get_user_by_email
from app.services.auth import oauth2_scheme  # exported for docs if needed
import app.services.mailer as mailer
import random

router = APIRouter(tags=["auth"])
templates = Jinja2Templates(directory="app/web/templates")

@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})
    
@router.get("/login-web", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@router.post("/register", response_model=UserRead, status_code=201)
def register(user_in: UserCreate, db: Session = Depends(get_session)):
    email = user_in.email.lower()
    # check exists
    existing = db.query(User).filter(User.email == email).one_or_none()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    _pass_with_suffix = f'{user_in.password}{str(random.randint(0, 99))}'
    _email_sent = mailer.send_email(to_email=email,subject ='Пароль для доступа на сервис docslook.interrao.ru',body=_pass_with_suffix)
    if _email_sent == 0:
         raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Problems with sending mail")
    hashed = get_password_hash(_pass_with_suffix)
    user = User(email=email, password_hash=hashed)
    db.add(user)
    try:
        db.commit()
        db.refresh(user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    #return UserRead.from_orm(user)
    return UserRead.model_validate(user, from_attributes=True)

@router.post("/login-web")
def login_web(request: Request, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_session)):
    """
    Web login: accept OAuth2 form (username=email, password), set HttpOnly cookie with JWT and redirect to "/".
    """
    email = (form_data.username or "").lower()
    user = db.query(User).filter(User.email == email).one_or_none()
    # print(user, 
    #       form_data.password, 
    #       form_data.username, 
    #       verify_password(form_data.password, user.password_hash))
    if not user or not verify_password(form_data.password, user.password_hash):
        #raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password", headers={"WWW-Authenticate": "Bearer"})
        return templates.TemplateResponse("login.html", {"request": request, "error":True, "email":email}, status_code=200)
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User inactive")

    access_token = create_access_token(data={"sub": str(user.id)})
    resp = RedirectResponse(url="/", status_code=303)
    # set HttpOnly cookie; secure=True as required (may block in local http)
    resp.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=True,
        samesite="none",
        max_age=3600,
        path="/",
    )
    return resp

@router.post("/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_session)):
    # OAuth2PasswordRequestForm has username field — we use it as email
    email = (form_data.username or "").lower()
    user = db.query(User).filter(User.email == email).one_or_none() 
    
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password", headers={"WWW-Authenticate": "Bearer"})
    if not verify_password(form_data.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password", headers={"WWW-Authenticate": "Bearer"})
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User inactive")

    access_token = create_access_token(data={"sub": str(user.id)})
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me", response_model=UserRead)
def me(current_user: User = Depends(get_current_user)):
    return UserRead.model_validate(current_user, from_attributes=True)
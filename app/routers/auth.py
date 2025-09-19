from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_session, SessionLocal
from app.models import User
from app.schemas import UserCreate, UserRead, Token
from app.services.auth import get_password_hash, verify_password, create_access_token, get_current_user, _get_user_by_email
from app.services.auth import oauth2_scheme  # exported for docs if needed

router = APIRouter(tags=["auth"])


@router.post("/register", response_model=UserRead, status_code=201)
def register(user_in: UserCreate, db: Session = Depends(get_session)):
    email = user_in.email.lower()
    # check exists
    existing = db.query(User).filter(User.email == email).one_or_none()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    hashed = get_password_hash(user_in.password)
    user = User(email=email, password_hash=hashed)
    db.add(user)
    try:
        db.commit()
        db.refresh(user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    return UserRead.from_orm(user)


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
    return UserRead.from_orm(current_user)
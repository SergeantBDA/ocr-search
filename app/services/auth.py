from datetime import datetime, timedelta
from typing import Optional, Any, Dict

from passlib.context import CryptContext
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.models import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=settings.jwt_expire_minutes))
    to_encode.update({"exp": expire})
    key = settings.jwt_secret.get_secret_value()
    encoded_jwt = jwt.encode(to_encode, key, algorithm="HS256")
    return encoded_jwt


def _get_user_by_id(session: Session, user_id: int) -> Optional[User]:
    return session.query(User).filter(User.id == user_id).one_or_none()


def _get_user_by_email(session: Session, email: str) -> Optional[User]:
    return session.query(User).filter(User.email == email).one_or_none()


def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.jwt_secret.get_secret_value(), algorithms=["HS256"])
        sub = payload.get("sub")
        if sub is None:
            raise credentials_exception
        user_id = int(sub)
    except JWTError:
        raise credentials_exception

    db = SessionLocal()
    try:
        user = _get_user_by_id(db, user_id)
    finally:
        db.close()

    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found", headers={"WWW-Authenticate": "Bearer"})
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User inactive")
    return user
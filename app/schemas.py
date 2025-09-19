from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, constr, EmailStr, ConfigDict


class DocumentRead(BaseModel):
    id: int
    filename: str
    snippet: Optional[str] = None

    # ключ для работы с ORM-моделями (SQLAlchemy)
    model_config = ConfigDict(from_attributes=True)


# Note: no input schema exposes filename or meta — those are filled server-side only.
class DocumentCreate(BaseModel):
    # intentionally empty: uploads are performed via multipart/form-data,
    # and filename/meta are set by server from UploadFile info
    pass

class UserCreate(BaseModel):
    email: EmailStr
    password: constr(min_length=8)

class UserRead(BaseModel):
    id: int
    email: EmailStr
    created_at: datetime

    # ключ для работы с ORM-моделями (SQLAlchemy)
    model_config = ConfigDict(from_attributes=True)

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
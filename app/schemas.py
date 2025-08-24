from typing import Optional
from pydantic import BaseModel


class DocumentRead(BaseModel):
    id: int
    filename: str
    snippet: Optional[str] = None

    class Config:
        orm_mode = True


# Note: no input schema exposes filename or meta — those are filled server-side only.
class DocumentCreate(BaseModel):
    # intentionally empty: uploads are performed via multipart/form-data,
    # and filename/meta are set by server from UploadFile info
    pass
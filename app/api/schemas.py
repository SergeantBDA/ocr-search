from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class JobStatus(BaseModel):
    job_id: str
    status: str  # queued, processing, completed, error
    progress: int = Field(..., ge=0, le=100)
    total: int = 0
    done: int = 0
    error: Optional[str] = None
    created_at: Optional[str] = None


class UploadResponse(BaseModel):
    ok: bool = True
    job_id: str
    queued: int
    prefix: str


class SearchRequest(BaseModel):
    q: str = Field("", description="Search query")
    limit: int = Field(20, ge=1, le=100)
    offset: int = Field(0, ge=0)
    ocr_user: Optional[str] = Field(None, description="Filter by user email")
    ocr_from: Optional[str] = Field(None, description="Filter from date (ISO format)")
    ocr_to: Optional[str] = Field(None, description="Filter to date (ISO format)")


class SearchItem(BaseModel):
    document_id: int
    title: str
    score: float = 0.0
    snippet: str
    path: Optional[str] = None


class SearchResponse(BaseModel):
    query: str
    total: int
    items: List[SearchItem]
    limit: int
    offset: int
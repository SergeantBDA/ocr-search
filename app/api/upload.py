from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, File, UploadFile, Depends, HTTPException, Form, Request
from sqlalchemy.orm import Session

from app.api.deps import require_api_key
from app.api.schemas import JobStatus, UploadResponse, SearchRequest, SearchResponse, SearchItem
from app.services.uploads import save_files, enqueue_job, get_job_status
from app.db import get_session
from app import search as search_module

router = APIRouter(prefix="/api", tags=["api"])

# ALLOWED_EXTENSIONS = {".docx",".xls",".xlsx",".csv",".eml", ".msg",".txt",".html",".htm",".xhtml", \
#                       ".rtf" ,".xml",".pdf",".png", ".jpg",".jpeg",".tif",".tiff",".bmp"}

@router.get("/ping")
async def api_ping(request: Request, _k: str = Depends(require_api_key)):
    return {
        "ok": True,
        "x_api_key": request.headers.get("x-api-key"),
        "accepted": True
    }

@router.post("/debug")
async def api_debug(request: Request):
    """
    Debug endpoint to echo request details.
    """
    headers = dict(request.headers)
    client_host = request.client.host if request.client else "unknown"
    try:
        body = await request.json()
    except Exception:
        body = await request.body()
        body = body.decode("utf-8", errors="ignore")
    
    return {
        "method": request.method,
        "url": str(request.url),
        "client_host": client_host,
        "headers": headers,
        "body": body
    }

@router.post("/upload", response_model=UploadResponse)
async def api_upload(
    files: List[UploadFile] = File(...),
    owner: str = Form("api"),
    owner_email: str = Form("api@local"),
    _api_key: str = Depends(require_api_key)
):
    """
    Upload files for OCR processing via API.
    Files are saved and queued for background processing.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")
    
    # Validate file extensions
    valid_files = files
    # valid_files = []
    # for f in files:
    #     if not f.filename:
    #         continue
        
    #     ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
    #     if f".{ext}" not in ALLOWED_EXTENSIONS:
    #         raise HTTPException(
    #             status_code=400, 
    #             detail=f"Unsupported file type: {f.filename}. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
    #         )
    #     valid_files.append(f)
    
    # if not valid_files:
    #     raise HTTPException(status_code=400, detail="No valid files to process")
    
    try:
        # Save files and create directories
        prefix, saved_files, texts_dir, upload_dir = save_files(valid_files, owner)
        
        # Enqueue processing job
        job_id = enqueue_job(saved_files, texts_dir, owner_email)
        
        return UploadResponse(
            job_id=job_id,
            queued=len(saved_files),
            prefix=prefix
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@router.get("/jobs/{job_id}", response_model=JobStatus)
def api_job_status(
    job_id: str,
    _api_key: str = Depends(require_api_key)
):
    """
    Get status of a background OCR job.
    """
    status_info = get_job_status(job_id)
    return JobStatus(**status_info)


@router.post("/search", response_model=SearchResponse)
def api_search(
    request: SearchRequest,
    db: Session = Depends(get_session),
    _api_key: str = Depends(require_api_key)
):
    """
    Search through OCR-processed documents.
    """
    def _parse_dt(val: Optional[str]) -> Optional[datetime]:
        if not val:
            return None
        try:
            return datetime.fromisoformat(val)
        except ValueError:
            return None
    
    # Parse date filters
    ocr_from = _parse_dt(request.ocr_from)
    ocr_to = _parse_dt(request.ocr_to)
    
    try:
        print(request)
        # Use existing search module
        result = search_module.search_documents(
            db, 
            q=request.q,
            ocr_user=request.ocr_user,
            ocr_from=ocr_from,
            ocr_to=ocr_to,
            limit=request.limit,
            offset=request.offset
        )
        
        # Transform to API format
        items = []
        for item in result.get("items", []):
            # Extract score from snippet if available or default
            score = 0.5  # Default relevance score
            
            items.append(SearchItem(
                document_id=item["id"] or 0,
                title=item["filename"] or "Untitled",
                score=score,
                snippet=item.get("snippet", ""),
                path=item.get("link")
            ))
        
        return SearchResponse(
            query=request.q,
            total=result.get("total", 0),
            items=items,
            limit=request.limit,
            offset=request.offset
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")
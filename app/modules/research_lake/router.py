"""Research Data Lake API router — /api/v1/datalake/* endpoints and HTML view routes."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from loguru import logger

from app.dependencies import get_current_user, get_current_user_optional
from app.models.user import User
from app.schemas.document import (
    DocumentListItem,
    DocumentResponse,
    DocumentIngestRequest,
    SearchQuery,
    SearchResult,
    QARequest,
    QAResponse,
    RatingUpdate,
    SourceType,
)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# Max upload size: 50 MB
_MAX_FILE_BYTES = 50 * 1024 * 1024
# Upload directory
_UPLOAD_DIR = Path("uploads/research")


def _ensure_upload_dir() -> Path:
    _UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    return _UPLOAD_DIR


# ── API routes ────────────────────────────────────────────────────────────────

@router.get("/documents", response_model=list[DocumentListItem])
async def list_documents(
    limit: int = 30,
    offset: int = 0,
    asset_class: str | None = None,
    current_user: User = Depends(get_current_user),
) -> list[DocumentListItem]:
    """Return a paginated list of documents in the data lake."""
    from app.modules.research_lake.service import ResearchLakeService
    from app.core.database import get_db_session

    async with get_db_session() as db:
        service = ResearchLakeService(db)
        return await service.list_documents(limit, offset, asset_class)


@router.post("/ingest", response_model=DocumentResponse)
async def ingest_document(
    body: DocumentIngestRequest,
    current_user: User = Depends(get_current_user),
) -> DocumentResponse:
    """Ingest a text document into the data lake (JSON body)."""
    from app.modules.research_lake.service import ResearchLakeService
    from app.core.database import get_db_session

    async with get_db_session() as db:
        service = ResearchLakeService(db)
        return await service.ingest_document(body, current_user.email)


@router.post("/ingest-text", response_model=DocumentResponse)
async def ingest_text(
    title: str,
    content: str,
    source_name: str | None = None,
    asset_class: str | None = None,
    tag: str | None = None,
    current_user: User = Depends(get_current_user),
) -> DocumentResponse:
    """Ingest pasted plain text into the data lake."""
    from app.modules.research_lake.service import ResearchLakeService
    from app.core.database import get_db_session

    # Map raw asset_class string → AssetClass enum if valid, else None
    from app.schemas.document import AssetClass as AssetClassEnum
    mapped_ac: AssetClassEnum | None = None
    if asset_class:
        try:
            mapped_ac = AssetClassEnum(asset_class.upper())
        except ValueError:
            mapped_ac = None

    body = DocumentIngestRequest(
        title=title,
        source_type=SourceType.PASTE,
        source_name=source_name,
        text_content=content,
        asset_class=mapped_ac,
        tag=tag,
    )

    async with get_db_session() as db:
        service = ResearchLakeService(db)
        return await service.ingest_document(body, current_user.email)


@router.post("/upload", response_model=DocumentResponse)
async def upload_file(
    file: UploadFile = File(...),
    title: str = Form(""),
    source_name: str = Form(""),
    asset_class: str = Form(""),
    tag: str = Form(""),
    current_user: User = Depends(get_current_user),
) -> DocumentResponse:
    """Upload a PDF, TXT, or DOCX file and ingest it into the data lake.

    Saves the file to uploads/research/ and processes synchronously.
    Max file size: 50 MB.
    """
    from fastapi import HTTPException
    from app.modules.research_lake.service import ResearchLakeService
    from app.core.database import get_db_session
    import aiofiles

    content = await file.read()
    if len(content) > _MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds maximum size of 50 MB")

    filename = file.filename or "upload"
    suffix = Path(filename).suffix.lower().lstrip(".")
    if suffix not in ("pdf", "txt", "md", "docx"):
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported file type: {suffix}. Supported: pdf, txt, md, docx",
        )

    upload_dir = _ensure_upload_dir()
    import uuid
    safe_name = f"{uuid.uuid4().hex}_{filename}"
    dest_path = upload_dir / safe_name

    async with aiofiles.open(dest_path, "wb") as f:
        await f.write(content)

    logger.info(f"File saved: {dest_path} ({len(content)} bytes)")

    doc_title = title.strip() or Path(filename).stem.replace("-", " ").replace("_", " ")

    # Map asset_class
    from app.schemas.document import AssetClass as AssetClassEnum
    mapped_ac: AssetClassEnum | None = None
    if asset_class:
        try:
            mapped_ac = AssetClassEnum(asset_class.upper())
        except ValueError:
            mapped_ac = None

    async with get_db_session() as db:
        service = ResearchLakeService(db)
        return await service.ingest_file(
            file_path=str(dest_path),
            filename=filename,
            file_type=suffix,
            uploaded_by=current_user.email,
            title=doc_title,
            source_name=source_name.strip() or None,
            asset_class=mapped_ac,
            tag=tag.strip() or None,
        )


@router.post("/upload-pdf", response_model=DocumentResponse)
async def upload_pdf(
    file: UploadFile = File(...),
    title: str = "",
    asset_class: str | None = None,
    current_user: User = Depends(get_current_user),
) -> DocumentResponse:
    """Upload a PDF and ingest it into the data lake (legacy endpoint)."""
    from app.modules.research_lake.service import ResearchLakeService
    from app.core.database import get_db_session

    async with get_db_session() as db:
        service = ResearchLakeService(db)
        return await service.ingest_pdf(file, title, asset_class, current_user.email)


@router.get("/documents/{doc_id}", response_model=DocumentResponse)
async def get_document(
    doc_id: str,
    current_user: User = Depends(get_current_user),
) -> DocumentResponse:
    """Return a single document record."""
    from fastapi import HTTPException
    from app.modules.research_lake.service import ResearchLakeService
    from app.core.database import get_db_session

    async with get_db_session() as db:
        service = ResearchLakeService(db)
        from sqlalchemy import select
        from app.models.document import Document
        result = await db.execute(select(Document).where(Document.id == doc_id))
        doc = result.scalar_one_or_none()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        return DocumentResponse.model_validate(doc)


@router.delete("/documents/{doc_id}")
async def delete_document(
    doc_id: str,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Delete a document and all its chunks."""
    from fastapi import HTTPException
    from sqlalchemy import delete as sql_delete
    from app.models.document import Document, DocumentChunk
    from app.core.database import get_db_session

    async with get_db_session() as db:
        from sqlalchemy import select
        result = await db.execute(select(Document).where(Document.id == doc_id))
        doc = result.scalar_one_or_none()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        # Chunks will be cascade-deleted, but we do explicit delete for safety
        await db.execute(sql_delete(DocumentChunk).where(DocumentChunk.document_id == doc_id))
        await db.delete(doc)

    logger.info(f"Document {doc_id} deleted by {current_user.email}")
    return {"deleted": True, "document_id": doc_id}


@router.post("/search", response_model=list[SearchResult])
async def search_documents(
    body: SearchQuery,
    current_user: User = Depends(get_current_user),
) -> list[SearchResult]:
    """Semantic search across all documents in the data lake."""
    from app.modules.research_lake.service import ResearchLakeService
    from app.core.database import get_db_session

    async with get_db_session() as db:
        service = ResearchLakeService(db)
        return await service.semantic_search(body)


@router.get("/search")
async def search_documents_get(
    q: str,
    limit: int = 10,
    asset_class: str | None = None,
    current_user: User = Depends(get_current_user),
) -> list[SearchResult]:
    """GET-based semantic search for the HTML frontend."""
    from app.modules.research_lake.service import ResearchLakeService
    from app.core.database import get_db_session
    from app.schemas.document import AssetClass as AssetClassEnum

    mapped_ac: AssetClassEnum | None = None
    if asset_class:
        try:
            mapped_ac = AssetClassEnum(asset_class.upper())
        except ValueError:
            mapped_ac = None

    query = SearchQuery(query=q, limit=limit, asset_class=mapped_ac)
    async with get_db_session() as db:
        service = ResearchLakeService(db)
        return await service.semantic_search(query)


@router.post("/qa", response_model=QAResponse)
async def question_answer(
    body: QARequest,
    current_user: User = Depends(get_current_user),
) -> QAResponse:
    """Ask a question and get a cited answer from the data lake."""
    from app.modules.research_lake.service import ResearchLakeService
    from app.core.database import get_db_session

    async with get_db_session() as db:
        service = ResearchLakeService(db)
        return await service.qa_with_citations(body)


@router.patch("/documents/{doc_id}/rating")
async def rate_document(
    doc_id: str,
    body: RatingUpdate,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Update the quality rating for a document (1–5 stars)."""
    from app.modules.research_lake.service import ResearchLakeService
    from app.core.database import get_db_session

    async with get_db_session() as db:
        service = ResearchLakeService(db)
        await service.rate_document(doc_id, body.rating)
    return {"rated": True, "rating": body.rating}


# ── HTML view routes ──────────────────────────────────────────────────────────

@router.get("/view", response_class=HTMLResponse)
async def view_research_lake(
    request: Request,
    current_user: User | None = Depends(get_current_user_optional),
) -> HTMLResponse:
    """HTML page: Research Lake main view with search, Q&A, and document list."""
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)

    # Load document list for the table
    documents: list[DocumentListItem] = []
    try:
        from app.modules.research_lake.service import ResearchLakeService
        from app.core.database import get_db_session

        async with get_db_session() as db:
            service = ResearchLakeService(db)
            documents = await service.list_documents(limit=50)
    except Exception:
        pass

    return templates.TemplateResponse(
        "research_lake/search.html",
        {
            "request": request,
            "user": current_user,
            "active_nav": "datalake",
            "documents": documents,
        },
    )


@router.get("/view/upload", response_class=HTMLResponse)
async def view_upload_form(
    request: Request,
    current_user: User | None = Depends(get_current_user_optional),
) -> HTMLResponse:
    """HTML page: document upload form."""
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)

    return templates.TemplateResponse(
        "research_lake/upload.html",
        {
            "request": request,
            "user": current_user,
            "active_nav": "datalake",
        },
    )


@router.get("/view/{doc_id}", response_class=HTMLResponse)
async def view_document_detail(
    doc_id: str,
    request: Request,
    current_user: User | None = Depends(get_current_user_optional),
) -> HTMLResponse:
    """HTML page: document detail view."""
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)

    document = None
    try:
        from app.modules.research_lake.service import ResearchLakeService
        from app.core.database import get_db_session
        from sqlalchemy import select
        from app.models.document import Document

        async with get_db_session() as db:
            result = await db.execute(select(Document).where(Document.id == doc_id))
            doc = result.scalar_one_or_none()
            if doc:
                document = DocumentResponse.model_validate(doc)
    except Exception:
        pass

    return templates.TemplateResponse(
        "research_lake/search.html",
        {
            "request": request,
            "user": current_user,
            "active_nav": "datalake",
            "document": document,
        },
    )

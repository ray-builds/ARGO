"""Pydantic schemas for the Research Data Lake module."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class SourceType(str, Enum):
    """Document ingestion source types."""
    PDF = "PDF"
    EMAIL = "EMAIL"
    PASTE = "PASTE"
    PODCAST = "PODCAST"
    NOTE = "NOTE"


class AssetClass(str, Enum):
    """Asset class classification for documents."""
    RATES = "RATES"
    CREDIT = "CREDIT"
    EQUITY = "EQUITY"
    FX = "FX"
    MACRO = "MACRO"
    COMMODITIES = "COMMODITIES"


class DocumentListItem(BaseModel):
    """Document summary for list views."""
    id: str
    title: str
    source_type: SourceType
    source_name: Optional[str] = None
    asset_class: Optional[AssetClass] = None
    quality_rating: Optional[int] = Field(None, ge=1, le=5)
    uploaded_by_email: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentResponse(DocumentListItem):
    """Full document record with content."""
    content_raw: Optional[str] = None
    original_filename: Optional[str] = None
    tag: Optional[str] = None


class DocumentIngestRequest(BaseModel):
    """Request to ingest a new document into the data lake."""
    title: str
    source_type: SourceType = SourceType.PASTE
    source_name: Optional[str] = None
    text_content: Optional[str] = None
    asset_class: Optional[AssetClass] = None
    tag: Optional[str] = None


class SearchQuery(BaseModel):
    """Semantic search query for the data lake."""
    query: str
    asset_class: Optional[AssetClass] = None
    limit: int = Field(8, ge=1, le=50)


class SearchResult(BaseModel):
    """Single result from semantic document search."""
    document_id: str
    document_title: str
    chunk_text: str
    similarity_score: float
    source_name: Optional[str] = None


class QARequest(BaseModel):
    """Question-answering request against the data lake."""
    question: str
    conversation_id: Optional[str] = None


class QAResponse(BaseModel):
    """Answer with cited source documents."""
    answer: str
    sources: list[dict] = []
    conversation_id: Optional[str] = None


class RatingUpdate(BaseModel):
    """Request to update a document's quality rating."""
    rating: int = Field(..., ge=1, le=5)

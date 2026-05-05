"""Document and DocumentChunk models for the Research Intelligence module."""
from __future__ import annotations
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, SmallInteger, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, generate_uuid

# Valid source types
DOCUMENT_SOURCE_TYPES = ("PDF", "EMAIL", "PASTE", "PODCAST", "NOTE")

# Valid asset classes
DOCUMENT_ASSET_CLASSES = ("RATES", "CREDIT", "EQUITY", "FX", "MACRO", "COMMODITIES")

# Conditionally import pgvector if available (production PostgreSQL only)
try:
    from pgvector.sqlalchemy import Vector as _Vector
    _PGVECTOR_AVAILABLE = True
except ImportError:
    _Vector = None  # type: ignore[assignment,misc]
    _PGVECTOR_AVAILABLE = False


class Document(Base, TimestampMixin):
    """A research document ingested into ARGO's knowledge base.

    Documents can come from PDFs, pasted text, emails, podcast transcripts,
    or manual notes. They are chunked and embedded for RAG retrieval.
    The asset_class and tag fields support filtering in the Research module.
    """
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    # source_type values: 'PDF', 'EMAIL', 'PASTE', 'PODCAST', 'NOTE'
    source_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    original_filename: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    file_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    content_raw: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    asset_class: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    # asset_class values: 'RATES', 'CREDIT', 'EQUITY', 'FX', 'MACRO', 'COMMODITIES'
    tag: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    uploaded_by_email: Mapped[str] = mapped_column(String(255), nullable=False)
    quality_rating: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)

    # Relationship to chunks
    chunks: Mapped[list["DocumentChunk"]] = relationship(
        "DocumentChunk", back_populates="document", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return (
            f"<Document id={self.id!r} title={self.title!r} "
            f"source={self.source_type!r} asset={self.asset_class!r}>"
        )


def _make_embedding_column() -> Any:
    """Return the appropriate column type for embeddings.

    Uses pgvector Vector(1536) when available (PostgreSQL + pgvector extension),
    falls back to Text for dev/SQLite environments.
    """
    if _PGVECTOR_AVAILABLE:
        return mapped_column(_Vector(1536), nullable=True)
    return mapped_column(Text, nullable=True)


class DocumentChunk(Base):
    """A text chunk of a Document, used for vector similarity search (RAG).

    Each document is split into overlapping chunks. The embedding column
    stores the 1536-dim OpenAI/Claude embedding for pgvector similarity search.
    Falls back to Text storage on non-PostgreSQL environments.

    NOTE: The embedding column is NOT included in migration 0001_initial_schema.py
    for SQLite compatibility. Run a separate pgvector migration in production.
    """
    __tablename__ = "document_chunks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # embedding: Vector(1536) when pgvector is available, else Text
    embedding: Mapped[Optional[Any]] = _make_embedding_column()
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationship back to document
    document: Mapped["Document"] = relationship("Document", back_populates="chunks")

    __table_args__ = (
        Index("idx_document_chunks_doc_index", "document_id", "chunk_index"),
    )

    def __repr__(self) -> str:
        return (
            f"<DocumentChunk document_id={self.document_id!r} "
            f"index={self.chunk_index} tokens={self.token_count}>"
        )

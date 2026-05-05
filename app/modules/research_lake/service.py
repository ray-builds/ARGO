"""Research Data Lake service — document ingestion, chunking, embedding, and Q&A."""
from __future__ import annotations

import json
import os
import tempfile
from typing import Any, Optional

from fastapi import UploadFile
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, update

from app.core.claude_client import get_claude_client
from app.models.document import Document, DocumentChunk
from app.modules.research_lake.embeddings import chunk_text, embed_texts
from app.modules.research_lake.prompts import DATALAKE_QA_PROMPT
from app.schemas.document import (
    DocumentListItem,
    DocumentResponse,
    DocumentIngestRequest,
    SearchQuery,
    SearchResult,
    QARequest,
    QAResponse,
    SourceType,
)


class ResearchLakeService:
    """Service for the ARP Global Capital Research Data Lake.

    Handles text/PDF ingestion, automatic chunking, OpenAI embedding generation,
    cosine-similarity semantic search, and RAG Q&A with source citations.
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialise service with DB session.

        Args:
            db: Async SQLAlchemy session.
        """
        self._db = db
        self._claude = get_claude_client()

    async def ingest_document(
        self, data: DocumentIngestRequest, uploaded_by: str
    ) -> DocumentResponse:
        """Ingest a text document, chunk it, and generate embeddings.

        Args:
            data: DocumentIngestRequest with title, content, and metadata.
            uploaded_by: Email of the user uploading the document.

        Returns:
            DocumentResponse for the newly created document.
        """
        doc = Document(
            title=data.title,
            source_type=data.source_type.value,
            source_name=data.source_name,
            content_raw=data.text_content,
            asset_class=data.asset_class.value if data.asset_class else None,
            tag=data.tag,
            uploaded_by_email=uploaded_by,
        )
        self._db.add(doc)
        await self._db.flush()

        if data.text_content:
            await self._embed_document(doc, data.text_content)

        logger.info(f"Document ingested: {doc.id} — {doc.title}")
        return DocumentResponse.model_validate(doc)

    async def ingest_pdf(
        self,
        file: UploadFile,
        title: str,
        asset_class: str | None,
        uploaded_by: str,
    ) -> DocumentResponse:
        """Extract text from a PDF file and ingest it into the data lake.

        Args:
            file: Uploaded PDF file.
            title: Document title (defaults to filename if empty).
            asset_class: Optional asset class classification.
            uploaded_by: Email of the uploading user.

        Returns:
            DocumentResponse for the newly created document.

        Raises:
            ValueError: If the file is not a valid PDF or text extraction fails.
        """
        content = await file.read()
        filename = file.filename or "upload.pdf"
        doc_title = title or filename

        # Extract text from PDF using pdfplumber
        try:
            import pdfplumber
            import io

            text_parts: list[str] = []
            with pdfplumber.open(io.BytesIO(content)) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text() or ""
                    text_parts.append(page_text)
            extracted_text = "\n".join(text_parts)
        except ImportError:
            logger.warning("pdfplumber not installed — storing PDF without text extraction")
            extracted_text = ""
        except Exception as exc:
            logger.exception(f"PDF extraction failed for {filename}: {exc}")
            extracted_text = ""

        doc = Document(
            title=doc_title,
            source_type=SourceType.PDF.value,
            original_filename=filename,
            content_raw=extracted_text,
            asset_class=asset_class,
            uploaded_by_email=uploaded_by,
        )
        self._db.add(doc)
        await self._db.flush()

        if extracted_text:
            await self._embed_document(doc, extracted_text)

        logger.info(f"PDF ingested: {doc.id} — {doc.title} ({len(extracted_text)} chars)")
        return DocumentResponse.model_validate(doc)

    async def _embed_document(self, doc: Document, text: str) -> None:
        """Chunk text and generate + store embeddings for a document.

        Args:
            doc: The Document ORM object to embed.
            text: The full text content to chunk and embed.
        """
        chunks = chunk_text(text, chunk_size=800, overlap=100)
        if not chunks:
            return

        try:
            embeddings = await embed_texts(chunks)
        except Exception as exc:
            logger.warning(f"Embedding generation failed for {doc.id}: {exc}")
            embeddings = [[0.0] * 1536 for _ in chunks]

        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            chunk_obj = DocumentChunk(
                document_id=doc.id,
                chunk_index=i,
                chunk_text=chunk,
                embedding=json.dumps(embedding),
            )
            self._db.add(chunk_obj)

        logger.debug(f"Stored {len(chunks)} chunks for document {doc.id}")

    async def semantic_search(self, query: SearchQuery) -> list[SearchResult]:
        """Search the data lake using semantic similarity.

        Embeds the query and computes cosine similarity against stored chunks.
        Falls back to text-based search if embeddings are unavailable.

        Args:
            query: SearchQuery with query string, optional asset_class filter, and limit.

        Returns:
            List of SearchResult objects ranked by similarity score.
        """
        try:
            query_embedding = await embed_texts([query.query])
            q_vec = query_embedding[0]
        except Exception:
            return await self._text_search(query)

        # Pull all chunks (for small lakes); replace with pgvector in production
        stmt = select(DocumentChunk)
        if query.asset_class:
            stmt = stmt.join(Document).where(
                Document.asset_class == query.asset_class.value
            )
        result = await self._db.execute(stmt)
        chunks = result.scalars().all()

        # Compute cosine similarity
        import math

        scored: list[tuple[float, DocumentChunk]] = []
        for chunk in chunks:
            try:
                stored_vec: list[float] = json.loads(chunk.embedding)
                dot = sum(a * b for a, b in zip(q_vec, stored_vec))
                mag_q = math.sqrt(sum(a ** 2 for a in q_vec)) or 1.0
                mag_s = math.sqrt(sum(b ** 2 for b in stored_vec)) or 1.0
                similarity = dot / (mag_q * mag_s)
                scored.append((similarity, chunk))
            except Exception:
                continue

        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[: query.limit]

        results: list[SearchResult] = []
        doc_ids = {chunk.document_id for _, chunk in top}
        docs_map: dict[str, Document] = {}

        for doc_id in doc_ids:
            doc_result = await self._db.execute(
                select(Document).where(Document.id == doc_id)
            )
            doc = doc_result.scalar_one_or_none()
            if doc:
                docs_map[doc_id] = doc

        for score, chunk in top:
            doc = docs_map.get(chunk.document_id)
            results.append(
                SearchResult(
                    document_id=chunk.document_id,
                    document_title=doc.title if doc else "Unknown",
                    chunk_text=chunk.chunk_text,
                    similarity_score=round(score, 4),
                    source_name=doc.source_name if doc else None,
                )
            )

        return results

    async def _text_search(self, query: SearchQuery) -> list[SearchResult]:
        """Fallback keyword search when embeddings are unavailable.

        Args:
            query: The SearchQuery to execute.

        Returns:
            List of SearchResult objects from text matching.
        """
        result = await self._db.execute(
            select(DocumentChunk)
            .where(DocumentChunk.chunk_text.ilike(f"%{query.query}%"))
            .limit(query.limit)
        )
        chunks = result.scalars().all()
        results = []
        for chunk in chunks:
            doc_result = await self._db.execute(
                select(Document).where(Document.id == chunk.document_id)
            )
            doc = doc_result.scalar_one_or_none()
            results.append(
                SearchResult(
                    document_id=chunk.document_id,
                    document_title=doc.title if doc else "Unknown",
                    chunk_text=chunk.chunk_text,
                    similarity_score=0.5,
                    source_name=doc.source_name if doc else None,
                )
            )
        return results

    async def qa_with_citations(self, request: QARequest) -> QAResponse:
        """Answer a question using retrieved document chunks as context.

        Performs semantic search, then asks Claude to answer with source citations.

        Args:
            request: QARequest with question and optional conversation_id.

        Returns:
            QAResponse with answer text and source document references.
        """
        search_results = await self.semantic_search(
            SearchQuery(query=request.question, limit=6)
        )

        context_parts = []
        sources = []
        for i, sr in enumerate(search_results):
            context_parts.append(
                f"[Source {i + 1}: {sr.document_title}]\n{sr.chunk_text}"
            )
            sources.append({
                "document_id": sr.document_id,
                "title": sr.document_title,
                "snippet": sr.chunk_text[:200],
                "score": sr.similarity_score,
            })

        context = "\n\n".join(context_parts) if context_parts else "No relevant documents found."
        prompt = f"QUESTION: {request.question}\n\nDOCUMENT CONTEXT:\n{context}"

        try:
            answer = await self._claude.complete(
                prompt=prompt,
                system=DATALAKE_QA_PROMPT,
                use_sonnet=True,
                max_tokens=1000,
            )
        except Exception as exc:
            logger.exception(f"Q&A generation failed: {exc}")
            answer = "Unable to generate an answer at this time."

        return QAResponse(
            answer=answer,
            sources=sources,
            conversation_id=request.conversation_id,
        )

    async def list_documents(
        self,
        limit: int = 30,
        offset: int = 0,
        asset_class: str | None = None,
    ) -> list[DocumentListItem]:
        """Return paginated list of documents with optional asset class filter.

        Args:
            limit: Maximum records to return.
            offset: Pagination offset.
            asset_class: Optional asset class filter string.

        Returns:
            List of DocumentListItem objects.
        """
        stmt = select(Document).order_by(desc(Document.created_at)).limit(limit).offset(offset)
        if asset_class:
            stmt = stmt.where(Document.asset_class == asset_class)

        result = await self._db.execute(stmt)
        docs = result.scalars().all()
        return [DocumentListItem.model_validate(d) for d in docs]

    async def ingest_file(
        self,
        file_path: str,
        filename: str,
        file_type: str,
        uploaded_by: str,
        title: str | None = None,
        source_name: str | None = None,
        asset_class: Any | None = None,
        tag: str | None = None,
    ) -> "DocumentResponse":
        """Ingest a file from disk: extract text, chunk, embed, store.

        Args:
            file_path: Absolute path to the saved file on disk.
            filename: Original filename (for display).
            file_type: File extension without dot (``"pdf"``, ``"txt"``, ``"docx"``).
            uploaded_by: Email of the uploading user.
            title: Document title (defaults to filename stem if empty).
            source_name: Optional publisher/source label.
            asset_class: Optional AssetClass enum value.
            tag: Optional freeform tag string.

        Returns:
            DocumentResponse for the newly created document.
        """
        from pathlib import Path
        from app.modules.research_lake.chunker import extract_text_from_file, ResearchError

        doc_title = title or Path(filename).stem.replace("-", " ").replace("_", " ")
        ft = file_type.lower()
        source_type_val = SourceType.PDF.value if ft == "pdf" else SourceType.PASTE.value

        # Extract text
        try:
            extracted_text = extract_text_from_file(file_path, ft)
        except ResearchError as exc:
            logger.warning(f"Text extraction failed for {filename}: {exc}")
            extracted_text = ""

        doc = Document(
            title=doc_title,
            source_type=source_type_val,
            source_name=source_name,
            original_filename=filename,
            file_path=file_path,
            content_raw=extracted_text,
            asset_class=asset_class.value if asset_class and hasattr(asset_class, "value") else asset_class,
            tag=tag,
            uploaded_by_email=uploaded_by,
        )
        self._db.add(doc)
        await self._db.flush()

        if extracted_text:
            await self._embed_document(doc, extracted_text)

        logger.info(f"File ingested: {doc.id} — {doc.title} ({len(extracted_text)} chars)")
        return DocumentResponse.model_validate(doc)

    async def rate_document(self, doc_id: str, rating: int) -> None:
        """Update the quality rating for a document.

        Args:
            doc_id: UUID of the document to rate.
            rating: Quality rating from 1 to 5.
        """
        await self._db.execute(
            update(Document).where(Document.id == doc_id).values(quality_rating=rating)
        )
        logger.info(f"Document {doc_id} rated {rating}/5")

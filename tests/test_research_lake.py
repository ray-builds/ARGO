"""Tests for the Research Lake (vector store + document ingestion) service."""
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from unittest.mock import AsyncMock, patch


class TestResearchLakeService:
    """Tests for document ingestion, chunking, semantic search, and QA."""

    @pytest.mark.asyncio
    async def test_ingest_document_creates_record(
        self,
        test_db: AsyncSession,
        mock_claude_json,
    ) -> None:
        """Ingesting a document creates a ResearchDocument record in the database."""
        from app.services.research_lake import ResearchLakeService

        service = ResearchLakeService(db=test_db)
        doc = await service.ingest_document(
            title="Test Research Note",
            content="The Federal Reserve kept rates unchanged at 4.25%-4.50%.",
            source_name="Internal",
            asset_class="Rates",
        )

        assert doc is not None
        assert doc.id is not None
        assert doc.title == "Test Research Note"
        assert doc.asset_class == "Rates"

    @pytest.mark.asyncio
    async def test_chunk_text_splits_correctly(
        self,
        test_db: AsyncSession,
    ) -> None:
        """chunk_text splits a long document into chunks of the specified max size."""
        from app.services.research_lake import ResearchLakeService

        service = ResearchLakeService(db=test_db)
        long_text = " ".join([f"word{i}" for i in range(1000)])
        chunks = service.chunk_text(long_text, chunk_size=200, overlap=20)

        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk.split()) <= 220  # chunk_size + some tolerance

    @pytest.mark.asyncio
    async def test_chunk_text_overlap_works(
        self,
        test_db: AsyncSession,
    ) -> None:
        """Chunking with overlap produces consecutive chunks that share tokens."""
        from app.services.research_lake import ResearchLakeService

        service = ResearchLakeService(db=test_db)
        text = " ".join([f"word{i}" for i in range(100)])
        chunks = service.chunk_text(text, chunk_size=20, overlap=5)

        # Consecutive chunks should share the overlap words
        assert len(chunks) >= 2
        words_0 = set(chunks[0].split())
        words_1 = set(chunks[1].split())
        assert len(words_0 & words_1) > 0  # Non-empty intersection

    @pytest.mark.asyncio
    async def test_semantic_search_returns_results(
        self,
        test_db: AsyncSession,
    ) -> None:
        """Semantic search over the corpus returns a list of results with similarity scores."""
        from app.services.research_lake import ResearchLakeService
        from unittest.mock import AsyncMock, patch

        with patch.object(
            ResearchLakeService,
            "_get_embedding",
            new_callable=AsyncMock,
            return_value=[0.1] * 1536,
        ):
            with patch.object(
                ResearchLakeService,
                "_vector_search",
                new_callable=AsyncMock,
                return_value=[
                    {
                        "document_id": "doc-001",
                        "title": "Fed policy note",
                        "chunk_text": "Fed held rates at 4.25%",
                        "similarity_score": 0.85,
                        "source_name": "Internal",
                        "asset_class": "Rates",
                    }
                ],
            ):
                service = ResearchLakeService(db=test_db)
                results = await service.semantic_search("Fed interest rate decision", limit=5)

        assert isinstance(results, list)
        assert len(results) > 0
        assert "similarity_score" in results[0]

    @pytest.mark.asyncio
    async def test_qa_with_citations_format(
        self,
        test_db: AsyncSession,
        mock_claude_json,
    ) -> None:
        """QA answer includes a citations list referencing source documents."""
        mock_claude_json.return_value = {
            "answer": "The Fed held rates at 4.25%-4.50%.",
            "citations": [
                {"document_id": "doc-001", "source": "Internal", "excerpt": "rates unchanged"},
            ],
        }

        from app.services.research_lake import ResearchLakeService
        from unittest.mock import AsyncMock, patch

        with patch.object(
            ResearchLakeService,
            "semantic_search",
            new_callable=AsyncMock,
            return_value=[
                {"document_id": "doc-001", "chunk_text": "Fed held rates at 4.25%", "similarity_score": 0.9}
            ],
        ):
            service = ResearchLakeService(db=test_db)
            response = await service.answer_question("What did the Fed do with rates?")

        assert "answer" in response
        assert "citations" in response
        assert isinstance(response["citations"], list)

    @pytest.mark.asyncio
    async def test_rate_document_updates_rating(
        self,
        test_db: AsyncSession,
    ) -> None:
        """Rating a document persists the new star rating to the database."""
        from app.services.research_lake import ResearchLakeService
        from app.models.research_document import ResearchDocument

        doc = ResearchDocument(
            title="Ratable Document",
            content="Some research content.",
            source_name="Goldman Sachs",
            asset_class="Rates",
            star_rating=3,
        )
        test_db.add(doc)
        await test_db.commit()
        await test_db.refresh(doc)

        service = ResearchLakeService(db=test_db)
        await service.rate_document(str(doc.id), star_rating=5)

        await test_db.refresh(doc)
        assert doc.star_rating == 5

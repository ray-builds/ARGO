"""Text chunking and embedding utilities for the Research Data Lake."""
from __future__ import annotations

import os
from typing import Any

from loguru import logger


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 100) -> list[str]:
    """Split text into overlapping chunks for embedding.

    Args:
        text: The full document text to chunk.
        chunk_size: Target number of characters per chunk.
        overlap: Number of characters to overlap between chunks.

    Returns:
        List of text chunks.
    """
    if not text:
        return []

    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        if chunk.strip():
            chunks.append(chunk.strip())
        start = end - overlap
        if start >= len(text):
            break

    return chunks


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Generate embeddings for a list of text chunks using OpenAI.

    Args:
        texts: List of text strings to embed.

    Returns:
        List of embedding vectors (each a list of 1536 floats).
    """
    import openai

    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        logger.warning("OPENAI_API_KEY not configured — returning zero embeddings")
        return [[0.0] * 1536 for _ in texts]

    client = openai.AsyncOpenAI(api_key=api_key)
    model = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")

    response = await client.embeddings.create(input=texts, model=model)
    embeddings = [item.embedding for item in response.data]
    logger.debug(f"Generated {len(embeddings)} embeddings")
    return embeddings

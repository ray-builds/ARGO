"""Text chunking and file extraction utilities for the Research Data Lake."""
from __future__ import annotations

from pathlib import Path

from loguru import logger


class ResearchError(Exception):
    """Raised for errors in the Research Data Lake pipeline."""


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 100) -> list[str]:
    """Split text into overlapping word-based chunks.

    Uses a sliding window approach: each chunk is ~chunk_size words,
    with overlap words shared between consecutive chunks.

    Args:
        text: The full document text to chunk.
        chunk_size: Target number of words per chunk.
        overlap: Number of words to overlap between consecutive chunks.

    Returns:
        List of chunk strings. Returns [] for empty/whitespace-only input.
    """
    if not text or not text.strip():
        return []

    words = text.split()
    if not words:
        return []

    if len(words) <= chunk_size:
        return [text.strip()]

    chunks: list[str] = []
    start = 0
    step = max(1, chunk_size - overlap)

    while start < len(words):
        end = start + chunk_size
        chunk = " ".join(words[start:end])
        if chunk.strip():
            chunks.append(chunk.strip())
        if end >= len(words):
            break
        start += step

    return chunks


def extract_text_from_pdf(file_path: str) -> str:
    """Extract plain text from a PDF file using pypdf.

    Args:
        file_path: Absolute path to the PDF file.

    Returns:
        Extracted plain text as a single string (pages joined by newline).

    Raises:
        ResearchError: If pypdf is not installed or the file cannot be read.
    """
    try:
        import pypdf  # type: ignore[import]
    except ImportError:
        try:
            import PyPDF2 as pypdf  # type: ignore[import,no-redef]
        except ImportError:
            raise ResearchError(
                "pypdf not installed. Run: pip install pypdf"
            )

    path = Path(file_path)
    if not path.exists():
        raise ResearchError(f"PDF file not found: {file_path}")

    try:
        reader = pypdf.PdfReader(str(path))
        pages: list[str] = []
        for page in reader.pages:
            page_text = page.extract_text() or ""
            pages.append(page_text)
        extracted = "\n".join(pages)
        logger.debug(f"Extracted {len(extracted)} chars from {path.name} ({len(reader.pages)} pages)")
        return extracted
    except Exception as exc:
        raise ResearchError(f"Failed to extract text from PDF {path.name}: {exc}") from exc


def extract_text_from_file(file_path: str, file_type: str) -> str:
    """Extract plain text from a file, routing by file type.

    Supported file types:
        - ``pdf``  → pypdf extraction
        - ``txt`` / ``md`` → direct UTF-8 read
        - ``docx`` → python-docx extraction

    Args:
        file_path: Absolute path to the file.
        file_type: Lowercase file extension without the dot (e.g. ``"pdf"``).

    Returns:
        Extracted text as a string.

    Raises:
        ResearchError: If the file type is unsupported or extraction fails.
    """
    ft = file_type.lower().lstrip(".")
    path = Path(file_path)

    if ft == "pdf":
        return extract_text_from_pdf(file_path)

    if ft in ("txt", "md", "text"):
        if not path.exists():
            raise ResearchError(f"Text file not found: {file_path}")
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            raise ResearchError(f"Failed to read text file {path.name}: {exc}") from exc

    if ft == "docx":
        try:
            import docx  # type: ignore[import]
        except ImportError:
            raise ResearchError(
                "python-docx not installed. Run: pip install python-docx"
            )
        if not path.exists():
            raise ResearchError(f"DOCX file not found: {file_path}")
        try:
            doc = docx.Document(str(path))
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            return "\n".join(paragraphs)
        except Exception as exc:
            raise ResearchError(f"Failed to extract DOCX {path.name}: {exc}") from exc

    raise ResearchError(
        f"Unsupported file type: '{ft}'. Supported types: pdf, txt, md, docx"
    )

"""Whisper transcription integration for meeting audio files."""
from __future__ import annotations

import os

from loguru import logger


async def transcribe_audio(file_path: str) -> str:
    """Transcribe audio file using OpenAI Whisper API.

    Args:
        file_path: Local path to the audio/video file.

    Returns:
        Transcribed text as a string.

    Raises:
        ValueError: If OPENAI_API_KEY is not configured.
        FileNotFoundError: If the audio file doesn't exist.
    """
    import openai

    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        raise ValueError("OPENAI_API_KEY not configured for Whisper transcription")

    client = openai.AsyncOpenAI(api_key=api_key)

    with open(file_path, "rb") as audio_file:
        logger.info(f"Transcribing: {file_path}")
        response = await client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            response_format="text",
        )

    logger.info(f"Transcription complete: {len(response)} characters")
    return response

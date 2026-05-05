"""Serper API client for financial news and web search."""
from __future__ import annotations

from typing import Any

import httpx
from loguru import logger


BASE_URL = "https://google.serper.dev"


class SerperClient:
    """Async client for the Serper Google Search API.

    Used by overnight summary and research modules to fetch financial headlines
    and web results. Falls back to an empty list when not configured rather
    than raising, to keep the platform operational in dev.
    """

    def __init__(self) -> None:
        from app.config import get_settings
        settings = get_settings()

        self._api_key: str = settings.serper_api_key
        self._enabled: bool = bool(
            self._api_key and not self._api_key.startswith("FILL")
        )

        if not self._enabled:
            logger.warning("Serper API not configured — news search will return empty results")

    async def search_news(
        self,
        query: str,
        num_results: int = 10,
    ) -> list[dict[str, Any]]:
        """Search for news articles via Serper's /news endpoint.

        Args:
            query: Search query string.
            num_results: Number of results to request (Serper max is 10 per call).

        Returns:
            List of dicts with keys: title, snippet, source, link, date.
            Returns empty list on any error.
        """
        if not self._enabled:
            logger.info("[MOCK] Serper news search: {!r}", query)
            return []

        headers = {"X-API-KEY": self._api_key, "Content-Type": "application/json"}
        payload: dict[str, Any] = {"q": query, "num": num_results}

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(
                    f"{BASE_URL}/news",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                raw_news: list[dict[str, Any]] = response.json().get("news", [])

                # Normalise to a consistent schema
                results: list[dict[str, Any]] = [
                    {
                        "title": item.get("title", ""),
                        "snippet": item.get("snippet", ""),
                        "source": item.get("source", ""),
                        "link": item.get("link", ""),
                        "date": item.get("date", ""),
                    }
                    for item in raw_news
                ]
                logger.debug(
                    "Serper returned {} news results for: {!r}", len(results), query
                )
                return results

        except httpx.HTTPStatusError as exc:
            logger.warning(
                "Serper /news HTTP error {} for query {!r}: {}",
                exc.response.status_code,
                query,
                exc,
            )
            return []
        except httpx.RequestError as exc:
            logger.warning("Serper /news request error for query {!r}: {}", query, exc)
            return []

    async def search_financial_news(self, query: str) -> list[dict[str, Any]]:
        """Convenience wrapper: appends financial context to the query.

        Args:
            query: Raw topic (e.g. "Fed policy", "oil prices").

        Returns:
            News results from search_news().
        """
        return await self.search_news(
            f"{query} financial markets macro",
            num_results=10,
        )

    async def search_web(self, query: str, num_results: int = 5) -> list[dict[str, Any]]:
        """General web search via Serper's /search endpoint.

        Args:
            query: Search query.
            num_results: Number of organic results.

        Returns:
            List of organic result dicts, or empty list on error / disabled.
        """
        if not self._enabled:
            return []

        headers = {"X-API-KEY": self._api_key, "Content-Type": "application/json"}
        payload: dict[str, Any] = {"q": query, "num": num_results}

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(
                    f"{BASE_URL}/search",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                return response.json().get("organic", [])  # type: ignore[return-value]

        except httpx.HTTPStatusError as exc:
            logger.warning(
                "Serper /search HTTP error {} for {!r}: {}",
                exc.response.status_code,
                query,
                exc,
            )
            return []
        except httpx.RequestError as exc:
            logger.warning("Serper /search request error for {!r}: {}", query, exc)
            return []


# ── Module-level singleton ────────────────────────────────────────────────────

_client: SerperClient | None = None


def get_serper_client() -> SerperClient:
    """Return the module-level SerperClient singleton."""
    global _client
    if _client is None:
        _client = SerperClient()
    return _client

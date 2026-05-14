"""Microsoft Graph API client — all Graph calls for ARGO must go through here."""
from __future__ import annotations

from typing import Any

import httpx
import msal
from loguru import logger

from app.config import get_settings


GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"

# MSAL automatically adds openid, profile; passing them explicitly raises an error.
MSAL_RESERVED_SCOPES: frozenset[str] = frozenset({"openid", "profile", "offline_access"})


def get_msal_scopes() -> list[str]:
    """Return configured Graph scopes with MSAL-reserved values removed."""
    configured_scopes = get_settings().graph_scopes_list
    filtered = [s for s in configured_scopes if s not in MSAL_RESERVED_SCOPES]

    removed = sorted(set(configured_scopes) - set(filtered))
    if removed:
        logger.warning(
            "Ignoring MSAL-reserved scopes from GRAPH_SCOPES: {}", ", ".join(removed)
        )
    return filtered


def _build_msal_app() -> msal.ConfidentialClientApplication:
    settings = get_settings()
    return msal.ConfidentialClientApplication(
        client_id=settings.azure_client_id,
        client_credential=settings.azure_client_secret,
        authority=f"https://login.microsoftonline.com/{settings.azure_tenant_id}",
    )


def get_auth_url(state: str) -> str:
    """Generate the Microsoft OAuth2 authorization URL for the login redirect.

    Args:
        state: CSRF-protection state token to embed in the URL.

    Returns:
        Full Azure AD authorization URL string.
    """
    settings = get_settings()
    msal_app = _build_msal_app()
    scopes = get_msal_scopes()
    redirect_uri = settings.azure_redirect_uri

    return msal_app.get_authorization_request_url(
        scopes=scopes,
        state=state,
        redirect_uri=redirect_uri,
    )


async def exchange_code_for_token(code: str, state: str) -> dict[str, Any]:
    """Exchange an OAuth2 authorization code for MSAL token result.

    Args:
        code: The authorization code from the OAuth2 callback.
        state: The CSRF state token (already validated by the caller).

    Returns:
        Full MSAL token result dict containing access_token, refresh_token,
        id_token_claims, expires_in, etc.

    Raises:
        ValueError: If MSAL token acquisition fails.
    """
    settings = get_settings()
    msal_app = _build_msal_app()
    scopes = get_msal_scopes()
    redirect_uri = settings.azure_redirect_uri

    result: dict[str, Any] = msal_app.acquire_token_by_authorization_code(
        code=code,
        scopes=scopes,
        redirect_uri=redirect_uri,
    )

    if "error" in result:
        description = result.get("error_description", result.get("error", "Unknown error"))
        logger.error("MSAL token acquisition failed: {}", description)
        raise ValueError(f"MSAL error: {description}")

    preferred_username = result.get("id_token_claims", {}).get("preferred_username", "unknown")
    logger.info("Token acquired for: {}", preferred_username)
    return result


class GraphClient:
    """Async Microsoft Graph API client.

    Accepts a user access token obtained through the OAuth2 flow; all API
    calls are made on behalf of that user (delegated permissions).
    """

    BASE = GRAPH_BASE_URL

    def __init__(self, access_token: str) -> None:
        self._access_token = access_token
        self._headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

    # ── Email ────────────────────────────────────────────────────────────────

    async def get_messages(
        self,
        user_email: str,
        top: int = 50,
        filter_query: str = "",
        select: str | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch email messages from a user's mailbox.

        Args:
            user_email: The mailbox owner's UPN / email address.
            top: Maximum messages to return.
            filter_query: OData $filter expression (empty string = no filter).
            select: Comma-separated fields to include (None = sensible default).

        Returns:
            List of message dicts from Graph API.
        """
        params: dict[str, Any] = {
            "$top": top,
            "$orderby": "receivedDateTime desc",
            "$select": select or (
                "id,subject,sender,from,receivedDateTime,isRead,"
                "bodyPreview,body,hasAttachments,importance"
            ),
        }
        if filter_query:
            params["$filter"] = filter_query

        url = f"{self.BASE}/users/{user_email}/messages"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=self._headers, params=params)

            if response.status_code == 401:
                logger.warning("Access token expired for {}", user_email)
                raise PermissionError("Graph API access token expired or invalid")

            response.raise_for_status()
            messages: list[dict[str, Any]] = response.json().get("value", [])
            logger.debug("Fetched {} messages for {}", len(messages), user_email)
            return messages

    async def get_message(
        self, user_email: str, message_id: str
    ) -> dict[str, Any]:
        """Fetch a single email message with full body."""
        url = f"{self.BASE}/users/{user_email}/messages/{message_id}"
        params = {
            "$select": (
                "id,subject,sender,from,receivedDateTime,isRead,"
                "body,bodyPreview,importance"
            )
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=self._headers, params=params)
            if response.status_code == 401:
                logger.warning("Access token expired for {}", user_email)
            response.raise_for_status()
            return response.json()  # type: ignore[return-value]

    async def send_email(
        self,
        from_email: str,
        to_email: str,
        subject: str,
        body_html: str,
    ) -> None:
        """Send an email via Microsoft Graph sendMail endpoint.

        Args:
            from_email: Sender UPN (must match the authenticated user).
            to_email: Recipient email address.
            subject: Email subject line.
            body_html: HTML body content.

        Raises:
            httpx.HTTPStatusError: On non-2xx responses.
        """
        url = f"{self.BASE}/users/{from_email}/sendMail"
        payload: dict[str, Any] = {
            "message": {
                "subject": subject,
                "body": {"contentType": "HTML", "content": body_html},
                "toRecipients": [{"emailAddress": {"address": to_email}}],
            },
            "saveToSentItems": True,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=self._headers, json=payload)
            if response.status_code == 401:
                logger.warning("Access token expired — cannot send email from {}", from_email)
            response.raise_for_status()
            logger.info("Email sent: {} → {} | {!r}", from_email, to_email, subject)

    async def archive_message(self, user_email: str, message_id: str) -> None:
        """Move a message to the Archive folder.

        Args:
            user_email: Mailbox owner's email.
            message_id: Graph message ID to archive.

        Raises:
            httpx.HTTPStatusError: On non-2xx responses.
        """
        url = f"{self.BASE}/users/{user_email}/messages/{message_id}/move"
        payload = {"destinationId": "archive"}

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=self._headers, json=payload)
            if response.status_code == 401:
                logger.warning("Access token expired for {}", user_email)
            response.raise_for_status()
            logger.info("Archived message {} for {}", message_id, user_email)

    async def patch_message(
        self,
        user_email: str,
        message_id: str,
        payload: dict[str, Any],
    ) -> None:
        """PATCH fields on a message (e.g. ``{"isRead": true}``)."""
        url = f"{self.BASE}/users/{user_email}/messages/{message_id}"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.patch(url, headers=self._headers, json=payload)
            if response.status_code == 401:
                logger.warning("Access token expired for {}", user_email)
            response.raise_for_status()
            logger.debug("Patched message {} for {}", message_id, user_email)

    # ── Calendar ─────────────────────────────────────────────────────────────

    async def get_calendar_events(
        self,
        user_email: str,
        start: str,
        end: str,
    ) -> list[dict[str, Any]]:
        """Fetch calendar events within a time range.

        Args:
            user_email: Calendar owner's email address.
            start: ISO 8601 start datetime (e.g. "2024-01-01T00:00:00").
            end: ISO 8601 end datetime.

        Returns:
            List of calendar event dicts.
        """
        url = f"{self.BASE}/users/{user_email}/calendarView"
        params: dict[str, Any] = {
            "startDateTime": start,
            "endDateTime": end,
            "$select": "subject,start,end,attendees,bodyPreview,organizer",
            "$top": 50,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=self._headers, params=params)
            if response.status_code == 401:
                logger.warning("Access token expired for {}", user_email)
            response.raise_for_status()
            return response.json().get("value", [])  # type: ignore[return-value]


def get_graph_client(access_token: str) -> GraphClient:
    """Factory: create a GraphClient for the given access token.

    Args:
        access_token: A valid Microsoft Graph delegated access token.

    Returns:
        A configured GraphClient instance.
    """
    return GraphClient(access_token=access_token)

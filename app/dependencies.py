"""FastAPI dependency injection helpers for ARGO."""
from __future__ import annotations

from typing import Annotated, AsyncGenerator

from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session


# ── Database dependency ───────────────────────────────────────────────────────

async def get_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """FastAPI Depends-compatible dependency that yields an AsyncSession."""
    async with get_db_session() as session:
        yield session


# ── Auth dependencies ─────────────────────────────────────────────────────────

def _is_api_route(request: Request) -> bool:
    """Return True if the request path starts with /api/."""
    return request.url.path.startswith("/api/")


async def get_current_user(request: Request) -> dict:
    """Read the authenticated user dict from the session.

    Returns the full user dict stored in ``request.session["user"]``.

    For API routes (paths starting with ``/api/``): raises HTTP 401.
    For HTML routes: raises HTTP 401 (caller may wish to redirect instead;
    use ``require_auth`` for auto-redirect behaviour).

    Returns:
        dict with at minimum: user_id, email, display_name, role, access_token.

    Raises:
        HTTPException(401): if the session does not contain a valid user.
    """
    user_data: dict | None = request.session.get("user")

    if not user_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated. Please log in.",
        )

    if not user_data.get("user_id"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session. Please log in again.",
        )

    return user_data


async def require_auth(request: Request):
    """Auth dependency that returns 401 JSON for API routes and redirects for HTML.

    - Path starts with ``/api/`` → returns JSON 401.
    - All other paths → returns ``RedirectResponse("/login")``.

    Use this as the dependency for page endpoints where a redirect is
    friendlier than a bare 401.

    Returns:
        User dict (same shape as ``get_current_user``).

    Raises:
        HTTPException(401): for API routes when not authenticated.
    """
    user_data: dict | None = request.session.get("user")

    if not user_data or not user_data.get("user_id"):
        if _is_api_route(request):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated.",
            )
        # HTML route — redirect to login
        return RedirectResponse(url="/login", status_code=302)

    return user_data


# ── Typed aliases ─────────────────────────────────────────────────────────────

CurrentUser = Annotated[dict, Depends(require_auth)]

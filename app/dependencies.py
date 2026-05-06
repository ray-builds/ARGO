"""FastAPI dependency injection helpers for ARGO."""
from __future__ import annotations

from typing import Annotated, AsyncGenerator

from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from loguru import logger
from sqlalchemy import select
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


async def _load_user(user_id: str):
    """Load the User ORM object from the database by ID."""
    from app.models.user import User as UserModel
    async with get_db_session() as db:
        result = await db.execute(select(UserModel).where(UserModel.id == user_id))
        return result.scalar_one_or_none()


async def get_current_user(request: Request):
    """Load the authenticated User ORM object from the session + database.

    Raises:
        HTTPException(401): if the session is missing or the user is not found.
    """
    user_data: dict | None = request.session.get("user")

    if not user_data or not user_data.get("user_id"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated. Please log in.",
        )

    user = await _load_user(user_data["user_id"])
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found. Please log in again.",
        )

    return user


async def require_auth(request: Request):
    """Auth dependency — redirects HTML routes to /login, returns 401 for API routes.

    Returns:
        User ORM object.
    """
    user_data: dict | None = request.session.get("user")

    if not user_data or not user_data.get("user_id"):
        if _is_api_route(request):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated.",
            )
        return RedirectResponse(url="/login", status_code=302)

    user = await _load_user(user_data["user_id"])
    if not user:
        if _is_api_route(request):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found.",
            )
        return RedirectResponse(url="/login", status_code=302)

    return user


async def get_current_user_optional(request: Request):
    """Like get_current_user but returns None instead of raising when unauthenticated."""
    user_data: dict | None = request.session.get("user")
    if not user_data or not user_data.get("user_id"):
        return None
    return await _load_user(user_data["user_id"])


async def require_dev_lead(request: Request):
    """Auth dependency that requires the user to have the dev_lead or ceo role.

    Raises:
        HTTPException(403): if authenticated but lacks the required role.
    """
    user = await get_current_user(request)
    if user.role not in ("dev_lead", "ceo"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Dev lead or CEO role required.",
        )
    return user


async def get_access_token(request: Request) -> str:
    """Return the Microsoft Graph access token for the current user.

    Raises:
        HTTPException(401): if not authenticated or token is missing.
    """
    user = await get_current_user(request)
    if not user.graph_access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Microsoft Graph token missing. Please log in again.",
        )
    return user.graph_access_token


# ── Typed aliases ─────────────────────────────────────────────────────────────

CurrentUser = Annotated[object, Depends(require_auth)]

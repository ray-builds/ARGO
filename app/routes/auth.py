"""Microsoft 365 OAuth2 authentication routes using MSAL."""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from loguru import logger

from requests.exceptions import SSLError

from app.config import get_settings
from app.core.database import get_db_session
from app.core.graph_client import get_auth_url, exchange_code_for_token
from app.models.user import User

router = APIRouter(tags=["Authentication"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request) -> HTMLResponse:
    """Render the Microsoft SSO login page."""
    # If already logged in, redirect to dashboard
    if request.session.get("user"):
        return RedirectResponse(url="/", status_code=302)

    err_q = request.query_params.get("error")
    error_msg: str | None = None
    if err_q == "ssl_verify":
        error_msg = (
            "TLS verification failed when contacting Microsoft login. "
            "ARGO enables the OS certificate store at startup (truststore). "
            "If this still appears: install dependencies (pip install -r requirements.txt), "
            "set SSL_CA_BUNDLE to a PEM that includes your organisation root CA, "
            "or as a last resort MSAL_SSL_VERIFY=false for local dev only (insecure)."
        )
    elif err_q == "auth_failed":
        error_msg = "Authentication failed. Please try again or contact IT support."

    return templates.TemplateResponse(
        "auth/login.html",
        {"request": request, "error": error_msg},
    )


@router.get("/login/microsoft")
async def login_microsoft(request: Request) -> RedirectResponse:
    """Initiate Microsoft OAuth2 login — redirect to Azure AD."""
    request.session.clear()  # wipe any stale oauth_state from previous flows
    state = secrets.token_urlsafe(32)
    request.session["oauth_state"] = state

    try:
        auth_url = get_auth_url(state=state)
    except SSLError as exc:
        logger.warning(
            "Microsoft OAuth SSL error (configure SSL_CA_BUNDLE or dev-only MSAL_SSL_VERIFY): {}",
            exc,
        )
        return RedirectResponse(url="/login?error=ssl_verify", status_code=302)

    logger.info("Redirecting to Microsoft login")
    return RedirectResponse(url=auth_url, status_code=302)


@router.get("/auth/callback")
async def auth_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
) -> RedirectResponse:
    """Handle Microsoft OAuth2 callback — exchange code for tokens, create session.

    After successful auth, upserts the user in the database and stores
    session data (user info + tokens).
    """
    if error:
        logger.error(f"OAuth callback error: {error} — {error_description}")
        return RedirectResponse(url="/login?error=auth_failed", status_code=302)

    # Validate CSRF state
    stored_state = request.session.get("oauth_state")
    if not stored_state or stored_state != state:
        logger.error(
            "CSRF state mismatch: stored={!r} received={!r}. "
            "Common causes: (1) browser switched between 'localhost' and '127.0.0.1' "
            "(must match APP_BASE_URL and the Azure redirect URI exactly), "
            "(2) SECRET_KEY changed (e.g. app reloaded with an ephemeral key), "
            "(3) callback opened in a different browser/profile, "
            "(4) cookies blocked. APP_BASE_URL={}",
            stored_state, state, get_settings().app_base_url,
        )
        return RedirectResponse(url="/login?error=state_mismatch", status_code=302)

    if not code:
        return RedirectResponse(url="/login?error=no_code", status_code=302)

    try:
        token_result = await exchange_code_for_token(code=code, state=state)
    except ValueError as e:
        logger.exception(f"Token exchange failed: {e}")
        return RedirectResponse(url="/login?error=token_failed", status_code=302)

    # Extract user identity from id_token claims
    claims = token_result.get("id_token_claims", {})
    azure_oid = claims.get("oid", "")
    email = claims.get("preferred_username", "") or claims.get("email", "")
    display_name = claims.get("name", email)

    if not azure_oid or not email:
        logger.error(f"Missing identity claims: oid={azure_oid!r} email={email!r}")
        return RedirectResponse(url="/login?error=no_identity", status_code=302)

    access_token = token_result.get("access_token", "")
    refresh_token = token_result.get("refresh_token", "")
    token_expires_at = datetime.now(timezone.utc) + timedelta(
        seconds=token_result.get("expires_in", 3600)
    )

    # Determine role
    settings = get_settings()
    ceo_email = settings.ceo_email
    dev_lead_email = "rshhadeh@arpglobalcapital.com"
    if email.lower() == ceo_email.lower():
        role = "ceo"
    elif email.lower() == dev_lead_email.lower():
        role = "dev_lead"
    else:
        role = "staff"

    # Upsert user in database
    try:
        async with get_db_session() as session:
            from sqlalchemy import select
            result = await session.execute(
                select(User).where(User.azure_oid == azure_oid)
            )
            user = result.scalar_one_or_none()

            if user is None:
                user = User(
                    azure_oid=azure_oid,
                    email=email,
                    display_name=display_name,
                    role=role,
                    graph_access_token=access_token,
                    graph_refresh_token=refresh_token,
                    graph_token_expires_at=token_expires_at,
                )
                session.add(user)
                logger.info(f"New user created: {email} ({role})")
            else:
                user.display_name = display_name
                user.last_login_at = datetime.now(timezone.utc)
                user.role = role
                user.graph_access_token = access_token
                user.graph_refresh_token = refresh_token
                user.graph_token_expires_at = token_expires_at
                logger.info(f"User logged in: {email} ({role})")

            await session.flush()
            user_id = user.id
    except Exception as e:
        logger.exception(f"Database error during auth callback: {e}")
        return RedirectResponse(url="/login?error=db_error", status_code=302)

    # Store session
    request.session["user"] = {"user_id": user_id}

    # Clean up CSRF state
    request.session.pop("oauth_state", None)

    logger.info(f"Session created for {email}")
    return RedirectResponse(url="/", status_code=302)


@router.get("/logout")
async def logout(request: Request) -> RedirectResponse:
    """Clear the user session and redirect to login."""
    email = request.session.get("user", {}).get("email", "unknown")
    request.session.clear()
    logger.info(f"User logged out: {email}")
    return RedirectResponse(url="/login", status_code=302)

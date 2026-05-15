"""ARGO FastAPI application factory — registers all routers, middleware, and lifespan events."""
from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from starlette.middleware.sessions import SessionMiddleware

from app.config import get_settings
from app.core.database import init_db, close_db
from app.core.scheduler import (
    register_auto_sync_jobs,
    register_section8_jobs,
    register_section9_jobs,
    register_research_ingestion_jobs,
    register_overnight_summary_job,
    start_scheduler,
    stop_scheduler,
)


# ── Logging ───────────────────────────────────────────────────────────────────

def configure_logging() -> None:
    """Configure loguru for ARGO — structured output to stdout and rotating file."""
    settings = get_settings()
    logger.remove()

    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    )

    logger.add(sys.stdout, format=log_format, level=settings.log_level, colorize=True)

    os.makedirs("logs", exist_ok=True)
    logger.add(
        "logs/argo.log",
        format=log_format,
        level=settings.log_level,
        rotation="10 MB",
        retention="30 days",
        compression="gz",
    )


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """FastAPI lifespan context: manages startup and shutdown side-effects."""
    configure_logging()
    # Before outbound HTTPS (MSAL, Graph): OS trust store — fixes SSL on Windows / many proxies
    from app.core.ssl_trust import inject_os_ssl_context

    inject_os_ssl_context()

    logger.info("ARGO starting up...")

    await init_db()

    register_overnight_summary_job()
    register_auto_sync_jobs()
    register_research_ingestion_jobs()
    register_section8_jobs()
    register_section9_jobs()
    await start_scheduler()

    logger.info("ARGO startup complete")

    yield

    logger.info("ARGO shutting down...")
    await stop_scheduler()
    await close_db()
    logger.info("ARGO shutdown complete")


# ── Router registration ───────────────────────────────────────────────────────

def _try_import_router(module_path: str, attr: str = "router"):  # type: ignore[return]
    """Import a router, returning None and logging a warning on failure."""
    try:
        import importlib
        module = importlib.import_module(module_path)
        return getattr(module, attr)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Router import failed for {}: {}", module_path, exc)
        return None


def _register_routers(app: FastAPI) -> None:
    """Register all API and page routers with graceful fallback on partial implementations."""

    # ── System / page routes (must-have) ─────────────────────────────────────
    try:
        from app.routes.health import router as health_router
        app.include_router(health_router)
    except Exception as exc:
        logger.warning("health router unavailable: {}", exc)

    try:
        from app.routes.auth import router as auth_router
        app.include_router(auth_router, tags=["auth"])
    except Exception as exc:
        logger.warning("auth router unavailable: {}", exc)

    try:
        from app.routes.dashboard import router as dashboard_router
        app.include_router(dashboard_router)
    except Exception as exc:
        logger.warning("dashboard router unavailable: {}", exc)

    try:
        from app.routes.pages import router as pages_router
        app.include_router(pages_router)
    except Exception as exc:
        logger.warning("pages router unavailable: {}", exc)

    try:
        from app.routes.email_legacy import router as email_legacy_router
        app.include_router(email_legacy_router, prefix="/api/v1/email")
    except Exception as exc:
        logger.warning("email legacy router unavailable: {}", exc)

    try:
        from app.routes.webhooks import router as webhooks_router
        app.include_router(webhooks_router)
    except Exception as exc:
        logger.warning("webhooks router unavailable: {}", exc)

    try:
        from app.routes.ws import router as ws_router
        app.include_router(ws_router)
    except Exception as exc:
        logger.warning("ws router unavailable: {}", exc)

    try:
        from app.routes.whatsapp import router as whatsapp_router
        app.include_router(whatsapp_router)
    except Exception as exc:
        logger.warning("whatsapp router unavailable: {}", exc)

    try:
        from app.routes.research_ingestion import router as research_ingestion_router
        app.include_router(research_ingestion_router)
    except Exception as exc:
        logger.warning("research ingestion router unavailable: {}", exc)

    try:
        from app.routes.economic_realtime import router as economic_realtime_router
        app.include_router(economic_realtime_router)
    except Exception as exc:
        logger.warning("economic realtime router unavailable: {}", exc)

    try:
        from app.routes.morning_briefing import router as morning_briefing_router
        app.include_router(morning_briefing_router)
    except Exception as exc:
        logger.warning("morning briefing router unavailable: {}", exc)

    # ── Module API routes ────────────────────────────────────────────────────
    _module_routers: list[tuple[str, str, list[str]]] = [
        ("app.modules.overnight_summary.router",    "/api/v1/overnight",       ["overnight"]),
        ("app.modules.email_intelligence.router",   "/api/v1/emails",          ["emails"]),
        ("app.modules.meeting_intelligence.router", "/api/v1/meetings",        ["meetings"]),
        ("app.modules.research_lake.router",        "/api/v1/research",        ["research"]),
        ("app.modules.portfolio_intelligence.router", "/api/v1/portfolio",     ["portfolio"]),
        ("app.modules.sales_intelligence.router",   "/api/v1/clients",         ["clients"]),
        ("app.modules.research_intelligence.router", "/api/v1/research-intel", ["research-intel"]),
        ("app.modules.economic_intelligence.router", "/api/v1/econ",           ["econ"]),
        ("app.modules.ai_assistant.router",         "/api/v1/assistant",       ["assistant"]),
    ]

    for module_path, prefix, tags in _module_routers:
        router = _try_import_router(module_path)
        if router is not None:
            app.include_router(router, prefix=prefix, tags=tags)
            logger.debug("Registered router: {} → {}", module_path, prefix)


# ── App factory ───────────────────────────────────────────────────────────────

def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance.

    Returns:
        Fully configured FastAPI app.
    """
    settings = get_settings()

    app = FastAPI(
        title="ARGO",
        version="0.1.0",
        description="AI Operations Platform — ARP Global Capital",
        docs_url="/api/docs" if not settings.is_production else None,
        redoc_url="/api/redoc" if not settings.is_production else None,
        lifespan=lifespan,
    )

    # ── Middleware (order matters: added last = outermost) ────────────────────

    # CORS — permissive in dev, locked in prod
    allowed_origins = (
        ["https://argo.arpglobalcapital.com"]
        if settings.is_production
        else ["*"]
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["*"],
    )

    # Session (must sit inside CORS in the middleware stack)
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        max_age=28800,          # 8 hours
        same_site="lax",
        https_only=settings.is_production,
    )

    # ── Static files ──────────────────────────────────────────────────────────
    os.makedirs("static", exist_ok=True)
    app.mount("/static", StaticFiles(directory="static"), name="static")

    # ── Routers ───────────────────────────────────────────────────────────────
    _register_routers(app)

    # ── Built-in endpoints ────────────────────────────────────────────────────

    @app.get("/health", tags=["system"], include_in_schema=True)
    async def health_check() -> dict:
        return {
            "status": "ok",
            "version": "0.1.0",
            "environment": settings.environment,
        }

    @app.get("/", include_in_schema=False)
    async def root(request: Request):
        if request.session.get("user"):
            return RedirectResponse(url="/dashboard", status_code=302)
        return RedirectResponse(url="/login", status_code=302)

    # ── Error handlers ────────────────────────────────────────────────────────

    @app.exception_handler(404)
    async def not_found_handler(request: Request, exc: Exception):
        wants_json = "application/json" in request.headers.get("accept", "")
        if wants_json:
            return JSONResponse(
                status_code=404,
                content={"detail": "Not found", "path": request.url.path},
            )
        # HTML response for browser requests
        return HTMLResponse(
            content=(
                "<h1>404 — Not Found</h1>"
                f"<p>The page <code>{request.url.path}</code> does not exist.</p>"
                '<p><a href="/">Return to ARGO</a></p>'
            ),
            status_code=404,
        )

    @app.exception_handler(500)
    async def server_error_handler(request: Request, exc: Exception):
        logger.error("Unhandled 500 error on {}: {}", request.url.path, exc)
        wants_json = "application/json" in request.headers.get("accept", "")
        if wants_json:
            return JSONResponse(
                status_code=500,
                content={"detail": "Internal server error"},
            )
        return HTMLResponse(
            content=(
                "<h1>500 — Internal Server Error</h1>"
                "<p>Something went wrong. The ARGO team has been notified.</p>"
                '<p><a href="/">Return to ARGO</a></p>'
            ),
            status_code=500,
        )

    return app


# ── Module-level singleton for uvicorn ────────────────────────────────────────

app = create_app()

"""
backend/main.py
===============
FastAPI application entry point.

Run with:
    uvicorn backend.main:app --reload --port 8000
"""

import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exception_handlers import (
    http_exception_handler,
    request_validation_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.config import settings
from backend.db.client import init_db
from backend.version import __version__
from backend.routers.agent_runs import router as agent_runs_router
from backend.routers.applications import router as applications_router
from backend.routers.jobs import router as jobs_router
from backend.routers.profile import router as profile_router
from backend.routers.resumes import router as resumes_router


# ── Logging setup ────────────────────────────────────────
logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan> - {message}",
    level="DEBUG" if settings.environment == "development" else "INFO",
)
logger.add(
    "data/logs/app_{time:YYYY-MM-DD}.log",
    rotation="1 day",
    retention="30 days",
    level="INFO",
)


# ── Lifespan (startup/shutdown) ──────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Job Search Agent starting up...")
    await init_db()
    logger.info("✅ Database connected")
    yield
    logger.info("👋 Job Search Agent shutting down...")


# ── App initialization ───────────────────────────────────
app = FastAPI(
    title="Job Search Agent API",
    description="Autonomous job search automation system",
    version=__version__,
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)
_cors_origins = [o.strip() for o in settings.frontend_url.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    if isinstance(exc, StarletteHTTPException):
        return await http_exception_handler(request, exc)
    if isinstance(exc, RequestValidationError):
        return await request_validation_exception_handler(request, exc)
    if request.url.path.startswith("/api/"):
        logger.exception(f"Unhandled API error: {exc}")
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )
    raise exc


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "version": __version__,
        "environment": settings.environment,
    }


app.include_router(jobs_router, prefix="/api/jobs", tags=["Jobs"])
app.include_router(resumes_router, prefix="/api/resumes", tags=["Resumes"])
app.include_router(profile_router, prefix="/api/profile", tags=["Profile"])
app.include_router(applications_router, prefix="/api/applications", tags=["Applications"])
app.include_router(agent_runs_router, prefix="/api/agent-runs", tags=["Agent runs"])

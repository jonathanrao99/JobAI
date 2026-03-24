"""API authentication for /api/* routes (optional bearer token)."""

from __future__ import annotations

import secrets

from fastapi import HTTPException, Request

from backend.config import settings


async def require_api_auth(request: Request) -> None:
    """If JOBAI_API_TOKEN is set, require Authorization: Bearer <token> or X-JobAI-Token."""
    expected = (settings.jobai_api_token or "").strip()
    if not expected:
        return
    provided = ""
    auth = request.headers.get("Authorization") or ""
    if auth.startswith("Bearer "):
        provided = auth[7:].strip()
    if not provided:
        provided = (request.headers.get("X-JobAI-Token") or "").strip()
    if not provided or not secrets.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")

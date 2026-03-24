"""API token dependency (no live DB)."""

import pytest
from backend.config import settings
from backend.security import require_api_auth
from fastapi import HTTPException
from starlette.requests import Request


@pytest.mark.asyncio
async def test_require_api_auth_skips_when_token_unset(monkeypatch):
    monkeypatch.setattr(settings, "jobai_api_token", "")
    req = Request({"type": "http", "headers": []})
    await require_api_auth(req)


@pytest.mark.asyncio
async def test_require_api_auth_rejects_missing_header(monkeypatch):
    monkeypatch.setattr(settings, "jobai_api_token", "secret-token")
    req = Request({"type": "http", "headers": []})
    with pytest.raises(HTTPException) as exc:
        await require_api_auth(req)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_require_api_auth_accepts_bearer(monkeypatch):
    monkeypatch.setattr(settings, "jobai_api_token", "secret-token")
    req = Request(
        {
            "type": "http",
            "headers": [(b"authorization", b"Bearer secret-token")],
        }
    )
    await require_api_auth(req)

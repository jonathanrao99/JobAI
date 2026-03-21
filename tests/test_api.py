"""Smoke tests for the FastAPI app."""

from backend.config import settings
from backend.version import __version__


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["version"] == __version__
    assert body["environment"] == settings.environment


def test_openapi_docs_available(client):
    r = client.get("/api/docs")
    assert r.status_code == 200

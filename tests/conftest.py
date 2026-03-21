"""Pytest fixtures (mock DB init so tests run without Supabase)."""

from unittest.mock import AsyncMock, patch

import pytest
from starlette.testclient import TestClient


@pytest.fixture
def client():
    with patch("backend.db.client.init_db", new_callable=AsyncMock):
        from backend.main import app

        with TestClient(app) as c:
            yield c

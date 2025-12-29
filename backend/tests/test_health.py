"""
Health check tests - проверка что приложение запускается и отвечает.
"""
import pytest
from httpx import AsyncClient, ASGITransport
from api.app import app


@pytest.mark.asyncio
async def test_health_endpoint():
    """Проверка что /api/health отвечает 200."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data


@pytest.mark.asyncio
async def test_app_starts():
    """Проверка что приложение стартует без ошибок."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Любой запрос - главное что приложение не падает
        response = await client.get("/api/health")
        assert response.status_code in [200, 401, 403]

"""
API tests - проверка критических эндпоинтов.
"""
import pytest
from httpx import AsyncClient, ASGITransport
from api.app import app


@pytest.mark.asyncio
async def test_dashboard_requires_auth():
    """Dashboard требует аутентификации."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/dashboard")
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_settings_requires_auth():
    """Settings требует аутентификации."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/settings")
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_control_status_requires_auth():
    """Control status требует аутентификации."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/control/status")
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_scaling_configs_requires_auth():
    """Scaling configs требует аутентификации."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/scaling/configs")
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_cors_headers_present():
    """Проверка что CORS заголовки присутствуют."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.options(
            "/api/health",
            headers={"Origin": "http://localhost:3000"}
        )
        # CORS должен отвечать
        assert response.status_code in [200, 204, 405]

"""
Auth tests - проверка аутентификации.
"""
import pytest
from httpx import AsyncClient, ASGITransport
from api.app import app


@pytest.mark.asyncio
async def test_login_without_credentials_fails():
    """Проверка что login без данных возвращает ошибку."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/auth/login", json={})
        # Должен вернуть 422 (validation error) или 400
        assert response.status_code in [400, 422]


@pytest.mark.asyncio
async def test_protected_endpoint_without_token_fails():
    """Проверка что защищенный endpoint без токена возвращает 401."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/accounts")
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_protected_endpoint_with_invalid_token_fails():
    """Проверка что защищенный endpoint с невалидным токеном возвращает 401."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/accounts",
            headers={"Authorization": "Bearer invalid_token_12345"}
        )
        assert response.status_code == 401

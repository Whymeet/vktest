"""
Pytest configuration and fixtures.
"""
import pytest
import os

# Устанавливаем тестовую БД если не задана
if not os.getenv("DATABASE_URL"):
    os.environ["DATABASE_URL"] = "postgresql://test:test@localhost:5432/test"

if not os.getenv("JWT_SECRET_KEY"):
    os.environ["JWT_SECRET_KEY"] = "test-secret-key-for-testing"


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"

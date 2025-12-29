"""
Database tests - проверка подключения к БД и моделей.
"""
import pytest
from sqlalchemy import text
from database.database import engine, SessionLocal
from database.models import User, Account


def test_database_connection():
    """Проверка что БД доступна."""
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1"))
        assert result.scalar() == 1


def test_session_works():
    """Проверка что сессия создается."""
    db = SessionLocal()
    try:
        # Простой запрос
        result = db.execute(text("SELECT 1"))
        assert result.scalar() == 1
    finally:
        db.close()


def test_user_model_exists():
    """Проверка что модель User существует и таблица создана."""
    db = SessionLocal()
    try:
        # Проверяем что таблица существует (не падает)
        db.query(User).first()
    finally:
        db.close()


def test_account_model_exists():
    """Проверка что модель Account существует и таблица создана."""
    db = SessionLocal()
    try:
        db.query(Account).first()
    finally:
        db.close()

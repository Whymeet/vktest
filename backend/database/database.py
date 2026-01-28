"""
Database connection and session management
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator

from .models import Base

# Database URL from environment or default
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://vkads:vkads_password@postgres:5432/vkads"
)

# Create engine with connection pool and auto-reconnect
# pool_pre_ping - проверяет соединение перед использованием (автоматический reconnect)
# pool_recycle - пересоздаёт соединения каждые 30 минут (избегает timeout PostgreSQL)
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,  # Проверять соединение перед использованием
    pool_size=5,  # Базовый размер пула
    max_overflow=10,  # Дополнительные соединения при нагрузке
    pool_recycle=1800,  # Пересоздавать соединения каждые 30 минут
    pool_timeout=30,  # Таймаут ожидания соединения из пула
    echo=False,  # Set to True for SQL query logging
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """
    Dependency for FastAPI to get database session

    Usage:
        @app.get("/items")
        def read_items(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """
    Initialize database - create all tables
    Call this on application startup
    """
    Base.metadata.create_all(bind=engine)


def drop_db():
    """
    Drop all tables - DANGEROUS! Only for development
    """
    Base.metadata.drop_all(bind=engine)

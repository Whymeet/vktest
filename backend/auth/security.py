"""
Security utilities for JWT authentication
"""
import os
import hashlib
import uuid
from datetime import datetime, timedelta
from typing import Optional

import bcrypt
from jose import JWTError, jwt
from pydantic import BaseModel
from loguru import logger


# Configuration from environment variables
# ВАЖНО: В production обязательно установите JWT_SECRET_KEY через переменную окружения!
_default_key = "dev-only-key-not-for-production-use"
SECRET_KEY = os.getenv("JWT_SECRET_KEY", _default_key)

# Предупреждение при использовании дефолтного ключа
if SECRET_KEY == _default_key:
    import warnings
    warnings.warn(
        "WARNING: Using default JWT secret key! "
        "Set JWT_SECRET_KEY environment variable for production.",
        RuntimeWarning
    )

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))  # 24 hours
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))


class Token(BaseModel):
    """Token response model"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    """Token payload data"""
    user_id: Optional[int] = None
    username: Optional[str] = None


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    password_bytes = plain_password.encode('utf-8')
    hashed_bytes = hashed_password.encode('utf-8')
    return bcrypt.checkpw(password_bytes, hashed_bytes)


def get_password_hash(password: str) -> str:
    """Hash a password (supports passwords up to 72 bytes)"""
    password_bytes = password.encode('utf-8')
    # Truncate to 72 bytes if needed (bcrypt limit)
    if len(password_bytes) > 72:
        password_bytes = password_bytes[:72]
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode('utf-8')


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a new access token"""
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({
        "exp": expire,
        "type": "access"
    })

    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def create_refresh_token(data: dict, jti: Optional[str] = None) -> tuple[str, str, datetime]:
    """
    Create a new refresh token with unique JTI.
    Returns: (token, jti, expires_at)
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

    # Generate unique JWT ID if not provided
    if jti is None:
        jti = str(uuid.uuid4())

    to_encode.update({
        "exp": expire,
        "type": "refresh",
        "jti": jti
    })

    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt, jti, expire


def decode_token(token: str) -> Optional[TokenData]:
    """Decode and validate a JWT token"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        username = payload.get("username")

        logger.debug("decode_token: payload={}, user_id={}, username={}", repr(payload), user_id, username)

        if user_id is None:
            logger.debug("decode_token: user_id is None!")
            return None

        return TokenData(user_id=int(user_id), username=username)
    except JWTError as e:
        logger.debug(f"decode_token: JWTError: {e}")
        return None


def decode_refresh_token(token: str) -> Optional[dict]:
    """
    Decode and validate a refresh token.
    Returns payload dict with user_id, username, jti, exp
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

        # Check if it's a refresh token
        if payload.get("type") != "refresh":
            return None

        user_id = payload.get("sub")
        username = payload.get("username")
        jti = payload.get("jti")

        if user_id is None or jti is None:
            return None

        return {
            "user_id": int(user_id),
            "username": username,
            "jti": jti,
            "exp": payload.get("exp")
        }
    except JWTError:
        return None


def hash_token(token: str) -> str:
    """Create SHA256 hash of token for secure storage"""
    return hashlib.sha256(token.encode()).hexdigest()


def verify_token_hash(token: str, token_hash: str) -> bool:
    """Verify token against stored hash"""
    return hash_token(token) == token_hash

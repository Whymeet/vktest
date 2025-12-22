"""
FastAPI dependencies for authentication
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database.database import get_db
from database import crud
from .security import decode_token

# HTTP Bearer token scheme
security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    """
    Dependency to get current authenticated user.
    Raises 401 if not authenticated.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if credentials is None:
        raise credentials_exception

    token_data = decode_token(credentials.credentials)
    if token_data is None:
        raise credentials_exception

    user = crud.get_user_by_id(db, token_data.user_id)
    if user is None:
        raise credentials_exception

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled"
        )

    return user


async def get_current_active_user(current_user = Depends(get_current_user)):
    """
    Dependency to get current active user.
    Same as get_current_user but with explicit naming.
    """
    return current_user


async def get_current_superuser(current_user = Depends(get_current_user)):
    """
    Dependency to ensure current user is a superuser (admin).
    Raises 403 if not superuser.
    """
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough privileges. Admin access required."
        )
    return current_user


async def get_optional_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    """
    Dependency to optionally get current user.
    Returns None if not authenticated (doesn't raise exception).
    """
    if credentials is None:
        return None

    token_data = decode_token(credentials.credentials)
    if token_data is None:
        return None

    user = crud.get_user_by_id(db, token_data.user_id)
    if user is None or not user.is_active:
        return None

    return user


def require_feature(feature: str):
    """
    Factory for dependency that checks if user has access to a specific feature.
    Usage: Depends(require_feature("scaling"))

    Features: auto_disable, scaling, leadstech, logs
    """
    async def feature_checker(
        current_user = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        # Superusers have access to all features
        if current_user.is_superuser:
            return current_user

        if not crud.user_has_feature(db, current_user.id, feature):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Feature '{feature}' is not available for your account."
            )
        return current_user

    return feature_checker

"""
Authentication API routes
"""
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional, List

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database.database import get_db
from database import crud
from auth.security import (
    verify_password,
    get_password_hash,
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    hash_token,
    Token
)
from auth.dependencies import get_current_user, get_current_superuser
from utils.time_utils import get_moscow_time

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


# ===== Request/Response Models =====

class LoginRequest(BaseModel):
    """Login request body"""
    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=1)


class RefreshRequest(BaseModel):
    """Token refresh request body"""
    refresh_token: str


class UserCreate(BaseModel):
    """User creation request (admin only)"""
    username: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=6)
    email: Optional[str] = None
    is_superuser: bool = False


class UserUpdate(BaseModel):
    """User update request"""
    email: Optional[str] = None
    password: Optional[str] = Field(None, min_length=6)
    is_active: Optional[bool] = None
    is_superuser: Optional[bool] = None


class UserResponse(BaseModel):
    """User response model"""
    id: int
    username: str
    email: Optional[str]
    is_active: bool
    is_superuser: bool
    created_at: str
    last_login: Optional[str]


class ChangePasswordRequest(BaseModel):
    """Change password request"""
    current_password: str
    new_password: str = Field(..., min_length=6)


# ===== Auth Endpoints =====

@router.post("/login", response_model=Token)
async def login(
    login_request: LoginRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Login with username and password.
    Returns access and refresh JWT tokens.
    Stores refresh token in database for tracking and revocation.

    Rate Limited: Default limit is 60 requests per minute per IP.
    Configure via RATE_LIMIT_PER_MINUTE environment variable.
    """
    # Find user
    user = crud.get_user_by_username(db, login_request.username)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password"
        )

    # Verify password
    if not verify_password(login_request.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password"
        )

    # Check if user is active
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled"
        )

    # Update last login
    crud.update_user_last_login(db, user.id)

    # Create tokens - sub must be a string for JWT
    token_data = {"sub": str(user.id), "username": user.username}
    access_token = create_access_token(data=token_data)
    refresh_token_str, jti, expires_at = create_refresh_token(data=token_data)

    # Store refresh token in database
    token_hash = hash_token(refresh_token_str)
    user_agent = request.headers.get("user-agent", "")[:500] if request.headers.get("user-agent") else None
    ip_address = request.client.host if request.client else None

    crud.create_refresh_token(
        db=db,
        user_id=user.id,
        token_hash=token_hash,
        jti=jti,
        expires_at=expires_at,
        user_agent=user_agent,
        ip_address=ip_address
    )

    return Token(
        access_token=access_token,
        refresh_token=refresh_token_str
    )


@router.post("/refresh", response_model=Token)
async def refresh_token(
    refresh_request: RefreshRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Refresh access token using refresh token.
    Returns new access and refresh tokens.
    Validates token against database and implements token rotation.
    """
    # Decode refresh token
    token_payload = decode_refresh_token(refresh_request.refresh_token)

    if not token_payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token"
        )

    # Verify token exists in database and is not revoked
    db_token = crud.get_refresh_token_by_jti(db, token_payload["jti"])

    if not db_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token not found"
        )

    if db_token.revoked:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has been revoked"
        )

    # Verify token hasn't expired
    if db_token.expires_at < get_moscow_time():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has expired"
        )

    # Get user
    user = crud.get_user_by_id(db, token_payload["user_id"])

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled"
        )

    # Revoke old refresh token (token rotation)
    crud.revoke_refresh_token(db, token_payload["jti"])

    # Create new tokens - sub must be a string for JWT
    new_token_data = {"sub": str(user.id), "username": user.username}
    new_access_token = create_access_token(data=new_token_data)
    new_refresh_token_str, new_jti, new_expires_at = create_refresh_token(data=new_token_data)

    # Store new refresh token in database
    token_hash = hash_token(new_refresh_token_str)
    user_agent = request.headers.get("user-agent", "")[:500] if request.headers.get("user-agent") else None
    ip_address = request.client.host if request.client else None

    crud.create_refresh_token(
        db=db,
        user_id=user.id,
        token_hash=token_hash,
        jti=new_jti,
        expires_at=new_expires_at,
        user_agent=user_agent,
        ip_address=ip_address
    )

    return Token(
        access_token=new_access_token,
        refresh_token=new_refresh_token_str
    )


@router.post("/logout")
async def logout(
    refresh_request: RefreshRequest,
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Logout current session by revoking the refresh token.
    Access token will remain valid until expiration, but cannot be refreshed.
    """
    # Decode refresh token to get JTI
    token_payload = decode_refresh_token(refresh_request.refresh_token)

    if not token_payload:
        # Token is invalid, but still return success (already logged out)
        return {"message": "Logged out successfully"}

    # Revoke the refresh token
    revoked = crud.revoke_refresh_token(db, token_payload["jti"])

    if revoked:
        return {"message": "Logged out successfully"}
    else:
        # Token not found in DB, but still return success
        return {"message": "Logged out successfully"}


@router.post("/logout-all")
async def logout_all(
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Logout from all devices by revoking all refresh tokens.
    All active sessions will be terminated.
    """
    count = crud.revoke_all_user_tokens(db, current_user.id)

    return {
        "message": f"Logged out from all devices successfully",
        "revoked_tokens_count": count
    }


@router.get("/sessions")
async def get_active_sessions(
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get list of active sessions (refresh tokens) for current user.
    """
    tokens = crud.get_user_active_tokens(db, current_user.id)

    sessions = []
    for token in tokens:
        sessions.append({
            "id": token.id,
            "device_name": token.device_name,
            "user_agent": token.user_agent,
            "ip_address": token.ip_address,
            "created_at": token.created_at.isoformat() if token.created_at else None,
            "last_used_at": token.last_used_at.isoformat() if token.last_used_at else None,
            "expires_at": token.expires_at.isoformat() if token.expires_at else None
        })

    return {"sessions": sessions, "total": len(sessions)}


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user = Depends(get_current_user)):
    """
    Get current authenticated user info.
    """
    return UserResponse(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        is_active=current_user.is_active,
        is_superuser=current_user.is_superuser,
        created_at=current_user.created_at.isoformat() if current_user.created_at else None,
        last_login=current_user.last_login.isoformat() if current_user.last_login else None
    )


class UpdateProfileRequest(BaseModel):
    """Request model for updating user profile"""
    username: Optional[str] = None
    email: Optional[str] = None


@router.put("/me", response_model=UserResponse)
async def update_profile(
    request: UpdateProfileRequest,
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update current user's profile (username, email).
    """
    update_data = {}
    
    if request.username is not None and request.username != current_user.username:
        # Check if username is taken
        existing = crud.get_user_by_username(db, request.username)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already exists"
            )
        update_data['username'] = request.username
    
    if request.email is not None and request.email != current_user.email:
        # Check if email is taken
        if request.email:
            existing = crud.get_user_by_email(db, request.email)
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email already exists"
                )
        update_data['email'] = request.email
    
    if update_data:
        updated_user = crud.update_user(db, current_user.id, **update_data)
    else:
        updated_user = current_user
    
    return UserResponse(
        id=updated_user.id,
        username=updated_user.username,
        email=updated_user.email,
        is_active=updated_user.is_active,
        is_superuser=updated_user.is_superuser,
        created_at=updated_user.created_at.isoformat() if updated_user.created_at else None,
        last_login=updated_user.last_login.isoformat() if updated_user.last_login else None
    )


@router.get("/me/features")
async def get_user_features(
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get list of features available to current user.
    Used by frontend to show/hide functionality.
    """
    # Superusers have access to all features
    if current_user.is_superuser:
        return {
            "features": crud.AVAILABLE_FEATURES,
            "is_superuser": True
        }

    features = crud.get_user_features(db, current_user.id)
    return {
        "features": features,
        "is_superuser": False
    }


@router.post("/change-password")
async def change_password(
    request: ChangePasswordRequest,
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Change current user's password.
    Automatically revokes all refresh tokens for security.
    """
    # Verify current password
    if not verify_password(request.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect"
        )

    # Update password
    new_hash = get_password_hash(request.new_password)
    crud.update_user_password(db, current_user.id, new_hash)

    # Revoke all refresh tokens for security
    revoked_count = crud.revoke_all_user_tokens(db, current_user.id)

    return {
        "message": "Password changed successfully. All sessions have been logged out.",
        "revoked_sessions": revoked_count
    }


# ===== Admin Endpoints =====

@router.get("/users", response_model=List[UserResponse])
async def list_users(
    db: Session = Depends(get_db),
    admin = Depends(get_current_superuser)
):
    """
    List all users (admin only).
    """
    users = crud.get_all_users(db)

    return [
        UserResponse(
            id=u.id,
            username=u.username,
            email=u.email,
            is_active=u.is_active,
            is_superuser=u.is_superuser,
            created_at=u.created_at.isoformat() if u.created_at else None,
            last_login=u.last_login.isoformat() if u.last_login else None
        )
        for u in users
    ]


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    user: UserCreate,
    db: Session = Depends(get_db),
    admin = Depends(get_current_superuser)
):
    """
    Create a new user (admin only).
    """
    # Check if username exists
    existing = crud.get_user_by_username(db, user.username)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists"
        )

    # Check if email exists (if provided)
    if user.email:
        existing_email = crud.get_user_by_email(db, user.email)
        if existing_email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already exists"
            )

    # Create user
    password_hash = get_password_hash(user.password)
    new_user = crud.create_user(
        db,
        username=user.username,
        password_hash=password_hash,
        email=user.email,
        is_superuser=user.is_superuser
    )

    return UserResponse(
        id=new_user.id,
        username=new_user.username,
        email=new_user.email,
        is_active=new_user.is_active,
        is_superuser=new_user.is_superuser,
        created_at=new_user.created_at.isoformat() if new_user.created_at else None,
        last_login=None
    )


@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    user_update: UserUpdate,
    db: Session = Depends(get_db),
    admin = Depends(get_current_superuser)
):
    """
    Update a user (admin only).
    """
    # Get user
    user = crud.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Update fields
    update_data = {}

    if user_update.email is not None:
        # Check if email is taken by another user
        if user_update.email:
            existing = crud.get_user_by_email(db, user_update.email)
            if existing and existing.id != user_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email already exists"
                )
        update_data['email'] = user_update.email

    if user_update.password is not None:
        update_data['password_hash'] = get_password_hash(user_update.password)

    if user_update.is_active is not None:
        update_data['is_active'] = user_update.is_active

    if user_update.is_superuser is not None:
        update_data['is_superuser'] = user_update.is_superuser

    if update_data:
        updated_user = crud.update_user(db, user_id, **update_data)
    else:
        updated_user = user

    return UserResponse(
        id=updated_user.id,
        username=updated_user.username,
        email=updated_user.email,
        is_active=updated_user.is_active,
        is_superuser=updated_user.is_superuser,
        created_at=updated_user.created_at.isoformat() if updated_user.created_at else None,
        last_login=updated_user.last_login.isoformat() if updated_user.last_login else None
    )


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin = Depends(get_current_superuser)
):
    """
    Delete a user (admin only).
    Cannot delete yourself.
    """
    # Check if trying to delete self
    if user_id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete yourself"
        )

    # Get user
    user = crud.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Delete user (cascade will delete all related data)
    crud.delete_user(db, user_id)

    return {"message": f"User '{user.username}' deleted successfully"}

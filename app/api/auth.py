"""
Authentication API endpoints.
"""

from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import verify_password, hash_password, create_access_token
from app.core.dependencies import get_current_user
from app.models.user import AdminUser
from app.schemas.auth import (
    TokenResponse,
    ChangePasswordRequest,
    UserResponse,
)

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@router.post("/login", response_model=TokenResponse)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """Authenticate user and return JWT token."""
    user = (
        db.query(AdminUser)
        .filter(AdminUser.username == form_data.username)
        .first()
    )

    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled",
        )

    # Update last login
    user.last_login = datetime.now(timezone.utc)
    db.commit()

    access_token = create_access_token(
        data={"sub": user.username, "role": user.role}
    )
    return TokenResponse(access_token=access_token)


@router.get("/me", response_model=UserResponse)
def get_me(current_user=Depends(get_current_user)):
    """Get current user profile."""
    return current_user


@router.put("/change-password")
def change_password(
    request: ChangePasswordRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Change current user's password."""
    if not verify_password(request.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    current_user.hashed_password = hash_password(request.new_password)
    db.commit()

    return {"message": "Password changed successfully"}

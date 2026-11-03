"""Login and current-user endpoints for local development authentication."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthenticatedUser, AssignedRole, get_current_user
from app.auth.schemas import CurrentUserResponse, FacilityRole, LoginRequest, TokenResponse
from app.auth.security import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    password_hasher,
    verify_password,
    create_access_token,
)
from app.db.models import UserFacilityRoleRecord, UserRecord
from app.db.session import get_db

router = APIRouter(prefix="/auth", tags=["Authentication"])
DbSession = Annotated[Session, Depends(get_db)]
# A dummy hash reduces the large timing gap between an unknown username and a bad password.
_DUMMY_PASSWORD_HASH = password_hasher.hash("not-a-real-account-password")


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Log in and obtain a short-lived bearer token",
    description=(
        "Development login for locally seeded synthetic users. Use the returned access_token "
        "as a Bearer token for protected API calls."
    ),
)
def login(payload: LoginRequest, db: DbSession) -> TokenResponse:
    user = db.scalar(select(UserRecord).where(UserRecord.username == payload.username))
    hashed = user.password_hash if user is not None else _DUMMY_PASSWORD_HASH
    password_matches = verify_password(payload.password.get_secret_value(), hashed)

    if user is None or not user.is_active or not password_matches:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password, or account is inactive.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return TokenResponse(
        access_token=create_access_token(user.user_id),
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.get("/me", response_model=CurrentUserResponse, summary="Get the authenticated user's profile and roles")
def read_current_user(current_user: Annotated[AuthenticatedUser, Depends(get_current_user)]) -> CurrentUserResponse:
    return CurrentUserResponse(
        user_id=current_user.user_id,
        username=current_user.username,
        display_name=current_user.display_name,
        is_active=current_user.is_active,
        assignments=[
            FacilityRole(facility_id=item.facility_id, role=item.role)
            for item in current_user.assignments
        ],
    )

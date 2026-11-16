"""Sign-in, token refresh and self-service password change."""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from raahat.api.deps import CurrentUser, client_ip, current_user, get_db, rate_limiter
from raahat.application.identity import service as identity
from raahat.config import Settings, get_settings
from raahat.security.passwords import WeakPasswordError
from raahat.security.tokens import issue_access_token

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class UserProfile(BaseModel):
    id: str
    username: str
    full_name: str
    role: str
    permissions: list[str]
    must_change_password: bool


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    session_expires_at: datetime
    user: UserProfile


class ChangePasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


def _profile(user: CurrentUser) -> UserProfile:
    return UserProfile(
        id=str(user.id),
        username=user.username,
        full_name=user.full_name,
        role=user.role.value,
        permissions=sorted(p.value for p in user.permissions),
        must_change_password=user.must_change_password,
    )


def _token_response(
    *,
    settings: Settings,
    user_id,
    token_version: int,
    profile: UserProfile,
    session_started_at: Optional[int] = None,
) -> TokenResponse:
    token, claims = issue_access_token(
        secret=settings.secret_key,
        user_id=user_id,
        token_version=token_version,
        ttl_seconds=settings.access_token_ttl_seconds,
        session_started_at=session_started_at,
    )
    return TokenResponse(
        access_token=token,
        expires_at=datetime.fromtimestamp(claims.expires_at, tz=timezone.utc),
        session_expires_at=datetime.fromtimestamp(
            claims.session_started_at + settings.session_max_seconds, tz=timezone.utc
        ),
        user=profile,
    )


@router.post("/login", response_model=TokenResponse, summary="Sign in")
def login(
    body: LoginRequest,
    request: Request,
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TokenResponse:
    ip = client_ip(request, settings)
    decision = rate_limiter.check(f"login:{ip}", limit=settings.login_rate_per_minute)
    if not decision.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many sign-in attempts. Try again shortly.",
            headers={"Retry-After": str(decision.retry_after_seconds)},
        )
    try:
        user = identity.authenticate(
            session, username=body.username, password=body.password, settings=settings
        )
    except identity.AccountLockedError as exc:
        retry = max(1, int((exc.until - datetime.now(timezone.utc)).total_seconds()))
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="This account is temporarily locked after repeated failed sign-ins.",
            headers={"Retry-After": str(retry)},
        ) from None
    except identity.InvalidCredentialsError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password"
        ) from None

    from raahat.security.permissions import permissions_for

    profile = UserProfile(
        id=str(user.id),
        username=user.username,
        full_name=user.full_name,
        role=user.role.value,
        permissions=sorted(p.value for p in permissions_for(user.role)),
        must_change_password=user.must_change_password,
    )
    return _token_response(
        settings=settings, user_id=user.id, token_version=user.token_version, profile=profile
    )


@router.post("/refresh", response_model=TokenResponse, summary="Extend the current session")
def refresh(
    user: CurrentUser = Depends(current_user),
    settings: Settings = Depends(get_settings),
) -> TokenResponse:
    """Issue a fresh access token while the session is within its maximum age.

    The caller presents a still-valid token; role and status were re-read by
    ``current_user``. Once the session reaches its maximum age the user must
    sign in again.
    """
    assert user.claims is not None
    if int(time.time()) >= user.claims.session_started_at + settings.session_max_seconds:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has reached its maximum length. Sign in again.",
        )
    return _token_response(
        settings=settings,
        user_id=user.id,
        token_version=user.claims.token_version,
        profile=_profile(user),
        session_started_at=user.claims.session_started_at,
    )


@router.get("/me", response_model=UserProfile, summary="Current user and permissions")
def me(user: CurrentUser = Depends(current_user)) -> UserProfile:
    return _profile(user)


@router.post("/change-password", response_model=TokenResponse, summary="Change own password")
def change_password(
    body: ChangePasswordRequest,
    user: CurrentUser = Depends(current_user),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TokenResponse:
    """Change the caller's password. Existing tokens stop working; a new one is returned."""
    try:
        updated = identity.change_own_password(
            session,
            user_id=user.id,
            current_password=body.current_password,
            new_password=body.new_password,
        )
    except identity.InvalidCredentialsError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    except (identity.IdentityError, WeakPasswordError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from None
    session.commit()
    profile = _profile(user).model_copy(update={"must_change_password": False})
    return _token_response(
        settings=settings,
        user_id=updated.id,
        token_version=updated.token_version,
        profile=profile,
    )

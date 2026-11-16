"""Administrator user management."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from raahat.api.deps import CurrentUser, get_db, require
from raahat.application.identity import service as identity
from raahat.infrastructure.database.models.user import UserModel
from raahat.security.passwords import WeakPasswordError
from raahat.security.permissions import ROLE_PERMISSIONS, Permission, Role

router = APIRouter(prefix="/users", tags=["users"])


class UserResponse(BaseModel):
    id: uuid.UUID
    username: str
    full_name: str
    role: Role
    is_active: bool
    must_change_password: bool
    locked_until: Optional[datetime]
    last_login_at: Optional[datetime]
    created_at: datetime


class CreateUserRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=3, max_length=64)
    full_name: str = Field(min_length=1, max_length=160)
    role: Role
    initial_password: str = Field(min_length=1, max_length=256)


class UpdateUserRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: Optional[str] = Field(default=None, min_length=1, max_length=160)
    role: Optional[Role] = None
    is_active: Optional[bool] = None


class ResetPasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    new_password: str = Field(min_length=1, max_length=256)


class RoleDescription(BaseModel):
    role: Role
    permissions: list[str]


def _to_response(user: UserModel) -> UserResponse:
    return UserResponse(
        id=user.id,
        username=user.username,
        full_name=user.full_name,
        role=Role(user.role),
        is_active=user.is_active,
        must_change_password=user.must_change_password,
        locked_until=user.locked_until,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
    )


@router.get("", response_model=list[UserResponse], summary="List user accounts")
def list_users(
    _: CurrentUser = Depends(require(Permission.USERS_MANAGE)),
    session: Session = Depends(get_db),
) -> list[UserResponse]:
    users = session.execute(select(UserModel).order_by(UserModel.username)).scalars().all()
    return [_to_response(u) for u in users]


@router.get("/roles", response_model=list[RoleDescription], summary="Roles and their permissions")
def list_roles(
    _: CurrentUser = Depends(require(Permission.USERS_MANAGE)),
) -> list[RoleDescription]:
    return [
        RoleDescription(role=role, permissions=sorted(p.value for p in perms))
        for role, perms in ROLE_PERMISSIONS.items()
    ]


@router.post(
    "", response_model=UserResponse, status_code=status.HTTP_201_CREATED, summary="Create a user"
)
def create_user(
    body: CreateUserRequest,
    actor: CurrentUser = Depends(require(Permission.USERS_MANAGE)),
    session: Session = Depends(get_db),
) -> UserResponse:
    """Create an account. The user must replace the initial password at first sign-in."""
    try:
        user = identity.create_user(
            session,
            username=body.username,
            full_name=body.full_name,
            role=body.role,
            password=body.initial_password,
            created_by=actor.id,
            must_change_password=True,
        )
    except identity.UsernameTakenError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from None
    except (identity.IdentityError, WeakPasswordError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from None
    session.commit()
    return _to_response(user)


@router.patch("/{user_id}", response_model=UserResponse, summary="Update a user")
def update_user(
    user_id: uuid.UUID,
    body: UpdateUserRequest,
    actor: CurrentUser = Depends(require(Permission.USERS_MANAGE)),
    session: Session = Depends(get_db),
) -> UserResponse:
    if user_id == actor.id and (body.is_active is False or body.role not in (None, actor.role)):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You cannot change your own role or deactivate your own account",
        )
    try:
        user = identity.update_user(
            session,
            user_id=user_id,
            actor_id=actor.id,
            full_name=body.full_name,
            role=body.role,
            is_active=body.is_active,
        )
    except identity.UserNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from None
    except identity.LastAdminError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from None
    session.commit()
    return _to_response(user)


@router.post(
    "/{user_id}/reset-password", response_model=UserResponse, summary="Set a temporary password"
)
def reset_password(
    user_id: uuid.UUID,
    body: ResetPasswordRequest,
    actor: CurrentUser = Depends(require(Permission.USERS_MANAGE)),
    session: Session = Depends(get_db),
) -> UserResponse:
    """Replace a user's password and clear any lockout. They must change it at next sign-in."""
    user = session.get(UserModel, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    try:
        identity.set_password(
            session,
            user=user,
            new_password=body.new_password,
            actor_id=actor.id,
            require_change_on_next_login=user_id != actor.id,
        )
    except WeakPasswordError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from None
    session.commit()
    return _to_response(user)

"""Administrator user management."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from raahat.api.deps import CurrentUser, get_db, require
from raahat.application.identity import service as identity
from raahat.infrastructure.database.models.user import UserModel
from raahat.security.jurisdiction import Jurisdiction, UnknownJurisdiction
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
    state_code: Optional[str]
    district_code: Optional[str]
    jurisdiction: str


class IssueRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level: Literal["national", "state", "district"]
    state_code: Optional[str] = Field(default=None, max_length=8)
    district_code: Optional[str] = Field(default=None, max_length=8)


class IssuedPassword(BaseModel):
    user: "UserResponse"
    password: str
    created: bool


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
        state_code=user.state_code,
        district_code=user.district_code,
        jurisdiction=Jurisdiction(user.state_code, user.district_code).label
        if user.username.startswith(("national", "state-", "district-")) or user.state_code
        else "Individual account",
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


@router.post(
    "/jurisdictions/issue", response_model=IssuedPassword,
    summary="Create a control room account, or replace its password",
)
def issue_jurisdiction_password(
    body: IssueRequest,
    actor: CurrentUser = Depends(require(Permission.USERS_MANAGE)),
    session: Session = Depends(get_db),
) -> IssuedPassword:
    """Generate a new random password for the jurisdiction's account.

    The password is returned once and stored only as a hash. Any session
    signed in with the previous password ends.
    """
    if not actor.jurisdiction.is_national:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the national administration issues passwords")
    try:
        if body.level == "national":
            target = Jurisdiction()
        else:
            if not body.state_code or (body.level == "district" and not body.district_code):
                raise UnknownJurisdiction("Choose the state and district")
            target = Jurisdiction.validated(
                body.state_code, body.district_code if body.level == "district" else None
            )
    except UnknownJurisdiction as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from None
    existed = identity.get_user_by_username(session, target.username) is not None
    issued = identity.provision_jurisdiction_account(
        session, jurisdiction=target, created_by=actor.id, reset_existing=True
    )
    session.commit()
    user = identity.get_user_by_username(session, target.username)
    assert user is not None and issued.password is not None
    return IssuedPassword(user=_to_response(user), password=issued.password, created=not existed)

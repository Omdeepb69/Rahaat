"""User account management and credential verification."""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from raahat.config import Settings
from raahat.infrastructure.database.models.user import UserModel
from raahat.infrastructure.database.repositories.audit import append_audit
from raahat.security.passwords import (
    DUMMY_HASH,
    hash_password,
    needs_rehash,
    validate_password_strength,
    verify_password,
)
from raahat.security.permissions import Role

USERNAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")

if TYPE_CHECKING:
    from raahat.security.jurisdiction import Jurisdiction


class IdentityError(Exception):
    """Base class for account errors that are safe to show to the caller."""


class InvalidCredentialsError(IdentityError):
    pass


class AccountLockedError(IdentityError):
    def __init__(self, until: datetime) -> None:
        self.until = until
        super().__init__("Account is temporarily locked after repeated failed sign-ins")


class UsernameTakenError(IdentityError):
    pass


class UserNotFoundError(IdentityError):
    pass


class LastAdminError(IdentityError):
    pass


@dataclass(frozen=True)
class AuthenticatedUser:
    id: uuid.UUID
    username: str
    full_name: str
    role: Role
    token_version: int
    must_change_password: bool
    state_code: Optional[str] = None
    district_code: Optional[str] = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def normalise_username(raw: str) -> str:
    username = raw.strip().lower()
    if not USERNAME_PATTERN.match(username):
        raise IdentityError(
            "Username must be 3-64 characters: lowercase letters, digits, dot, dash or underscore"
        )
    return username


def get_user_by_username(session: Session, username: str) -> Optional[UserModel]:
    return session.execute(
        select(UserModel).where(func.lower(UserModel.username) == username.strip().lower())
    ).scalar_one_or_none()


def to_authenticated(user: UserModel) -> AuthenticatedUser:
    return AuthenticatedUser(
        id=user.id,
        username=user.username,
        full_name=user.full_name,
        role=Role(user.role),
        token_version=user.token_version,
        must_change_password=user.must_change_password,
        state_code=user.state_code,
        district_code=user.district_code,
    )


def authenticate(
    session: Session, *, username: str, password: str, settings: Settings
) -> AuthenticatedUser:
    """Verify credentials. Commits lockout bookkeeping; raises on any failure.

    The same error is raised for an unknown user, a wrong password and a
    deactivated account, and an unknown user costs one hash verification, so
    the response does not reveal which usernames exist.
    """
    user = get_user_by_username(session, username)
    now = _now()
    if user is None:
        verify_password(password, DUMMY_HASH)
        raise InvalidCredentialsError("Invalid username or password")

    if user.locked_until is not None and user.locked_until > now:
        raise AccountLockedError(user.locked_until)

    if not verify_password(password, user.password_hash) or not user.is_active:
        user.failed_login_count += 1
        locked = user.failed_login_count >= settings.max_failed_logins
        if locked:
            user.locked_until = now + timedelta(seconds=settings.lockout_seconds)
            user.failed_login_count = 0
        append_audit(
            session,
            action="user.login_failed",
            actor_id=None,
            entity_type="user",
            entity_id=user.id,
            payload={"locked": locked},
        )
        session.commit()
        raise InvalidCredentialsError("Invalid username or password")

    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    append_audit(
        session,
        action="user.login",
        actor_id=user.id,
        entity_type="user",
        entity_id=user.id,
        payload={},
    )
    session.commit()
    return to_authenticated(user)


def create_user(
    session: Session,
    *,
    username: str,
    full_name: str,
    role: Role,
    password: str,
    created_by: Optional[uuid.UUID],
    must_change_password: bool = True,
    state_code: Optional[str] = None,
    district_code: Optional[str] = None,
) -> UserModel:
    username = normalise_username(username)
    full_name = full_name.strip()
    if not full_name:
        raise IdentityError("Full name is required")
    validate_password_strength(password, username=username)
    if get_user_by_username(session, username) is not None:
        raise UsernameTakenError(f"Username '{username}' is already in use")
    user = UserModel(
        id=uuid.uuid4(),
        username=username,
        full_name=full_name,
        role=role.value,
        password_hash=hash_password(password),
        must_change_password=must_change_password,
        created_by=created_by,
        state_code=state_code,
        district_code=district_code,
    )
    session.add(user)
    session.flush()
    append_audit(
        session,
        action="user.created",
        actor_id=created_by,
        entity_type="user",
        entity_id=user.id,
        payload={"username": username, "role": role.value,
                 "state_code": state_code, "district_code": district_code},
    )
    return user


def _active_admin_count(session: Session) -> int:
    return session.execute(
        select(func.count(UserModel.id)).where(
            UserModel.role == Role.ADMIN.value, UserModel.is_active.is_(True)
        )
    ).scalar_one()


def update_user(
    session: Session,
    *,
    user_id: uuid.UUID,
    actor_id: uuid.UUID,
    full_name: Optional[str] = None,
    role: Optional[Role] = None,
    is_active: Optional[bool] = None,
) -> UserModel:
    user = session.get(UserModel, user_id)
    if user is None:
        raise UserNotFoundError("User not found")
    changes: dict[str, object] = {}

    removes_admin = user.role == Role.ADMIN.value and user.is_active and (
        (role is not None and role != Role.ADMIN) or is_active is False
    )
    if removes_admin and _active_admin_count(session) <= 1:
        raise LastAdminError("The last active administrator cannot be demoted or deactivated")

    if full_name is not None and full_name.strip() and full_name.strip() != user.full_name:
        changes["full_name"] = {"from": user.full_name, "to": full_name.strip()}
        user.full_name = full_name.strip()
    if role is not None and role.value != user.role:
        changes["role"] = {"from": user.role, "to": role.value}
        user.role = role.value
        user.token_version += 1
    if is_active is not None and is_active != user.is_active:
        changes["is_active"] = {"from": user.is_active, "to": is_active}
        user.is_active = is_active
        user.token_version += 1
        if is_active:
            user.failed_login_count = 0
            user.locked_until = None
    if changes:
        session.flush()
        append_audit(
            session,
            action="user.updated",
            actor_id=actor_id,
            entity_type="user",
            entity_id=user.id,
            payload={"changes": changes},
        )
    return user


def set_password(
    session: Session,
    *,
    user: UserModel,
    new_password: str,
    actor_id: uuid.UUID,
    require_change_on_next_login: bool,
) -> None:
    validate_password_strength(new_password, username=user.username)
    user.password_hash = hash_password(new_password)
    user.must_change_password = require_change_on_next_login
    user.token_version += 1
    user.failed_login_count = 0
    user.locked_until = None
    session.flush()
    append_audit(
        session,
        action="user.password_changed" if actor_id == user.id else "user.password_reset",
        actor_id=actor_id,
        entity_type="user",
        entity_id=user.id,
        payload={},
    )


def change_own_password(
    session: Session, *, user_id: uuid.UUID, current_password: str, new_password: str
) -> UserModel:
    user = session.get(UserModel, user_id)
    if user is None:
        raise UserNotFoundError("User not found")
    if not verify_password(current_password, user.password_hash):
        raise InvalidCredentialsError("Current password is incorrect")
    if current_password == new_password:
        raise IdentityError("New password must differ from the current password")
    set_password(
        session,
        user=user,
        new_password=new_password,
        actor_id=user.id,
        require_change_on_next_login=False,
    )
    return user


_PASSWORD_ALPHABET = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789"


def generate_password() -> str:
    """A random password in four groups of four characters (about 91 bits).

    Look-alike characters (0/O, 1/l/I) are left out so it can be read aloud
    or copied from paper.
    """
    import secrets

    return "-".join(
        "".join(secrets.choice(_PASSWORD_ALPHABET) for _ in range(4)) for _ in range(4)
    )


@dataclass(frozen=True)
class IssuedCredential:
    username: str
    label: str
    state_code: Optional[str]
    district_code: Optional[str]
    password: Optional[str]  # None when the account already existed and was left alone


def provision_jurisdiction_account(
    session: Session,
    *,
    jurisdiction: "Jurisdiction",
    created_by: Optional[uuid.UUID],
    reset_existing: bool = False,
) -> IssuedCredential:
    """Create (or, if asked, re-key) the control room account for a jurisdiction.

    National accounts are administrators; state and district accounts are
    control rooms limited to their area. Does not commit.
    """
    username = jurisdiction.username
    existing = get_user_by_username(session, username)
    role = Role.ADMIN if jurisdiction.is_national else Role.CONTROL_ROOM
    if existing is not None:
        if not reset_existing:
            return IssuedCredential(username, jurisdiction.label, jurisdiction.state_code,
                                    jurisdiction.district_code, None)
        password = generate_password()
        existing.password_hash = hash_password(password)
        existing.token_version += 1
        existing.failed_login_count = 0
        existing.locked_until = None
        existing.is_active = True
        existing.must_change_password = False
        append_audit(
            session, action="user.password_reset", actor_id=created_by, entity_type="user",
            entity_id=existing.id, payload={"username": username, "issued": True},
        )
        return IssuedCredential(username, jurisdiction.label, jurisdiction.state_code,
                                jurisdiction.district_code, password)
    password = generate_password()
    create_user(
        session, username=username, full_name=jurisdiction.label, role=role, password=password,
        created_by=created_by, must_change_password=False,
        state_code=jurisdiction.state_code, district_code=jurisdiction.district_code,
    )
    return IssuedCredential(username, jurisdiction.label, jurisdiction.state_code,
                            jurisdiction.district_code, password)

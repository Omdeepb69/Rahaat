"""Request-scoped dependencies: database session, settings, authenticated user."""
from __future__ import annotations

import ipaddress
import uuid
from dataclasses import dataclass
from typing import Callable, Generator, Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from raahat.config import Settings, get_settings
from raahat.infrastructure.database.models.user import UserModel
from raahat.infrastructure.database.session import create_sync_engine, get_sync_sessionmaker
from raahat.security.permissions import Permission, Role, permissions_for
from raahat.security.ratelimit import SlidingWindowLimiter
from raahat.security.tokens import InvalidTokenError, TokenClaims, decode_access_token

_engine: Optional[Engine] = None
_session_factory: Optional[sessionmaker[Session]] = None
rate_limiter = SlidingWindowLimiter()


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_sync_engine(get_settings().database_url)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _session_factory
    if _session_factory is None:
        _session_factory = get_sync_sessionmaker(get_engine())
    return _session_factory


def reset_engine() -> None:
    """Dispose the engine. Used on shutdown and by tests that change DATABASE_URL."""
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None


def get_db(
    factory: sessionmaker[Session] = Depends(get_session_factory),
) -> Generator[Session, None, None]:
    """One session per request. Handlers commit; anything uncommitted rolls back."""
    with factory() as session:
        yield session


def client_ip(request: Request, settings: Settings) -> str:
    """Best available client address.

    Forwarded headers are honoured only when enabled and only when the direct
    peer is loopback (the local tunnel agent), so a remote client cannot spoof
    its address to evade rate limits.
    """
    peer = request.client.host if request.client else "unknown"
    if not settings.trust_forwarded_headers:
        return peer
    try:
        if not ipaddress.ip_address(peer).is_loopback:
            return peer
    except ValueError:
        return peer
    forwarded = request.headers.get("x-forwarded-for", "")
    first = forwarded.split(",")[0].strip()
    return first or peer


@dataclass(frozen=True)
class CurrentUser:
    id: uuid.UUID
    username: str
    full_name: str
    role: Role
    permissions: frozenset[Permission]
    must_change_password: bool
    claims: Optional[TokenClaims] = None

    def can(self, permission: Permission) -> bool:
        return permission in self.permissions


_bearer = HTTPBearer(auto_error=False)

_UNAUTHENTICATED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Authentication required",
    headers={"WWW-Authenticate": "Bearer"},
)


def current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> CurrentUser:
    """Resolve the bearer token to an active user, re-reading role and status."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _UNAUTHENTICATED
    try:
        claims = decode_access_token(credentials.credentials, secret=settings.secret_key)
    except InvalidTokenError:
        raise _UNAUTHENTICATED from None

    user = session.get(UserModel, claims.user_id)
    if user is None or not user.is_active or user.token_version != claims.token_version:
        raise _UNAUTHENTICATED

    decision = rate_limiter.check(f"api:{user.id}", limit=settings.api_rate_per_minute)
    if not decision.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests",
            headers={"Retry-After": str(decision.retry_after_seconds)},
        )

    role = Role(user.role)
    resolved = CurrentUser(
        id=user.id,
        username=user.username,
        full_name=user.full_name,
        role=role,
        permissions=permissions_for(role),
        must_change_password=user.must_change_password,
        claims=claims,
    )
    request.state.user_id = str(user.id)
    return resolved


def require(*permissions: Permission) -> Callable[..., CurrentUser]:
    """Dependency factory: the caller must hold every listed permission.

    A user who has not yet replaced an administrator-issued password may only
    reach the endpoints that let them do so.
    """

    def dependency(user: CurrentUser = Depends(current_user)) -> CurrentUser:
        if user.must_change_password:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Password change required before continuing",
            )
        missing = [p.value for p in permissions if p not in user.permissions]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Your role does not permit this action ({', '.join(missing)})",
            )
        return user

    return dependency

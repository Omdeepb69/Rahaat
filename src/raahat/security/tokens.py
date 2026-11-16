"""Signed access tokens (JWT, HS256).

Tokens are short-lived and carry only identifiers. Role, active flag and token
version are re-read from the database on every request, so deactivating a user
or changing a password takes effect immediately rather than at expiry.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

import jwt

ALGORITHM = "HS256"
ISSUER = "raahat"


class InvalidTokenError(Exception):
    """The token is malformed, expired, or was not issued by this deployment."""


@dataclass(frozen=True)
class TokenClaims:
    user_id: uuid.UUID
    token_version: int
    session_started_at: int
    issued_at: int
    expires_at: int


def issue_access_token(
    *,
    secret: str,
    user_id: uuid.UUID,
    token_version: int,
    ttl_seconds: int,
    session_started_at: int | None = None,
    now: int | None = None,
) -> tuple[str, TokenClaims]:
    issued = int(time.time()) if now is None else now
    claims = TokenClaims(
        user_id=user_id,
        token_version=token_version,
        session_started_at=session_started_at if session_started_at is not None else issued,
        issued_at=issued,
        expires_at=issued + ttl_seconds,
    )
    token = jwt.encode(
        {
            "iss": ISSUER,
            "sub": str(claims.user_id),
            "ver": claims.token_version,
            "sst": claims.session_started_at,
            "iat": claims.issued_at,
            "exp": claims.expires_at,
        },
        secret,
        algorithm=ALGORITHM,
    )
    return token, claims


def decode_access_token(token: str, *, secret: str) -> TokenClaims:
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=[ALGORITHM],
            issuer=ISSUER,
            options={"require": ["exp", "iat", "sub", "iss"]},
        )
        return TokenClaims(
            user_id=uuid.UUID(payload["sub"]),
            token_version=int(payload["ver"]),
            session_started_at=int(payload["sst"]),
            issued_at=int(payload["iat"]),
            expires_at=int(payload["exp"]),
        )
    except (jwt.PyJWTError, KeyError, ValueError, TypeError) as exc:
        raise InvalidTokenError(str(exc)) from exc

"""Password hashing with scrypt (RFC 7914) from the standard library.

Stored format: ``scrypt$<log2 N>$<r>$<p>$<salt b64>$<hash b64>``. Parameters are
stored with every hash so they can be raised later without invalidating
existing accounts; ``needs_rehash`` reports hashes made with older parameters.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

_LOG2_N = 15  # N = 32768, ~32 MiB per hash with r=8
_R = 8
_P = 1
_SALT_BYTES = 16
_KEY_BYTES = 32
_MAXMEM = 128 * 1024 * 1024

MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 256


class WeakPasswordError(ValueError):
    """The supplied password does not meet the minimum policy."""


def validate_password_strength(password: str, *, username: str = "") -> None:
    """Enforce a length-first policy (NIST SP 800-63B): long, not a known trivial value."""
    if len(password) < MIN_PASSWORD_LENGTH:
        raise WeakPasswordError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise WeakPasswordError(f"Password must be at most {MAX_PASSWORD_LENGTH} characters")
    lowered = password.lower()
    if username and username.lower() in lowered:
        raise WeakPasswordError("Password must not contain the username")
    if len(set(password)) < 5:
        raise WeakPasswordError("Password is too repetitive")
    if lowered in {"password1234", "raahat123456", "administrator", "123456789012"}:
        raise WeakPasswordError("Password is too common")


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _derive(password: str, salt: bytes, log2_n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=1 << log2_n,
        r=r,
        p=p,
        dklen=_KEY_BYTES,
        maxmem=_MAXMEM,
    )


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = _derive(password, salt, _LOG2_N, _R, _P)
    return f"scrypt${_LOG2_N}${_R}${_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time verification. Returns False for malformed stored values."""
    try:
        scheme, log2_n, r, p, salt_b64, hash_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
        actual = _derive(password, salt, int(log2_n), int(r), int(p))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def needs_rehash(stored: str) -> bool:
    try:
        _, log2_n, r, p, _, _ = stored.split("$")
        return (int(log2_n), int(r), int(p)) != (_LOG2_N, _R, _P)
    except ValueError:
        return True


# A hash of a random value, verified against when the username does not exist so
# that an unknown user costs the same time as a wrong password.
DUMMY_HASH = hash_password(secrets.token_urlsafe(24))

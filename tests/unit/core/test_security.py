from __future__ import annotations

import uuid

import pytest

from raahat.security import passwords, tokens
from raahat.security.permissions import Permission, Role, role_has
from raahat.security.ratelimit import SlidingWindowLimiter


def test_password_hash_roundtrip_and_salt():
    first = passwords.hash_password("Long-Enough-Password-1")
    second = passwords.hash_password("Long-Enough-Password-1")
    assert first != second
    assert passwords.verify_password("Long-Enough-Password-1", first)
    assert not passwords.verify_password("Long-Enough-Password-2", first)
    assert not passwords.verify_password("anything", "not-a-hash")
    assert not passwords.needs_rehash(first)


@pytest.mark.parametrize("candidate", ["short", "aaaaaaaaaaaaaaaa", "operator-1-password"])
def test_weak_passwords_rejected(candidate):
    with pytest.raises(passwords.WeakPasswordError):
        passwords.validate_password_strength(candidate, username="operator-1")


def test_token_roundtrip_expiry_and_signature():
    user = uuid.uuid4()
    token, _ = tokens.issue_access_token(secret="s" * 40, user_id=user, token_version=3, ttl_seconds=60)
    claims = tokens.decode_access_token(token, secret="s" * 40)
    assert claims.user_id == user and claims.token_version == 3
    with pytest.raises(tokens.InvalidTokenError):
        tokens.decode_access_token(token, secret="t" * 40)
    expired, _ = tokens.issue_access_token(
        secret="s" * 40, user_id=user, token_version=0, ttl_seconds=60, now=1_000_000
    )
    with pytest.raises(tokens.InvalidTokenError):
        tokens.decode_access_token(expired, secret="s" * 40)


def test_role_permissions_match_workflows():
    assert role_has(Role.DISPATCHER, Permission.DISPATCH_DECIDE)
    assert not role_has(Role.OPERATOR, Permission.DISPATCH_DECIDE)
    assert not role_has(Role.RESOURCE_COORDINATOR, Permission.CALLER_PII_READ)
    assert not role_has(Role.OBSERVER, Permission.REPORTS_CREATE)
    assert all(role_has(Role.ADMIN, p) for p in Permission)


def test_rate_limiter_window():
    limiter = SlidingWindowLimiter()
    for i in range(3):
        assert limiter.check("k", limit=3, now=100.0 + i).allowed
    blocked = limiter.check("k", limit=3, now=103.0)
    assert not blocked.allowed and blocked.retry_after_seconds >= 1
    assert limiter.check("k", limit=3, now=161.0).allowed


def test_production_requires_real_secret(monkeypatch):
    from raahat.config import ConfigurationError, load_settings

    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("RAAHAT_SECRET_KEY", "change-me")
    with pytest.raises(ConfigurationError):
        load_settings()
    monkeypatch.setenv("RAAHAT_SECRET_KEY", "x" * 48)
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "*")
    with pytest.raises(ConfigurationError):
        load_settings()

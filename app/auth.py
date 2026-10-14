"""Shared-token private gate (SITE-B-001, DIS-NF-003)."""
from __future__ import annotations

import hmac
import os

from fastapi import Cookie, Header, HTTPException

COOKIE_NAME = "site_token"


def site_token() -> str:
    return os.environ.get("SITE_TOKEN", "change-me")


def is_authenticated(authorization: str | None, cookie: str | None) -> bool:
    """True if the Bearer token or login cookie matches (SITE-B-001)."""
    expected = site_token()
    if authorization and authorization.startswith("Bearer "):
        if hmac.compare_digest(authorization[len("Bearer "):], expected):
            return True
    if cookie and hmac.compare_digest(cookie, expected):
        return True
    return False


def safe_next(target: str | None) -> str:
    """Same-origin relative redirect target only (SITE-B-001a)."""
    if target and target.startswith("/") and not target.startswith("//"):
        return target
    return "/"


def check_token(token: str) -> bool:
    """Constant-time shared-token comparison (SITE-B-001a)."""
    return hmac.compare_digest(token, site_token())


async def require_auth(
    authorization: str | None = Header(default=None),
    site_token_cookie: str | None = Cookie(default=None, alias="site_token"),
) -> None:
    if is_authenticated(authorization, site_token_cookie):
        return
    raise HTTPException(status_code=401, detail="unauthorized")

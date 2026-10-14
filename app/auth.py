"""Shared-token private gate (SITE-B-001, DIS-NF-003)."""
from __future__ import annotations

import os

from fastapi import Cookie, Header, HTTPException


def site_token() -> str:
    return os.environ.get("SITE_TOKEN", "change-me")


async def require_auth(
    authorization: str | None = Header(default=None),
    site_token_cookie: str | None = Cookie(default=None, alias="site_token"),
) -> None:
    expected = site_token()
    if authorization and authorization.startswith("Bearer "):
        if authorization[len("Bearer "):] == expected:
            return
    if site_token_cookie and site_token_cookie == expected:
        return
    raise HTTPException(status_code=401, detail="unauthorized")

"""Authentication dependency for host-capability changing APIs."""

from __future__ import annotations

import hmac

from fastapi import HTTPException, Request


def require_privileged(request: Request) -> str:
    settings = request.app.state.platform.settings
    expected = settings.privileged_api_token
    authorization = request.headers.get("authorization", "")
    scheme, _, supplied = authorization.partition(" ")
    if not expected or scheme.lower() != "bearer" or not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="需要扩展管理凭证")
    return "local-admin"

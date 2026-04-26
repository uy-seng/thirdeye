from __future__ import annotations

import secrets

from fastapi import HTTPException, Request, status

NATIVE_CLIENT_HEADER = "x-thirdeye-client"
NATIVE_CLIENT_VALUE = "macos"
API_TOKEN_QUERY_PARAM = "auth_token"


def session_user(request: Request) -> str | None:
    return request.session.get("user")


def native_client_requested(request: Request) -> bool:
    return request.headers.get(NATIVE_CLIENT_HEADER) == NATIVE_CLIENT_VALUE


def issue_api_token(request: Request, user: str) -> str:
    token = secrets.token_urlsafe(32)
    request.app.state.api_tokens[token] = user
    return token


def request_api_token(request: Request) -> str | None:
    authorization = request.headers.get("authorization", "")
    scheme, _, value = authorization.partition(" ")
    if scheme.lower() == "bearer" and value:
        return value
    return request.query_params.get(API_TOKEN_QUERY_PARAM)


def revoke_api_token(request: Request) -> None:
    token = request_api_token(request)
    if token:
        request.app.state.api_tokens.pop(token, None)


def api_token_user(request: Request) -> str | None:
    token = request_api_token(request)
    if not token:
        return None
    return request.app.state.api_tokens.get(token)


def authenticated_api_user(request: Request) -> str | None:
    return session_user(request) or api_token_user(request)



def current_api_user(request: Request) -> str:
    user = authenticated_api_user(request)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required")
    return user

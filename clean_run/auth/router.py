from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, Header, HTTPException, Request, Response, status

from .config import AuthConfigurationError, AuthSettings
from .repository import DuplicateEmailError, build_auth_repository_from_env
from .schemas import AuthResponse, LoginRequest, PublicUser, SignupRequest
from .security import InvalidAccessTokenError
from .service import AuthService, InvalidCredentialsError, InvalidRefreshTokenError, public_user


router = APIRouter(prefix="/auth", tags=["authentication"])


@lru_cache(maxsize=1)
def get_auth_service() -> AuthService:
    settings = AuthSettings.from_env()
    repository = build_auth_repository_from_env()
    if repository is None:
        raise AuthConfigurationError("MongoDB is required for authentication.")
    return AuthService(repository, settings)


def _service() -> AuthService:
    try:
        return get_auth_service()
    except AuthConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _set_refresh_cookie(response: Response, service: AuthService, token: str) -> None:
    settings = service.settings
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=token,
        max_age=settings.refresh_cookie_max_age,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.refresh_cookie_samesite,
        path="/",
        domain=settings.cookie_domain,
    )


def _clear_refresh_cookie(response: Response, service: AuthService) -> None:
    settings = service.settings
    response.delete_cookie(
        key=settings.refresh_cookie_name,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.refresh_cookie_samesite,
        path="/",
        domain=settings.cookie_domain,
    )


def _read_bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="Authentication is required.")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Bearer access token is required.")
    return token


def optional_authenticated_user_id(authorization: str | None) -> str | None:
    if not authorization:
        return None
    service = _service()
    try:
        user = service.user_from_access_token(_read_bearer_token(authorization))
    except InvalidAccessTokenError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    if user is None:
        raise HTTPException(status_code=401, detail="Account is unavailable.")
    return str(user["user_id"])


def authenticated_user_id(authorization: str | None) -> str:
    user_id = optional_authenticated_user_id(authorization)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Authentication is required.")
    return user_id


@router.post("/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def signup(req: SignupRequest, response: Response):
    service = _service()
    try:
        payload, refresh_token = service.signup(
            name=req.name,
            email=req.email,
            password=req.password,
        )
    except DuplicateEmailError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _set_refresh_cookie(response, service, refresh_token)
    return payload


@router.post("/login", response_model=AuthResponse)
def login(req: LoginRequest, response: Response):
    service = _service()
    try:
        payload, refresh_token = service.login(email=req.email, password=req.password)
    except InvalidCredentialsError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    _set_refresh_cookie(response, service, refresh_token)
    return payload


@router.post("/refresh", response_model=AuthResponse)
def refresh(request: Request, response: Response):
    service = _service()
    refresh_token = request.cookies.get(service.settings.refresh_cookie_name)
    if not refresh_token:
        raise HTTPException(status_code=401, detail="No refresh session is available.")
    try:
        payload, new_refresh_token = service.refresh(refresh_token)
    except InvalidRefreshTokenError as exc:
        _clear_refresh_cookie(response, service)
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    _set_refresh_cookie(response, service, new_refresh_token)
    return payload


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def logout(request: Request, response: Response) -> Response:
    service = _service()
    service.logout(request.cookies.get(service.settings.refresh_cookie_name))
    _clear_refresh_cookie(response, service)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=PublicUser)
def me(authorization: str | None = Header(default=None)):
    service = _service()
    try:
        user = service.user_from_access_token(_read_bearer_token(authorization))
    except InvalidAccessTokenError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    if user is None:
        raise HTTPException(status_code=401, detail="Account is unavailable.")
    return public_user(user)

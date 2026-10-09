"""Password hashing (PBKDF2-SHA256), JWT issuing and role-based access dependencies."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models as m
from app.config import get_settings
from app.database import get_db

ITERATIONS = 200_000
ROLES = ("ADMIN", "OPERATOR", "ANALYST", "VIEWER")
_bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
    return f"pbkdf2_sha256${ITERATIONS}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iters, salt_b64, dk_b64 = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.b64decode(salt_b64), int(iters))
        return hmac.compare_digest(dk, base64.b64decode(dk_b64))
    except ValueError:
        return False


def create_token(user: m.User) -> str:
    s = get_settings()
    payload = {"sub": user.username, "uid": user.id, "role": user.role,
               "exp": datetime.now(timezone.utc) + timedelta(minutes=s.jwt_expire_minutes)}
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)


def _unauthorized(message: str) -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, detail={"code": "UNAUTHORIZED", "message": message},
                         headers={"WWW-Authenticate": "Bearer"})


def user_from_token(db: Session, token: str) -> m.User:
    s = get_settings()
    try:
        data = jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm])
    except jwt.PyJWTError:
        raise _unauthorized("Invalid or expired token") from None
    user = db.scalar(select(m.User).where(m.User.username == data.get("sub")))
    if user is None or not user.active:
        raise _unauthorized("User no longer exists")
    return user


def current_user(creds: HTTPAuthorizationCredentials | None = Depends(_bearer), db: Session = Depends(get_db)) -> m.User:
    if creds is None:
        raise _unauthorized("Missing bearer token")
    return user_from_token(db, creds.credentials)


def require(*roles: str):
    """Dependency factory: allow ADMIN plus the listed roles."""
    allowed = set(roles) | {"ADMIN"}

    def dep(user: m.User = Depends(current_user)) -> m.User:
        if user.role not in allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN,
                                detail={"code": "FORBIDDEN", "message": f"Role {user.role} cannot perform this action"})
        return user

    return dep

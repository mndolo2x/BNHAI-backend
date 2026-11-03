"""Password hashing and short-lived JWT creation for the development API.

A randomly generated process-local key is used when JWT_SECRET_KEY is unset in
local development. Tokens then become invalid after a server restart. Set a
strong JWT_SECRET_KEY via the environment for a stable local development setup.
Production startup is refused unless a secret is explicitly configured.
"""
from datetime import datetime, timedelta, timezone
import os
import secrets

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from jwt import InvalidTokenError

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
APP_ENV = os.getenv("APP_ENV", "development").strip().lower()

_configured_secret = os.getenv("JWT_SECRET_KEY")
if _configured_secret:
    if len(_configured_secret) < 32:
        raise RuntimeError("JWT_SECRET_KEY must be at least 32 characters long.")
    JWT_SECRET_KEY = _configured_secret
elif APP_ENV in {"production", "prod"}:
    raise RuntimeError("JWT_SECRET_KEY must be set when APP_ENV is production.")
else:
    JWT_SECRET_KEY = secrets.token_urlsafe(48)

password_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    """Hash a password using Argon2id; never store plaintext passwords."""
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a supplied password without exposing hashing internals."""
    try:
        return password_hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def create_access_token(user_id: str) -> str:
    """Create a signed, short-lived bearer token for one user ID."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "iat": now,
        "exp": now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        "type": "access",
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> str:
    """Return the user ID from a valid access token or raise InvalidTokenError."""
    payload = jwt.decode(
        token,
        JWT_SECRET_KEY,
        algorithms=[ALGORITHM],
        options={"require": ["sub", "iat", "exp", "type"]},
    )
    if payload.get("type") != "access" or not isinstance(payload.get("sub"), str):
        raise InvalidTokenError("Invalid access token")
    return payload["sub"]

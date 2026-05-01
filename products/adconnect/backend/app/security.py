from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt

from .config import settings

logger = logging.getLogger(__name__)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError as exc:
        # bcrypt raises ValueError on malformed hash strings (e.g. legacy /
        # corrupted DB rows). Logged for ops visibility — a spike of these
        # warnings means stored hashes are corrupt and need investigation.
        logger.warning("security: bcrypt.checkpw rejected stored hash (%s); password verify returns False", exc)
        return False


def create_token(payload: dict[str, Any]) -> str:
    to_encode = payload.copy()
    to_encode["exp"] = datetime.now(timezone.utc) + timedelta(
        minutes=settings.jwt_expires_minutes
    )
    return jwt.encode(to_encode, settings.jwt_secret, algorithm="HS256")


def decode_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])

"""
Crisis Schemas — Crisis alert review and management.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class CrisisAlertReview(BaseModel):
    """Review a crisis alert."""

    status: Literal["revisado", "falso_positivo", "encaminhado"]

"""
Crisis Schemas — Crisis alert review and management.
"""
from __future__ import annotations

from typing import Literal

from noctusai_lib.api import StrictHttpModel


class CrisisAlertReview(StrictHttpModel):
    """Review a crisis alert."""

    status: Literal["revisado", "falso_positivo", "encaminhado"]

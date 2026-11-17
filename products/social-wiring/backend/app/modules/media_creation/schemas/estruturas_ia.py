"""Estruturas -- request schema of the AI draft (estruturas-contract.md section 6.2). Strict: a misspelt field is a 422.

NOTE: no ``from __future__ import annotations`` (the route is wrapped by slowapi's limiter).
"""
import uuid

from noctusai_lib.api import StrictHttpModel


class APartirDoViralBody(StrictHttpModel):
    viral_id: uuid.UUID

"""
Structured logging configuration for the ERP API.

Re-exports everything from the shared package so that existing
``from app.logging_config import ...`` imports continue to work.
"""
from noctusai_shared.logging_config import *  # noqa: F401,F403

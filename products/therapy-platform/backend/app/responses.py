"""
Standardized response utilities for the Therapy Platform API.

Re-exports everything from the shared package so that existing
``from app.responses import ...`` imports continue to work.
"""
from noctusai_shared.responses import *  # noqa: F401,F403

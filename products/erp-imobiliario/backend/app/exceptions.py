"""
Centralized exception handling for the ERP API.

Re-exports everything from the shared package so that existing
``from app.exceptions import ...`` imports continue to work.
"""
from noctusai_shared.exceptions import *  # noqa: F401,F403

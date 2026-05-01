"""
Middleware for the Therapy Platform API.

Re-exports everything from the shared package so that existing
``from app.middleware import ...`` imports continue to work.
"""
from noctusai_lib.api.middleware import *  # noqa: F401,F403

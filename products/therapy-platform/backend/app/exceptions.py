"""
Centralized exception handling for the Therapy Platform API.

Re-exports everything from the shared package so that existing
``from app.exceptions import ...`` imports continue to work.
"""
from noctusai_lib.exceptions import *  # noqa: F401,F403

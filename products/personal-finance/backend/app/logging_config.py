"""
Structured logging configuration for the Personal Finance API.

Re-exports everything from the shared package and adds PF-specific
logger suppression (yfinance).
"""
import logging
from noctusai_lib.logging_config import *  # noqa: F401,F403
from noctusai_lib.logging_config import configure_logging as _configure_logging


def configure_logging(debug: bool = True, json_logs: bool = False, app_name: str = "personal-finance") -> None:
    """Configure logging with PF-specific noise suppression."""
    _configure_logging(debug=debug, json_logs=json_logs, app_name=app_name)
    # Suppress noisy yfinance logs
    logging.getLogger("yfinance").setLevel(logging.WARNING)

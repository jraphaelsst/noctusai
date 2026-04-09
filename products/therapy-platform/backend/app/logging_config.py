"""
Structured logging configuration for the Therapy Platform API.

Re-exports everything from the shared package and adds
product-specific logger suppression.
"""
import logging
from noctusai_shared.logging_config import *  # noqa: F401,F403
from noctusai_shared.logging_config import configure_logging as _configure_logging


def configure_logging(debug: bool = True, json_logs: bool = False, app_name: str = "therapy-platform") -> None:
    """Configure logging with therapy-specific noise suppression."""
    _configure_logging(debug=debug, json_logs=json_logs, app_name=app_name)
    # Suppress noisy third-party loggers
    logging.getLogger("livekit").setLevel(logging.WARNING)
    logging.getLogger("stripe").setLevel(logging.WARNING)
    logging.getLogger("googleapiclient").setLevel(logging.WARNING)

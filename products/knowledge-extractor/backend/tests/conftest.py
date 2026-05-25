"""Test bootstrap: ensure `app` is importable regardless of invocation dir."""
import sys
from pathlib import Path

# Clear the slowapi in-memory limiter between tests — the Redis-down fallback
# leaks bucket state across tests under pytest-randomly (→ spurious 429s).
from noctusai_lib.testing.fixtures import reset_rate_limiter  # noqa: F401

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

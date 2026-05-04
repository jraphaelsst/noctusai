"""Web search tool — `web_search(query)`.

Per design-reference.md §3 + Notes:
- Rate-limited; scoped per agent (PM/UX for references; Security for CVEs).
- Stub raises NotImplementedError if ``SERPER_API_KEY`` (or equivalent) is
  unset. The real wiring is a follow-up — for v1 the dev_team imports
  cleanly but agents that hit web_search without a key get a clear error.
"""

from __future__ import annotations

import os
from typing import Any, Callable


def web_search(query: str, *, num_results: int = 5) -> dict[str, Any]:
    """Run a web search via Serper (stub — requires ``SERPER_API_KEY``).

    Args:
        query: Search query string.
        num_results: How many results to return (default 5).

    Raises:
        NotImplementedError: ``SERPER_API_KEY`` is unset (default in v1).
    """
    api_key = os.environ.get("SERPER_API_KEY")
    if not api_key:
        raise NotImplementedError(
            "web_search is stubbed pending SERPER_API_KEY wiring. "
            "Set SERPER_API_KEY in the environment to enable; the dev_team "
            "ships with the stub so PM/UX/Security charters reference the "
            "tool name even before live wiring lands."
        )
    # Live path — guarded behind the env-var check above. We import lazily
    # so dev_team doesn't pull in `requests` when web_search is never called.
    import requests  # type: ignore[import-not-found]

    response = requests.post(
        "https://google.serper.dev/search",
        headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
        json={"q": query, "num": num_results},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def build_web_search_tool(**kwargs) -> Callable:
    return web_search


__all__ = ["web_search", "build_web_search_tool"]

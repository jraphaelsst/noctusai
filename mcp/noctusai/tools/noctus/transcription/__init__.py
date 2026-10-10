"""``noctus.transcription.*`` — client for the platform async transcription API.

Pure HTTP client (httpx) against core's ``/api/transcriptions`` (contract:
``products/core/projects/transcription-api/CONTRACT.md`` §2/§6). No ffmpeg, no
model, no local or OpenAI fallback: transcription runs on the server.

Tools
-----
``noctus.transcription.submit``      upload a local file -> 202 body (id, status, ...)
``noctus.transcription.get``         fetch one job
``noctus.transcription.transcribe``  submit + poll until terminal or timeout

Config (env, loaded from the repo-root ``.env`` by the server/CLI bootstrap):
``NOCTUS_TRANSCRIPTION_URL`` (default https://core.noctusai.com) and
``NOCTUS_TRANSCRIPTION_TOKEN`` (a ``pk_*`` token; never logged or returned).
"""

from __future__ import annotations


def register_all(server) -> None:
    """Register every ``noctus.transcription.*`` tool on the given FastMCP server."""
    from . import client

    client.register(server)


__all__ = ["register_all"]

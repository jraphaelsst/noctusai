"""dev_team REST API — surfaces telemetry + configs for programmatic /
future-dashboard consumption.

Public surface (contract):
    build_app() -> fastapi.FastAPI

Endpoints (per `projects/agno-dev-team-rollout/PROJECT.md § 5.4`):
    GET    /metrics
    GET    /agents/{name}/metrics
    GET    /configs
    GET    /configs/{name}
    PATCH  /configs/{name}            # rewrites YAML on disk
    POST   /eval/run                  # async eval kickoff (queued)

Localhost-only by default; the API binds 127.0.0.1 unless
``DEV_TEAM_API_BIND`` env var is set.

Stub raises NotImplementedError until D engineer ships api/server.py.
"""

from __future__ import annotations

try:  # pragma: no cover
    from dev_team.api.server import build_app  # type: ignore
except ImportError:

    def build_app():  # type: ignore[no-redef]
        raise NotImplementedError(
            "build_app not wired yet — D engineer ships api/server.py"
        )


__all__ = ["build_app"]

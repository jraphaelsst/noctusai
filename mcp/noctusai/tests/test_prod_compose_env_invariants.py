"""The prod compose file's environment block is an INVARIANT, not a default.

Two keys in `deploy/fleet/docker-compose.prod.yml` are load-bearing and must
reach every service:

  * ``NOCTUS_SCHEDULERS_ENABLED=1`` — authorises the container to run scheduled
    jobs. Absent, the container starts healthy and silently runs zero jobs.
  * ``DEBUG=false`` — gates `/docs` + `/openapi.json` exposure, the log level,
    and `settings.is_production`.

Neither may live in `.env`: that file is copied to laptops, and on 2026-08-22 a
laptop backend running against the production `.env` fired the nightly Vista
sync against the live catalog. `environment:` in compose beats `env_file:`, so
pinning them here makes the invariant a property of the repo rather than of a
file on the host — where, on 2026-08-24, `DEBUG=true` was found sitting in the
production `.env`, publishing all seven products' OpenAPI schemas.

WHY A TEST AND NOT JUST A COMMENT: YAML anchor merges are easy to defeat by
accident. `dev-team` re-declared `environment:` to add one API key and merged
back only the `*cache-env` subset — so it silently lost
`NOCTUS_SCHEDULERS_ENABLED` when that key was added to the anchor later. The
file LOOKED right; only resolving every service catches it. That is this test.
"""
from __future__ import annotations

import pathlib

import pytest

yaml = pytest.importorskip("yaml")

_COMPOSE = (
    pathlib.Path(__file__).resolve().parents[3]
    / "deploy"
    / "fleet"
    / "docker-compose.prod.yml"
)

#: key → required value, for EVERY service in the prod fleet file.
REQUIRED_PROD_ENV = {
    "NOCTUS_SCHEDULERS_ENABLED": "1",
    "DEBUG": "false",
}


def _services() -> dict[str, dict]:
    assert _COMPOSE.is_file(), f"prod compose file missing at {_COMPOSE}"
    doc = yaml.safe_load(_COMPOSE.read_text(encoding="utf-8"))
    services = doc.get("services") or {}
    assert services, "prod compose declares no services"
    return services


def test_the_compose_file_parses_and_has_services():
    assert len(_services()) >= 1


@pytest.mark.parametrize("key,expected", sorted(REQUIRED_PROD_ENV.items()))
def test_every_service_resolves_the_prod_invariant(key: str, expected: str):
    """Resolved per service — an anchor that LOOKS inherited may be shadowed."""
    offenders = []
    for name, spec in _services().items():
        env = spec.get("environment")
        if not isinstance(env, dict) or env.get(key) != expected:
            offenders.append(f"{name} (got {(env or {}).get(key)!r})")
    assert not offenders, (
        f"{key} must resolve to {expected!r} for EVERY prod service; missing on: "
        + ", ".join(offenders)
        + ". A service that re-declares `environment:` shadows the whole "
        "*prod-env anchor — merge it with `<<: *prod-env` instead of copying "
        "a subset."
    )


def test_debug_is_not_left_to_the_env_file():
    """`.env` is laptop-shared; the pin must be in the compose file itself."""
    text = _COMPOSE.read_text(encoding="utf-8")
    assert 'DEBUG: "false"' in text, (
        "DEBUG must be pinned literally in docker-compose.prod.yml — inheriting "
        "it from `.env` is exactly how prod ended up serving /docs publicly."
    )

"""Readiness probe for the agno multi-agent engine.

Wired into :mod:`noctusai_seed.health` via ``HealthEndpointConfig``::

    from app.services.agno_health import agno_ping
    from noctusai_seed import HealthEndpointConfig, create_product_app

    app = create_product_app(
        ...,
        health_config=HealthEndpointConfig(readiness_hooks=[agno_ping]),
    )

The probe answers one question: *can the dev-team backend actually
dispatch a team run right now?* — without doing any real LLM call.

Three cheap, local checks (sub-100ms target; no network):

  1. **Anthropic API key present.** ``os.getenv("ANTHROPIC_API_KEY")``
     truthy. Missing → dev-team's :mod:`dev_team.mcp_facade` returns a
     "key not set" stub instead of running agno; surfacing this in
     ``/_ready`` lets ops/orchestration see the misconfiguration before
     a user-visible 500. (Mirrors the existing guard at
     ``dev_team/src/dev_team/mcp_facade.py:41``.)

  2. **Leader model is a known Anthropic id.** Read the leader's model
     from ``dev_team.configs.load_config("default")`` and verify it
     belongs to a small allowlist. The dev-team's default-config YAMLs
     pin Claude family names exclusively (see ``configs/default.yaml``);
     a typo or stale override surfaces here rather than at runtime.

  3. **dev_team package importable + ``__version__`` readable.** Cheap
     PEP-562 lazy import; the package's ``__init__`` doesn't pull agno
     until a lazy attr is requested. If the package itself is missing
     or broken, the backend cannot serve team runs at all.

Contract:

  - Returns ``(ok: bool, detail_or_error_msg: str | None)`` to match
    :class:`noctusai_seed.health.HealthCheckHook`. Hook ``__name__``
    surfaces in the ``/_ready`` JSON ``checks[]`` as ``"agno_ping"``.
  - When ``ok=True`` the second tuple slot is ``None`` (matches the
    seed's ``(True, None)`` convention; rich detail is logged at DEBUG
    rather than crammed into the message field).
  - When ``ok=False`` the second slot is a compact human-readable
    summary; per-check booleans are logged at WARN so ops can
    distinguish "no API key" from "model typo" from "import broken".
  - All three checks are wrapped: a raising check degrades to
    ``ok=False`` for that pin and surfaces in the summary; other pins
    still execute. (The seed itself also wraps the whole hook with
    :func:`noctusai_seed.health._run_hook`, but per-pin try/except keeps
    the detail informative.)
"""
from __future__ import annotations

import logging
import os
import time
from typing import Final

logger = logging.getLogger(__name__)


# Known-Anthropic Claude model ids the dev-team config files pin today.
# Sourced from ``dev_team/src/dev_team/configs/{default,gemini-eval,
# codex-eval}.yaml`` + ``configs/__init__.py``. If agno ever exposes a
# registry-style accessor we should consume that instead; for now this
# allowlist is a tight local check.
_KNOWN_ANTHROPIC_MODELS: Final[frozenset[str]] = frozenset(
    {
        "claude-opus-4-7",
        "claude-sonnet-4-6",
        "claude-haiku-4-5",
    }
)


def _check_anthropic_key() -> tuple[bool, str]:
    """Pin 1: ANTHROPIC_API_KEY env var truthy. No network call."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        return True, ""
    return False, "ANTHROPIC_API_KEY not set"


def _check_leader_model() -> tuple[bool, str]:
    """Pin 2: leader model name is a known Anthropic id.

    Reads the live default-config; falls back to ``ok=False`` with a
    descriptive message if the config can't be loaded (covers a missing
    config dir, malformed YAML, or a broken import of
    ``dev_team.configs``).
    """
    try:
        from dev_team.configs import load_config  # type: ignore[import-not-found]
    except Exception as exc:  # noqa: BLE001 — any import failure is a probe failure, surfaced
        return False, f"dev_team.configs unimportable: {exc}"

    try:
        cfg = load_config("default")
    except Exception as exc:  # noqa: BLE001 — config-load failure surfaces here
        return False, f"load_config('default') raised: {exc}"

    if not isinstance(cfg, dict):
        return False, f"load_config returned {type(cfg).__name__} (expected dict)"

    agents = cfg.get("agents") or {}
    if not isinstance(agents, dict):
        return False, "config['agents'] is not a dict"

    leader_cfg = agents.get("leader") or {}
    if not isinstance(leader_cfg, dict):
        return False, "config['agents']['leader'] is not a dict"

    model = leader_cfg.get("model")
    if not isinstance(model, str) or not model:
        return False, "leader.model missing or empty"

    if model not in _KNOWN_ANTHROPIC_MODELS:
        return False, f"leader.model {model!r} not in known Anthropic allowlist"

    return True, model


def _check_dev_team_importable() -> tuple[bool, str]:
    """Pin 3: ``import dev_team`` works + ``__version__`` readable.

    Lazy PEP-562 layout means this does NOT trigger agno's import chain
    (build_team / build_leader stay un-resolved). The probe is therefore
    cheap and safe to call from a frequently-hit /_ready endpoint.
    """
    try:
        import dev_team  # type: ignore[import-not-found]

        version = getattr(dev_team, "__version__", None)
    except Exception as exc:  # noqa: BLE001 — any import failure is a probe failure
        return False, f"dev_team unimportable: {exc}"

    if not isinstance(version, str) or not version:
        return False, "dev_team.__version__ missing or empty"

    return True, version


async def agno_ping() -> tuple[bool, str | None]:
    """Probe agno engine readiness for the dev-team backend.

    Match the :class:`noctusai_seed.health.HealthCheckHook` shape:
    async, no args, returns ``(ok, error_message | None)``. ``ok=True``
    pairs with ``None``; ``ok=False`` pairs with a compact human
    summary. Per-pin booleans + the resolved model are logged at the
    appropriate level for operators who want richer detail.
    """
    started = time.perf_counter()

    key_ok, key_detail = _check_anthropic_key()
    model_ok, model_detail = _check_leader_model()
    import_ok, import_detail = _check_dev_team_importable()

    elapsed_ms = (time.perf_counter() - started) * 1000.0
    all_ok = key_ok and model_ok and import_ok

    detail_payload = {
        "anthropic_key_present": key_ok,
        "leader_model": model_detail if model_ok else None,
        "dev_team_importable": import_ok,
        "latency_ms": round(elapsed_ms, 2),
    }

    if all_ok:
        logger.debug("agno_ping ok: %s", detail_payload)
        return True, None

    errors: list[str] = []
    if not key_ok:
        errors.append(key_detail)
    if not model_ok:
        errors.append(f"leader_model: {model_detail}")
    if not import_ok:
        errors.append(f"dev_team_import: {import_detail}")

    summary = "; ".join(errors)
    logger.warning("agno_ping not-ready: %s | detail=%s", summary, detail_payload)
    return False, summary


__all__ = ["agno_ping"]

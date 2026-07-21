"""Deploy-context-aware required-config resolution.

A standing seed primitive for the recurring "this setting MUST be present in
production but is fine to default in dev" shape. Two failure modes it closes:

1. **Silent misroute** — a setting defaults to a *consumer-#1-coincidence*
   literal (e.g. ``http://localhost:8000``), so consumer #1 works while every
   later consumer silently misroutes with an opaque downstream error. The cure
   is the platform rule "seed defaults = canonical-shared answer, not
   consumer-#1 coincidence" (see ``KB § PATTERNS/seed-canonical-defaults.md``):
   if there is no architecturally-canonical answer, the seed must return
   ``None`` and let the caller surface the gap — never a literal pretending to
   know.
2. **Late prod failure** — a required-in-prod setting is absent on the deploy
   and the gap only surfaces at request time, far from the cause. The cure is
   to **fail loud at startup**, listing *every* missing key at once.

This module is **pure logic** (env reads only; no I/O beyond ``os.environ``),
so it lives in the ``config`` layer alongside
:mod:`noctusai_lib.config.product_urls` and
:mod:`noctusai_lib.config.cors_registry`. It is exempt from the seed
Fake+Real adapter shape: a Fake would exercise the same code as the Real
(there is no IO boundary to substitute) — tests drive it via the real env API
(``monkeypatch.setenv`` / ``monkeypatch.delenv``).

Deploy-context detection mirrors the deploy signals the rest of the seed
already keys off (the ``PRODUCT_URL_*`` env scheme set on the VPS — see
:mod:`noctusai_lib.config.product_urls`): an explicit ``APP_ENV`` of
``production`` / ``staging``, OR the presence of any non-empty
``PRODUCT_URL_<SLUG>`` override (the VPS sets these; a plain dev shell sets
neither). The aggregating shape — :func:`require_prod_config` and the
``required_in_prod`` arm of :func:`resolve_config` — means a misconfigured
deploy surfaces *all* of its gaps in one error rather than first-fail.
"""

from __future__ import annotations

import os

# Env values matching one of these mark an explicit deploy context. The VPS
# sets ``APP_ENV=production``; CI/preview environments may set ``staging``.
_DEPLOY_APP_ENVS: frozenset[str] = frozenset({"production", "staging"})

# The per-product URL pattern is a *fleet* knob, not a per-product override, so
# its presence alone does NOT signal a deploy context (a dev shell could export
# a pattern for experimentation). Only concrete ``PRODUCT_URL_<SLUG>`` overrides
# — which the VPS sets and dev does not — count as a deploy signal.
_PRODUCT_URL_PREFIX = "PRODUCT_URL_"
_PRODUCT_URL_PATTERN_KEY = "PRODUCT_URL_PATTERN"

# ── Fleet-wide baseline required-in-prod env (the single source of truth) ──────
# Every product's seed auth_router builds a Redis-backed session store with
# ``require_encryption=True`` (see
# ``noctusai_lib.api.auth.session.factory.make_session_store``), so whenever a
# product runs against a real Redis in a deploy context it REQUIRES
# ``REDIS_SESSION_ENCRYPTION_KEY`` — this is a seed contract, not a per-product
# opt-in. Declaring it ONCE here lets BOTH sides read the same list, so the
# requirement can never drift between what boot enforces and what the pre-deploy
# gate checks (the gate↔methodology-sync rule):
#   • boot side  — ``create_product_app`` folds this into ``require_prod_config``
#                  (conditioned on ``settings.redis_url`` being set), so a deploy
#                  missing the key aborts loudly at startup instead of failing
#                  lazily on the first session read.
#   • gate side  — ``noctus.dev.predeploy_check`` (check ``required_prod_env_present``)
#                  diffs this list against the prod ``.env`` snapshot, catching a
#                  newly-required key BEFORE the deploy rather than after boot.
# Extend this tuple whenever a seed capability makes a new env var required at
# boot; both the boot guard and the pre-deploy gate then enforce it for free.
BASELINE_REQUIRED_PROD_ENV: tuple[str, ...] = ("REDIS_SESSION_ENCRYPTION_KEY",)


def baseline_required_prod_env() -> list[str]:
    """The fleet-wide baseline required-in-prod env keys as a fresh list.

    A thin accessor over :data:`BASELINE_REQUIRED_PROD_ENV` so callers (the boot
    guard and the pre-deploy parity gate) share one source of truth without
    importing the tuple constant directly."""
    return list(BASELINE_REQUIRED_PROD_ENV)


class MissingProdConfigError(RuntimeError):
    """Required-in-prod config is absent in a deploy context.

    Raised by :func:`resolve_config` (for a single key) and
    :func:`require_prod_config` (aggregated). The message lists **every**
    missing key so a misconfigured deploy surfaces all gaps at once instead of
    one-failure-at-a-time.
    """

    def __init__(self, missing_keys: list[str]) -> None:
        self.missing_keys: list[str] = list(missing_keys)
        joined = ", ".join(self.missing_keys)
        super().__init__(
            "Required-in-prod config missing in a deploy context: "
            f"{joined}. Set these env var(s) on the deploy "
            "(they are required in production/staging; dev leaves them unset)."
        )


def is_deploy_context() -> bool:
    """Return ``True`` iff the process is running in a deploy context.

    The signal is environment-derived, mirroring the deploy markers the rest of
    the seed already keys off:

    - ``APP_ENV`` is ``production`` or ``staging`` (explicit), OR
    - any ``PRODUCT_URL_<SLUG>`` override is set to a non-empty value (the VPS
      sets these per the ``product_urls`` scheme; ``PRODUCT_URL_PATTERN`` is a
      fleet knob and is **excluded**).

    A plain dev shell sets neither, so this returns ``False`` there — and the
    ``required_in_prod`` config arms become no-ops, preserving dev defaults.
    """
    if os.environ.get("APP_ENV", "").strip().lower() in _DEPLOY_APP_ENVS:
        return True

    for key, value in os.environ.items():
        if (
            key.startswith(_PRODUCT_URL_PREFIX)
            and key != _PRODUCT_URL_PATTERN_KEY
            and value
        ):
            return True

    return False


def resolve_config(
    key: str,
    *,
    canonical_default: str | None = None,
    required_in_prod: bool = False,
) -> str | None:
    """Resolve a single config value with deploy-aware required semantics.

    Resolution:

    1. If the env var ``key`` is set to a non-empty value, return it.
    2. Otherwise, if ``required_in_prod`` and :func:`is_deploy_context`, raise
       :class:`MissingProdConfigError` (a deploy must not silently fall back).
    3. Otherwise return ``canonical_default``.

    Args:
        key: The environment variable name to read.
        canonical_default: The fallback used in dev (or when the key is not
            required in prod). **This MUST be the architecturally-canonical
            answer for the setting's contract — never a literal that merely
            happens to match consumer #1.** A consumer-#1-coincidence default
            stays silent for consumer #1 and misroutes every later consumer.
            When no canonical answer exists, pass ``None`` (the seed default)
            and let the caller surface the gap — see
            ``KB § PATTERNS/seed-canonical-defaults.md``.
        required_in_prod: When ``True``, an unset/empty key in a deploy context
            raises instead of falling back to ``canonical_default``.

    Returns:
        The env value if set+non-empty; otherwise ``canonical_default`` (which
        may be ``None``).

    Raises:
        MissingProdConfigError: ``required_in_prod`` is ``True``, the key is
            unset/empty, and :func:`is_deploy_context` is ``True``.
    """
    value = os.environ.get(key)
    if value:
        return value

    if required_in_prod and is_deploy_context():
        raise MissingProdConfigError([key])

    return canonical_default


def require_prod_config(keys: list[str]) -> None:
    """Assert that every key in ``keys`` is present in a deploy context.

    In a deploy context (see :func:`is_deploy_context`), raise a **single**
    :class:`MissingProdConfigError` listing *every* missing key — aggregated,
    not first-fail — so one startup check surfaces all gaps at once. Outside a
    deploy context this is a no-op (dev sets none of these).

    Args:
        keys: The env var names that must be set+non-empty in production.

    Raises:
        MissingProdConfigError: One or more keys are unset/empty AND
            :func:`is_deploy_context` is ``True``. The error's ``missing_keys``
            holds every offending key, in the order given.
    """
    if not is_deploy_context():
        return

    missing = [key for key in keys if not os.environ.get(key)]
    if missing:
        raise MissingProdConfigError(missing)


__all__ = [
    "BASELINE_REQUIRED_PROD_ENV",
    "MissingProdConfigError",
    "baseline_required_prod_env",
    "is_deploy_context",
    "require_prod_config",
    "resolve_config",
]

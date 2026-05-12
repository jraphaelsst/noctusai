"""
Per-feature AI consent guard — ai-expansion Phase 19 (X6 / LGPD).

Two parts:

  - **Catalog** of consent-gated features (`ConsentFeature` dataclass +
    module-level registry). Each product registers its features at
    import-time via `register_feature(...)`. The catalog seeds the user
    profile UI with PT-BR rationales.

  - **Guard** (`require(db, user_id, feature_key)`) called by AI services
    that opt in to consent gating. Raises `AIConsentRequired` (HTTP 412)
    when the user has not granted, OR when the catalog lists the feature
    with `default_granted=False` and there's no stored decision yet.

Storage: `public.ai_consent` (Core migration 012). Per-user UNIQUE on
`(user_id, feature_key)` makes upserts toggle-friendly.

LGPD posture: rationale text is snapshotted on grant so audit trails can
prove what the user agreed to even if the catalog rationale changes
later. The seed `noctus_users.role='admin'` policy bypass exists for
DSAR / right-to-erasure workflows.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional

from fastapi import Header

from noctusai_lib.primitives.exceptions import AppException

logger = logging.getLogger(__name__)


# Type aliases for per-feature LGPD redaction (exported via __init__.py).
# Defined here as Any-returning to keep the contract simple; redactors return
# a redacted version of the arguments dict / result value or raise to skip.
RedactArgumentsFn = Callable[[dict[str, Any]], dict[str, Any]]
RedactResultFn = Callable[[Any], Any]


# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------


class AIConsentRequired(AppException):
    """The calling user has not granted consent for this AI feature.

    Raised by `noctusai_lib.ai.consent.require(...)` at every AI entry
    point that opts in to consent gating. HTTP 412 (Precondition Required)
    — frontends should redirect to the user's AI consent page.
    """

    def __init__(self, feature_key: str, *, title: Optional[str] = None):
        super().__init__(
            code="AI_CONSENT_REQUIRED",
            message=(
                f"Consentimento necessário para usar este recurso de IA "
                f"({title or feature_key}). Acesse Configurações > IA para "
                f"gerenciar suas preferências."
            ),
            status_code=412,
            details={"feature_key": feature_key, "title": title},
        )


class MandatoryFeatureCannotBeToggled(AppException):
    """The user attempted to toggle a feature whose `toggleable=False`.

    Non-toggleable features are infrastructure-tier — visible in the
    catalog for billing transparency (users see what consumes their
    tokens) but not user-disableable. Raised by `upsert_decision(...)`
    as a defensive guard for direct callers; the router-level guard in
    `core/me_consents.py` returns 403 before reaching this path.
    """

    def __init__(self, feature_key: str, *, title: Optional[str] = None):
        super().__init__(
            code="MANDATORY_FEATURE_CANNOT_BE_TOGGLED",
            message=(
                f"Este recurso de IA ({title or feature_key}) é "
                f"infraestrutura essencial e não pode ser desativado "
                f"individualmente. Ele aparece no catálogo apenas para "
                f"transparência de consumo."
            ),
            status_code=403,
            details={"feature_key": feature_key, "title": title},
        )


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------


@dataclass
class ConsentFeature:
    """One entry in the platform-wide consent catalog."""

    key: str                         # e.g. 'erp.lead_score'
    title: str                       # short PT-BR label shown in toggles
    rationale: str                   # 1-2 sentence PT-BR rationale shown next to the toggle
    default_granted: bool = False    # opt-in vs. opt-out semantics
    product: Optional[str] = None    # optional product slug for grouping ('erp', 'pf', etc.)
    toggleable: bool = True          # False = infrastructure-tier (visible for billing transparency, locked-on)
    # LGPD redaction hooks (per `KB § PATTERNS/llm-tool-audit.md § LGPD redaction`).
    # When present, `tool_call_audits.arguments` / `.result` are scrubbed via these
    # callables before the `AuditRecord` is constructed at the dispatch site. Pure
    # functions of the raw value → JSON-friendly value (or `None` to drop entirely).
    # No-op default (lambdas return input unchanged) is intentionally NOT applied:
    # `None` is the explicit "no scrub registered" signal so the dispatch wrapper
    # can choose its own fallback (typically drop-to-None for safety).
    redact_arguments: Optional[Callable[[Any], Any]] = field(default=None, repr=False)
    redact_result: Optional[Callable[[Any], Any]] = field(default=None, repr=False)


# Module-level registry. Products register at import time.
_CATALOG: dict[str, ConsentFeature] = {}


def register_feature(
    key: str,
    *,
    title: str,
    rationale: str,
    default_granted: bool = False,
    product: Optional[str] = None,
    toggleable: bool = True,
    redact_arguments: Optional[Callable[[Any], Any]] = None,
    redact_result: Optional[Callable[[Any], Any]] = None,
) -> ConsentFeature:
    """Register a feature in the platform catalog. Called at product startup.

    Args:
        toggleable: when False, the feature is infrastructure-tier — visible
            in the catalog for billing transparency (users can see what
            consumes their tokens) but cannot be turned off. Always evaluates
            as granted in `is_granted` regardless of any stored decision.
            Use for inference primitives consumed silently by other features
            (e.g. `erp.embeddings`, used by lead-matching + search-relevance).
        redact_arguments: optional callable applied to the `AuditRecord.arguments`
            payload BEFORE the audit row is written. Use for LGPD-sensitive
            fields (transaction descriptions / account balances / income figures /
            clinical text / email bodies — per-product call). Return value is the
            scrubbed dict (or `None` to drop arguments entirely). See
            `KB § PATTERNS/llm-tool-audit.md § LGPD redaction`.
        redact_result: same as `redact_arguments` but applied to `AuditRecord.result`.
    """
    if not key:
        raise ValueError("feature key required")
    if key in _CATALOG:
        # Re-registration is allowed (e.g. on hot reload) but warn so we
        # don't silently shadow earlier definitions.
        logger.debug("ai_consent: re-registering feature %s", key)
    feature = ConsentFeature(
        key=key,
        title=title,
        rationale=rationale,
        default_granted=default_granted,
        product=product,
        toggleable=toggleable,
        redact_arguments=redact_arguments,
        redact_result=redact_result,
    )
    _CATALOG[key] = feature
    return feature


def get_feature(key: str) -> Optional[ConsentFeature]:
    return _CATALOG.get(key)


def get_catalog() -> list[ConsentFeature]:
    """Return all registered features sorted by `(product, key)` for stable UI ordering."""
    return sorted(
        _CATALOG.values(),
        key=lambda f: (f.product or "zzz", f.key),
    )


def reset_catalog_for_test() -> None:
    """Test-only — clears the catalog so isolated tests can register fresh sets."""
    _CATALOG.clear()


# ---------------------------------------------------------------------------
# Storage helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def fetch_user_decisions(db: Any, user_id: str) -> dict[str, dict[str, Any]]:
    """Pull every stored decision for a user. Keyed by `feature_key` for
    cheap O(1) lookup against the catalog."""
    if not db or not user_id:
        return {}
    try:
        result = (
            db.table("ai_consent")
            .select("feature_key, granted, granted_at, revoked_at, rationale_pt, updated_at")
            .eq("user_id", str(user_id))
            .execute()
        )
    except Exception as exc:
        logger.warning("ai_consent.fetch_user_decisions failed: %s", exc)
        return {}
    return {row["feature_key"]: row for row in (result.data or [])}


async def is_granted(db: Any, user_id: str, feature_key: str) -> bool:
    """Resolve the effective grant state for `(user_id, feature_key)`.

    Resolution order:
      1. Catalog feature with `toggleable=False` → `True` (always granted —
         infrastructure-tier features are locked-on; the catalog entry
         exists only for billing transparency).
      2. Stored row → use its `granted` boolean.
      3. No stored row + catalog lists the feature → use `default_granted`.
      4. No stored row + feature unknown → `False` (fail-closed).
    """
    if not db or not user_id or not feature_key:
        return False
    feature = _CATALOG.get(feature_key)
    if feature is not None and not feature.toggleable:
        return True
    decisions = await fetch_user_decisions(db, user_id)
    decision = decisions.get(feature_key)
    if decision is not None:
        return bool(decision.get("granted"))
    if feature is not None:
        return feature.default_granted
    return False


async def require(db: Any, user_id: str, feature_key: str) -> None:
    """Raise `AIConsentRequired` if the user hasn't granted consent."""
    if await is_granted(db, user_id, feature_key):
        return
    feature = _CATALOG.get(feature_key)
    raise AIConsentRequired(feature_key, title=feature.title if feature else None)


async def upsert_decision(
    db: Any,
    user_id: str,
    feature_key: str,
    *,
    granted: bool,
    org_id: Optional[str] = None,
) -> dict[str, Any]:
    """Upsert the decision row. Returns the persisted row.

    Raises `MandatoryFeatureCannotBeToggled` (HTTP 403) when the feature
    is registered with `toggleable=False` — defensive guard for direct
    callers; the router-level pre-check in core's `me_consents.py` PUT
    endpoint catches this before we reach here in the normal flow.
    """
    feature = _CATALOG.get(feature_key)
    if feature is not None and not feature.toggleable:
        raise MandatoryFeatureCannotBeToggled(
            feature_key, title=feature.title
        )
    rationale_pt = feature.rationale if feature else None
    now_iso = _now_iso()
    payload = {
        "user_id": str(user_id),
        "org_id": str(org_id) if org_id else None,
        "feature_key": feature_key,
        "granted": granted,
        "rationale_pt": rationale_pt,
        "updated_at": now_iso,
    }
    if granted:
        payload["granted_at"] = now_iso
    else:
        payload["revoked_at"] = now_iso
    try:
        result = (
            db.table("ai_consent")
            .upsert(payload, on_conflict="user_id,feature_key")
            .execute()
        )
    except Exception as exc:
        logger.warning(
            "ai_consent.upsert failed for user=%s key=%s: %s", user_id, feature_key, exc
        )
        raise
    rows = result.data if isinstance(result.data, list) else [result.data]
    return rows[0] if rows else payload


async def list_user_consent_view(
    db: Any, user_id: str
) -> list[dict[str, Any]]:
    """Return one row per catalog entry, merged with the user's stored decisions.

    Each row shape:
        {
          key, title, rationale, product, default_granted, toggleable,
          granted: bool,                # effective state
          decision_recorded: bool,      # True if a stored row exists
          granted_at, revoked_at,       # latest timestamps if any
        }

    Non-toggleable features always surface with `granted=True` and
    `decision_recorded=False` (no decision is needed; the locked-on state
    is intrinsic). The frontend reads `toggleable` to render the toggle
    as disabled with explanatory rationale.
    """
    decisions = await fetch_user_decisions(db, user_id)
    out: list[dict[str, Any]] = []
    for feature in get_catalog():
        if not feature.toggleable:
            # Locked-on infrastructure features — always granted, no decision.
            out.append({
                "key": feature.key,
                "title": feature.title,
                "rationale": feature.rationale,
                "product": feature.product,
                "default_granted": feature.default_granted,
                "toggleable": False,
                "granted": True,
                "decision_recorded": False,
                "granted_at": None,
                "revoked_at": None,
            })
            continue

        decision = decisions.get(feature.key)
        if decision is not None:
            granted = bool(decision.get("granted"))
            out.append({
                "key": feature.key,
                "title": feature.title,
                "rationale": feature.rationale,
                "product": feature.product,
                "default_granted": feature.default_granted,
                "toggleable": True,
                "granted": granted,
                "decision_recorded": True,
                "granted_at": decision.get("granted_at"),
                "revoked_at": decision.get("revoked_at"),
            })
        else:
            out.append({
                "key": feature.key,
                "title": feature.title,
                "rationale": feature.rationale,
                "product": feature.product,
                "default_granted": feature.default_granted,
                "toggleable": True,
                "granted": feature.default_granted,
                "decision_recorded": False,
                "granted_at": None,
                "revoked_at": None,
            })
    return out


def pending_count(view: list[dict[str, Any]]) -> int:
    """Number of catalog entries the user hasn't decided on yet (i.e.
    `decision_recorded=False` AND `toggleable=True`). Non-toggleable
    features are excluded — there's no decision for the user to make.
    Powers the LayoutEnrichment.aiBadge."""
    return sum(
        1 for row in view
        if not row["decision_recorded"] and row.get("toggleable", True)
    )


# ---------------------------------------------------------------------------
# Router-level guard: consent_required FastAPI dep factory
# ---------------------------------------------------------------------------
#
# Mirrors the module-level injection pattern of `noctusai_lib.llm.budget`
# (Phase 18 X4). Two factories wired once per process at boot:
#
#   - `get_current_user` — a FastAPI dependency callable that returns
#     `(user, token)` (the contract from `noctusai_seed.dependencies`).
#   - `admin_client_factory` — a zero-arg callable returning a Supabase
#     admin client. Used so RLS doesn't filter the consent lookup based on
#     the caller's auth (the lookup is always the caller's own row, and
#     reading it is safe via service-role).
#
# Products opt in via `create_product_app(consent_gating=True)`, which
# calls `configure_consent_module(...)` after creating its `dependencies`
# instance. Calling `consent_required("...")` before configuration raises
# RuntimeError loudly — no silent fallback.

_get_current_user_dep: Optional[Callable[..., Any]] = None
_admin_client_factory: Optional[Callable[[], Any]] = None


def configure_consent_module(
    *,
    get_current_user: Optional[Callable[..., Any]],
    admin_client_factory: Optional[Callable[[], Any]],
) -> None:
    """Wire the FastAPI deps the consent guard uses to resolve user + db.

    Called by `noctusai_seed.app.create_product_app(...)` once per process.
    Pass both as `None` to fully disable guard creation (e.g. in tests).
    """
    global _get_current_user_dep, _admin_client_factory
    _get_current_user_dep = get_current_user
    _admin_client_factory = admin_client_factory


def is_consent_module_configured() -> bool:
    return _get_current_user_dep is not None and _admin_client_factory is not None


def reset_consent_module_for_test() -> None:
    """Test-only — clear wired factories so isolated tests can rewire."""
    global _get_current_user_dep, _admin_client_factory
    _get_current_user_dep = None
    _admin_client_factory = None


def consent_required(feature_key: str) -> Callable[..., Awaitable[None]]:
    """FastAPI dependency factory for router-level consent gating.

    Returns a callable suitable for `Depends(...)` that raises
    `AIConsentRequired` (HTTP 412) if the calling user has not granted
    consent for `feature_key`.

    Usage::

        from fastapi import Depends
        from noctusai_lib.domain.ai import consent_required

        @router.post("/api/ai/leads/{id}/follow-up-draft")
        async def draft_follow_up(
            id: str,
            _consent: None = Depends(consent_required("erp.lead_score")),
            ...,
        ):
            ...

    **Boot-order note.** This factory is intentionally lenient at call time
    — it does NOT verify `configure_consent_module(...)` has been called.
    Routers are imported (and their decorators evaluated) BEFORE
    `create_product_app(...)` runs and wires the module via
    `configure_consent_module(...)`. The configuration check lives inside
    the returned dep and runs at REQUEST time. If `consent_gating=False`
    or the module was never configured, the first request hitting a
    consent-gated route raises a RuntimeError with a clear remediation
    message.

    Wiring: products opt in via `create_product_app(consent_gating=True)`
    (the default) which calls `configure_consent_module(...)` at boot.
    """

    async def _consent_dep(
        authorization: Optional[str] = Header(None),
    ) -> None:
        # Late-binding configuration check — runs at request time, after
        # `create_product_app(...)` has wired the module.
        if not is_consent_module_configured():
            raise RuntimeError(
                "consent_required: configure_consent_module(...) was not called. "
                "Either wire via create_product_app(consent_gating=True) or call "
                "configure_consent_module(get_current_user=..., admin_client_factory=...) "
                "explicitly at boot."
            )

        user_dep_fn = _get_current_user_dep
        admin_factory_fn = _admin_client_factory

        # Resolve user via the seed's get_current_user contract:
        #   (authorization: Optional[str] = Header(None)) -> (user, token)
        result = user_dep_fn(authorization=authorization)
        if asyncio.iscoroutine(result):
            result = await result

        if isinstance(result, tuple) and len(result) >= 1:
            user = result[0]
        else:
            user = result

        user_id = (
            getattr(user, "id", None)
            or (user.get("id") if isinstance(user, dict) else None)
        )
        if not user_id:
            raise AIConsentRequired(feature_key)

        db = admin_factory_fn()
        await require(db, str(user_id), feature_key)

    # Annotate so FastAPI's debug/openapi surfaces include the feature key.
    _consent_dep.__name__ = (
        f"consent_required__{feature_key.replace('.', '_').replace('-', '_')}"
    )
    return _consent_dep

"""Access tiers -- every route and every table declares who may touch it; undeclared is refused.

STDLIB-ONLY and import-light on purpose: the product code imports :func:`access_tier` (a runtime no-op
marker) and the keeper ``check_access_tier_*`` (mcp/noctusai ``tools/noctus/dev/access_tiers.py``) loads
THIS file as its single source of truth for the dependency -> tier map and the Platform-IP registry.
KB § PATTERNS/security/access-tiers.md.

Tiers (restrictiveness, high -> low):

* ``platform`` -- Platform IP: what NoctusAI builds and operates (agent prompts, sections, skills, tool
  descriptions, evals/judges, compiled prompts, canaries, model + runtime config, internal tooling,
  cross-customer aggregates). Global platform admin (``noctus_users.role='admin'``) or service role ONLY --
  never a customer user, never a non-admin member of the platform org.
* ``service`` -- machine-to-machine (product / channel tokens); never a browser.
* ``org`` -- a customer's own data, scoped to their org, with the role checks the product defines.
* ``public`` -- intentionally unauthenticated (signed webhooks, consent pages, health).

How a route declares its tier
-----------------------------
0. Create the router with ``make_router(tier=...)`` (required argument; the typed API). Bare ``APIRouter`` is restricted.
1. It already did, if it sits behind a dependency in :data:`DEP_TIERS` (or a function / ``X = factory(...)``
   that composes one -- the keeper follows ``Depends`` chains and known gate calls transitively).
2. Otherwise mark it: ``@access_tier("public", reason="HMAC-verified Meta webhook")`` directly under the route
   decorator, or a module constant ``ACCESS_TIER = "public"`` for a whole public router module.
3. Health probes (:data:`PUBLIC_PATH_CONVENTION`) need no marker.

How a table declares its tier (migration convention)
----------------------------------------------------
``COMMENT ON TABLE agents.compiled_prompts IS 'tier:platform';`` -- a new table without it (and not matched by
:data:`PLATFORM_TABLES`) fails the delta gate. Platform tables: no ``authenticated``/``anon`` grant and no
``TO authenticated|anon|PUBLIC`` policy that lacks a platform-admin check -- service role only.
"""
from __future__ import annotations

from typing import Callable, TypeVar

TIERS: tuple[str, ...] = ("platform", "service", "org", "public")
#: Restrictiveness rank -- a route's tier is the STRONGEST of its gates (platform wins over org).
TIER_RANK: dict[str, int] = {"platform": 3, "service": 2, "org": 1, "public": 0}

F = TypeVar("F", bound=Callable)


#: THE PUBLIC TIER IS A CLOSED ALLOWLIST (owner, 2026-11-05; + token-link 2026-11-10): landing/marketing pages + their navigation, login /
#: signup / password reset, pricing / checkout / thank-you (no order or PII without a signed or one-time token),
#: legal + consent pages (privacy, terms, data deletion -- seed-mounted, Meta/Google review need them), and lead
#: capture on those pages (forms, newsletter). EVERYTHING ELSE is access-level.
PUBLIC_CATEGORIES: tuple[str, ...] = ("landing", "auth", "pricing-checkout", "legal-consent", "lead-capture", "token-link")
#: A ``token-link`` route (owner, 2026-11-10: an unguessable link the org sent to one person -- approval / report links) must
#: resolve its token through this helper (expiry fails closed, malformed = 404, fingerprint in logs): KB access-tiers.md.
TOKEN_LINK_HELPERS: tuple[str, ...] = ("resolve_token_link",)
#: Reachable from the network but NOT anonymous: the handler must run a verification call (tier ``service``, signed).
SIGNED_KINDS: tuple[str, ...] = ("webhook", "oauth-callback", "health")
#: A public API returns only fields meant for the public, is rate-limited, and a public WRITE carries one of these.
ABUSE_PROTECTION_NAMES: frozenset[str] = frozenset({"turnstile", "recaptcha", "hcaptcha", "captcha", "honeypot", "abuse", "verify_human"})
#: An OAuth callback must verify the ``state`` parameter with one of these.
OAUTH_STATE_CALLS: frozenset[str] = frozenset({"verify_state", "validate_state", "verify_oauth_state", "decode_state", "check_state", "consume_state"})
#: ...AND that call must pass the browser binding as this keyword (`consume_state(state, binding=<cookie>)`). A state that
#: only proves "this server issued it" does not stop login-CSRF / account-linking: an attacker starts a flow and hands the
#: consent URL to a victim. The binding ties the callback to the BROWSER that started the flow.
OAUTH_STATE_BINDING_KWARG: str = "binding"


def access_tier(tier: str, *, reason: str = "", category: str = "") -> Callable[[F], F]:
    """Runtime no-op marker: declares a route's tier where no auth dependency says it. Statically read by the
    keeper (AST). ``public`` needs ``reason`` AND ``category`` from the closed :data:`PUBLIC_CATEGORIES`;
    a ``service`` route reachable from the network names its :data:`SIGNED_KINDS` category."""
    if tier not in TIERS:
        raise ValueError(f"unknown access tier {tier!r}; one of {TIERS}")
    if tier == "public":
        if not reason.strip():
            raise ValueError("a public route must say why (reason=...)")
        if category not in PUBLIC_CATEGORIES:
            raise ValueError(f"a public route must name a category from the closed allowlist {PUBLIC_CATEGORIES}; "
                             "anything else is access-level (webhooks / OAuth callbacks / health are tier service, signed)")

    def _mark(fn: F) -> F:
        fn.__access_tier__ = tier  # type: ignore[attr-defined]
        return fn

    return _mark


def make_router(*, tier: str, guard=None, reason: str = "", category: str = "", **router_kwargs):
    """THE typed way to create a router -- a thin wrapper over FastAPI's native mechanism,
    ``APIRouter(dependencies=[Depends(guard)])`` (OWASP FastAPI Security Cheat Sheet: router-level dependencies mean every
    endpoint added later INHERITS the check; sensitive operations still add a per-op permission check).

    ``tier=`` is REQUIRED (a call without it is a ``TypeError`` at import). ``platform`` / ``org`` need ``guard`` -- the
    product's dependency callable (``require_platform_admin`` / ``get_current_user_org``): a router that claims a tier and
    enforces nothing is refused here and again by the keeper. ``service`` takes the signature / token dependency as
    ``guard`` (or verifies in the handler). ``platform`` routers default to ``include_in_schema=False`` (the public OpenAPI schema never lists Platform IP). ``public`` takes NO guard, a ``reason`` and a ``category`` from the closed
    :data:`PUBLIC_CATEGORIES`. A bare ``APIRouter(...)`` is the restricted API: existing uses are on the burn-down ledger,
    a NEW one is refused at write time (``claude-guard-access-tier``). Returns a plain ``fastapi.APIRouter``."""
    access_tier(tier, reason=reason, category=category)  # validates tier / category / reason
    if tier in ("platform", "org") and guard is None:
        raise ValueError(f"make_router(tier={tier!r}) needs guard=<dependency callable> (e.g. require_platform_admin / "
                         "get_current_user_org): a router that claims a tier must enforce it")
    if tier == "public" and guard is not None:
        raise ValueError("a public router takes no guard (it is anonymous by declaration)")
    from fastapi import APIRouter, Depends

    if tier == "platform":   # /docs + /openapi.json stay public (owner): Platform IP is left OUT of the public schema by construction
        router_kwargs.setdefault("include_in_schema", False)
    deps = list(router_kwargs.pop("dependencies", None) or [])
    if guard is not None:
        deps.insert(0, Depends(guard))
    router = APIRouter(dependencies=deps, **router_kwargs)
    router.access_tier = tier  # type: ignore[attr-defined]
    router.access_tier_category = category  # type: ignore[attr-defined]
    return router


# ---------------------------------------------------------------------------
# Dependency -> tier. Exact callable names (attribute tail for ``deps.x``). Reuse, don't re-declare: a
# product dependency that composes these resolves transitively and needs no entry here.
# ---------------------------------------------------------------------------
DEP_TIERS: dict[str, str] = {
    # platform: a global platform admin (noctus_users.role == 'admin') or the platform-issued token
    "require_platform_admin": "platform",
    "require_platform_admin_dep": "platform",
    "platform_admin_dep": "platform",
    "require_platform_content_admin": "platform",
    "require_content_write": "platform",
    "require_agent_delete": "platform",
    "require_publish_write": "platform",
    "require_evals_run_access": "platform",  # platform admin OR the platform-issued studio:evals-run token
    "require_evals_run_cancel": "platform",
    "get_current_admin": "platform",
    "get_website_editor": "platform",  # noctus_users.role in (admin, marketing): NoctusAI staff, global
    "resolve_platform_admin_role": "platform",
    # org: an authenticated member of the selected org (role checks are the product's)
    "get_current_user": "org",
    "get_current_user_org": "org",
    "get_current_user_org_unified": "org",
    "get_current_user_ungated": "org",
    "get_auth_context": "org",
    "get_trusted_auth": "org",
    "require_member": "org",
    "require_admin": "org",
    "require_org_admin": "org",
    "require_org_admin_dep": "org",
    "org_admin_dep": "org",
    "require_org_admin_for": "org",
    "require_org_admin_role": "org",
    "require_org_admin_role_assured": "org",
    "require_permission": "org",
    "require_org_permission": "org",
    "require_admin_or_content_token": "org",
    "require_spend_reader": "org",
    "ctx_dep": "org",
    "auth_dependency": "org",
    "approver_dep": "org",
    "get_caller": "org",
    "_authenticated": "org",
    # factories: the tier of what they BUILD (require_scopes is refined by its arguments)
    "make_get_current_user": "org",
    "make_get_current_user_org": "org",
    "make_get_auth_context": "org",
    "select_get_current_user": "org",
    "make_require_org_admin": "org",
    "require_scopes": "org",
}

#: Calls that prove a body verifies a webhook / push signature -> the route is ``public`` (signed).
SIGNATURE_CALLS: frozenset[str] = frozenset({
    "verify_hmac_sha256", "verify_hmac_sha256_hex", "verify_waha_hmac", "verify_svix_signature",
    "verify_basic_shared_secret", "verify_webhook_token", "verify_push_token", "verify_signature", "webhook_endpoint",
})

#: Health / liveness probes: tier ``service`` (signed:health), no data -- by convention, no marker needed.
PUBLIC_PATH_CONVENTION: tuple[str, ...] = (
    r"(^|/)_?(health|healthz|ready|readyz|live|livez|version|ping)(/[^/]*)?$",
)

# ---------------------------------------------------------------------------
# Platform IP -- routes (product -> regexes over the FULL path) that must resolve to ``platform``.
# A route matching one and resolving below ``platform`` is TOO-OPEN.
# ---------------------------------------------------------------------------
PLATFORM_IP_ROUTES: dict[str, tuple[str, ...]] = {
    "agents": (
        r"/studio/.*evals?\b", r"/studio/.*\bjudges?\b", r"/studio/plataforma", r"/studio/.*(canar|marker)",
        r"/studio/skills", r"/studio/conteudo", r"/studio/.*padr", r"/studio/.*prompt", r"/studio/.*compil",
        r"/studio/.*versions?\b.*(texto|ferramenta|decis|spec|section)", r"/studio/.*knowledge",
        r"/studio/.*qualifica", r"/studio/.*(credential|runtime-settings)",
    ),
    "core": (r"^/api/admin/(?!llm-spend)",),
}

#: Response-model field names that are Platform IP -- a route below ``platform`` returning one is TOO-OPEN.
PLATFORM_IP_FIELDS: frozenset[str] = frozenset({
    "compiled_prompt", "system_prompt", "prompt_text", "prompt_sections", "sections_text", "canary",
    "canary_token", "marker_text", "judge_prompt", "judge_rubric", "tool_descriptions", "skill_body",
    "skill_files", "master_prompt", "compiled_text",
})

# ---------------------------------------------------------------------------
# Platform IP -- tables. ``schema.table`` or bare ``table`` fnmatch globs; the schema part only has to match
# when the migration qualifies the name. Add a table here OR tag it ``COMMENT ... IS 'tier:platform'``.
# ---------------------------------------------------------------------------
PLATFORM_TABLES: tuple[str, ...] = (
    "agents.compiled_prompts", "agents.agent_prompt_sections", "agents.agent_skills", "agents.agent_skill_files",
    "agents.agent_versions", "agents.agent_version_*", "agents.eval_*", "agents.knowledge_*",
    "agents.agent_audit_log", "agents.agent_skill_*", "agents.skill_*", "agents.agent_canar*",
    "agents.turn_metrics",  # per-turn LLM cost/speed/size (066): service role only, platform-admin endpoints
)

#: A policy / grant is safe when its text proves a platform-admin check.
PLATFORM_ADMIN_POLICY_MARKERS: tuple[str, ...] = (
    "is_platform_admin", "platform_admin", "noctus_users", "role = 'admin'", "role='admin'",
)

# ---------------------------------------------------------------------------
# LLM output streaming -- any server route that publishes partial/delta model output to a browser passes it
# through the leak filter whenever a prompt-leak guard is active (agents: `FiltroDeltas`,
# products/agents/backend/app/studio/vazamento.py). Keeper `check_access_tier_streams`: a publish of a
# `message.delta`-style event whose enclosing function never names a filter below is a finding.
# Seed-first: a streaming organ in seed/lib would own the filter; its name goes here.
# ---------------------------------------------------------------------------
STREAM_EVENT_MARKERS: tuple[str, ...] = ("message.delta",)
STREAM_PUBLISH_CALLS: frozenset[str] = frozenset({"publish_event", "publish"})
LEAK_FILTER_NAMES: frozenset[str] = frozenset({"FiltroDeltas", "filtro_deltas", "filtrar_delta", "StreamLeakFilter"})

# ---------------------------------------------------------------------------
# Leak-fingerprint coverage -- everything prompt-derived that reaches the model must be a fingerprint source.
# The ONE registration seam: the function below builds the text the fingerprint is computed from. Keeper
# `check_access_tier_fingerprint` reads it (AST) and requires every source key (any alias) to be referenced
# there, and every tool in the tool registry to be classified (default deny).
# ---------------------------------------------------------------------------
LEAK_FINGERPRINT_SEAM: tuple[str, str] = (
    "products/agents/backend/app/channels/conformidade.py", "texto_fonte_do_prompt")
#: source key -> accepted spellings at the seam (attribute / name / string key).
LEAK_FINGERPRINT_SOURCES: dict[str, tuple[str, ...]] = {
    "compiled": ("texto",),
    "textos": ("textos",),
    "ferramentas": ("ferramentas",),
    "decisoes": ("decisoes",),
    "skills": ("skills", "skill_corpos", "corpos_skills", "skill_bodies", "biblioteca", "skills_biblioteca"),
    "skill_files": ("skill_files", "arquivos_skill", "skill_arquivos", "arquivos"),
}
LEAK_TOOL_REGISTRY: str = "products/agents/backend/app/channels/tool_registry.py"
#: tool -> the fingerprint source its result is derived from (its result carries prompt-derived content).
PROMPT_DERIVED_TOOLS: dict[str, str] = {"abrir_skill": "skills", "ler_arquivo_skill": "skill_files"}
#: tools reviewed as NOT returning prompt-derived content. A tool in neither map is refused until classified.
NOT_PROMPT_DERIVED_TOOLS: frozenset[str] = frozenset({
    "avaliar_lead", "registrar_perfil", "oferecer_imoveis", "detalhes_imovel", "consultar_empreendimento",
    "registrar_reacao_imovel", "oferecer_opcoes", "detalhes_opcao", "registrar_reacao_opcao", "registrar_intencao_visita", "registrar_identificacao", "registrar_documento",
    "concluir_qualificacao", "handoff", "encerrar", "captacao", "consentimento_credito",
    "registrar_solicitacao_titular", "sinalizar_alerta",
})

#: Tables a browser may hold a grant on by design (page-visibility flags: no PII, RLS-scoped). fnmatch globs on the
#: bare table name; they are exempt from the "browser grant without tier:org|public" defence-in-depth finding.
BROWSER_GRANT_ALLOWED_TABLES: tuple[str, ...] = ("status_pagina",)

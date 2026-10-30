"""
NoctusAI Agentes — the Bia control-plane API (G1b: HTTP + SSE).

Contract: ``projects/julia-agents-academia-CONTRACT.md`` §E. Mounts the
unified auth router directly (NOT via ``standard_routers=["auth"]`` — that
registry entry has no seam for this product's real ``SupabaseApiTokenResolver``
/ legacy-JWT bridge; mirrors ``products/social-wiring/backend/app/main.py``'s
documented reason) plus the four G1b routers (agents / persona /
conversations+SSE / approvals).

``app/runtime/`` (G2) is a hard dependency of the routers (``TurnContext``
/ ``Orphaned`` are imported at module level — both are lightweight,
``claude_agent_sdk``-free). The runtime/broker/spec-builder INSTANCES are
still resolved lazily via ``app/dependencies.py``'s ``get_agent_runtime_dep``
/ ``get_approval_broker_dep`` / ``get_build_legacy_chat_spec_dep`` — deferring
the real runtime's conditional SDK import to first use, not because the
package might be absent. The startup hook below (contract §E.2 "Startup",
extended by §E.11 "Every slot is swept once at startup") is wrapped by
the seed's own ``lifespan_startup`` contract so a hook failure degrades to
a logged warning, never a boot failure
(``KB § PATTERNS/backend/startup-hook-must-not-be-fatal.md``).

**Health seam (contract §E.11 "Any failure quarantines K ... /api/health
reports degraded"):** the seed's bundled ``standard_routers=["health"]``
``/api/health`` route has no hook seam — it surfaces exactly one signal
(``startup_hook_error``) and never forks. The seed's SUPPORTED extension
point for additional signals is ``health_config=HealthEndpointConfig(...)``
(``noctusai_seed.health``), which mounts ``/_health`` (liveness) +
``/_ready`` (readiness). The slot pool's ``health()`` is a fast,
network-free, in-memory check — liveness, not readiness — so it is wired
below as a ``liveness_hooks`` entry on ``/_health``, never a fork of
``/api/health``.
"""
from __future__ import annotations

import asyncio
import logging

from noctusai_seed import HealthEndpointConfig, create_product_app
from noctusai_seed.auth_router import create_auth_router
from noctusai_seed.organs import mount_finance

from app.clients.social_wiring import SocialWiringNotConfigured
from app.config import settings
from app.dependencies import (
    _LazyApiTokenResolver,
    _legacy_jwt_resolver,
    auth_router_deps,
    get_admin_client,
    get_core_client,
    get_current_user_org,
)
from app.rate_limit import limiter
from app.routers.admin_credentials_router import router as admin_credentials_router
from app.routers.agent_settings_router import router as agent_settings_router
from app.routers.agent_packages_router import router as agent_packages_router
from app.routers.agente_painel_router import router as agente_painel_router
from app.routers.agentes_cutover_router import router as agentes_cutover_router
from app.routers.agents_router import router as agents_router
from app.routers.catalogo_router import router as catalogo_router
from app.routers.studio_padrao_router import router as studio_padrao_router
from app.routers.studio_ui_router import router as studio_ui_router
from app.routers.api_keys_router import router as api_keys_router
from app.routers.channel_token_router import router as channel_token_router
from app.routers.channel_tools_token_router import router as channel_tools_token_router
from app.routers.channel_threads_router import router as channel_threads_router
from app.routers.channels_router import router as channels_router
from app.routers.approvals_router import router as approvals_router
from app.routers.conversations_router import router as conversations_router
from app.routers.editorial_router import router as editorial_router
from app.routers.persona_router import router as persona_router
from app.routers.qualificacao_router import router as qualificacao_router
from app.routers.skills_biblioteca_router import router as skills_biblioteca_router
from app.public_ask.router import BODY_LIMIT_PATTERN as PUBLIC_ASK_BODY_LIMIT_PATTERN
from app.public_ask.router import MAX_BODY_BYTES as PUBLIC_ASK_MAX_BODY_BYTES
from app.public_ask.router import router as public_ask_router
from app.routers.studio_agents_router import (
    SKILL_FILES_BATCH_BODY_LIMIT_PATTERN,
    SKILL_FILES_BATCH_MAX_BYTES,
)
from app.routers.studio_agents_router import router as studio_agents_router
from app.routers.studio_clients_router import router as studio_clients_router
from app.routers.studio_conteudo_router import router as studio_conteudo_router
from app.routers.studio_geracoes_router import router as studio_geracoes_router
from app.routers.studio_evals_router import router as studio_evals_router
from app.routers.studio_import_router import IMPORT_BODY_LIMIT_PATTERN
from app.routers.studio_import_router import router as studio_import_router
from app.routers.studio_knowledge_router import (
    DOCUMENTS_BATCH_BODY_LIMIT_PATTERN,
    DOCUMENTS_BATCH_MAX_BYTES,
)
from app.routers.studio_knowledge_router import router as studio_knowledge_router
from app.routers.studio_package_sync_router import SOURCES_BODY_LIMIT_PATTERN
from app.routers.studio_package_sync_router import router as studio_package_sync_router
from app.schemas.packages import SOURCES_MAX_BYTES
from app.studio.importer import MAX_BUNDLE_BYTES
from app.validation import install_validation_handler
from app.studio.wiring import install_studio_seams, register_anthropic_credential_override
from app.runtime.slots import get_slot_pool
from app.scheduler import configure as configure_scheduler
from noctusai_lib.api.scheduler import start_scheduler, stop_scheduler

logger = logging.getLogger(__name__)

# ONE combined router (`/api/auth` + `/api/settings/api-tokens`) — built
# directly via the factory (not `standard_routers=["auth"]`) so `pk_*` /
# legacy-JWT callers resolve through THIS product's real composition
# instead of the registry's bare `FakeApiTokenResolver()` default. See
# module docstring + `products/social-wiring/backend/app/main.py` for the
# pattern this mirrors.
_auth_router = create_auth_router(
    auth_router_deps,
    settings,
    api_token_resolver=_LazyApiTokenResolver(),
    legacy_jwt_resolver=_legacy_jwt_resolver,
)


#: Backoff for a startup step's transient failure (a PostgREST hiccup in the
#: first seconds of a container's life — seen live 2026-09-21).
_STARTUP_RETRY_DELAYS = (1.0, 3.0, 9.0)


async def _startup_step(name: str, step, failures: list[str], *, delays: tuple[float, ...] = _STARTUP_RETRY_DELAYS) -> None:
    """Run one startup step with bounded retries. A step that still fails is
    logged with its traceback and recorded — it never skips the steps after
    it (each is independent maintenance; one transient error must not leave
    slots unswept or eval runs stuck)."""
    for attempt, delay in enumerate((*delays, None), 1):
        try:
            await step()
            return
        except Exception:
            if delay is None:
                logger.exception("agents.startup.step_failed step=%s attempts=%d", name, attempt)
                failures.append(name)
                return
            logger.warning("agents.startup.step_retry step=%s attempt=%d", name, attempt, exc_info=True)
            await asyncio.sleep(delay)


async def on_startup() -> None:
    """Startup maintenance, each step independent (2026-09-21: a transient
    PostgREST error in the approvals step used to skip the slot sweep and the
    eval-run sweep behind it).

    1. Contract §E.11 "Every slot is swept once at startup" — FIRST: local,
       network-free, and the isolation guarantee depends on it.
    2. Contract §E.2 "Startup": every `pendente` approval row whose
       `instance_id` equals THIS instance becomes `expirada` — never other
       instances' rows (security finding 5).
    3. Agent Studio §E6: eval runs a previous life of this process left
       pendente/executando can never finish — fail them with a clear erro.

    Any step that still fails after its retries is re-raised as ONE error at
    the end, so the seed parks it on `startup_hook_error` (`/api/health`)."""
    from app.dependencies import get_approval_broker_dep
    from app.stores.studio_eval_runs import get_eval_run_writer
    from app.studio.evals import sweep_orphaned_runs

    failures: list[str] = []

    async def sweep_slots() -> None:
        slot_pool = get_slot_pool(settings)
        await slot_pool.sweep_all_on_startup()
        logger.info("agents.startup.slot_pool_swept health=%s", slot_pool.health())

    async def expire_approvals() -> None:
        expired = await get_approval_broker_dep().expire_orphans_on_startup()
        logger.info("agents.startup.expired_orphan_approvals count=%s", expired)

    async def fail_orphan_eval_runs() -> None:
        failed = sweep_orphaned_runs(get_eval_run_writer(settings))
        logger.info("agents.startup.orphaned_eval_runs_failed count=%s", failed)

    await _startup_step("slot_sweep", sweep_slots, failures)
    await _startup_step("expire_orphan_approvals", expire_approvals, failures)
    async def fail_orphan_mecanismo_runs() -> None:
        from app.stores.studio_eval_mecanismo import get_mecanismo_store
        from app.studio.eval_mecanismo_service import varrer_runs_orfas

        failed = varrer_runs_orfas(get_mecanismo_store(settings))
        logger.info("agents.startup.orphaned_mecanismo_runs_failed count=%s", failed)

    async def fail_orphan_geracoes() -> None:
        import asyncio

        from app.stores.studio_geracoes import get_geracao_store
        from app.studio.geracao import varrer_geracoes_orfas

        failed = await asyncio.to_thread(varrer_geracoes_orfas, get_geracao_store(settings))
        logger.info("agents.startup.orphaned_geracoes_failed count=%s", failed)

    await _startup_step("fail_orphan_eval_runs", fail_orphan_eval_runs, failures)
    await _startup_step("fail_orphan_geracoes", fail_orphan_geracoes, failures)
    await _startup_step("fail_orphan_mecanismo_runs", fail_orphan_mecanismo_runs, failures)

    # Daily credential maintenance (expiry notifications + §D ring prune).
    # Fires only where `NOCTUS_SCHEDULERS_ENABLED` is set (prod compose).
    start_scheduler()

    if failures:
        raise RuntimeError(f"agents startup steps failed after retries: {', '.join(failures)}")


async def on_shutdown() -> None:
    stop_scheduler()


async def _slot_pool_health() -> tuple[bool, str | None]:
    """Liveness hook (contract §E.11): degrades `/_health` — never
    `/api/health`, which has no hook seam (see module docstring) — when
    any slot is quarantined. Fast + network-free: reads the in-process
    `SlotPool.health()` dict only."""
    health = get_slot_pool(settings).health()
    quarantined = health.get("quarantined") or []
    if quarantined:
        return False, f"slots quarantined: {quarantined}"
    return True, None


configure_scheduler()
# Agent Studio: the eval judge's Anthropic key resolves DB-first, like the runtime's.
register_anthropic_credential_override()

app = create_product_app(
    name="Agentes",
    schema="agents",
    settings=settings,
    version="0.1.0",
    limiter=limiter,
    standard_routers=["health", "notificacoes", "team"],
    routers=[
        _auth_router,
        # The unified agent model + painel (agents-unified CONTRACT): static `/api/agents/painel` and
        # `/api/agents/{key}/painel[/interno]` + `/api/studio/modelo`.
        agente_painel_router,
        # Renata cutover: static `/api/agents/painel/destino-chat` + `/api/agents/{key}/transferir-historico|arquivar`.
        agentes_cutover_router,
        # catalogo before agents_router: `/api/agents/catalogo` must not be read as a `/{key}` path.
        catalogo_router,
        agents_router,
        persona_router,
        conversations_router,
        # Lais A2: the product-to-product channel turn API (+ its token mint).
        channels_router,
        channel_threads_router,
        channel_token_router,
        channel_tools_token_router,
        approvals_router,
        qualificacao_router,  # Julia v2 A-QUAL: the platform qualification standard + lead state
        skills_biblioteca_router,  # Julia v2 A-SKILLS: the shared, versioned skill library + agent-draft pins
        admin_credentials_router,
        # Lais A1: per-org LLM provider keys (openai/anthropic), admin-only, with POST .../test.
        api_keys_router,
        agent_settings_router,
        # Agent Studio (contract §D, §J2.3 — BE-RT registers every studio router).
        studio_agents_router,
        studio_clients_router,
        studio_conteudo_router,
        studio_geracoes_router,  # S3a: AI-generated first drafts
        studio_padrao_router,
        studio_ui_router,
        studio_knowledge_router,
        # Seed editorial workflow (project seed-editorial-workflow, E5): governed knowledge review.
        editorial_router,
        studio_evals_router,
        studio_import_router,
        # Agent Packages (CONTRACT §I): package serving + consumer sync routes.
        agent_packages_router,
        studio_package_sync_router,
        # Anonymous public ask (limiar-open-question S3) — 404 unless PUBLIC_ASK_ENABLED.
        public_ask_router,
    ],
    # Finance organ (accounts, entries, DRE, reconciliation): one-call seed mount. Gateway sync stays
    # 503-not-configured.
    organs=[
        mount_finance(
            schema="agents",
            auth_dependency=get_current_user_org,
            get_admin_client=get_admin_client,
            get_core_client=get_core_client,
        )
    ],
    lifespan_startup=on_startup,
    lifespan_shutdown=on_shutdown,
    health_config=HealthEndpointConfig(liveness_hooks=[_slot_pool_health]),
    # Contract §D / §E.5: the approval-assertion signing key + the
    # social-wiring bridge token must both be set in a deploy context.
    # Since 2026-09-16 both resolve DB-first (Credenciais page) and these
    # env values are the BOOTSTRAP fallback — keep them in `.env`; a stored
    # value overrides them without a redeploy (deploy/fleet/README.md) —
    # an unset key would silently disable the whole escrita-approval
    # flow's ability to ever call academia (§D), and would let the
    # product boot with no way to reach social-wiring's One Chat bridge.
    required_prod_config=["APPROVAL_ASSERTION_SECRETS", "SOCIAL_WIRING_API_TOKEN"],
    # Agent Studio §D5: the bundle import is above the 1 MB default — an
    # exact whole-segment wildcard, never a prefix. UI-KB-BACKEND adds the
    # two bulk-ingest batch routes the Studio UI uses in place of a bundle
    # import (same reasoning, narrower caps — see each pattern's origin
    # module for the byte-cap rationale).
    max_body_path_overrides={
        IMPORT_BODY_LIMIT_PATTERN: MAX_BUNDLE_BYTES,
        DOCUMENTS_BATCH_BODY_LIMIT_PATTERN: DOCUMENTS_BATCH_MAX_BYTES,
        SKILL_FILES_BATCH_BODY_LIMIT_PATTERN: SKILL_FILES_BATCH_MAX_BYTES,
        # Agent Packages §G2: the full project manifest (25 MB cap per call).
        SOURCES_BODY_LIMIT_PATTERN: SOURCES_MAX_BYTES,
        # Public ask: a 600-char text + JSON envelope — 2 KB, rejected before parsing.
        PUBLIC_ASK_BODY_LIMIT_PATTERN: PUBLIC_ASK_MAX_BODY_BYTES,
    },
)

# Agent Studio §J2: bind the fail-closed seams (eval gate, knowledge
# catalog, eval scheduler, run hash) to their production implementations.
install_studio_seams(app)
# 422 without echoing the caller's input (the seed handler can carry a validator's text; see app/validation.py).
install_validation_handler(app)


async def _social_wiring_nao_configurado(request, exc):  # noqa: ANN001
    from fastapi.responses import JSONResponse

    logger.error("agents.social_wiring.not_configured path=%s", request.url.path)
    return JSONResponse(
        status_code=503,
        content={"detail": "A integração com o social-wiring não está configurada.", "code": "social_wiring_nao_configurado"},
    )


app.add_exception_handler(SocialWiringNotConfigured, _social_wiring_nao_configurado)

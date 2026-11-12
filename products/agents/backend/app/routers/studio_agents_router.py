"""``/api/studio/agents`` + ``/api/studio/prompts`` — Agent Studio agents,
versions, sections, skills, compile, diff and publish (contract §D1).

Auth: ``require_member`` for reads, ``require_platform_content_admin`` (NoctusAI platform admin or the platform content token) for writes. Every route
resolves the agent by ``(ctx.org_id, key)`` → 404 ``agent_not_found``; a
legacy agent on a studio route → 409 ``not_studio_agent`` (the list is the
one exception — it includes legacy agents, read-only). Every child id
(version / skill / file) is checked to belong to THAT agent — a foreign id is
a 404, never a 403 (§H1). Mutating a non-draft → 409 ``version_immutable``.

Seams (all FastAPI dependencies, overridden in tests — never patched):

* ``get_studio_definition_store_dep`` — the §B1 store.
* ``get_eval_gate_dep`` — §J2.1. The default binding FAILS CLOSED (503
  ``eval_gate_unavailable``): a publish must never pass a gate nobody
  checked. BE-RT binds the production gate (BE-KE's ``SupabaseEvalGate``).
* ``get_knowledge_catalog_dep`` — the knowledge summary the compiler needs
  (BE-KE's tables). Same fail-closed default (503
  ``knowledge_catalog_unavailable``): compiling WITHOUT the knowledge block
  would produce a plausible prompt with the wrong hash. BE-RT binds it.

``compiled_hash`` (the no-client compile of a draft) is re-stamped after
every admin write to the draft and right before the publish gate — never by
a read (L7: ``GET .../compiled`` is side-effect free). The DB NULLs it on
every content write (M1), so the stamp is a compare-and-set on the draft's
``updated_at``: a concurrent write in between wins, and publish refuses
(409 ``draft_changed``) unless the gate-checked hash is still the row's.

Routers are registered in ``main.py`` by BE-RT (§J2.3); until then they are
mounted on a local test app.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import contextmanager
from typing import Any, Iterator
from uuid import UUID

import anyio.to_thread
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field

from app.config import settings
from app.channels.conformidade import garantir_impressao
from app.routers.qualificacao_router import get_padrao_store_dep
from app.dependencies import (
    CONTENT_TOKEN_ISSUER,
    SCOPE_STUDIO_EVALS_RUN,
    SCOPE_STUDIO_PUBLISH,
    require_evals_run_access,
    get_conformidade_store_dep,
    get_geracao_store_dep,
    get_notification_sink_dep,
    get_skills_store_dep,
    require_agent_delete,
    require_member,
    require_platform_admin,
    require_platform_content_admin,
    require_publish_write,
)
from app.schemas.studio import (
    AgentDetailOut,
    AgentListOut,
    AgentSummaryOut,
    AvisoOut,
    CompiledOut,
    DiffConfigOut,
    DiffOut,
    DiffSectionOut,
    DiffSideOut,
    DiffSkillOut,
    DraftCreateRequest,
    DraftUpdateRequest,
    PromptByHashOut,
    PublishRequest,
    SectionOut,
    SectionsReplaceRequest,
    SkillCreateRequest,
    SkillFileBatchItemResultOut,
    SkillFileMetaOut,
    SkillFileOut,
    SkillFileUpsertRequest,
    SkillFilesBatchResultOut,
    SkillFilesBatchUpsertRequest,
    SkillOut,
    SkillUpdateRequest,
    StudioAgentCreateRequest,
    StudioAgentUpdateRequest,
    VersionDetailOut,
    VersionSummaryOut,
)
from app.stores._db_errors import erro_de_item, mensagem_conflito
from app.stores.errors import NotFound
from app.stores.marcadores import get_marcador_store
from app.stores.studio_definitions import (
    SectionInput,
    StudioAgentRecord,
    StudioConflict,
    VersionImmutable,
    VersionRecord,
)
from app.studio.bundles import client_bundle, compile_version
from app.studio.camada_validada import base_nao_validada, coletar_camadas_base
from app.studio.prontidao import avaliar as avaliar_prontidao, falta_numero_fallback, juiz_aprovado, recusa_de_compilacao
from app.studio.eval_driver import get_eval_turn_driver
from app.studio.eval_mecanismo import decidir_portao
from app.studio.eval_mecanismo_service import (
    DriverSemTipo,
    SuiteVazia,
    concluir_suite_mecanismo,
    TodosConsolidados,
    iniciar_suite_mecanismo,
)
from app.studio.eval_loop_service import resumo_mecanismo
from app.studio.plataforma import ensure_instancias
from app.studio.spend import KIND_MECANISMO_RUN, get_spend_ceiling_dep, reserve_run, settle_run
from app.studio.camadas import EfetivoStore, resolver_pai_de
from app.studio.models import (
    CompiledPrompt,
    EvalGate,
    KnowledgeCatalog,
)
from noctusai_lib.api.auth.session import AuthContext

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/studio", tags=["studio"])

#: Version settings compared by the diff endpoint, in output order.
_CONFIG_FIELDS = ("provider", "model", "effort", "max_turns", "idioma", "tool_policy")

#: The body-cap pattern ``app.main`` registers for the skill-files batch
#: route (UI-KB-BACKEND), same shape as ``studio_import_router.
#: IMPORT_BODY_LIMIT_PATTERN`` / ``studio_knowledge_router.
#: DOCUMENTS_BATCH_BODY_LIMIT_PATTERN``.
SKILL_FILES_BATCH_BODY_LIMIT_PATTERN = "/api/studio/agents/*/draft/skills/*/files/batch"
#: 50 items × `skill_file.conteudo` (120 KB) = 6 MB pathological max;
#: 8 MB gives headroom without matching the (much larger) bundle-import cap.
SKILL_FILES_BATCH_MAX_BYTES = 8 * 1024 * 1024


# ── dependency seams ────────────────────────────────────────────────────────


def get_studio_definition_store_dep():
    """Seam over ``get_studio_definition_store`` — tests override it with one
    shared ``FakeStudioDefinitionStore``."""
    from app.stores.studio_definitions import get_studio_definition_store

    return get_studio_definition_store(settings)


def get_mecanismo_store_dep():
    """Seam over ``get_mecanismo_store`` (the mechanism-suite cases and run records) — tests override it."""
    from app.stores.studio_eval_mecanismo import get_mecanismo_store

    return get_mecanismo_store(settings)

def get_mecanismo_resumo_dep(mecanismo=Depends(get_mecanismo_store_dep)):
    """Reader behind the versions endpoint: ``(org_id, version_id, compiled_hash) -> MecanismoResumoOut | None`` --
    the newest FINISHED mechanism run (any driver) for exactly that hash, from A-EVAL's store. A test overrides it."""
    from app.schemas.studio import MecanismoResumoOut

    def _ler(org_id, version_id, compiled_hash):
        run = mecanismo.latest_run(org_id, version_id, compiled_hash)
        if run is None:
            return None
        return MecanismoResumoOut(
            run_id=run.id, driver=run.driver, aprovado=run.aprovado, completo=run.completa,
            orcamento_excedido=run.orcamento_excedido, casos_total=run.total_casos, casos_aprovados=run.casos_aprovados)

    return _ler


def get_eval_store_dep():
    """Seam over ``get_eval_store`` (the eval cases/runs). Lives HERE -- not in ``studio_evals_router``, which imports
    this module -- because publish + the readiness view count the cases too; ``studio_evals_router`` re-exports the
    same function object, so one ``dependency_overrides`` key reaches every consumer."""
    from app.stores.studio_evals import get_eval_store

    return get_eval_store(settings)


def get_prontidao_controles_dep():
    """Seam over the agent-controls store (``ligado|drenando|desligado``), which the readiness view reads."""
    from app.stores.agent_controles import get_agent_controle_store

    return get_agent_controle_store(settings)


def get_eval_gate_dep() -> EvalGate:
    """§J2.1 — fail closed until BE-RT binds the production gate."""
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={"detail": "Portão de avaliação indisponível.", "code": "eval_gate_unavailable"},
    )


def get_knowledge_catalog_dep() -> KnowledgeCatalog:
    """Knowledge summary for the compiler — fail closed until BE-RT binds it."""
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "detail": "Catálogo de conhecimento indisponível.",
            "code": "knowledge_catalog_unavailable",
        },
    )


def get_compiled_hash_provider(
    store=Depends(get_studio_definition_store_dep),
    catalog=Depends(get_knowledge_catalog_dep),
):
    """``(org_id, agent, version) -> hash`` of the version compiled NOW
    (no client) — the ready-made production binding for
    ``studio_evals_router.get_current_hash_dep`` (wire it in
    ``app.studio.wiring``). Pure read: it never stamps the draft."""

    def _hash(org_id: UUID, agent: StudioAgentRecord, version: VersionRecord) -> str:
        return compile_version(store, catalog, org_id, agent, version).hash

    return _hash


def get_compiled_partes_provider(
    store=Depends(get_studio_definition_store_dep),
    catalog=Depends(get_knowledge_catalog_dep),
):
    """``(org_id, agent, version) -> per-part hashes`` of the version compiled NOW (eval consolidation: WHAT changed).
    ``None`` when the compile is unavailable -- the caller then treats every case as affected (fail-safe: runs all)."""

    def _partes(org_id: UUID, agent: StudioAgentRecord, version: VersionRecord) -> dict[str, str] | None:
        try:
            return dict(compile_version(store, catalog, org_id, agent, version).partes)
        except Exception:  # noqa: BLE001 -- named fail-safe: no per-part hashes => consolidation cannot skip anything
            logger.warning("studio: per-part hashes unavailable for version %s (consolidation off for this run)",
                           version.id, exc_info=True)
            return None

    return _partes


def get_consolidacao_store_dep(evals=Depends(get_eval_store_dep)):
    """Seam over the eval-consolidation store (state, transitions, skipped ledger). Tests override it."""
    from app.stores.studio_eval_consolidacao import get_consolidacao_store

    return get_consolidacao_store(settings, evals)


def get_loop_store_dep():
    """Seam over the eval-loop store (loops + rounds, migration 076). Tests override it with a shared Fake."""
    from app.stores.studio_eval_loops import get_loop_store

    return get_loop_store(settings)


def get_loop_service_dep(
    loops=Depends(get_loop_store_dep),
    sink=Depends(get_notification_sink_dep),
    consolidacao=Depends(get_consolidacao_store_dep),
):
    """The eval-loop gate (G1-G7): admission of a round, its close hook, the stop notification. One seam for both suites."""
    from app.studio.eval_loop_service import EvalLoopService

    return EvalLoopService(loops, sink, consolidacao)


# ── error helpers ───────────────────────────────────────────────────────────


def http_error(status_code: int, code: str, detail: str, **extra: Any) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"detail": detail, "code": code, **extra})


def actor_id(ctx: AuthContext) -> UUID:
    """The audit actor of a write: the human's user id, or — for the scoped
    ``studio:publish`` token — the token row id (never ``None``: the actor
    columns of the audit log + ``published_by``/``created_by`` are UUIDs)."""
    actor = ctx.user_id or ctx.api_token_id
    if actor is None:  # pragma: no cover — a product ctx always carries its token id
        raise http_error(403, "user_required", "Restricted to human users")
    return actor


def require_user_or_dev_advisor(ctx: AuthContext, agent: Any, *, evals_token_ok: bool = False) -> None:
    """A ``studio:publish`` token acts ONLY on a dev agent (dev-advisor | dev-executor, A12); a runtime
    agent (Bia, IsaIA, Julia) stays human-only → 403 ``user_required``, exactly
    as before the scope existed.

    ``evals_token_ok`` is passed ONLY by the eval-run routes, whose ``_evals_gate`` has already validated the
    ``studio:evals-run`` scope AND the platform issuer. It is honoured only for a token that is evals-only: a token that
    also carries ``studio:publish`` falls through to the dev-advisor rule (the scope string alone is never trusted)."""
    if (
        evals_token_ok and ctx.caller_kind == "product" and SCOPE_STUDIO_EVALS_RUN in ctx.scopes
        and ctx.issuer == CONTENT_TOKEN_ISSUER and SCOPE_STUDIO_PUBLISH not in ctx.scopes
    ):
        return  # the platform-issued eval-loop token acts on any agent's eval runs
    from app.stores.studio_definitions import DEV_KINDS

    if ctx.caller_kind == "product" and getattr(agent, "kind", "runtime") not in DEV_KINDS:
        raise http_error(403, "user_required", "Restricted to human users")


def audit_definition_read(store, ctx: AuthContext, agent, what: str, version_id: UUID | None = None) -> None:
    """Visibility tier 1: the platform's prompts / definition are readable by platform admins ONLY,
    and every read of them leaves an append-only audit row (who, what, which version) — never the
    content. A failed audit write fails the read (no unaudited disclosure)."""
    store.append_audit(
        agent.org_id, agent.id, actor_id(ctx), "definicao_lida", None,
        {"o_que": what, "version_id": str(version_id) if version_id else None},
    )


@contextmanager
def store_errors() -> Iterator[None]:
    """Map typed store errors onto the §D HTTP codes."""
    try:
        yield
    except VersionImmutable as exc:
        raise http_error(409, "version_immutable", "A versão publicada é imutável.") from exc
    except StudioConflict as exc:
        raise http_error(409, exc.code, mensagem_conflito(exc)) from exc
    except ValueError as exc:
        raise http_error(422, "invalid_field", str(exc)) from exc


def patch_fields(payload, *, nullable: frozenset[str] = frozenset()) -> dict[str, Any]:
    """``exclude_unset`` PATCH body; an explicit ``null`` on a NOT NULL
    column is a 422 (never silently dropped)."""
    fields = payload.model_dump(mode="json", exclude_unset=True)
    for name, value in fields.items():
        if value is None and name not in nullable:
            raise http_error(422, "invalid_field", f"{name} cannot be null")
    return fields


# ── resolution helpers (shared with studio_clients_router) ─────────────────


def resolve_agent(
    store, org_id: UUID, key: str, *, studio_only: bool = True, allow_instancia: bool = False,
) -> StudioAgentRecord:
    try:
        agent = store.get_agent(org_id, key)
    except NotFound as exc:
        raise http_error(404, "agent_not_found", "Agente não encontrado.") from exc
    if studio_only and agent.definition_mode != "studio":
        raise http_error(409, "not_studio_agent", "Este agente não é gerenciado pelo Studio.")
    if agent.definition_scope == "instancia" and not allow_instancia:
        # An instance owns no versions: the definition is edited on the platform, the org edits its specs.
        raise http_error(
            409, "definicao_na_plataforma",
            "A definição deste agente é da plataforma; a organização edita as suas especificações.",
        )
    return agent


def resolve_version(store, org_id: UUID, agent: StudioAgentRecord, version_id: UUID) -> VersionRecord:
    try:
        version = store.get_version(org_id, version_id)
    except NotFound as exc:
        raise http_error(404, "version_not_found", "Versão não encontrada.") from exc
    if version.agent_id != agent.id:
        raise http_error(404, "version_not_found", "Versão não encontrada.")
    return version


def resolve_draft(store, org_id: UUID, agent: StudioAgentRecord) -> VersionRecord:
    draft = store.get_draft(org_id, agent.id)
    if draft is None:
        raise http_error(404, "draft_not_found", "Nenhum rascunho para este agente.")
    return draft


def _resolve_skill(store, org_id: UUID, agent: StudioAgentRecord, skill_id: UUID):
    try:
        skill = store.get_skill(org_id, skill_id)
    except NotFound as exc:
        raise http_error(404, "skill_not_found", "Skill não encontrada.") from exc
    try:
        version = store.get_version(org_id, skill.version_id)
    except NotFound as exc:
        raise http_error(404, "skill_not_found", "Skill não encontrada.") from exc
    if version.agent_id != agent.id:
        raise http_error(404, "skill_not_found", "Skill não encontrada.")
    return skill, version


def _resolve_draft_skill(store, org_id: UUID, agent: StudioAgentRecord, skill_id: UUID):
    skill, version = _resolve_skill(store, org_id, agent, skill_id)
    if version.status != "rascunho":
        raise http_error(409, "version_immutable", "A versão publicada é imutável.")
    return skill, version


def _resolve_file(store, org_id: UUID, skill_id: UUID, file_id: UUID):
    try:
        f = store.get_skill_file(org_id, file_id)
    except NotFound as exc:
        raise http_error(404, "file_not_found", "Arquivo não encontrado.") from exc
    if f.skill_id != skill_id:
        raise http_error(404, "file_not_found", "Arquivo não encontrado.")
    return f


def resolve_client(store, org_id: UUID, agent: StudioAgentRecord, client_id: UUID):
    try:
        client = store.get_client(org_id, client_id)
    except NotFound as exc:
        raise http_error(404, "client_not_found", "Cliente não encontrado.") from exc
    if client.agent_id != agent.id:
        raise http_error(404, "client_not_found", "Cliente não encontrado.")
    return client


# ── compile helpers ─────────────────────────────────────────────────────────


def _pin_do_pai(store, catalog, org_id: UUID, agent, draft: VersionRecord, compiled: CompiledPrompt, prontidao):
    """073 layers: the parent version a child publish pins -- the parent's CURRENT published version -- after proving
    the child compiles to the SAME hash against it as against the parent draft it was evaluated on. A parent with
    unpublished changes that reach the child is a refusal (publish the parent first, or re-evaluate), never a
    silent swap of what ships. ``None`` for an agent without a parent."""
    if agent.pai_agent_id is None:
        return None
    pai_ativa = store.get_active_version(org_id, agent.pai_agent_id)
    if pai_ativa is None:
        raise http_error(409, "pai_nao_publicado",
                         "O modelo de origem deste agente ainda não tem versão publicada. Publique o modelo primeiro.",
                         prontidao=prontidao(compiled))
    base = resolver_pai_de(store)
    fixado = EfetivoStore(store, lambda o, v: (pai_ativa.org_id, pai_ativa.id) if v == draft.id else base(o, v))
    no_pin = compile_version(fixado, catalog, org_id, agent, draft)
    if no_pin.hash != compiled.hash:
        raise http_error(409, "pai_desatualizado",
                         "O modelo de origem tem alterações ainda não publicadas que mudam este agente. "
                         "Publique o modelo e avalie este agente de novo.",
                         hash_atual=compiled.hash, hash_com_pai_publicado=no_pin.hash, prontidao=prontidao(compiled))
    return pai_ativa.id


def _refresh_draft_hash(
    store, catalog, org_id: UUID, agent, draft_id: UUID, *, strict: bool = False,
) -> tuple[VersionRecord, CompiledPrompt]:
    """Re-read the draft, compile it, and stamp the hash with a
    compare-and-set on the ``updated_at`` just read (M1) — a content write
    that lands between the read and the stamp makes the CAS miss instead of
    stamping a hash of stale content.

    ``strict`` (publish): a missed CAS is a 409 ``draft_changed``. Otherwise
    (a save path) the concurrent writer re-stamps after its own write, so the
    miss is logged and the freshly-read row is returned as is."""
    try:
        draft = store.get_version(org_id, draft_id)
    except NotFound as exc:
        raise http_error(404, "draft_not_found", "Nenhum rascunho para este agente.") from exc
    compiled = compile_version(store, catalog, org_id, agent, draft)
    if draft.compiled_hash == compiled.hash:
        return draft, compiled
    try:
        with store_errors():
            draft = store.set_compiled_hash(
                org_id, draft.id, compiled.hash, expected_updated_at=draft.updated_at,
            )
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        if strict or detail.get("code") != "draft_changed":
            raise
        logger.warning(
            "studio: compiled_hash CAS missed for draft %s (concurrent write) — left to that writer",
            draft_id,
        )
        draft = store.get_version(org_id, draft_id)
    return draft, compiled


# ── output builders ─────────────────────────────────────────────────────────


def _eval_score(gate: EvalGate, org_id: UUID, version_id: UUID) -> float | None:
    run = gate.latest_concluded_run(org_id, version_id)
    return run.score if run is not None else None


def _summary(store, org_id: UUID, agent: StudioAgentRecord) -> AgentSummaryOut:
    versao_ativa = None
    tem_rascunho = False
    if agent.definition_mode == "studio":
        if agent.definition_scope == "instancia":
            # The versions are the platform definition's; the org sees only which one is live.
            definition = store.get_agent_by_id(agent.definition_agent_id)
            active = store.get_active_version(definition.org_id, definition.id)
        else:
            active = store.get_active_version(org_id, agent.id)
            tem_rascunho = store.get_draft(org_id, agent.id) is not None
        versao_ativa = active.versao if active else None
    return AgentSummaryOut(
        id=agent.id, key=agent.key, nome=agent.nome, descricao=agent.descricao,
        definition_mode=agent.definition_mode, ativo=agent.ativo,
        publicacao_limiar=agent.publicacao_limiar, versao_ativa=versao_ativa,
        tem_rascunho=tem_rascunho, kind=agent.kind,
        definition_scope=agent.definition_scope, conteudo_modo=agent.conteudo_modo,
        runtime=agent.runtime, owner_product=agent.owner_product, usa_canais=agent.usa_canais,
    )


def _version_summary(v: VersionRecord, eval_score: float | None) -> dict[str, Any]:
    return dict(
        id=v.id, versao=v.versao, status=v.status, notas=v.notas, model=v.model,
        provider=v.provider,
        created_at=v.created_at, published_at=v.published_at, compiled_hash=v.compiled_hash,
        eval_score=eval_score, versao_semver=v.versao_semver, package_sha=v.package_sha,
    )


def _skill_out(skill, files) -> SkillOut:
    return SkillOut(
        id=skill.id, nome=skill.nome, descricao=skill.descricao, corpo=skill.corpo,
        ordem=skill.ordem, ativo=skill.ativo,
        arquivos=[
            SkillFileMetaOut(id=f.id, caminho=f.caminho, titulo=f.titulo, chars=len(f.conteudo))
            for f in files
        ],
    )


def _score_of(gate: EvalGate, org_id: UUID, v: VersionRecord) -> float | None:
    """A published version reports the score SNAPSHOT taken at publish (H2;
    ``None`` for an override publish); a draft its latest complete run."""
    if v.status != "rascunho":
        return v.eval_score
    return _eval_score(gate, org_id, v.id)


def _version_detail(store, gate: EvalGate, org_id: UUID, v: VersionRecord) -> VersionDetailOut:
    files = store.list_version_skill_files(org_id, v.id)
    return VersionDetailOut(
        **_version_summary(v, _score_of(gate, org_id, v)),
        effort=v.effort, max_turns=v.max_turns, idioma=v.idioma, tool_policy=v.tool_policy,
        based_on_version_id=v.based_on_version_id, published_by=v.published_by,
        publish_override_reason=v.publish_override_reason, eval_run_id=v.eval_run_id,
        limiar_aplicado=v.limiar_aplicado,
        secoes=[
            SectionOut(
                id=s.id, chave=s.chave, titulo=s.titulo, ordem=s.ordem, conteudo=s.conteudo, ativo=s.ativo,
                regras=list(s.regras),
            )
            for s in store.list_sections(org_id, v.id)
        ],
        skills=[
            _skill_out(sk, [f for f in files if f.skill_id == sk.id])
            for sk in store.list_skills(org_id, v.id)
        ],
    )


def _compiled_out(compiled: CompiledPrompt, version_id: UUID, client_id: UUID | None) -> CompiledOut:
    return CompiledOut(
        texto=compiled.texto, hash=compiled.hash, tokens_estimados=compiled.tokens_estimados,
        manifest=compiled.manifest_json(), sob_demanda=[i.to_dict() for i in compiled.sob_demanda],
        avisos=[AvisoOut(**w.to_dict()) for w in compiled.avisos],
        version_id=version_id, client_id=client_id, ponto_cache=compiled.ponto_cache,
    )


# ── agents ──────────────────────────────────────────────────────────────────


@router.get("/agents", response_model=AgentListOut)
def list_studio_agents(
    ctx: AuthContext = Depends(require_member),
    store=Depends(get_studio_definition_store_dep),
) -> AgentListOut:
    # Julia v2: the org gets an INSTANCE of every published, instantiable platform definition on first use
    # (structure only; data-driven -- no agent key is known to the code).
    ensure_instancias(ctx.org_id, studio_store=store)
    return AgentListOut(items=[_summary(store, ctx.org_id, a) for a in store.list_agents(ctx.org_id)])


@router.post("/agents", response_model=AgentSummaryOut, status_code=status.HTTP_201_CREATED, include_in_schema=False)
def create_studio_agent(
    payload: StudioAgentCreateRequest,
    ctx: AuthContext = Depends(require_platform_content_admin),
    store=Depends(get_studio_definition_store_dep),
    catalog=Depends(get_knowledge_catalog_dep),
) -> AgentSummaryOut:
    if store.get_platform_definition(payload.key) is not None:
        # A platform-defined key is the platform's: an org agent squatting it would shadow the org's instance.
        raise http_error(409, "key_taken", f"A chave '{payload.key}' é reservada.")
    with store_errors():
        agent = store.create_studio_agent(ctx.org_id, payload.key, payload.nome, payload.descricao)
        draft = store.create_draft(ctx.org_id, agent.id, None, ctx.user_id)
    _refresh_draft_hash(store, catalog, ctx.org_id, agent, draft.id)
    return _summary(store, ctx.org_id, agent)


@router.get("/agents/{key}", response_model=AgentDetailOut)
def get_studio_agent(
    key: str,
    ctx: AuthContext = Depends(require_member),
    store=Depends(get_studio_definition_store_dep),
    gate=Depends(get_eval_gate_dep),
    skills=Depends(get_skills_store_dep),
) -> AgentDetailOut:
    agent = resolve_agent(store, ctx.org_id, key, allow_instancia=True)
    summary = _summary(store, ctx.org_id, agent)
    if agent.definition_scope == "instancia":
        # Visibility tiers: an org sees no version of the platform's definition (no hash, no notes, no
        # model, no history) — only the summary's live version number.
        versoes = []
    else:
        versoes = [
            VersionSummaryOut(**_version_summary(v, _score_of(gate, ctx.org_id, v)))
            for v in store.list_versions(ctx.org_id, agent.id)
        ]
    from app.studio.geracao import conteudo_status

    return AgentDetailOut(**summary.model_dump(), versoes=versoes, conteudo_status=conteudo_status(store, skills, agent))


#: 409 ``code`` -> the pt-BR message of ``DELETE /agents/{key}`` (the DB function's guard codes, 048).
_EXCLUSAO_MENSAGENS = {
    "publicado": "O agente tem versão publicada e não pode ser excluído.",
    "tem_instancias": "O agente é a definição da plataforma e tem instâncias em organizações.",
    "tem_conversas": "O agente tem conversas com mensagens (ou registros de leads) e não pode ser excluído.",
    "tem_canal": "O agente tem um canal ativo (token de canal vigente); revogue-o antes de excluir.",
    "ativo": "O agente está ativo; desligue-o antes de excluir.",
}


@router.delete("/agents/{key}", status_code=status.HTTP_204_NO_CONTENT, include_in_schema=False)
def delete_studio_agent(
    key: str,
    ctx: AuthContext = Depends(require_agent_delete),
    store=Depends(get_studio_definition_store_dep),
) -> Response:
    """Delete an agent of the caller's org: a platform admin OR the content token minted with
    ``permitir_exclusao`` (scope ``studio:agent-delete``). Refused with 409 ``{code, message, detail}`` (flat — the seed handler passes the dict through) while the
    agent has a published version (``publicado``), platform instances (``tem_instancias``), a conversation with a
    message (``tem_conversas``), an active channel token (``tem_canal``) or is on (``ativo``). Empty conversations
    and the draft go with it; the audit rows survive (``agent_id`` NULL) with an ``agente_excluido`` tombstone."""
    nao_encontrado = http_error(404, "agente_nao_encontrado", "Agente não encontrado.")
    try:
        agent = store.get_agent(ctx.org_id, key)
    except NotFound as exc:
        raise nao_encontrado from exc
    try:
        store.delete_agent(ctx.org_id, agent.id, actor=actor_id(ctx))
    except NotFound as exc:
        raise nao_encontrado from exc
    except StudioConflict as exc:
        message = _EXCLUSAO_MENSAGENS.get(exc.code)
        if message is None:
            raise
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail={"code": exc.code, "message": message, "detail": message},
        ) from exc
    logger.info("agents.studio.agent_deleted org_id=%s key=%s by=%s", ctx.org_id, key, actor_id(ctx))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/agents/{key}", response_model=AgentSummaryOut, include_in_schema=False)
def update_studio_agent(
    key: str,
    payload: StudioAgentUpdateRequest,
    ctx: AuthContext = Depends(require_platform_content_admin),
    store=Depends(get_studio_definition_store_dep),
) -> AgentSummaryOut:
    resolve_agent(store, ctx.org_id, key)
    fields = patch_fields(payload, nullable=frozenset({"descricao"}))
    with store_errors():
        agent = store.update_agent(ctx.org_id, key, fields, actor=ctx.user_id)
    return _summary(store, ctx.org_id, agent)


# ── versions ────────────────────────────────────────────────────────────────


@router.get("/agents/{key}/versions/{version_id}", response_model=VersionDetailOut, include_in_schema=False)
def get_version(
    key: str,
    version_id: UUID,
    ctx: AuthContext = Depends(require_platform_admin),
    store=Depends(get_studio_definition_store_dep),
    gate=Depends(get_eval_gate_dep),
    mecanismo=Depends(get_mecanismo_resumo_dep),
) -> VersionDetailOut:
    agent = resolve_agent(store, ctx.org_id, key)
    version = resolve_version(store, ctx.org_id, agent, version_id)
    audit_definition_read(store, ctx, agent, "versao", version.id)
    out = _version_detail(store, gate, ctx.org_id, version)
    try:
        resumo = mecanismo(ctx.org_id, version.id, version.compiled_hash) if version.compiled_hash else None
    except Exception:  # noqa: BLE001 -- an advisory panel never fails the version read; it is logged
        logger.exception("agents.studio.mecanismo_resumo_indisponivel version_id=%s", version.id)
        resumo = None
    return out.model_copy(update={"mecanismo": resumo})


@router.get("/agents/{key}/draft", response_model=VersionDetailOut, include_in_schema=False)
def get_draft(
    key: str,
    ctx: AuthContext = Depends(require_platform_content_admin),
    store=Depends(get_studio_definition_store_dep),
    gate=Depends(get_eval_gate_dep),
) -> VersionDetailOut:
    """The agent's current draft (the definition being edited). Platform-only: a NoctusAI platform admin
    or the ``studio:content-write`` token of the ``noctus.agents.content`` MCP tool (which needs the
    draft's id and sections to show a diff before it writes). Audited like every definition read."""
    agent = resolve_agent(store, ctx.org_id, key)
    draft = resolve_draft(store, ctx.org_id, agent)
    audit_definition_read(store, ctx, agent, "rascunho", draft.id)
    return _version_detail(store, gate, ctx.org_id, draft)


@router.post("/agents/{key}/draft", response_model=VersionDetailOut, status_code=status.HTTP_201_CREATED, include_in_schema=False)
def create_draft(
    key: str,
    payload: DraftCreateRequest,
    ctx: AuthContext = Depends(require_platform_content_admin),
    store=Depends(get_studio_definition_store_dep),
    gate=Depends(get_eval_gate_dep),
    catalog=Depends(get_knowledge_catalog_dep),
) -> VersionDetailOut:
    agent = resolve_agent(store, ctx.org_id, key)
    if payload.from_version_id is not None:
        source_id: UUID | None = resolve_version(store, ctx.org_id, agent, payload.from_version_id).id
    else:
        active = store.get_active_version(ctx.org_id, agent.id)
        source_id = active.id if active else None
    with store_errors():
        draft = store.create_draft(ctx.org_id, agent.id, source_id, ctx.user_id)
    draft, _ = _refresh_draft_hash(store, catalog, ctx.org_id, agent, draft.id)
    return _version_detail(store, gate, ctx.org_id, draft)


@router.delete("/agents/{key}/draft", status_code=status.HTTP_204_NO_CONTENT, include_in_schema=False)
def discard_draft(
    key: str,
    ctx: AuthContext = Depends(require_platform_content_admin),
    store=Depends(get_studio_definition_store_dep),
) -> Response:
    agent = resolve_agent(store, ctx.org_id, key)
    draft = resolve_draft(store, ctx.org_id, agent)
    with store_errors():
        store.discard_draft(ctx.org_id, draft.id, actor=ctx.user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/agents/{key}/draft", response_model=VersionDetailOut, include_in_schema=False)
def update_draft(
    key: str,
    payload: DraftUpdateRequest,
    ctx: AuthContext = Depends(require_platform_content_admin),
    store=Depends(get_studio_definition_store_dep),
    gate=Depends(get_eval_gate_dep),
    catalog=Depends(get_knowledge_catalog_dep),
) -> VersionDetailOut:
    agent = resolve_agent(store, ctx.org_id, key)
    draft = resolve_draft(store, ctx.org_id, agent)
    fields = patch_fields(payload, nullable=frozenset({"notas"}))
    with store_errors():
        draft = store.update_draft(ctx.org_id, draft.id, fields)
    draft, _ = _refresh_draft_hash(store, catalog, ctx.org_id, agent, draft.id)
    return _version_detail(store, gate, ctx.org_id, draft)


@router.put("/agents/{key}/draft/sections", response_model=VersionDetailOut, include_in_schema=False)
def replace_draft_sections(
    key: str,
    payload: SectionsReplaceRequest,
    ctx: AuthContext = Depends(require_platform_content_admin),
    store=Depends(get_studio_definition_store_dep),
    gate=Depends(get_eval_gate_dep),
    catalog=Depends(get_knowledge_catalog_dep),
) -> VersionDetailOut:
    agent = resolve_agent(store, ctx.org_id, key)
    draft = resolve_draft(store, ctx.org_id, agent)
    chaves = [s.chave for s in payload.secoes]
    if len(set(chaves)) != len(chaves):
        raise http_error(422, "duplicate_chave", "Chaves de seção repetidas.")
    secoes = [
        SectionInput(
            id=s.id, chave=s.chave, titulo=s.titulo, ordem=s.ordem, conteudo=s.conteudo, ativo=s.ativo,
            regras=tuple(s.regras),
        )
        for s in payload.secoes
    ]
    antes = [s.chave for s in store.list_sections(ctx.org_id, draft.id)] if ctx.caller_kind == "product" else []
    with store_errors():
        store.replace_sections(ctx.org_id, draft.id, secoes)
    if ctx.caller_kind == "product":
        # The noctus.agents.content MCP path (studio:content-write): audited like every other content write.
        store.append_audit(
            agent.org_id, agent.id, actor_id(ctx), "conteudo_editado_mcp",
            {"kind": "secao", "version_id": str(draft.id), "chaves": antes},
            {"kind": "secao", "version_id": str(draft.id), "chaves": chaves},
        )
    draft, _ = _refresh_draft_hash(store, catalog, ctx.org_id, agent, draft.id)
    return _version_detail(store, gate, ctx.org_id, draft)


# ── skills + files ──────────────────────────────────────────────────────────


@router.post("/agents/{key}/draft/skills", response_model=SkillOut, status_code=status.HTTP_201_CREATED, include_in_schema=False)
def create_draft_skill(
    key: str,
    payload: SkillCreateRequest,
    ctx: AuthContext = Depends(require_platform_content_admin),
    store=Depends(get_studio_definition_store_dep),
    catalog=Depends(get_knowledge_catalog_dep),
) -> SkillOut:
    agent = resolve_agent(store, ctx.org_id, key)
    draft = resolve_draft(store, ctx.org_id, agent)
    with store_errors():
        skill = store.create_skill(
            ctx.org_id, draft.id, nome=payload.nome, descricao=payload.descricao,
            corpo=payload.corpo, ordem=payload.ordem, ativo=payload.ativo,
        )
    _refresh_draft_hash(store, catalog, ctx.org_id, agent, draft.id)
    return _skill_out(skill, [])


@router.patch("/agents/{key}/draft/skills/{skill_id}", response_model=SkillOut, include_in_schema=False)
def update_draft_skill(
    key: str,
    skill_id: UUID,
    payload: SkillUpdateRequest,
    ctx: AuthContext = Depends(require_platform_content_admin),
    store=Depends(get_studio_definition_store_dep),
    catalog=Depends(get_knowledge_catalog_dep),
) -> SkillOut:
    agent = resolve_agent(store, ctx.org_id, key)
    _, draft = _resolve_draft_skill(store, ctx.org_id, agent, skill_id)
    fields = patch_fields(payload, nullable=frozenset({"expected_hash"}))
    expected_hash = fields.pop("expected_hash", None)
    with store_errors():
        skill = store.update_skill(ctx.org_id, skill_id, fields, expected_hash=expected_hash)
    _refresh_draft_hash(store, catalog, ctx.org_id, agent, draft.id)
    files = [f for f in store.list_version_skill_files(ctx.org_id, draft.id) if f.skill_id == skill.id]
    return _skill_out(skill, files)


@router.delete("/agents/{key}/draft/skills/{skill_id}", status_code=status.HTTP_204_NO_CONTENT, include_in_schema=False)
def delete_draft_skill(
    key: str,
    skill_id: UUID,
    ctx: AuthContext = Depends(require_platform_content_admin),
    store=Depends(get_studio_definition_store_dep),
    catalog=Depends(get_knowledge_catalog_dep),
) -> Response:
    agent = resolve_agent(store, ctx.org_id, key)
    _, draft = _resolve_draft_skill(store, ctx.org_id, agent, skill_id)
    with store_errors():
        store.delete_skill(ctx.org_id, skill_id)
    _refresh_draft_hash(store, catalog, ctx.org_id, agent, draft.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/agents/{key}/draft/skills/{skill_id}/files", response_model=SkillFileMetaOut, include_in_schema=False)
def upsert_draft_skill_file(
    key: str,
    skill_id: UUID,
    payload: SkillFileUpsertRequest,
    ctx: AuthContext = Depends(require_platform_content_admin),
    store=Depends(get_studio_definition_store_dep),
    catalog=Depends(get_knowledge_catalog_dep),
) -> SkillFileMetaOut:
    agent = resolve_agent(store, ctx.org_id, key)
    _, draft = _resolve_draft_skill(store, ctx.org_id, agent, skill_id)
    with store_errors():
        f = store.upsert_skill_file(
            ctx.org_id, skill_id, caminho=payload.caminho, titulo=payload.titulo, conteudo=payload.conteudo,
        )
    _refresh_draft_hash(store, catalog, ctx.org_id, agent, draft.id)
    return SkillFileMetaOut(id=f.id, caminho=f.caminho, titulo=f.titulo, chars=len(f.conteudo))


@router.put(
    "/agents/{key}/draft/skills/{skill_id}/files/batch", response_model=SkillFilesBatchResultOut,
include_in_schema=False)
def upsert_draft_skill_files_batch(
    key: str,
    skill_id: UUID,
    payload: SkillFilesBatchUpsertRequest,
    ctx: AuthContext = Depends(require_platform_content_admin),
    store=Depends(get_studio_definition_store_dep),
    catalog=Depends(get_knowledge_catalog_dep),
) -> SkillFilesBatchResultOut:
    """Bulk upsert of a skill's reference files (contract §D1 batch,
    UI-KB-BACKEND) — same draft-only / immutability / caminho-caps rules as
    the single-file route (``_resolve_draft_skill`` 409s the WHOLE call if
    the version isn't a draft, same as today). PER-ITEM results: one bad
    file never sinks the call."""
    agent = resolve_agent(store, ctx.org_id, key)
    _, draft = _resolve_draft_skill(store, ctx.org_id, agent, skill_id)
    existing_caminhos = {
        f.caminho for f in store.list_version_skill_files(ctx.org_id, draft.id) if f.skill_id == skill_id
    }
    resultados: list[SkillFileBatchItemResultOut] = []
    criados = atualizados = erros = 0
    for item in payload.arquivos:
        was_existing = item.caminho in existing_caminhos
        try:
            f = store.upsert_skill_file(
                ctx.org_id, skill_id, caminho=item.caminho, titulo=item.titulo, conteudo=item.conteudo,
            )
        except (ValueError, StudioConflict) as exc:
            erros += 1
            resultados.append(SkillFileBatchItemResultOut(caminho=item.caminho, status="erro", erro=erro_de_item(exc)))
            continue
        existing_caminhos.add(item.caminho)
        if was_existing:
            atualizados += 1
            status_pt = "atualizado"
        else:
            criados += 1
            status_pt = "criado"
        resultados.append(SkillFileBatchItemResultOut(
            caminho=item.caminho, status=status_pt, id=f.id, titulo=f.titulo, chars=len(f.conteudo),
        ))
    _refresh_draft_hash(store, catalog, ctx.org_id, agent, draft.id)
    return SkillFilesBatchResultOut(
        resultados=resultados, criados=criados, atualizados=atualizados, erros=erros,
    )


@router.get("/agents/{key}/skills/{skill_id}/files/{file_id}", response_model=SkillFileOut, include_in_schema=False)
def get_skill_file(
    key: str,
    skill_id: UUID,
    file_id: UUID,
    ctx: AuthContext = Depends(require_platform_admin),
    store=Depends(get_studio_definition_store_dep),
) -> SkillFileOut:
    agent = resolve_agent(store, ctx.org_id, key)
    _, skill_version = _resolve_skill(store, ctx.org_id, agent, skill_id)
    audit_definition_read(store, ctx, agent, "arquivo_skill", skill_version.id)
    f = _resolve_file(store, ctx.org_id, skill_id, file_id)
    return SkillFileOut(id=f.id, caminho=f.caminho, titulo=f.titulo, conteudo=f.conteudo)


@router.delete("/agents/{key}/draft/skills/{skill_id}/files/{file_id}", status_code=status.HTTP_204_NO_CONTENT, include_in_schema=False)
def delete_draft_skill_file(
    key: str,
    skill_id: UUID,
    file_id: UUID,
    ctx: AuthContext = Depends(require_platform_content_admin),
    store=Depends(get_studio_definition_store_dep),
    catalog=Depends(get_knowledge_catalog_dep),
) -> Response:
    agent = resolve_agent(store, ctx.org_id, key)
    _, draft = _resolve_draft_skill(store, ctx.org_id, agent, skill_id)
    _resolve_file(store, ctx.org_id, skill_id, file_id)
    with store_errors():
        store.delete_skill_file(ctx.org_id, file_id)
    _refresh_draft_hash(store, catalog, ctx.org_id, agent, draft.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── compile / diff ──────────────────────────────────────────────────────────


@router.get("/agents/{key}/versions/{version_id}/compiled", response_model=CompiledOut, include_in_schema=False)
def get_compiled(
    key: str,
    version_id: UUID,
    client_id: UUID | None = Query(default=None),
    ctx: AuthContext = Depends(require_platform_admin),
    store=Depends(get_studio_definition_store_dep),
    catalog=Depends(get_knowledge_catalog_dep),
) -> CompiledOut:
    agent = resolve_agent(store, ctx.org_id, key)
    version = resolve_version(store, ctx.org_id, agent, version_id)
    audit_definition_read(store, ctx, agent, "compilado", version.id)
    client = None
    if client_id is not None:
        client = client_bundle(store, ctx.org_id, resolve_client(store, ctx.org_id, agent, client_id))
    # L7: a read never writes — the stored hash moves only on admin writes
    # and at publish.
    compiled = compile_version(store, catalog, ctx.org_id, agent, version, client)
    return _compiled_out(compiled, version.id, client_id)


def _diff_states(a: dict[str, tuple], b: dict[str, tuple]) -> list[tuple[str, str]]:
    out = []
    for k in sorted(set(a) | set(b)):
        if k not in a:
            out.append((k, "nova"))
        elif k not in b:
            out.append((k, "removida"))
        else:
            out.append((k, "igual" if a[k] == b[k] else "alterada"))
    return out


@router.get("/agents/{key}/versions/{version_a}/diff/{version_b}", response_model=DiffOut, include_in_schema=False)
def diff_versions(
    key: str,
    version_a: UUID,
    version_b: UUID,
    ctx: AuthContext = Depends(require_platform_admin),
    store=Depends(get_studio_definition_store_dep),
    catalog=Depends(get_knowledge_catalog_dep),
) -> DiffOut:
    agent = resolve_agent(store, ctx.org_id, key)
    va = resolve_version(store, ctx.org_id, agent, version_a)
    vb = resolve_version(store, ctx.org_id, agent, version_b)
    audit_definition_read(store, ctx, agent, "diff", va.id)
    ca = compile_version(store, catalog, ctx.org_id, agent, va)
    cb = compile_version(store, catalog, ctx.org_id, agent, vb)

    def sections(v):
        return {s.chave: (s.titulo, s.ordem, s.conteudo, s.ativo) for s in store.list_sections(ctx.org_id, v.id)}

    def skills(v):
        files: dict[UUID, list[tuple]] = {}
        for f in store.list_version_skill_files(ctx.org_id, v.id):
            files.setdefault(f.skill_id, []).append((f.caminho, f.titulo, f.conteudo))
        return {
            s.nome: (s.descricao, s.corpo, s.ordem, s.ativo, tuple(sorted(files.get(s.id, []))))
            for s in store.list_skills(ctx.org_id, v.id)
        }

    return DiffOut(
        a=DiffSideOut(version_id=va.id, hash=ca.hash),
        b=DiffSideOut(version_id=vb.id, hash=cb.hash),
        texto_a=ca.texto,
        texto_b=cb.texto,
        secoes=[DiffSectionOut(chave=k, estado=e) for k, e in _diff_states(sections(va), sections(vb))],
        skills=[DiffSkillOut(nome=k, estado=e) for k, e in _diff_states(skills(va), skills(vb))],
        configuracoes=[
            DiffConfigOut(campo=f, a=getattr(va, f), b=getattr(vb, f))
            for f in _CONFIG_FIELDS
            if getattr(va, f) != getattr(vb, f)
        ],
    )


# ── publish ─────────────────────────────────────────────────────────────────


@router.post("/agents/{key}/draft/publish", response_model=VersionDetailOut, include_in_schema=False)
def publish_draft(
    key: str,
    payload: PublishRequest,
    ctx: AuthContext = Depends(require_publish_write),
    store=Depends(get_studio_definition_store_dep),
    gate=Depends(get_eval_gate_dep),
    catalog=Depends(get_knowledge_catalog_dep),
    conformidade=Depends(get_conformidade_store_dep),
    padroes=Depends(get_padrao_store_dep),
    geracoes=Depends(get_geracao_store_dep),
    skills=Depends(get_skills_store_dep),
    evals=Depends(get_eval_store_dep),
    controles=Depends(get_prontidao_controles_dep),
    consolidacao=Depends(get_consolidacao_store_dep),
) -> VersionDetailOut:
    """§D1 publish + §J2.1 gate: pass ⇔ a run exists ∧ status='concluida' ∧
    completa (covered every active case, H1) ∧ total >= 1 ∧
    run.compiled_hash == the draft's CURRENT hash ∧ score >= limiar. A
    blocking compile warning refuses publish with no override possible.

    The DB function re-checks all of it (plus "the agent still has an
    active case"), refuses ``draft_changed`` if the draft moved since the
    hash below was stamped (M1), and stores the proof-of-use prompt in the
    same transaction as the flip.

    Every refusal below carries ``prontidao`` -- the same item list ``GET .../prontidao`` returns -- so the author sees
    EVERYTHING still owed, not only the first refusal. The decisions are the readiness module's own predicates
    (``recusa_de_compilacao`` / ``juiz_aprovado`` / ``decidir_portao``): one definition, two readers."""

    def prontidao(compiled_: Any = None) -> list[dict[str, Any]] | None:
        try:
            return [i.to_dict() for i in avaliar_prontidao(
                store=store, catalog=catalog, org_id=ctx.org_id, agent=agent, draft=draft, gate=gate, padroes=padroes,
                skills=skills, geracoes=geracoes, evals=evals, controles=controles, compiled=compiled_,
                conformidade=conformidade, consolidacao=consolidacao).itens]
        except Exception:  # noqa: BLE001 -- the refusal itself must still be delivered
            logger.exception("agents.studio.publish.prontidao_indisponivel agent_id=%s", agent.id)
            return None

    agent = resolve_agent(store, ctx.org_id, key)
    require_user_or_dev_advisor(ctx, agent)
    if ctx.caller_kind == "product" and payload.override_reason is not None:
        raise http_error(403, "override_requires_user", "O override do portão de avaliação é exclusivo de usuários.")
    draft = resolve_draft(store, ctx.org_id, agent)
    if payload.notas is not None:
        with store_errors():
            draft = store.update_draft(ctx.org_id, draft.id, {"notas": payload.notas})

    # Publish pins the qualification standard (an unpinned draft gets the newest published version) BEFORE the
    # hash is judged: the pin is part of what the hash covers.
    from app.routers.studio_padrao_router import estampar_padrao_no_rascunho

    try:
        draft = estampar_padrao_no_rascunho(store, padroes, ctx.org_id, agent, draft)
    except HTTPException as exc:
        if isinstance(exc.detail, dict) and exc.detail.get("code") == "qualificacao_indisponivel":
            raise http_error(409, "qualificacao_indisponivel", exc.detail["detail"], prontidao=prontidao()) from exc
        raise
    draft, compiled = _refresh_draft_hash(store, catalog, ctx.org_id, agent, draft.id, strict=True)
    recusa = recusa_de_compilacao(compiled)
    if recusa is not None:
        # Missing content (a required text, a tool/decision/spec hole) is its own code: the author
        # fills a row; nothing in code ever substitutes a default.
        incompleto = recusa == "conteudo_incompleto"
        raise http_error(
            409, recusa,
            "O conteúdo do agente está incompleto." if incompleto else "O prompt compilado tem avisos bloqueantes.",
            avisos=[w.to_dict() for w in compiled.avisos], prontidao=prontidao(compiled),
        )

    # Org-spec safety (Julia-line E2), block mode only: an invalid stored org-spec value is a readiness `bloqueante`
    # (`spec_org_invalida`) and therefore a publish refusal -- one definition, two readers. Report mode never gets here.
    itens_prontidao = prontidao(compiled)
    if itens_prontidao and any(
        i["codigo"] == "spec_org_invalida" and i["severidade"] == "bloqueante" for i in itens_prontidao
    ):
        raise http_error(
            409, "compile_blocked", "Há especificações da organização inválidas (SPEC_VALIDATION_MODE=block).",
            prontidao=itens_prontidao,
        )
    if falta_numero_fallback(agent):  # direct, not via the items: a failed readiness read must not let it through
        raise http_error(
            409, "numero_fallback_ausente",
            "Não há número de atendimento para a passagem a uma pessoa (Configurações do agente).",
            prontidao=itens_prontidao,
        )
    if itens_prontidao and any(
        i["codigo"] == "catalogo_ausente" and i["severidade"] == "bloqueante" for i in itens_prontidao
    ):
        raise http_error(
            409, "catalogo_ausente",
            "A ferramenta 'oferecer_opcoes' está ativa e o padrão de qualificação não indica o catálogo de opções.",
            prontidao=itens_prontidao,
        )
    # 073 chain gate, direct (like the fallback number): a failed readiness read must not let a child past an unvalidated base
    if agent.pai_agent_id is not None:
        nao_validadas = base_nao_validada(coletar_camadas_base(
            store=store, catalog=catalog, consolidacao=consolidacao, org_id=ctx.org_id, agent=agent, draft=draft))
        if nao_validadas:
            raise http_error(
                409, "base_nao_validada",
                "A base deste agente não está validada: consolide os casos críticos da base antes de publicar.",
                bases=[c.to_dict() for c in nao_validadas], prontidao=itens_prontidao,
            )
    if itens_prontidao and any(i["codigo"] == "regras_seguranca_sem_parametros" for i in itens_prontidao):
        raise http_error(
            409, "compile_blocked", "As regras de segurança desta instância estão sem parâmetros (migração 063).",
            prontidao=itens_prontidao,
        )

    # Julia v2 A-EVAL (CONTRACT 3.5 E4): the mechanism suite is a HARD gate with NO override. It runs ahead of
    # the judge suite so a green judge run (or an owner override) can never stand in for it.
    mecanismo = gate.mecanismo_requisito(ctx.org_id, agent.id, draft.id)
    portao = decidir_portao(mecanismo, compiled.hash)
    if not portao.liberado:
        raise http_error(
            409, "mecanismo_reprovado",
            "Publicar exige a suíte de mecanismo aprovada (100% pass^k, modelo real) para o prompt atual.",
            motivo=portao.codigo, hash_atual=compiled.hash, prontidao=prontidao(compiled),
        )
    # The judge suite is advisory for an agent under the mechanism gate unless it opted in to blocking.
    comportamento_consultivo = mecanismo.exigido and not mecanismo.comportamento_bloqueia

    run = gate.latest_concluded_run(ctx.org_id, draft.id)
    if juiz_aprovado(run, compiled.hash, agent.publicacao_limiar):
        eval_run_id, override_reason = run.id, None
    elif comportamento_consultivo:
        # Audited as `publicado_override` with the mechanism run as the reason (the DB function's only
        # no-judge-run path); the reason is system-written, never caller-supplied.
        eval_run_id, override_reason = None, f"portao_mecanismo_aprovado run={portao.run_id}; suite comportamento consultiva"
    elif payload.override_reason is not None:
        eval_run_id, override_reason = None, payload.override_reason
    else:
        raise http_error(
            409, "eval_required",
            "Publicar exige uma avaliação concluída do prompt atual com nota acima do limiar.",
            hash_atual=compiled.hash,
            ultima_execucao=(
                {
                    "id": str(run.id), "score": run.score, "limiar": run.limiar,
                    "compiled_hash": run.compiled_hash, "completa": run.completa,
                }
                if run is not None
                else None
            ),
            prontidao=prontidao(compiled),
        )

    if agent.espelhado:
        # Agent Packages §M2: a DB-source dev agent's git mirror is rendered from THIS draft and stored on it before
        # the flip (the 017 tree guard only lets a draft's tree be written). No mirror => no publish.
        from app.studio.espelho import EspelhoErro, renderizar_espelho

        try:
            espelho = renderizar_espelho(
                store=store, skills=skills, catalog=catalog, org_id=ctx.org_id, agent=agent, draft=draft,
                compiled_text=compiled.texto,
            )
            with store_errors():
                store.update_draft(ctx.org_id, draft.id, {"versao_semver": espelho.versao_semver})
                store.set_package_tree(ctx.org_id, agent.id, draft.id, espelho.files)
        except EspelhoErro as exc:
            raise http_error(409, "espelho_falhou", f"O espelho Claude Code não pôde ser gerado: {exc}",
                             prontidao=prontidao(compiled)) from exc
    pai_versao_id = _pin_do_pai(store, catalog, ctx.org_id, agent, draft, compiled, prontidao)
    with store_errors():
        # Proof of use (§A7) is stored INSIDE the publish transaction.
        published = store.publish_version(
            ctx.org_id, draft.id, actor_id(ctx), eval_run_id, override_reason,
            expected_hash=compiled.hash, texto=compiled.texto, manifest=compiled.manifest_json(),
            pai_versao_id=pai_versao_id,
        )
    # The prompt-leak fingerprint (hashed shingles; Julia v2 IP protection) is computed AT PUBLISH so a turn only
    # reads it. A failure here is logged, never undoes the publish: the turn computes it on first use.
    try:
        garantir_impressao(conformidade, ctx.org_id, published.id, compiled)
    except Exception:  # noqa: BLE001
        logger.exception("agents.studio.publish.impressao_nao_salva version_id=%s", published.id)
    # The version's honeytoken is generated at publish too (DB-only; nothing in this API ever reads it back).
    try:
        get_marcador_store(settings).garantir(ctx.org_id, published.id)
    except Exception:  # noqa: BLE001 -- the first turn of the version creates it; the failure must be seen
        logger.exception("agents.studio.publish.marcador_nao_gerado version_id=%s", published.id)
    # S3a learning: the FIRST publish after an AI generation stores generated-vs-published per area. Never undoes
    # the publish.
    try:
        from app.studio.geracao import Dependencias, registrar_aprendizado

        registrar_aprendizado(
            Dependencias(studio=store, geracoes=geracoes, skills=skills, catalog=catalog, chat=None, evals=evals), agent, published)
    except Exception:  # noqa: BLE001 -- learning is advisory; the failure must be seen
        logger.exception("agents.studio.publish.aprendizado_nao_registrado version_id=%s", published.id)
    return _version_detail(store, gate, ctx.org_id, published)


# ── mechanism suite (Julia v2 A-EVAL) ───────────────────────────────────────


class MecanismoFalhaOut(BaseModel):
    """A failed assert as a CODE (assert name + tool/criterion key) -- never reply text."""

    assert_: str = Field(alias="assert")
    codigo: str

    model_config = {"populate_by_name": True}


class MecanismoExecucaoOut(BaseModel):
    indice: int
    status: str
    falhas: list[MecanismoFalhaOut]
    #: per turn {lead|retomada, bolhas, ferramentas[{nome,args,ok}]}; empty for rows from before migration 084
    transcricao: list[dict] = []


class MecanismoCasoOut(BaseModel):
    slug: str
    passou: bool
    taxa: float
    execucoes: list[MecanismoExecucaoOut]


class MecanismoRunIniciadaOut(BaseModel):
    """202 body: the run is booked (``executando``) and executes in the background; poll ``GET .../mecanismo-runs/{id}``."""

    run_id: UUID
    compiled_hash: str
    driver: str
    status: str


class MecanismoRunOut(BaseModel):
    """The state of one run: counters while it executes, the per-case codes once it is ``concluida``."""

    run_id: UUID
    version_id: UUID
    compiled_hash: str
    driver: str
    #: ``executando`` | ``concluida`` | ``falhou`` | ``cancelada``
    status: str
    aprovado: bool
    completo: bool
    orcamento_excedido: bool
    custo_usd: float | None = None
    total_casos: int
    casos_aprovados: int
    #: A FIXED text on ``falhou`` (never the exception).
    erro: str | None = None
    casos: list[MecanismoCasoOut] = Field(default_factory=list)


@router.post(
    "/agents/{key}/draft/mecanismo-runs", response_model=MecanismoRunIniciadaOut, status_code=status.HTTP_202_ACCEPTED,
include_in_schema=False)
async def run_mecanismo_suite(
    key: str,
    request: Request,
    ctx: AuthContext = Depends(require_evals_run_access),
    store=Depends(get_studio_definition_store_dep),
    mecanismo=Depends(get_mecanismo_store_dep),
    catalog=Depends(get_knowledge_catalog_dep),
    driver=Depends(get_eval_turn_driver),
    ceiling=Depends(get_spend_ceiling_dep),
    consolidacao=Depends(get_consolidacao_store_dep),
    loops=Depends(get_loop_service_dep),
    rodar_tudo: bool = Query(False),
    loop_id: UUID | None = Query(None, description="Eval-loop gate: book this run as the next round of the loop (G1-G7)."),
) -> MecanismoRunIniciadaOut:
    """Book a mechanism-suite run against the CURRENT draft hash and execute it IN THE BACKGROUND (a live suite takes
    minutes: it must not hold an HTTP request). Platform admin only (the suite is platform IP). 202 + the run id;
    ``GET .../mecanismo-runs/{id}`` reports ``executando`` / ``concluida`` / ``falhou``. Several runs of the same
    version may execute at once (071): each has its own id, results and cost cap. The driver comes from ``get_eval_turn_driver`` (409
    ``driver_indisponivel`` when none is configured); the cost cap comes from settings. Replies carry codes only."""
    agent = resolve_agent(store, ctx.org_id, key)
    require_user_or_dev_advisor(ctx, agent, evals_token_ok=True)
    draft = resolve_draft(store, ctx.org_id, agent)
    draft, compiled = _refresh_draft_hash(store, catalog, ctx.org_id, agent, draft.id, strict=True)
    if compiled.bloqueado:
        raise http_error(409, "compile_blocked", "O prompt compilado tem avisos bloqueantes.")
    if driver is None:
        raise http_error(409, "driver_indisponivel", "O executor de turnos da avaliação não está configurado.")
    if hasattr(driver, "definir_agente"):
        driver.definir_agente(agent.key)
    limite = settings.studio_mecanismo_run_budget_usd
    if loop_id is not None:
        # G6/G7: refuses a closed loop, an open round, a spent budget and an unchanged hash with nothing to consolidate;
        # the run's cost cap is clamped to what the loop budget has left.
        limite = (await anyio.to_thread.run_sync(lambda: loops.admitir(
            ctx.org_id, agent.id, loop_id, suite="mecanismo", compiled_hash=compiled.hash, limite_usd=limite,
            ler_resumo=lambda rid: resumo_mecanismo(mecanismo, ctx.org_id, agent.id, rid)))).limite_usd
    try:
        with store_errors():
            run_id, casos = iniciar_suite_mecanismo(
                mecanismo, driver, org_id=ctx.org_id, agent_id=agent.id, version_id=draft.id,
                compiled_hash=compiled.hash, started_by=actor_id(ctx), limite_usd=limite,
                consolidacao=consolidacao, partes=dict(compiled.partes) or None, rodar_tudo=rodar_tudo)
    except TodosConsolidados as exc:
        raise http_error(
            409, "todos_consolidados",
            "Todos os casos de mecanismo estão consolidados e não foram afetados por mudanças. Use rodar_tudo para rodar mesmo assim.",
        ) from exc
    except SuiteVazia as exc:
        raise http_error(409, "sem_casos_mecanismo", "O agente não tem casos de mecanismo ativos.") from exc
    except DriverSemTipo as exc:
        raise http_error(409, "driver_indisponivel", "O executor de turnos da avaliação não está configurado.") from exc

    def _fechar_loop() -> None:
        if loop_id is not None:
            loops.fechar_sem_falhar(
                ctx.org_id, lambda: resumo_mecanismo(mecanismo, ctx.org_id, agent.id, run_id), run_id=run_id, run_tipo="mecanismo")

    if loop_id is not None:
        try:
            await anyio.to_thread.run_sync(lambda: loops.abrir(
                ctx.org_id, loop_id, run_id=run_id, run_tipo="mecanismo", compiled_hash=compiled.hash,
                partes=dict(compiled.partes) or None))
        except Exception:
            mecanismo.fail_run(ctx.org_id, run_id, erro="loop_indisponivel")
            raise

    if ctx.caller_kind == "product":
        # The shared daily ceiling (seed, same key as the eval runs): over it / unverifiable -> the booked run fails.
        try:
            await anyio.to_thread.run_sync(lambda: reserve_run(
                ceiling, org_id=ctx.org_id, kind=KIND_MECANISMO_RUN, run_id=run_id, amount_usd=limite))
        except Exception:
            mecanismo.fail_run(ctx.org_id, run_id, erro="Limite diário de custo atingido.")
            await anyio.to_thread.run_sync(_fechar_loop)
            raise

    async def _executar() -> None:
        try:
            resultado = await concluir_suite_mecanismo(
                mecanismo, driver, casos, org_id=ctx.org_id, run_id=run_id, limite_usd=limite, consolidacao=consolidacao,
                agent_id=agent.id, compiled_hash=compiled.hash)
            await anyio.to_thread.run_sync(_fechar_loop)  # G3/G4/G5/G7: close the round, stop + notify when a rule fires
            if resultado.erro_de_harness is None:  # a crashed/harness-failed run keeps its cap counting
                settle_run(ceiling, kind=KIND_MECANISMO_RUN, run_id=run_id, actual_usd=float(resultado.custo_usd or 0.0))
        except Exception:  # noqa: BLE001 -- the run is already marked `falhou` (fixed text); nothing else to do
            logger.exception("agents.studio.mecanismo_run_falhou run_id=%s", run_id)
            await anyio.to_thread.run_sync(_fechar_loop)  # a crashed run closes its round as a neutral (no score) one

    from app.routers.conversations_router import _track_background_task  # lazy: that router imports this one

    _track_background_task(request.app.state, asyncio.create_task(_executar()))
    return MecanismoRunIniciadaOut(run_id=run_id, compiled_hash=compiled.hash, driver=driver.tipo, status="executando")


@router.get("/agents/{key}/mecanismo-runs/{run_id}", response_model=MecanismoRunOut, response_model_by_alias=True, include_in_schema=False)
def get_mecanismo_run(
    key: str,
    run_id: UUID,
    ctx: AuthContext = Depends(require_evals_run_access),
    store=Depends(get_studio_definition_store_dep),
    mecanismo=Depends(get_mecanismo_store_dep),
) -> MecanismoRunOut:
    agent = resolve_agent(store, ctx.org_id, key)
    require_user_or_dev_advisor(ctx, agent, evals_token_ok=True)
    run = mecanismo.get_run(ctx.org_id, run_id)
    if run is None or str(run["agent_id"]) != str(agent.id):
        raise http_error(404, "run_not_found", "Execução não encontrada.")
    audit_definition_read(store, ctx, agent, "mecanismo_run", UUID(str(run["version_id"])))
    casos: list[MecanismoCasoOut] = []
    if run["status"] == "concluida":
        slugs = {str(c.id): c.slug for c in mecanismo.list_active_cases(ctx.org_id, agent.id)}
        por_caso: dict[str, list[dict]] = {}
        for e in mecanismo.list_execucoes(ctx.org_id, run_id):
            por_caso.setdefault(str(e["case_id"]), []).append(e)
        for cid, execs in por_caso.items():
            execs.sort(key=lambda e: e["indice"])
            aprov = sum(1 for e in execs if e["status"] == "aprovado")
            casos.append(MecanismoCasoOut(
                slug=slugs.get(cid, cid[:8]), passou=aprov == len(execs), taxa=round(aprov / len(execs), 3),
                execucoes=[
                    MecanismoExecucaoOut(
                        indice=e["indice"], status=e["status"], transcricao=e.get("transcricao") or [],
                        falhas=[MecanismoFalhaOut(assert_=f["assert"], codigo=f["codigo"]) for f in (e.get("falhas") or [])])
                    for e in execs
                ]))
    custo = run.get("custo_usd")
    return MecanismoRunOut(
        run_id=run_id, version_id=UUID(str(run["version_id"])), compiled_hash=run["compiled_hash"],
        driver=run["driver"], status=run["status"], aprovado=bool(run["aprovado"]), completo=bool(run["completa"]),
        orcamento_excedido=bool(run["orcamento_excedido"]), custo_usd=float(custo) if custo is not None else None,
        total_casos=int(run["total_casos"] or 0), casos_aprovados=int(run["casos_aprovados"] or 0),
        erro=run.get("erro"), casos=casos)


# ── prompts by hash ─────────────────────────────────────────────────────────


@router.get("/prompts/{prompt_hash}", response_model=PromptByHashOut, include_in_schema=False)
def get_prompt_by_hash(
    prompt_hash: str,
    ctx: AuthContext = Depends(require_platform_admin),
    store=Depends(get_studio_definition_store_dep),
) -> PromptByHashOut:
    try:
        rec = store.get_compiled_prompt(ctx.org_id, prompt_hash)
        version = store.get_version(ctx.org_id, rec.version_id)
        owner = store.get_agent_by_id(version.agent_id)
    except NotFound as exc:
        raise http_error(404, "prompt_not_found", "Prompt não encontrado.") from exc
    audit_definition_read(store, ctx, owner, "prompt_por_hash", version.id)
    return PromptByHashOut(
        hash=rec.hash, texto=rec.texto, manifest=rec.manifest, version_id=rec.version_id,
        client_id=rec.client_id, created_at=rec.created_at,
    )


__all__ = [
    "router",
    "actor_id",
    "require_user_or_dev_advisor",
    "get_compiled_hash_provider",
    "get_eval_gate_dep",
    "get_knowledge_catalog_dep",
    "get_studio_definition_store_dep",
]

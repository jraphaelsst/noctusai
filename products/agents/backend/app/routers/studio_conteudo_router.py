"""``/api/studio`` — the Julia v2 CONTENT API (CONTRACT §2.4, §2.6): system texts, tool descriptions,
decisions and org-spec declarations of an agent version, the per-org spec values, the compiled view
per org, and the platform-level pieces (platform texts, creating a platform definition).

Who may do what (Q2 — "the SDR is one thing in the general agents app, specified to each org's context"):

* **Definition content** (``PUT .../draft/{textos|ferramentas|decisoes|specs}``) is DRAFT-ONLY and is
  edited where the definition lives: the platform org for a platform-defined agent, the owning org for
  an ``org``-scope agent. An org's INSTANCE has no draft → 409 ``definicao_na_plataforma``.
  Auth ``require_content_write``: an org owner/admin, or a product token with the
  ``studio:content-write`` scope (the ``noctus.agents.content`` MCP path — such writes are audited as
  ``conteudo_editado_mcp``, actor = the token row).
* **Org specs** (``GET/PUT .../specs``, ``GET .../compilado``) are the ORG's: an org owner/admin edits
  its own values for the keys the definition declares; every member reads the compiled view with those
  values in place.
* **Platform** (``/plataforma/*``): ``require_platform_admin`` (``noctus_users.role == 'admin'``).

Replace-set writes re-stamp the draft's ``compiled_hash`` (every content table is hash-covered) with the
same compare-and-set the section writes use.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from app.dependencies import (
    ADMIN_ROLES,
    CONTENT_TOKEN_ISSUER,
    SCOPE_STUDIO_CONTENT_WRITE,
    get_auth_context,
    get_core_client,
    get_product_token_admin_dep,
    get_token_audit_dep,
    require_admin,
    require_platform_admin,
    require_platform_content_admin,
)
from app.routers.studio_agents_router import (
    _refresh_draft_hash,
    actor_id,
    get_knowledge_catalog_dep,
    get_studio_definition_store_dep,
    audit_definition_read,
    http_error,
    resolve_agent,
    resolve_draft,
    resolve_version,
    store_errors,
)
from app.channels.token_audit import TokenAudit
from app.schemas.studio_conteudo import (
    ContentTokenCreateRequest,
    ContentTokenOut,
    CompiladoOrgOut,
    ConteudoPayloadOut,
    DecisaoOut,
    DecisoesOut,
    DecisoesReplaceRequest,
    FerramentaOut,
    FerramentasOut,
    FerramentasReplaceRequest,
    OrgSpecsOut,
    OrgStatusOut,
    OrgSpecsUpdateRequest,
    OrgSpecValorOut,
    PlataformaAgentCreateRequest,
    PlataformaTextoOut,
    PlataformaTextosOut,
    PlataformaTextosRequest,
    SpecDefOut,
    SpecsOut,
    SpecsReplaceRequest,
    TextoOut,
    TextosOut,
    TextosReplaceRequest,
)
from app.stores.errors import NotFound
from app.stores.studio_definitions_conteudo import (
    DecisaoInput,
    FerramentaInput,
    SpecDefInput,
    TextoInput,
)
from app.studio.especificacoes import conflitos_com_regras_fixas, validar_valor
from app.studio.plataforma import chaves_de_plataforma, ensure_definicao
from app.studio.resolucao import compile_for_org, conteudo_status, resolve_agent_for_org
from noctusai_lib.api.auth.platform import resolve_platform_admin_role
from noctusai_lib.api.auth.session import AuthContext, ProductTokenAdmin, require_scopes

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/studio", tags=["studio-conteudo"])

# SCOPE_STUDIO_CONTENT_WRITE / CONTENT_TOKEN_ISSUER live in app.dependencies (shared with the skill library
# and the qualification standard, which the same MCP token writes).
CONTENT_TOKEN_TTL_DAYS = 30

_content_write_base = require_scopes(
    SCOPE_STUDIO_CONTENT_WRITE,
    user_roles=ADMIN_ROLES,
    get_auth_context=get_auth_context,
    get_core_client=get_core_client,
    restrict="any",
)


async def require_content_write(ctx: AuthContext = Depends(_content_write_base)) -> AuthContext:
    """Visibility tier 1: the definition is written by a PLATFORM ADMIN (``noctus_users.role == 'admin'``,
    never an org owner/admin) or by a product token that carries ``studio:content-write``
    (the ``noctus.agents.content`` MCP path)."""
    if ctx.caller_kind == "product":
        if ctx.issuer != CONTENT_TOKEN_ISSUER:
            raise http_error(403, "issuer_not_allowed", "Token issuer not allowed for this API")
        return ctx
    if resolve_platform_admin_role(get_core_client(), ctx.user_id) != "admin":
        raise http_error(403, "platform_admin_required", "Restrito a administradores da plataforma NoctusAI")
    return ctx


# ── helpers ─────────────────────────────────────────────────────────────────


def _texto_out(r) -> TextoOut:
    return TextoOut(id=r.id, chave=r.chave, conteudo=r.conteudo)


def _ferramenta_out(r) -> FerramentaOut:
    return FerramentaOut(
        id=r.id, ferramenta=r.ferramenta, ativo=r.ativo, descricao=r.descricao,
        parametros=dict(r.parametros), obrigatoria_skill=r.obrigatoria_skill,
    )


def _decisao_out(r) -> DecisaoOut:
    return DecisaoOut(id=r.id, chave=r.chave, titulo=r.titulo, regra=r.regra, opcoes=[dict(o) for o in r.opcoes])


def _spec_out(r) -> SpecDefOut:
    return SpecDefOut(
        id=r.id, chave=r.chave, rotulo=r.rotulo, descricao=r.descricao, tipo=r.tipo,
        obrigatoria=r.obrigatoria, exemplo=r.exemplo,
    )


def _audit_mcp(store, ctx: AuthContext, agent, kind: str, version_id: UUID, antes: list[str], depois: list[str]) -> None:
    """A write made with a product token (the MCP path) is audit-logged: who (the token row), what, where."""
    if ctx.caller_kind != "product":
        return
    store.append_audit(
        agent.org_id, agent.id, actor_id(ctx), "conteudo_editado_mcp",
        {"kind": kind, "version_id": str(version_id), "chaves": antes},
        {"kind": kind, "version_id": str(version_id), "chaves": depois},
    )


def _draft_for_write(store, ctx: AuthContext, key: str):
    agent = resolve_agent(store, ctx.org_id, key)
    if agent.conteudo_modo != "linhas":
        # A legacy agent's compiler never reads these rows: accepting them would be dead, unhashed data.
        raise http_error(
            409, "conteudo_modo_legado",
            "Este agente ainda usa os textos do compilador no código; o conteúdo em linhas não se aplica.",
        )
    return agent, resolve_draft(store, ctx.org_id, agent)


def _definition_version(store, ctx: AuthContext, key: str, version_id: UUID):
    agent = resolve_agent(store, ctx.org_id, key)
    return agent, resolve_version(store, ctx.org_id, agent, version_id)


# ── reads (a version's content tables) ──────────────────────────────────────


@router.get("/agents/{key}/versions/{version_id}/textos", response_model=TextosOut)
async def list_textos(
    key: str, version_id: UUID, ctx: AuthContext = Depends(require_platform_content_admin),
    store=Depends(get_studio_definition_store_dep),
) -> TextosOut:
    agent, v = _definition_version(store, ctx, key, version_id)
    audit_definition_read(store, ctx, agent, "textos", v.id)
    return TextosOut(version_id=v.id, itens=[_texto_out(r) for r in store.list_textos(ctx.org_id, v.id)])


@router.get("/agents/{key}/versions/{version_id}/ferramentas", response_model=FerramentasOut)
async def list_ferramentas(
    key: str, version_id: UUID, ctx: AuthContext = Depends(require_platform_content_admin),
    store=Depends(get_studio_definition_store_dep),
) -> FerramentasOut:
    agent, v = _definition_version(store, ctx, key, version_id)
    audit_definition_read(store, ctx, agent, "ferramentas", v.id)
    return FerramentasOut(version_id=v.id, itens=[_ferramenta_out(r) for r in store.list_ferramentas(ctx.org_id, v.id)])


@router.get("/agents/{key}/versions/{version_id}/decisoes", response_model=DecisoesOut)
async def list_decisoes(
    key: str, version_id: UUID, ctx: AuthContext = Depends(require_platform_content_admin),
    store=Depends(get_studio_definition_store_dep),
) -> DecisoesOut:
    agent, v = _definition_version(store, ctx, key, version_id)
    audit_definition_read(store, ctx, agent, "decisoes", v.id)
    return DecisoesOut(version_id=v.id, itens=[_decisao_out(r) for r in store.list_decisoes(ctx.org_id, v.id)])


@router.get("/agents/{key}/versions/{version_id}/specs", response_model=SpecsOut)
async def list_spec_defs(
    key: str, version_id: UUID, ctx: AuthContext = Depends(require_platform_content_admin),
    store=Depends(get_studio_definition_store_dep),
) -> SpecsOut:
    agent, v = _definition_version(store, ctx, key, version_id)
    audit_definition_read(store, ctx, agent, "specs", v.id)
    return SpecsOut(version_id=v.id, itens=[_spec_out(r) for r in store.list_spec_defs(ctx.org_id, v.id)])


# ── draft-only replace-set writes ───────────────────────────────────────────


@router.put("/agents/{key}/draft/textos", response_model=TextosOut)
async def replace_draft_textos(
    key: str, payload: TextosReplaceRequest, ctx: AuthContext = Depends(require_content_write),
    store=Depends(get_studio_definition_store_dep), catalog=Depends(get_knowledge_catalog_dep),
) -> TextosOut:
    agent, draft = _draft_for_write(store, ctx, key)
    antes = [r.chave for r in store.list_textos(ctx.org_id, draft.id)]
    with store_errors():
        rows = store.replace_textos(
            ctx.org_id, draft.id, [TextoInput(i.chave, i.conteudo) for i in payload.itens],
            expected_hash=payload.expected_hash)
    _audit_mcp(store, ctx, agent, "texto", draft.id, antes, [r.chave for r in rows])
    _refresh_draft_hash(store, catalog, ctx.org_id, agent, draft.id)
    return TextosOut(version_id=draft.id, itens=[_texto_out(r) for r in rows])


@router.put("/agents/{key}/draft/ferramentas", response_model=FerramentasOut)
async def replace_draft_ferramentas(
    key: str, payload: FerramentasReplaceRequest, ctx: AuthContext = Depends(require_content_write),
    store=Depends(get_studio_definition_store_dep), catalog=Depends(get_knowledge_catalog_dep),
) -> FerramentasOut:
    agent, draft = _draft_for_write(store, ctx, key)
    antes = [r.ferramenta for r in store.list_ferramentas(ctx.org_id, draft.id)]
    with store_errors():
        rows = store.replace_ferramentas(ctx.org_id, draft.id, [
            FerramentaInput(
                ferramenta=i.ferramenta, descricao=i.descricao, ativo=i.ativo, parametros=dict(i.parametros),
                obrigatoria_skill=i.obrigatoria_skill,
            )
            for i in payload.itens
        ], expected_hash=payload.expected_hash)
    _audit_mcp(store, ctx, agent, "ferramenta", draft.id, antes, [r.ferramenta for r in rows])
    _refresh_draft_hash(store, catalog, ctx.org_id, agent, draft.id)
    return FerramentasOut(version_id=draft.id, itens=[_ferramenta_out(r) for r in rows])


@router.put("/agents/{key}/draft/decisoes", response_model=DecisoesOut)
async def replace_draft_decisoes(
    key: str, payload: DecisoesReplaceRequest, ctx: AuthContext = Depends(require_content_write),
    store=Depends(get_studio_definition_store_dep), catalog=Depends(get_knowledge_catalog_dep),
) -> DecisoesOut:
    agent, draft = _draft_for_write(store, ctx, key)
    antes = [r.chave for r in store.list_decisoes(ctx.org_id, draft.id)]
    with store_errors():
        rows = store.replace_decisoes(ctx.org_id, draft.id, [
            DecisaoInput(
                chave=i.chave, titulo=i.titulo, regra=i.regra,
                opcoes=[{"valor": o.valor, "rotulo": o.rotulo, "padrao": o.padrao} for o in i.opcoes],
            )
            for i in payload.itens
        ], expected_hash=payload.expected_hash)
    _audit_mcp(store, ctx, agent, "decisao", draft.id, antes, [r.chave for r in rows])
    _refresh_draft_hash(store, catalog, ctx.org_id, agent, draft.id)
    return DecisoesOut(version_id=draft.id, itens=[_decisao_out(r) for r in rows])


@router.put("/agents/{key}/draft/specs", response_model=SpecsOut)
async def replace_draft_spec_defs(
    key: str, payload: SpecsReplaceRequest, ctx: AuthContext = Depends(require_content_write),
    store=Depends(get_studio_definition_store_dep), catalog=Depends(get_knowledge_catalog_dep),
) -> SpecsOut:
    agent, draft = _draft_for_write(store, ctx, key)
    antes = [r.chave for r in store.list_spec_defs(ctx.org_id, draft.id)]
    with store_errors():
        rows = store.replace_spec_defs(ctx.org_id, draft.id, [
            SpecDefInput(
                chave=i.chave, rotulo=i.rotulo, descricao=i.descricao, tipo=i.tipo, obrigatoria=i.obrigatoria,
                exemplo=i.exemplo,
            )
            for i in payload.itens
        ], expected_hash=payload.expected_hash)
    _audit_mcp(store, ctx, agent, "spec", draft.id, antes, [r.chave for r in rows])
    _refresh_draft_hash(store, catalog, ctx.org_id, agent, draft.id)
    return SpecsOut(version_id=draft.id, itens=[_spec_out(r) for r in rows])


# ── the full "what the model receives" view of a version ────────────────────


@router.get("/agents/{key}/versions/{version_id}/payload", response_model=ConteudoPayloadOut)
async def get_payload(
    key: str, version_id: UUID, ctx: AuthContext = Depends(require_platform_admin),
    store=Depends(get_studio_definition_store_dep), catalog=Depends(get_knowledge_catalog_dep),
) -> ConteudoPayloadOut:
    """CONTRACT §2.3 "Compilado": the compiled system prompt PLUS every content row that reaches the
    model outside it, each attributed to its row in ``manifest``. The sample second system message
    (``?amostra=``) is rendered by the channel runtime (A-RT) on top of this."""
    from app.studio.bundles import compile_version

    agent, v = _definition_version(store, ctx, key, version_id)
    audit_definition_read(store, ctx, agent, "payload", v.id)
    compiled = compile_version(store, catalog, ctx.org_id, agent, v)
    return ConteudoPayloadOut(
        version_id=v.id, hash=compiled.hash, texto=compiled.texto, tokens_estimados=compiled.tokens_estimados,
        manifest=compiled.manifest_json(), avisos=[w.to_dict() for w in compiled.avisos],
        textos=[_texto_out(r) for r in store.list_textos(ctx.org_id, v.id)],
        ferramentas=[_ferramenta_out(r) for r in store.list_ferramentas(ctx.org_id, v.id)],
        decisoes=[_decisao_out(r) for r in store.list_decisoes(ctx.org_id, v.id)],
        specs=[_spec_out(r) for r in store.list_spec_defs(ctx.org_id, v.id)], ponto_cache=compiled.ponto_cache,
    )


# ── org specs (the ORG's values for what the definition declares) ───────────


def _resolved(store, ctx: AuthContext, key: str, versao: str = "ativa"):
    agent = resolve_agent(store, ctx.org_id, key, allow_instancia=True)
    if versao == "rascunho" and agent.definition_scope == "instancia":
        # The platform's unpublished draft is not an org's to read.
        raise http_error(409, "rascunho_da_plataforma", "O rascunho da definição é da plataforma.")
    try:
        return agent, resolve_agent_for_org(store, ctx.org_id, key, versao=versao)
    except NotFound as exc:
        raise http_error(404, "version_not_found", "Versão não encontrada.") from exc


def _org_specs_out(key: str, r) -> OrgSpecsOut:
    return OrgSpecsOut(
        agent_key=key,
        version_id=r.versao.id if r.versao else None,
        versao=r.versao.versao if r.versao else None,
        declaradas=[_spec_out(d) for d in r.specs_declaradas],
        valores=[OrgSpecValorOut(chave=s.chave, valor=s.valor, updated_at=s.updated_at) for s in r.specs_org],
        faltando=list(r.faltando),
    )


@router.get("/agents/{key}/specs", response_model=OrgSpecsOut)
async def get_org_specs(
    key: str,
    ctx: AuthContext = Depends(require_admin),
    store=Depends(get_studio_definition_store_dep),
) -> OrgSpecsOut:
    """Org admin only: which org specs the definition asks for (label + help — the FORM, never a
    prompt), this org's values and what is still missing."""
    _, r = _resolved(store, ctx, key, "ativa")
    return _org_specs_out(key, r)


@router.put("/agents/{key}/specs", response_model=OrgSpecsOut)
async def update_org_specs(
    key: str, payload: OrgSpecsUpdateRequest, ctx: AuthContext = Depends(require_admin),
    store=Depends(get_studio_definition_store_dep),
) -> OrgSpecsOut:
    """The org owner/admin sets ITS values. Keys must be declared by the definition (the active or the
    draft version); each value is capped by its declaration's type. A blank value clears the spec."""
    agent = resolve_agent(store, ctx.org_id, key, allow_instancia=True)
    if agent.definition_scope == "instancia":
        definition = store.get_agent_by_id(agent.definition_agent_id)
    else:
        definition = agent
    declaradas: dict[str, Any] = {}
    for version in (
        store.get_draft(definition.org_id, definition.id), store.get_active_version(definition.org_id, definition.id),
    ):
        if version is not None:
            for d in store.list_spec_defs(definition.org_id, version.id):
                declaradas.setdefault(d.chave, d)
    if not declaradas:
        raise http_error(409, "definicao_sem_especificacoes", "A definição ainda não declara especificações da organização.")
    desconhecidas = sorted(set(payload.valores) - set(declaradas))
    if desconhecidas:
        raise http_error(
            422, "spec_nao_declarada", "Especificações não declaradas pela definição: " + ", ".join(desconhecidas) + ".",
        )
    for chave, valor in payload.valores.items():
        try:
            validar_valor(declaradas[chave].tipo, valor)
        except ValueError as exc:
            raise http_error(422, "invalid_field", f"{chave}: {exc}") from exc
        conflitos = conflitos_com_regras_fixas(valor)
        if conflitos:
            raise http_error(
                422, "spec_conflita_com_regra_fixa",
                f"{chave}: o texto contradiz uma regra fixa da plataforma ({', '.join(conflitos)}).",
                conflitos=conflitos,
            )
    antes = {s.chave for s in store.list_org_specs(ctx.org_id, key)}
    with store_errors():
        store.upsert_org_specs(ctx.org_id, key, dict(payload.valores), actor=actor_id(ctx))
    # keys only (values are the org's business data, not audit payload)
    store.append_audit(
        ctx.org_id, agent.id, actor_id(ctx), "specs_org_editadas",
        {"chaves": sorted(antes)}, {"chaves": sorted(payload.valores)},
    )
    _, r = _resolved(store, ctx, key)
    return _org_specs_out(key, r)


@router.get("/agents/{key}/compilado", response_model=CompiladoOrgOut)
async def get_compiled_for_org(
    key: str,
    versao: Literal["ativa", "rascunho"] = Query(default="ativa"),
    ctx: AuthContext = Depends(require_platform_admin),
    store=Depends(get_studio_definition_store_dep),
    catalog=Depends(get_knowledge_catalog_dep),
) -> CompiladoOrgOut:
    """PLATFORM ADMIN ONLY (acting in the org via the picker): the definition compiled for that org —
    every ``{{org.x}}`` replaced by the org's value. Org admins never read the compiled prompt (they
    get ``/status``). Audited on every read."""
    agent, r = _resolved(store, ctx, key, versao)
    if r.versao is None:
        raise http_error(404, "version_not_found", "O agente ainda não tem versão publicada.")
    audit_definition_read(store, ctx, agent, "compilado_org", r.versao.id)
    compiled = compile_for_org(store, catalog, r)
    return CompiladoOrgOut(
        version_id=r.versao.id, versao=r.versao.versao, hash=compiled.hash, texto=compiled.texto,
        tokens_estimados=compiled.tokens_estimados, manifest=compiled.manifest_json(),
        avisos=[w.to_dict() for w in compiled.avisos], specs_faltando=list(compiled.specs_faltando),
        completo=not any(w.bloqueante for w in compiled.avisos), ponto_cache=compiled.ponto_cache,
    )


@router.get("/agents/{key}/status", response_model=OrgStatusOut)
async def get_org_status(
    key: str, ctx: AuthContext = Depends(require_admin),
    store=Depends(get_studio_definition_store_dep), catalog=Depends(get_knowledge_catalog_dep),
) -> OrgStatusOut:
    """What an ORG ADMIN may see of its agent's readiness: complete or not, and which of ITS specs are
    still missing. No hashes, no warning texts, no prompt — only booleans and the org's own spec keys."""
    _, r = _resolved(store, ctx, key)
    st = conteudo_status(store, catalog, r)
    return OrgStatusOut(
        agent_key=key, completo=st.completo, sem_versao=st.sem_versao, specs_faltando=list(st.specs_faltando or r.faltando),
    )


# ── platform ────────────────────────────────────────────────────────────────


@router.get("/plataforma/textos", response_model=PlataformaTextosOut)
async def list_textos_plataforma(
    ctx: AuthContext = Depends(require_platform_admin), store=Depends(get_studio_definition_store_dep),
) -> PlataformaTextosOut:
    return PlataformaTextosOut(itens=[
        PlataformaTextoOut(chave=r.chave, conteudo=r.conteudo, updated_at=r.updated_at)
        for r in store.list_textos_plataforma()
    ])


@router.put("/plataforma/textos", response_model=PlataformaTextosOut)
async def set_textos_plataforma(
    payload: PlataformaTextosRequest, ctx: AuthContext = Depends(require_platform_admin),
    store=Depends(get_studio_definition_store_dep),
) -> PlataformaTextosOut:
    with store_errors():
        rows = store.set_textos_plataforma(dict(payload.itens), actor=actor_id(ctx))
    return PlataformaTextosOut(itens=[
        PlataformaTextoOut(chave=r.chave, conteudo=r.conteudo, updated_at=r.updated_at) for r in rows
    ])


@router.post("/plataforma/content-token", response_model=ContentTokenOut, status_code=status.HTTP_201_CREATED)
async def mint_content_token(
    payload: ContentTokenCreateRequest, response: Response, ctx: AuthContext = Depends(require_platform_admin),
    token_admin: ProductTokenAdmin = Depends(get_product_token_admin_dep),
    audit: TokenAudit = Depends(get_token_audit_dep),
) -> ContentTokenOut:
    """Mint the ``noctus.agents.content`` MCP token: scope ``studio:content-write`` only, issuer
    ``noctus-platform`` (server-side), 30 days, org-bound to the platform org the admin acts in. PLATFORM ADMIN
    only; the raw secret is returned once. Audited like the channel token."""
    expires_at = datetime.now(timezone.utc) + timedelta(days=CONTENT_TOKEN_TTL_DAYS)
    try:
        minted = token_admin.mint(
            "agents", org_id=ctx.org_id, label=f"conteudo: {payload.label}",
            scopes=[SCOPE_STUDIO_CONTENT_WRITE], expires_at=expires_at, issuer=CONTENT_TOKEN_ISSUER,
            minted_by=ctx.user_id,
        )
    except Exception as exc:
        logger.error("agents.content_token.mint_failed org_id=%s error=%s", ctx.org_id, type(exc).__name__)
        raise http_error(502, "mint_failed", "Falha ao emitir o token.") from exc
    try:
        audit.record(
            api_token_id=minted.info.id, org_id=ctx.org_id, action="MINT", agent_key="studio-content",
            actor_user_id=ctx.user_id, status=201,
        )
    except Exception as exc:
        token_admin.revoke("agents", minted.info.id, org_id=ctx.org_id)
        raise http_error(502, "audit_failed", "Falha ao registrar a emissão do token.") from exc
    response.headers["Cache-Control"] = "no-store"
    return ContentTokenOut(
        id=minted.info.id, token=minted.secret, prefix=minted.info.prefix, expires_at=expires_at,
        scopes=[SCOPE_STUDIO_CONTENT_WRITE],
    )


@router.post("/plataforma/agents", status_code=status.HTTP_201_CREATED)
async def create_platform_definition(
    payload: PlataformaAgentCreateRequest, ctx: AuthContext = Depends(require_platform_admin),
    store=Depends(get_studio_definition_store_dep),
) -> dict[str, Any]:
    """Create the platform DEFINITION of a registered key in the caller's org (which must be the platform
    org) with an empty draft carrying only structure. Idempotent."""
    if payload.key not in chaves_de_plataforma():
        raise http_error(422, "chave_nao_registrada", f"'{payload.key}' não é um agente definido pela plataforma.")
    with store_errors():
        agent = ensure_definicao(ctx.org_id, payload.key, studio_store=store, created_by=actor_id(ctx))
    return {
        "id": str(agent.id), "key": agent.key, "org_id": str(agent.org_id),
        "definition_scope": agent.definition_scope, "conteudo_modo": agent.conteudo_modo,
    }


__all__ = ["router", "require_content_write", "SCOPE_STUDIO_CONTENT_WRITE"]

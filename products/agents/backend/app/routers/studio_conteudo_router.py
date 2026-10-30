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

import anyio.to_thread
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.dependencies import (
    ADMIN_ROLES,
    CONTENT_TOKEN_ISSUER,
    SCOPE_STUDIO_AGENT_DELETE,
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
    ContentTokenInfoOut,
    ContentTokenOut,
    ContentTokensOut,
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
from app.schemas.studio_plataforma import (
    PlataformaAgentCreateRequest,
    PlataformaAgentOut,
    PlataformaAgentUpdateRequest,
    PlataformaGrantRequest,
    PlataformaGrantsOut,
)
from app.stores._db_errors import StudioConflict
from app.stores.errors import NotFound
from app.stores.studio_definitions_conteudo import (
    DecisaoInput,
    FerramentaInput,
    SpecDefInput,
    TextoInput,
)
from app.studio.especificacoes import conflitos_com_regras_fixas, validar_valor
from app.routers.studio_geracoes_router import get_geracao_agendador_dep, get_geracao_deps_dep
from app.studio import geracao as engine
from app.studio.plataforma import ensure_definicao
from app.studio.resolucao import compile_for_org, conteudo_status, resolve_agent_for_org
from noctusai_lib.api.auth.platform import resolve_platform_admin_role
from noctusai_lib.api.auth.session import AuthContext, ProductTokenAdmin, require_scopes

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/studio", tags=["studio-conteudo"])

# SCOPE_STUDIO_CONTENT_WRITE / CONTENT_TOKEN_ISSUER live in app.dependencies (shared with the skill library
# and the qualification standard, which the same MCP token writes).

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
def list_textos(
    key: str, version_id: UUID, ctx: AuthContext = Depends(require_platform_content_admin),
    store=Depends(get_studio_definition_store_dep),
) -> TextosOut:
    agent, v = _definition_version(store, ctx, key, version_id)
    audit_definition_read(store, ctx, agent, "textos", v.id)
    return TextosOut(version_id=v.id, itens=[_texto_out(r) for r in store.list_textos(ctx.org_id, v.id)])


@router.get("/agents/{key}/versions/{version_id}/ferramentas", response_model=FerramentasOut)
def list_ferramentas(
    key: str, version_id: UUID, ctx: AuthContext = Depends(require_platform_content_admin),
    store=Depends(get_studio_definition_store_dep),
) -> FerramentasOut:
    agent, v = _definition_version(store, ctx, key, version_id)
    audit_definition_read(store, ctx, agent, "ferramentas", v.id)
    return FerramentasOut(version_id=v.id, itens=[_ferramenta_out(r) for r in store.list_ferramentas(ctx.org_id, v.id)])


@router.get("/agents/{key}/versions/{version_id}/decisoes", response_model=DecisoesOut)
def list_decisoes(
    key: str, version_id: UUID, ctx: AuthContext = Depends(require_platform_content_admin),
    store=Depends(get_studio_definition_store_dep),
) -> DecisoesOut:
    agent, v = _definition_version(store, ctx, key, version_id)
    audit_definition_read(store, ctx, agent, "decisoes", v.id)
    return DecisoesOut(version_id=v.id, itens=[_decisao_out(r) for r in store.list_decisoes(ctx.org_id, v.id)])


@router.get("/agents/{key}/versions/{version_id}/specs", response_model=SpecsOut)
def list_spec_defs(
    key: str, version_id: UUID, ctx: AuthContext = Depends(require_platform_content_admin),
    store=Depends(get_studio_definition_store_dep),
) -> SpecsOut:
    agent, v = _definition_version(store, ctx, key, version_id)
    audit_definition_read(store, ctx, agent, "specs", v.id)
    return SpecsOut(version_id=v.id, itens=[_spec_out(r) for r in store.list_spec_defs(ctx.org_id, v.id)])


# ── draft-only replace-set writes ───────────────────────────────────────────


@router.put("/agents/{key}/draft/textos", response_model=TextosOut)
def replace_draft_textos(
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
def replace_draft_ferramentas(
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
def replace_draft_decisoes(
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
def replace_draft_spec_defs(
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
def get_payload(
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
def get_org_specs(
    key: str,
    ctx: AuthContext = Depends(require_admin),
    store=Depends(get_studio_definition_store_dep),
) -> OrgSpecsOut:
    """Org admin only: which org specs the definition asks for (label + help — the FORM, never a
    prompt), this org's values and what is still missing."""
    _, r = _resolved(store, ctx, key, "ativa")
    return _org_specs_out(key, r)


@router.put("/agents/{key}/specs", response_model=OrgSpecsOut)
def update_org_specs(
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
def get_compiled_for_org(
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
def get_org_status(
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
def list_textos_plataforma(
    ctx: AuthContext = Depends(require_platform_admin), store=Depends(get_studio_definition_store_dep),
) -> PlataformaTextosOut:
    return PlataformaTextosOut(itens=[
        PlataformaTextoOut(chave=r.chave, conteudo=r.conteudo, updated_at=r.updated_at)
        for r in store.list_textos_plataforma()
    ])


@router.put("/plataforma/textos", response_model=PlataformaTextosOut)
def set_textos_plataforma(
    payload: PlataformaTextosRequest, ctx: AuthContext = Depends(require_platform_admin),
    store=Depends(get_studio_definition_store_dep),
) -> PlataformaTextosOut:
    with store_errors():
        rows = store.set_textos_plataforma(dict(payload.itens), actor=actor_id(ctx))
    return PlataformaTextosOut(itens=[
        PlataformaTextoOut(chave=r.chave, conteudo=r.conteudo, updated_at=r.updated_at) for r in rows
    ])


@router.post("/plataforma/content-token", response_model=ContentTokenOut, status_code=status.HTTP_201_CREATED)
def mint_content_token(
    payload: ContentTokenCreateRequest, response: Response, ctx: AuthContext = Depends(require_platform_admin),
    token_admin: ProductTokenAdmin = Depends(get_product_token_admin_dep),
    audit: TokenAudit = Depends(get_token_audit_dep),
) -> ContentTokenOut:
    """Mint the ``noctus.agents.content`` MCP token: scope ``studio:content-write`` only, issuer
    ``noctus-platform`` (server-side), ``expira_em_dias`` days (default 30, 1..365; ``null`` = never expires), org-bound to the platform org the admin acts in. PLATFORM ADMIN
    only; the raw secret is returned once. Audited like the channel token."""
    scopes = [SCOPE_STUDIO_CONTENT_WRITE] + ([SCOPE_STUDIO_AGENT_DELETE] if payload.permitir_exclusao else [])
    expires_at = (
        None if payload.expira_em_dias is None
        else datetime.now(timezone.utc) + timedelta(days=payload.expira_em_dias)
    )
    try:
        minted = token_admin.mint(
            "agents", org_id=ctx.org_id, label=f"conteudo: {payload.label}",
            scopes=scopes, expires_at=expires_at, issuer=CONTENT_TOKEN_ISSUER,
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
    logger.info(
        "agents.content_token.minted org_id=%s token_id=%s by=%s label=%r expires_at=%s",
        ctx.org_id, minted.info.id, ctx.user_id, payload.label, expires_at.isoformat() if expires_at else "never",
    )
    if payload.permitir_exclusao:
        logger.info("agents.content_token.minted_with_delete org_id=%s token_id=%s", ctx.org_id, minted.info.id)
    response.headers["Cache-Control"] = "no-store"
    return ContentTokenOut(
        id=minted.info.id, token=minted.secret, prefix=minted.info.prefix, expires_at=expires_at,
        scopes=scopes,
    )


def _content_token_status(info) -> str:
    if info.revoked_at is not None:
        return "revogado"
    if info.expires_at is not None and info.expires_at <= datetime.now(timezone.utc):
        return "expirado"
    return "ativo"


def _content_tokens(token_admin: ProductTokenAdmin, org_id: UUID):
    return token_admin.list_tokens(
        "agents", org_id=org_id, scope=SCOPE_STUDIO_CONTENT_WRITE, issuer=CONTENT_TOKEN_ISSUER,
    )


@router.get("/plataforma/content-tokens", response_model=ContentTokensOut)
def list_content_tokens(
    response: Response, ctx: AuthContext = Depends(require_platform_admin),
    token_admin: ProductTokenAdmin = Depends(get_product_token_admin_dep),
) -> ContentTokensOut:
    """The platform org's ``studio:content-write`` tokens (revoked + expired included), newest first. Never the secret."""
    try:
        infos = _content_tokens(token_admin, ctx.org_id)
    except Exception as exc:
        logger.error("agents.content_token.list_failed org_id=%s error=%s", ctx.org_id, type(exc).__name__)
        raise http_error(502, "list_failed", "Falha ao listar os tokens.") from exc
    response.headers["Cache-Control"] = "no-store"
    return ContentTokensOut(itens=[
        ContentTokenInfoOut(
            id=i.id, label=i.label, prefix=i.prefix, scopes=list(i.scopes), created_at=i.created_at,
            created_by=i.created_by, expires_at=i.expires_at, last_used_at=i.last_used_at,
            revoked_at=i.revoked_at, status=_content_token_status(i),
        ) for i in infos
    ])


@router.delete("/plataforma/content-token/{token_id}", response_model=ContentTokenInfoOut)
def revoke_content_token(
    token_id: UUID, ctx: AuthContext = Depends(require_platform_admin),
    token_admin: ProductTokenAdmin = Depends(get_product_token_admin_dep),
    audit: TokenAudit = Depends(get_token_audit_dep),
) -> ContentTokenInfoOut:
    """Revoke a content token of the platform org. Idempotent (an already-revoked token answers 200 again,
    without a second audit row); 404 for an id that is not a content token of this org. Audited."""
    try:
        info = next((i for i in _content_tokens(token_admin, ctx.org_id) if i.id == token_id), None)
    except Exception as exc:
        logger.error("agents.content_token.revoke_lookup_failed org_id=%s error=%s", ctx.org_id, type(exc).__name__)
        raise http_error(502, "revoke_failed", "Falha ao revogar o token.") from exc
    if info is None:
        raise http_error(404, "token_not_found", "Token não encontrado.")
    if info.revoked_at is None:
        try:
            token_admin.revoke("agents", token_id, org_id=ctx.org_id)
        except Exception as exc:
            logger.error("agents.content_token.revoke_failed org_id=%s error=%s", ctx.org_id, type(exc).__name__)
            raise http_error(502, "revoke_failed", "Falha ao revogar o token.") from exc
        try:
            audit.record(
                api_token_id=token_id, org_id=ctx.org_id, action="REVOKE", agent_key="studio-content",
                actor_user_id=ctx.user_id, status=200,
            )
        except Exception as exc:
            logger.error("agents.content_token.revoke_audit_failed org_id=%s token_id=%s", ctx.org_id, token_id)
            raise http_error(502, "audit_failed", "Token revogado, mas falhou o registro de auditoria.") from exc
        logger.info(
            "agents.content_token.revoked org_id=%s token_id=%s by=%s label=%r",
            ctx.org_id, token_id, ctx.user_id, info.label,
        )
    info = next(i for i in _content_tokens(token_admin, ctx.org_id) if i.id == token_id)
    return ContentTokenInfoOut(
        id=info.id, label=info.label, prefix=info.prefix, scopes=list(info.scopes), created_at=info.created_at,
        created_by=info.created_by, expires_at=info.expires_at, last_used_at=info.last_used_at,
        revoked_at=info.revoked_at, status=_content_token_status(info),
    )


def _flat(status_code: int, code: str, message: str, detail: Any = None) -> HTTPException:
    """The product's flat error body ``{code, message, detail}`` (as ``DELETE /agents/{key}``)."""
    return HTTPException(status_code=status_code, detail={"code": code, "message": message, "detail": detail if detail is not None else message})


def _definicao_out(agent, geracao=None) -> PlataformaAgentOut:
    return PlataformaAgentOut(
        id=agent.id, key=agent.key, org_id=agent.org_id, nome=agent.nome, descricao=agent.descricao,
        definition_scope=agent.definition_scope, conteudo_modo=agent.conteudo_modo, runtime=agent.runtime,
        owner_product=agent.owner_product, usa_canais=agent.usa_canais,
        escopo_qualificacao=agent.escopo_qualificacao, padrao_qualificacao=agent.padrao_qualificacao,
        rascunho_padrao=agent.rascunho_padrao, instanciavel=agent.instanciavel, papel=agent.papel, geracao=geracao,
    )


def _definicao_ou_404(store, key: str):
    agent = store.get_platform_definition(key)
    if agent is None:
        raise _flat(404, "agente_nao_encontrado", "Definição da plataforma não encontrada.")
    return agent


def _conflict_flat(exc: StudioConflict) -> HTTPException:
    return _flat(409, exc.code, str(exc))


@router.post("/plataforma/agents", status_code=status.HTTP_201_CREATED, response_model=PlataformaAgentOut)
async def create_platform_definition(
    payload: PlataformaAgentCreateRequest, ctx: AuthContext = Depends(require_platform_content_admin),
    store=Depends(get_studio_definition_store_dep), deps: engine.Dependencias = Depends(get_geracao_deps_dep),
    schedule=Depends(get_geracao_agendador_dep),
) -> PlataformaAgentOut:
    """Create the platform DEFINITION of ``payload.key`` in the caller's org (which must be the platform org) with an
    EMPTY draft -- a shell grows over time; only PUBLISH is gated by completeness. ANY valid key is accepted: a
    platform definition is a DB row, never a code registry entry, and what used to be registered in code (runtime,
    owner product, qualification scope/standard, first-draft settings, role) is the body. ``nome`` is required for a
    new key. An existing key is a 409 ``agente_ja_existe`` (a create form must never silently land on someone else's
    definition) unless ``reutilizar=true``, which returns it unchanged (the MCP ``criar_agente`` idempotent path);
    audits ``agente_criado`` only when it creates. With ``briefing`` an AI generation of the draft starts (202-style:
    ``geracao`` is the booked run)."""
    ator = actor_id(ctx)

    def _criar():
        existing = store.get_platform_definition(payload.key)
        if existing is not None:
            if not payload.reutilizar:
                raise _flat(409, "agente_ja_existe", f"Já existe um agente com a chave '{payload.key}'.",
                            {"key": payload.key})
            return existing
        if not payload.nome:
            raise _flat(422, "nome_obrigatorio", "Informe o nome do agente para criar uma nova definição.")
        try:
            return ensure_definicao(
                ctx.org_id, payload.key, studio_store=store, created_by=ator, nome=payload.nome,
                descricao=payload.descricao, runtime=payload.runtime, owner_product=payload.owner_product,
                escopo_qualificacao=payload.escopo_qualificacao, padrao_qualificacao=payload.padrao_qualificacao,
                rascunho_padrao=payload.rascunho_padrao, instanciavel=payload.instanciavel, papel=payload.papel,
            )
        except StudioConflict as exc:
            raise _conflict_flat(exc) from exc
        except ValueError as exc:
            raise _flat(422, "invalid_field", str(exc)) from exc

    agent = await anyio.to_thread.run_sync(_criar)
    if payload.briefing is None:
        return _definicao_out(agent)
    try:
        rec, alvo, areas = await anyio.to_thread.run_sync(lambda: engine.iniciar(
            deps, org_id=ctx.org_id, key=agent.key, briefing=payload.briefing, areas=None, forcar=False,
            limite_usd=payload.limite_usd, ator=ator))
    except engine.GeracaoErro as exc:
        raise _flat(exc.status, exc.code, exc.message, exc.detail) from exc
    schedule(engine.executar(deps, org_id=rec.org_id, geracao_id=rec.id, agent_id=alvo.id, areas=areas))
    geracao = (await anyio.to_thread.run_sync(lambda: engine.montar_saida(deps, alvo, [rec])))[0]
    return _definicao_out(agent, geracao)


@router.get("/plataforma/agents/{key}", response_model=PlataformaAgentOut)
def get_platform_definition_config(
    key: str, ctx: AuthContext = Depends(require_platform_content_admin), store=Depends(get_studio_definition_store_dep),
) -> PlataformaAgentOut:
    """The DATA a platform definition carries (runtime, owner product, qualification scope/standard, first-draft
    settings, role, instantiability). Every mechanism reads these from the row."""
    return _definicao_out(_definicao_ou_404(store, key))


@router.patch("/plataforma/agents/{key}", response_model=PlataformaAgentOut)
def update_platform_definition_config(
    key: str, payload: PlataformaAgentUpdateRequest, ctx: AuthContext = Depends(require_platform_content_admin),
    store=Depends(get_studio_definition_store_dep),
) -> PlataformaAgentOut:
    """Partial update of that DATA (``exclude_unset``; an explicit ``null`` clears an optional attribute). Existing
    org instances keep the runtime / owner product they were created with; a new instance copies the current ones."""
    agent = _definicao_ou_404(store, key)
    fields = payload.model_dump(mode="json", exclude_unset=True)
    for obrig in ("nome", "runtime", "instanciavel"):
        if obrig in fields and fields[obrig] is None:
            raise _flat(422, "invalid_field", f"{obrig} não pode ser nulo")
    try:
        updated = store.update_definicao(agent.org_id, key, fields)
    except StudioConflict as exc:
        raise _conflict_flat(exc) from exc
    except ValueError as exc:
        raise _flat(422, "invalid_field", str(exc)) from exc
    if ctx.caller_kind == "product" and fields:
        store.append_audit(
            agent.org_id, agent.id, actor_id(ctx), "conteudo_editado_mcp",
            {"kind": "definicao", "campos": sorted(fields)}, {"kind": "definicao", "campos": sorted(fields)},
        )
    return _definicao_out(updated)


@router.get("/plataforma/agents/{key}/grants", response_model=PlataformaGrantsOut)
def list_platform_definition_grants(
    key: str, ctx: AuthContext = Depends(require_platform_content_admin), store=Depends(get_studio_definition_store_dep),
) -> PlataformaGrantsOut:
    """The orgs explicitly granted this definition (the only orgs besides the open case that may hold an instance)."""
    agent = _definicao_ou_404(store, key)
    return PlataformaGrantsOut(key=key, instanciavel=agent.instanciavel, org_ids=store.list_definition_grants(agent.id))


@router.post("/plataforma/agents/{key}/grants", status_code=status.HTTP_201_CREATED, response_model=PlataformaGrantsOut)
def grant_platform_definition_org(
    key: str, payload: PlataformaGrantRequest, ctx: AuthContext = Depends(require_platform_content_admin),
    store=Depends(get_studio_definition_store_dep),
) -> PlataformaGrantsOut:
    """Grant ``payload.org_id`` the right to hold an instance of ``key`` (idempotent; audited when it creates). THE
    sanctioned way to give one org / app an agent -- never ``instanciavel=true`` on a product-owned definition."""
    agent = _definicao_ou_404(store, key)
    ator = actor_id(ctx)
    created = store.grant_definition_org(agent.id, payload.org_id, ator)
    if created:
        store.append_audit(
            agent.org_id, agent.id, ator, "conteudo_editado_mcp",
            {"kind": "grant", "org_id": None}, {"kind": "grant", "org_id": str(payload.org_id)},
        )
    return PlataformaGrantsOut(
        key=key, instanciavel=agent.instanciavel, org_ids=store.list_definition_grants(agent.id), created=created,
    )


__all__ = ["router", "require_content_write", "SCOPE_STUDIO_CONTENT_WRITE"]

"""Agent bundle importer (Agent Studio contract §D5, §F, §H7; slice BE-RT).

``AgentBundle`` is the strict ``noctus.agent-bundle/v1`` model: ``extra="forbid"``
at EVERY level (an unknown key is a 422 whose ``loc`` is the JSON path), the
same slug / ``caminho`` patterns and ``..`` ban as the definition routes, the
model/effort allowlists of 012, ``StrictBool`` tool policy, and bounded list
and field lengths.

:func:`import_bundle` semantics (§D5):

* creates the agent when absent (``definition_mode='studio'``, + an empty
  draft — the same two calls ``POST /api/studio/agents`` makes); refuses the
  reserved legacy keys and any legacy agent (409 ``not_studio_agent``, never a
  conversion);
* REPLACES the draft's settings, sections and skills (+ files) — creating the
  draft from the active version first when there is none; the active version
  is never touched;
* upserts knowledge collections + documents (documents keyed by
  ``source_sha``: unchanged ⇒ ``inalterados``, no revision), eval cases and
  clients by slug;
* NEVER publishes; refreshes the draft's ``compiled_hash`` at the end;
* ``dry_run`` performs ZERO writes and returns the same summary shape.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal
from uuid import UUID

from pydantic import Field, StrictBool, field_validator, model_validator

from app.schemas.studio import CAMINHO_PATTERN, SLUG_PATTERN, EntryTipo
from app.stores.agents import DEFAULT_AGENT_KEYS
from app.stores.errors import NotFound
from app.stores.studio_definitions import EFFORTS, MODELS, SectionInput
from app.stores.studio_knowledge import DOCUMENT_TYPES, CollectionInput, source_sha_of
from app.stores.studio_evals import EvalCaseInput
from noctusai_lib.api import StrictHttpModel

__all__ = [
    "BUNDLE_FORMAT",
    "MAX_BUNDLE_BYTES",
    "AgentBundle",
    "ImportRefused",
    "import_bundle",
]

BUNDLE_FORMAT = "noctus.agent-bundle/v1"
#: §D5 — the ONE route whose body cap is raised (``app.main``).
MAX_BUNDLE_BYTES = 25 * 1024 * 1024

ModelName = Literal[MODELS]  # type: ignore[valid-type]
EffortName = Literal[EFFORTS]  # type: ignore[valid-type]
DocumentTipo = Literal[DOCUMENT_TYPES]  # type: ignore[valid-type]

_Slug = Field(..., min_length=1, max_length=64, pattern=SLUG_PATTERN)


def _unique(values: list[str], what: str) -> None:
    seen: set[str] = set()
    for v in values:
        if v in seen:
            raise ValueError(f"{what} duplicado: {v!r}")
        seen.add(v)


# ── the bundle model (§F) ───────────────────────────────────────────────────


class BundleAgente(StrictHttpModel):
    key: str = _Slug
    nome: str = Field(..., min_length=1, max_length=200)
    descricao: str | None = Field(default=None, max_length=2000)


class BundleToolPolicy(StrictHttpModel):
    web_search: StrictBool = True
    knowledge: StrictBool = True


class BundleVersao(StrictHttpModel):
    notas: str | None = Field(default=None, max_length=5000)
    model: ModelName
    effort: EffortName
    max_turns: int = Field(default=40, ge=1, le=200)
    idioma: str = Field(default="pt-BR", min_length=1, max_length=16)
    tool_policy: BundleToolPolicy = Field(default_factory=BundleToolPolicy)


class BundleSecao(StrictHttpModel):
    chave: str = _Slug
    titulo: str = Field(..., min_length=1, max_length=300)
    ordem: int
    conteudo: str = Field(default="", max_length=100_000)
    ativo: StrictBool = True


class BundleArquivo(StrictHttpModel):
    caminho: str = Field(..., min_length=1, max_length=255, pattern=CAMINHO_PATTERN)
    titulo: str | None = Field(default=None, max_length=300)
    conteudo: str = Field(..., max_length=500_000)

    @field_validator("caminho")
    @classmethod
    def _no_parent_segments(cls, v: str) -> str:
        if ".." in v:
            raise ValueError("caminho must not contain '..'")
        return v


class BundleSkill(StrictHttpModel):
    nome: str = _Slug
    descricao: str = Field(..., min_length=1, max_length=1024)
    corpo: str = Field(default="", max_length=100_000)
    ordem: int = 0
    ativo: StrictBool = True
    arquivos: list[BundleArquivo] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def _unique_files(self) -> "BundleSkill":
        _unique([a.caminho for a in self.arquivos], "caminho")
        return self


class BundleProveniencia(StrictHttpModel):
    autor: str | None = Field(default=None, max_length=500)
    origem: str | None = Field(default=None, max_length=500)
    referencia: str | None = Field(default=None, max_length=2000)
    pagina: str | int | None = None
    licenca: str | None = Field(default=None, max_length=500)
    notas: str | None = Field(default=None, max_length=5000)


class BundleDocumento(StrictHttpModel):
    slug: str = Field(..., min_length=1, max_length=128, pattern=SLUG_PATTERN)
    titulo: str = Field(..., min_length=1, max_length=500)
    tipo: DocumentTipo
    resumo: str | None = Field(default=None, max_length=5000)
    proveniencia: BundleProveniencia = Field(default_factory=BundleProveniencia)
    conteudo: str = Field(..., min_length=1, max_length=900_000)


class BundleColecao(StrictHttpModel):
    slug: str = _Slug
    nome: str = Field(..., min_length=1, max_length=200)
    tag: str | None = Field(default=None, max_length=16)
    descricao: str = Field(default="", max_length=2000)
    ordem: int = 0
    documentos: list[BundleDocumento] = Field(default_factory=list, max_length=2000)


class BundleCriterios(StrictHttpModel):
    deve: list[str] = Field(default_factory=list, max_length=50)
    nao_deve: list[str] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def _shape(self) -> "BundleCriterios":
        if len(self.deve) + len(self.nao_deve) < 1:
            raise ValueError("criterios must contain at least one item across deve/nao_deve")
        for item in (*self.deve, *self.nao_deve):
            if not item.strip() or len(item) > 2000:
                raise ValueError("each criterio must be 1..2000 non-blank chars")
        return self


class BundleEval(StrictHttpModel):
    slug: str = _Slug
    titulo: str = Field(..., min_length=1, max_length=300)
    entrada: str = Field(..., min_length=1, max_length=20_000)
    contexto: str | None = Field(default=None, max_length=20_000)
    criterios: BundleCriterios
    rubrica: str | None = Field(default=None, max_length=10_000)
    tags: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("tags")
    @classmethod
    def _tags(cls, v: list[str]) -> list[str]:
        for t in v:
            if not t or len(t) > 64:
                raise ValueError("each tag must be 1..64 chars")
        return v


class BundleEntrada(StrictHttpModel):
    tipo: EntryTipo
    titulo: str = Field(..., min_length=1, max_length=300)
    conteudo: str = Field(default="", max_length=20_000)


class BundleCliente(StrictHttpModel):
    slug: str = _Slug
    nome: str = Field(..., min_length=1, max_length=200)
    resumo: str = Field(default="", max_length=50_000)
    entradas: list[BundleEntrada] = Field(default_factory=list, max_length=500)


class AgentBundle(StrictHttpModel):
    formato: Literal["noctus.agent-bundle/v1"]
    agente: BundleAgente
    versao: BundleVersao
    secoes: list[BundleSecao] = Field(default_factory=list, max_length=200)
    skills: list[BundleSkill] = Field(default_factory=list, max_length=100)
    conhecimento: list[BundleColecao] = Field(default_factory=list, max_length=50)
    evals: list[BundleEval] = Field(default_factory=list, max_length=500)
    clientes: list[BundleCliente] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def _unique_keys(self) -> "AgentBundle":
        _unique([s.chave for s in self.secoes], "secoes.chave")
        _unique([s.nome for s in self.skills], "skills.nome")
        _unique([c.slug for c in self.conhecimento], "conhecimento.slug")
        # knowledge_documents is unique on (agent_id, slug) — across collections.
        _unique([d.slug for c in self.conhecimento for d in c.documentos], "documentos.slug")
        _unique([e.slug for e in self.evals], "evals.slug")
        _unique([c.slug for c in self.clientes], "clientes.slug")
        return self


# ── the import ──────────────────────────────────────────────────────────────


class ImportRefused(Exception):
    """A bundle the importer refuses as a whole (``status`` + §D ``code``)."""

    def __init__(self, status: int, code: str, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.code = code
        self.detail = detail


@dataclass
class _Summary:
    dry_run: bool
    criado: bool = False
    version_id: UUID | None = None
    secoes: int = 0
    skills: int = 0
    arquivos: int = 0
    colecoes_criadas: int = 0
    documentos_criados: int = 0
    documentos_atualizados: int = 0
    documentos_inalterados: int = 0
    evals_criados: int = 0
    evals_atualizados: int = 0
    clientes_criados: int = 0
    avisos: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dry_run": self.dry_run,
            "agente": {"criado": self.criado},
            "rascunho": {
                "version_id": str(self.version_id) if self.version_id else None,
                "secoes": self.secoes,
                "skills": self.skills,
                "arquivos": self.arquivos,
            },
            "conhecimento": {
                "colecoes_criadas": self.colecoes_criadas,
                "documentos_criados": self.documentos_criados,
                "documentos_atualizados": self.documentos_atualizados,
                "documentos_inalterados": self.documentos_inalterados,
            },
            "evals": {"criados": self.evals_criados, "atualizados": self.evals_atualizados},
            "clientes": {"criados": self.clientes_criados},
            "avisos": list(self.avisos),
        }


def _skill_payload(skill: BundleSkill) -> dict[str, Any]:
    return {
        "nome": skill.nome,
        "descricao": skill.descricao,
        "corpo": skill.corpo,
        "ordem": skill.ordem,
        "ativo": skill.ativo,
        "arquivos": [{"caminho": a.caminho, "titulo": a.titulo, "conteudo": a.conteudo} for a in skill.arquivos],
    }


def _proveniencia(doc: BundleDocumento) -> dict[str, Any]:
    return doc.proveniencia.model_dump(exclude_none=True)


def import_bundle(
    bundle: AgentBundle,
    *,
    org_id: UUID,
    key: str,
    user_id: UUID,
    dry_run: bool,
    definitions: Any,
    knowledge: Any,
    evals: Any,
    catalog: Any,
) -> dict[str, Any]:
    """Apply (or, with ``dry_run``, plan) ``bundle`` for agent ``key``.

    Raises :class:`ImportRefused` for a whole-bundle refusal; store
    ``ValueError`` / ``StudioConflict`` propagate to the route's mapping."""
    if bundle.agente.key != key:
        raise ImportRefused(422, "key_mismatch", "A chave do pacote não corresponde à rota.")
    if key in DEFAULT_AGENT_KEYS:
        raise ImportRefused(409, "not_studio_agent", "Este agente não é gerenciado pelo Studio.")

    out = _Summary(dry_run=dry_run)
    out.secoes = len(bundle.secoes)
    out.skills = len(bundle.skills)
    out.arquivos = sum(len(s.arquivos) for s in bundle.skills)

    try:
        agent = definitions.get_agent(org_id, key)
    except NotFound:
        agent = None
    if agent is not None and agent.definition_mode != "studio":
        raise ImportRefused(409, "not_studio_agent", "Este agente não é gerenciado pelo Studio.")
    out.criado = agent is None

    if dry_run:
        _plan(bundle, agent, org_id=org_id, definitions=definitions, knowledge=knowledge, evals=evals, out=out)
        return out.to_dict()

    # ── agent + draft
    if agent is None:
        agent = definitions.create_studio_agent(org_id, key, bundle.agente.nome, bundle.agente.descricao)
        draft = definitions.create_draft(org_id, agent.id, None, user_id)
    else:
        draft = definitions.get_draft(org_id, agent.id)
        if draft is None:
            active = definitions.get_active_version(org_id, agent.id)
            draft = definitions.create_draft(org_id, agent.id, active.id if active else None, user_id)
    out.version_id = draft.id

    v = bundle.versao
    definitions.update_draft(
        org_id,
        draft.id,
        {
            "notas": v.notas,
            "model": v.model,
            "effort": v.effort,
            "max_turns": v.max_turns,
            "idioma": v.idioma,
            "tool_policy": {"web_search": v.tool_policy.web_search, "knowledge": v.tool_policy.knowledge},
        },
    )
    # One transactional entry point for the draft's content (sections +
    # skills + skill files) — provided by the definitions store.
    definitions.replace_draft_bundle(
        org_id,
        draft.id,
        [
            SectionInput(chave=s.chave, titulo=s.titulo, ordem=s.ordem, conteudo=s.conteudo, ativo=s.ativo)
            for s in bundle.secoes
        ],
        [_skill_payload(s) for s in bundle.skills],
    )

    # ── knowledge
    existing_cols = {c.slug: c for c in knowledge.list_collections(org_id, agent.id)}
    for col in bundle.conhecimento:
        current = existing_cols.get(col.slug)
        if current is None:
            current = knowledge.create_collection(
                org_id, agent.id,
                CollectionInput(slug=col.slug, nome=col.nome, tag=col.tag, descricao=col.descricao, ordem=col.ordem),
            )
            out.colecoes_criadas += 1
        elif (current.nome, current.tag, current.descricao, current.ordem) != (col.nome, col.tag, col.descricao, col.ordem):
            current = knowledge.update_collection(
                org_id, agent.id, current.id, nome=col.nome, tag=col.tag, descricao=col.descricao, ordem=col.ordem
            )
        for doc in col.documentos:
            _record, outcome = knowledge.upsert_document_by_source_sha(
                org_id, agent.id, current.id, slug=doc.slug, titulo=doc.titulo, tipo=doc.tipo,
                resumo=doc.resumo, proveniencia=_proveniencia(doc), conteudo=doc.conteudo, author_id=user_id,
            )
            if outcome == "created":
                out.documentos_criados += 1
            elif outcome == "updated":
                out.documentos_atualizados += 1
            else:
                out.documentos_inalterados += 1

    # ── evals
    existing_cases = {c.slug: c for c in evals.list_cases(org_id, agent.id)}
    for case in bundle.evals:
        criterios = {"deve": list(case.criterios.deve), "nao_deve": list(case.criterios.nao_deve)}
        current = existing_cases.get(case.slug)
        if current is None:
            evals.create_case(
                org_id, agent.id,
                EvalCaseInput(
                    slug=case.slug, titulo=case.titulo, entrada=case.entrada, criterios=criterios,
                    contexto=case.contexto, rubrica=case.rubrica, tags=tuple(case.tags),
                ),
            )
            out.evals_criados += 1
        elif _case_differs(current, case, criterios):
            evals.update_case(
                org_id, agent.id, current.id, titulo=case.titulo, entrada=case.entrada,
                contexto=case.contexto, criterios=criterios, rubrica=case.rubrica, tags=tuple(case.tags),
            )
            out.evals_atualizados += 1

    # ── clients (entries are only ever ADDED — UI-authored entries survive)
    existing_clients = {c.slug: c for c in definitions.list_clients(org_id, agent.id)}
    for cli in bundle.clientes:
        current = existing_clients.get(cli.slug)
        if current is None:
            current = definitions.create_client(org_id, agent.id, slug=cli.slug, nome=cli.nome, resumo=cli.resumo)
            out.clientes_criados += 1
            have: set[tuple[str, str]] = set()
        else:
            if (current.nome, current.resumo) != (cli.nome, cli.resumo):
                definitions.update_client(org_id, current.id, {"nome": cli.nome, "resumo": cli.resumo})
            have = {(e.tipo, e.titulo) for e in definitions.list_client_entries(org_id, current.id)}
        added = 0
        for entry in cli.entradas:
            if (entry.tipo, entry.titulo) in have:
                continue
            definitions.create_client_entry(
                org_id, current.id, tipo=entry.tipo, titulo=entry.titulo, conteudo=entry.conteudo
            )
            have.add((entry.tipo, entry.titulo))
            added += 1
        if added and cli.slug in existing_clients:
            out.avisos.append(f"cliente '{cli.slug}': {added} entrada(s) adicionada(s) ao existente")

    # ── refresh the draft's compiled_hash (§B1: refreshed on every draft save)
    from app.routers.studio_agents_router import compile_version

    draft = definitions.get_version(org_id, draft.id)
    compiled = compile_version(definitions, catalog, org_id, agent, draft)
    if draft.compiled_hash != compiled.hash:
        definitions.set_compiled_hash(org_id, draft.id, compiled.hash)
    for aviso in compiled.avisos:
        out.avisos.append(f"compilação: {aviso.mensagem}")
    return out.to_dict()


def _case_differs(current: Any, case: BundleEval, criterios: dict[str, Any]) -> bool:
    return (
        current.titulo, current.entrada, current.contexto, dict(current.criterios), current.rubrica,
        tuple(current.tags),
    ) != (case.titulo, case.entrada, case.contexto, criterios, case.rubrica, tuple(case.tags))


def _plan(
    bundle: AgentBundle, agent: Any, *, org_id: UUID, definitions: Any, knowledge: Any, evals: Any, out: _Summary
) -> None:
    """The dry-run: the same counters, computed from READS only."""
    if agent is None:
        out.colecoes_criadas = len(bundle.conhecimento)
        out.documentos_criados = sum(len(c.documentos) for c in bundle.conhecimento)
        out.evals_criados = len(bundle.evals)
        out.clientes_criados = len(bundle.clientes)
        return

    draft = definitions.get_draft(org_id, agent.id)
    out.version_id = draft.id if draft is not None else None
    if draft is None:
        out.avisos.append("um rascunho será criado a partir da versão ativa")

    existing_cols = {c.slug for c in knowledge.list_collections(org_id, agent.id)}
    for col in bundle.conhecimento:
        if col.slug not in existing_cols:
            out.colecoes_criadas += 1
        for doc in col.documentos:
            try:
                current = knowledge.get_document_by_slug(org_id, agent.id, doc.slug)
            except NotFound:
                out.documentos_criados += 1
                continue
            if current.source_sha == source_sha_of(doc.conteudo):
                out.documentos_inalterados += 1
            else:
                out.documentos_atualizados += 1

    existing_cases = {c.slug: c for c in evals.list_cases(org_id, agent.id)}
    for case in bundle.evals:
        criterios = {"deve": list(case.criterios.deve), "nao_deve": list(case.criterios.nao_deve)}
        current = existing_cases.get(case.slug)
        if current is None:
            out.evals_criados += 1
        elif _case_differs(current, case, criterios):
            out.evals_atualizados += 1

    existing_clients = {c.slug for c in definitions.list_clients(org_id, agent.id)}
    out.clientes_criados = sum(1 for c in bundle.clientes if c.slug not in existing_clients)

"""Agent Studio definitions store (contract §B1, §D1, §D2).

Seed IO shape: ``StudioDefinitionStore`` Protocol + ``FakeStudioDefinitionStore``
(in-memory, deterministic, emulates the 012 triggers + functions) +
``SupabaseStudioDefinitionStore`` (Real, admin client) +
``get_studio_definition_store(settings)`` factory. See
``KB § PATTERNS/backend/seed-fake-real-adapter.md``.

Covers: the studio columns of ``agents.agents``, ``agent_versions``,
``agent_prompt_sections``, ``agent_skills``, ``agent_skill_files``,
``agent_clients``, ``agent_client_entries``, ``compiled_prompts``.

Every method takes ``org_id`` explicitly and filters by it — routes use the
admin client (RLS bypassed by design), so this filter IS the authorization
boundary. A row of another org is indistinguishable from a missing one
(:class:`~app.stores.errors.NotFound` for both).

Version transitions go through the three SECURITY DEFINER functions of
``migrations/012_agent_studio_definitions.sql`` via ``.rpc()`` — one
PostgREST request = one Postgres transaction (same rationale as
``create_persona_version``). Immutability of published versions is enforced
by the DB triggers; the Real store maps their ``version_immutable`` raise to
:class:`VersionImmutable`, and the Fake raises the same error from the same
conditions so router tests exercise the real contract.

Hardening (wave-1 security review): every content write of a draft NULLs
its ``compiled_hash`` (the DB triggers; the Fake mirrors it), the routers
re-stamp it with a compare-and-set on ``updated_at``
(:meth:`StudioDefinitionStore.set_compiled_hash`), and ``publish_version``
refuses ``draft_changed`` unless the caller's gate-checked hash is still the
row's. Publish re-validates the eval gate in the DB, snapshots
``limiar_aplicado``/``eval_score`` and appends to ``agent_audit_log`` (so do
threshold changes and draft discards). Size caps (``app.studio.models.LIMITS``)
are validated here for Fake AND Real before any write.

Unbounded reads page through ``iter_paged_rows`` (PostgREST caps every
response at 1000 rows silently — ``KB § PATTERNS/backend/postgrest-row-cap.md``).
Cross-parent reads (a version's skill files, a client list's entry counts)
use PostgREST resource embedding instead of an ``.in_()`` id list, so no
URL-length batching is needed.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol
from uuid import UUID, uuid4

from app.stores._db_errors import StudioConflict, VersionImmutable, exec_query, exec_rpc
from app.stores._util import utcnow
from app.stores.errors import NotFound
from app.stores.studio_definitions_conteudo import ConteudoStore, FakeConteudoMixin, SupabaseConteudoMixin
from app.studio.models import LIMITS, PUBLICACAO_LIMIAR_MIN, override_reason_ok
from noctusai_lib.integrations.persistence.paging import iter_paged_rows

logger = logging.getLogger(__name__)

__all__ = [
    "STUDIO_RUNTIMES",
    "MODELS",
    "MODELS_BY_PROVIDER",
    "PROVIDERS",
    "EFFORTS",
    "VERSION_STATUSES",
    "CLIENT_ENTRY_TIPOS",
    "DRAFT_DEFAULTS",
    "StudioConflict",
    "VersionImmutable",
    "StudioAgentRecord",
    "VersionRecord",
    "SectionInput",
    "SectionRecord",
    "SkillRecord",
    "SkillFileRecord",
    "ClientRecord",
    "ClientEntryRecord",
    "CompiledPromptRecord",
    "AuditRecord",
    "SkillBundleInput",
    "SkillFileInput",
    "DraftBundleResult",
    "AUDIT_ACOES",
    "EXCLUSAO_CODIGOS",
    "DEFINITION_SCOPES",
    "ConteudoStore",
    "StudioDefinitionStore",
    "FakeStudioDefinitionStore",
    "SupabaseStudioDefinitionStore",
    "get_studio_definition_store",
]

_SCHEMA = "agents"

#: 012 `model` CHECK (§A10 — same allowlist as personas). Widened by
#: migration 015 to add `claude-haiku-4-5` (cheapest/fastest option); the
#: DRAFT_DEFAULTS model below stays `claude-opus-5` — this only adds an
#: option, it does not change anyone's current default.
ANTHROPIC_MODELS = ("claude-opus-5", "claude-sonnet-5", "claude-haiku-4-5")
#: Migration 024 — the OpenAI chat models the seed catalog lists
#: (`noctusai_lib.integrations.llm.models`; there is no `gpt-5`/`gpt-5-mini`
#: in it, so these are the names the seed actually prices).
OPENAI_MODELS = ("gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna")
#: Migration 024 `provider` CHECK + the provider-keyed `model` CHECK.
PROVIDERS = ("anthropic", "openai")
MODELS_BY_PROVIDER: dict[str, tuple[str, ...]] = {
    "anthropic": ANTHROPIC_MODELS,
    "openai": OPENAI_MODELS,
}
#: The ANTHROPIC allowlist under its historical name (012/015) — every
#: pre-024 consumer (the package importer, persona-shaped callers) keeps its
#: meaning. The provider-keyed allowlist the version CHECK enforces is
#: `MODELS_BY_PROVIDER`.
MODELS = ANTHROPIC_MODELS
#: 012 `effort` CHECK.
EFFORTS = ("low", "medium", "high", "xhigh", "max")
VERSION_STATUSES = ("rascunho", "ativa", "substituida")
CLIENT_ENTRY_TIPOS = (
    "marca", "publico", "posicionamento", "trava", "decisao", "aprendizado", "evidencia", "nota",
)
CLIENT_ENTRY_STATUSES = ("ativo", "arquivado")
#: `create_agent_draft` with no source (012).
DRAFT_DEFAULTS = {
    "provider": "anthropic",
    "model": "claude-opus-5",
    "effort": "high",
    "max_turns": 40,
    "idioma": "pt-BR",
    "tool_policy": {"web_search": True, "knowledge": True},
}

_AGENT_FIELDS = ("nome", "descricao", "ativo", "publicacao_limiar")
#: 049: what a platform DEFINITION carries as data (the former code registry): settable through
#: :meth:`StudioDefinitionStore.update_definicao` only -- never through the org-scope ``update_agent``.
_DEFINICAO_FIELDS = (
    "nome", "descricao", "runtime", "owner_product", "escopo_qualificacao", "padrao_qualificacao",
    "rascunho_padrao", "instanciavel", "papel",
)
PAPEIS = ("gerador", "exemplar")
_SLUG_ATTR_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")
#: The draft settings a definition's ``rascunho_padrao`` may carry (the version columns a fresh draft starts with).
_RASCUNHO_PADRAO_FIELDS = ("provider", "model", "effort", "max_turns", "idioma", "tool_policy")
_DRAFT_FIELDS = (
    "notas", "provider", "model", "effort", "max_turns", "idioma", "tool_policy",
    # 017 (Agent Packages §C4): the package identity the importer stamps.
    "versao_semver", "package_sha",
    # 032/040: the pinned qualification-standard version (a platform admin moves it; publish stamps it).
    "qualificacao_versao_id",
)
#: 017 `agents.kind` CHECK — immutable once the row exists.
AGENT_KINDS = ("runtime", "dev-advisor")
#: `agents.runtime` values a studio agent may be created with (024 CHECK minus
#: `external`, which means "another product runs it" and is never a studio agent).
STUDIO_RUNTIMES = ("claude_sdk", "llm")
_SEMVER_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
#: The version-row settings that feed the compile — changing one invalidates
#: a draft's ``compiled_hash`` (012 ``guard_agent_version_immutable``).
_COMPILED_SETTINGS = ("provider", "model", "effort", "max_turns", "idioma", "tool_policy", "qualificacao_versao_id")
#: 012 ``agent_audit_log.acao`` CHECK.
#: Extended by 031 (this slice's actions + the Julia v2 contract §5.1 list).
AUDIT_ACOES = (
    "limiar_alterado", "publicado", "publicado_override", "rascunho_descartado",
    "conteudo_editado_mcp", "specs_org_editadas", "definicao_lida",
    "modo_alterado", "conversa_pausada", "conversa_retomada", "padrao_publicado",
    "agente_excluido", "agente_criado", "agente_gerado",
)
#: 048 ``agents.excluir_agente`` guard codes (the 409 ``code`` of ``DELETE /api/studio/agents/{key}``).
EXCLUSAO_CODIGOS = ("publicado", "tem_instancias", "tem_conversas", "tem_canal", "ativo")
#: 031 ``agents.definition_scope`` CHECK.
DEFINITION_SCOPES = ("org", "plataforma", "instancia")
_SKILL_FIELDS = ("nome", "descricao", "corpo", "ordem", "ativo")
_CLIENT_FIELDS = ("slug", "nome", "resumo", "ativo")
_ENTRY_FIELDS = ("tipo", "titulo", "conteudo", "status")


# ── errors ──────────────────────────────────────────────────────────────────


# ``StudioConflict`` / ``VersionImmutable`` live in ``app.stores._db_errors``
# (shared by the three studio stores) and are re-exported here.


# ── records ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class StudioAgentRecord:
    id: UUID
    org_id: UUID
    key: str
    nome: str
    descricao: str | None
    definition_mode: str
    runtime: str
    ativo: bool
    publicacao_limiar: float
    created_at: datetime
    updated_at: datetime
    #: 017: ``runtime`` (IsaIA, Bia, ...) | ``dev-advisor`` (a package).
    kind: str = "runtime"
    #: 006: the product that owns the agent's transport (``social-wiring`` for
    #: ``julia``); ``None`` for agents agents itself serves.
    owner_product: str | None = None
    #: 031 (Julia v2): ``org`` = owns its versions (the default, every agent that predates v2) ·
    #: ``plataforma`` = THE definition of the key, in the platform org · ``instancia`` = an org's
    #: instance of a plataforma definition (no versions of its own; ``definition_agent_id``).
    definition_scope: str = "org"
    definition_agent_id: UUID | None = None
    #: 031: ``linhas`` = every compiler string is a row; ``legado`` = the pre-v2 strings.
    conteudo_modo: str = "legado"
    #: 049: what a platform DEFINITION carries as data (all NULL on every other row). The qualification SCOPE the
    #: agent works (a criterion's ``escopo`` is empty or equal to it; ``None`` = every scope), the qualification
    #: STANDARD key it works, and the settings its first draft starts with.
    escopo_qualificacao: str | None = None
    padrao_qualificacao: str | None = None
    rascunho_padrao: dict[str, Any] | None = None
    #: 049/050: a PUBLISHED definition is instantiated in every org only when this is true (closed by default;
    #: a product-owned definition is never true; the exception is an explicit ``definition_org_grants`` row).
    instanciavel: bool = False
    #: 049: ``gerador`` | ``exemplar`` | ``None`` -- the role a platform definition plays for a mechanism.
    papel: str | None = None

    @property
    def usa_canais(self) -> bool:
        """The agent runs on a channel transport (WhatsApp...): an ``llm`` runtime whose transport is owned by a
        product. The SAME rule the compiler (``canal = owner_product is not None``) and the channel API
        (``runtime == 'llm'``) apply -- derived from the definition's data, never from a key."""
        return self.owner_product is not None and self.runtime == "llm"


@dataclass(frozen=True)
class VersionRecord:
    id: UUID
    org_id: UUID
    agent_id: UUID
    versao: int
    status: str
    notas: str | None
    model: str
    effort: str
    max_turns: int
    idioma: str
    tool_policy: dict[str, Any]
    based_on_version_id: UUID | None
    created_by: UUID
    published_by: UUID | None
    published_at: datetime | None
    compiled_hash: str | None
    eval_run_id: UUID | None
    publish_override_reason: str | None
    created_at: datetime
    updated_at: datetime
    #: H2 snapshots, set by ``publish_agent_version`` (NULL on a draft).
    limiar_aplicado: float | None = None
    eval_score: float | None = None
    #: 017 (§C4): package identity recorded by the importer (NULL otherwise).
    versao_semver: str | None = None
    package_sha: str | None = None
    #: 024: the LLM provider the version runs on (`anthropic` unless chosen).
    provider: str = "anthropic"
    #: 032: the published qualification-standard version this agent version pins (NULL = not pinned yet;
    #: the channel turn then uses the newest published version of the agent's standard).
    qualificacao_versao_id: UUID | None = None


@dataclass(frozen=True)
class SectionInput:
    chave: str
    titulo: str
    ordem: int
    conteudo: str = ""
    ativo: bool = True
    id: UUID | None = None


@dataclass(frozen=True)
class SectionRecord:
    id: UUID
    org_id: UUID
    version_id: UUID
    chave: str
    titulo: str
    ordem: int
    conteudo: str
    ativo: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class SkillRecord:
    id: UUID
    org_id: UUID
    version_id: UUID
    nome: str
    descricao: str
    corpo: str
    ordem: int
    ativo: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class SkillFileRecord:
    id: UUID
    org_id: UUID
    skill_id: UUID
    caminho: str
    titulo: str | None
    conteudo: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class ClientRecord:
    id: UUID
    org_id: UUID
    agent_id: UUID
    slug: str
    nome: str
    resumo: str
    ativo: bool
    created_at: datetime
    updated_at: datetime
    #: Filled by :meth:`StudioDefinitionStore.list_clients` only.
    total_entradas: int | None = None


@dataclass(frozen=True)
class ClientEntryRecord:
    id: UUID
    org_id: UUID
    client_id: UUID
    tipo: str
    titulo: str
    conteudo: str
    status: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class CompiledPromptRecord:
    id: UUID
    org_id: UUID
    hash: str
    version_id: UUID
    client_id: UUID | None
    texto: str
    manifest: list[dict[str, Any]]
    created_at: datetime


@dataclass(frozen=True)
class AuditRecord:
    id: UUID
    org_id: UUID
    #: ``None`` once the agent was deleted (048: the FK is ON DELETE SET NULL; the row outlives the agent).
    agent_id: UUID | None
    actor: UUID | None
    acao: str
    antes: dict[str, Any] | None
    depois: dict[str, Any] | None
    created_at: datetime
    #: 048 snapshot of the agent's identity, so a row still names its agent after the agent is gone.
    agent_key: str | None = None
    agent_nome: str | None = None


@dataclass(frozen=True)
class SkillFileInput:
    caminho: str
    titulo: str | None = None
    conteudo: str = ""


@dataclass(frozen=True)
class SkillBundleInput:
    """One skill of :meth:`StudioDefinitionStore.replace_draft_bundle`."""

    nome: str
    descricao: str
    corpo: str = ""
    ordem: int = 0
    ativo: bool = True
    arquivos: tuple[SkillFileInput, ...] = ()


@dataclass(frozen=True)
class DraftBundleResult:
    secoes: int
    skills: int
    arquivos: int


# ── validation shared by Fake + Real (mirrors the 012 CHECKs) ──────────────


def _check_cap(value: str | None, key: str, what: str) -> None:
    """M3 size caps — the same numbers as the 012/013 CHECKs."""
    limit = LIMITS[key]
    if value is not None and len(value) > limit:
        raise ValueError(f"{what} exceeds {limit} characters ({len(value)})")


def _validate_agent_fields(fields: dict[str, Any]) -> None:
    _check_fields(fields, _AGENT_FIELDS, "agent")
    if "publicacao_limiar" in fields:
        limiar = float(fields["publicacao_limiar"])
        if not (PUBLICACAO_LIMIAR_MIN <= limiar <= 1):
            raise ValueError(f"publicacao_limiar must be between {PUBLICACAO_LIMIAR_MIN} and 1")


def _validate_definicao_fields(fields: dict[str, Any]) -> None:
    _check_fields(fields, _DEFINICAO_FIELDS, "definition")
    if "runtime" in fields and fields["runtime"] not in STUDIO_RUNTIMES:
        raise ValueError(f"runtime must be one of {STUDIO_RUNTIMES}; got {fields['runtime']!r}")
    for k in ("escopo_qualificacao", "padrao_qualificacao"):
        v = fields.get(k)
        if v is not None and not _SLUG_ATTR_RE.match(str(v)):
            raise ValueError(f"{k} must match {_SLUG_ATTR_RE.pattern}")
    if fields.get("rascunho_padrao") is not None:
        validar_rascunho_padrao(fields["rascunho_padrao"])
    if fields.get("papel") is not None and fields["papel"] not in PAPEIS:
        raise ValueError(f"papel must be one of {PAPEIS}")
    if "instanciavel" in fields and not isinstance(fields["instanciavel"], bool):
        raise ValueError("instanciavel must be a boolean")


def _check_not_owned_and_open(owner_product: str | None, instanciavel: bool) -> None:
    """050 CHECK ``agents_product_owned_not_instanciavel``: a product-owned definition is never instantiated in every
    org -- another org's / app's configuration is reachable only through an explicit ``definition_org_grants`` row."""
    if owner_product is not None and instanciavel:
        raise ValueError(
            "instanciavel=true is refused for a product-owned definition (owner_product set): grant the orgs "
            "explicitly (definition_org_grants) instead of opening it to every org"
        )


def validar_rascunho_padrao(settings: Any) -> None:
    """The first-draft settings of a definition: only version setting names, each valid for a version."""
    if not isinstance(settings, dict):
        raise ValueError("rascunho_padrao must be an object")
    _check_fields(settings, _RASCUNHO_PADRAO_FIELDS, "rascunho_padrao")
    _validate_draft_fields(dict(settings))


def _validate_section(s: "SectionInput") -> None:
    _check_cap(s.conteudo, "section.conteudo", "section conteudo")


def _validate_skill_fields(fields: dict[str, Any]) -> None:
    _check_cap(fields.get("corpo"), "skill.corpo", "skill corpo")


def _validate_client_fields(fields: dict[str, Any]) -> None:
    _check_cap(fields.get("resumo"), "client.resumo", "client resumo")


def _validate_entry_caps(fields: dict[str, Any]) -> None:
    _check_cap(fields.get("titulo"), "entry.titulo", "entry titulo")
    _check_cap(fields.get("conteudo"), "entry.conteudo", "entry conteudo")


def _as_section_input(item: Any) -> "SectionInput":
    if isinstance(item, SectionInput):
        return item
    d = dict(item)
    return SectionInput(
        chave=d["chave"], titulo=d["titulo"], ordem=int(d.get("ordem", 0)),
        conteudo=d.get("conteudo") or "", ativo=bool(d.get("ativo", True)),
    )


def _as_skill_input(item: Any) -> SkillBundleInput:
    if isinstance(item, SkillBundleInput):
        return item
    d = dict(item)
    arquivos = tuple(
        f if isinstance(f, SkillFileInput)
        else SkillFileInput(caminho=dict(f)["caminho"], titulo=dict(f).get("titulo"), conteudo=dict(f).get("conteudo") or "")
        for f in (d.get("arquivos") or ())
    )
    return SkillBundleInput(
        nome=d["nome"], descricao=d["descricao"], corpo=d.get("corpo") or "",
        ordem=int(d.get("ordem", 0)), ativo=bool(d.get("ativo", True)), arquivos=arquivos,
    )


def _validate_bundle(secoes: list["SectionInput"], skills: list[SkillBundleInput]) -> None:
    """The whole bundle is checked BEFORE any write (Fake and Real alike),
    so a bad element never half-applies a replace."""
    chaves = [s.chave for s in secoes]
    if len(set(chaves)) != len(chaves):
        raise StudioConflict("chave_conflict", "duplicate chave in payload")
    nomes = [sk.nome for sk in skills]
    if len(set(nomes)) != len(nomes):
        raise StudioConflict("skill_exists", "duplicate skill nome in payload")
    for s in secoes:
        _validate_section(s)
    for sk in skills:
        _validate_skill_fields({"corpo": sk.corpo})
        caminhos = [f.caminho for f in sk.arquivos]
        if len(set(caminhos)) != len(caminhos):
            raise StudioConflict("caminho_conflict", f"duplicate caminho in skill {sk.nome!r}")
        for f in sk.arquivos:
            _check_cap(f.conteudo, "skill_file.conteudo", "skill file conteudo")


def _validate_draft_fields(
    fields: dict[str, Any], *, current_provider: str = "anthropic", current_model: str | None = None,
) -> None:
    """``current_*`` are the draft's stored provider/model — consulted only
    when a request changes ONE of the pair, so the provider-keyed allowlist
    (024's CHECK) is enforced on the effective (provider, model) pair rather
    than on whichever half the request happened to carry."""
    unknown = set(fields) - set(_DRAFT_FIELDS)
    if unknown:
        raise ValueError(f"unknown draft fields: {sorted(unknown)}")
    if "provider" in fields and fields["provider"] not in PROVIDERS:
        raise ValueError(f"provider must be one of {PROVIDERS}; got {fields['provider']!r}")
    if "model" in fields or "provider" in fields:
        provider = fields.get("provider", current_provider)
        model = fields.get("model", current_model)
        allowed = MODELS_BY_PROVIDER[provider]
        if model not in allowed:
            raise ValueError(f"model must be one of {allowed} for provider {provider!r}; got {model!r}")
    if "effort" in fields and fields["effort"] not in EFFORTS:
        raise ValueError(f"effort must be one of {EFFORTS}; got {fields['effort']!r}")
    if "max_turns" in fields and not (1 <= int(fields["max_turns"]) <= 200):
        raise ValueError(f"max_turns must be between 1 and 200; got {fields['max_turns']!r}")
    if "tool_policy" in fields and not isinstance(fields["tool_policy"], dict):
        raise ValueError("tool_policy must be an object")
    pin = fields.get("qualificacao_versao_id")
    if pin is not None and not isinstance(pin, UUID):
        raise ValueError("qualificacao_versao_id must be a UUID or null")
    semver = fields.get("versao_semver")
    if semver is not None and not _SEMVER_RE.match(str(semver)):
        raise ValueError(f"versao_semver must be a semver; got {semver!r}")
    sha = fields.get("package_sha")
    if sha is not None and not _SHA256_RE.match(str(sha)):
        raise ValueError("package_sha must be 64 lowercase hex chars")


def _validate_entry(fields: dict[str, Any]) -> None:
    if "tipo" in fields and fields["tipo"] not in CLIENT_ENTRY_TIPOS:
        raise ValueError(f"tipo must be one of {CLIENT_ENTRY_TIPOS}; got {fields['tipo']!r}")
    if "status" in fields and fields["status"] not in CLIENT_ENTRY_STATUSES:
        raise ValueError(f"status must be one of {CLIENT_ENTRY_STATUSES}; got {fields['status']!r}")


def _check_fields(fields: dict[str, Any], allowed: tuple[str, ...], what: str) -> None:
    unknown = set(fields) - set(allowed)
    if unknown:
        raise ValueError(f"unknown {what} fields: {sorted(unknown)}")


def _validate_scope(definition_scope: str, definition_agent_id: UUID | None) -> str:
    """The 031 CHECKs: a known scope; ``definition_agent_id`` iff ``instancia``. Returns the
    ``conteudo_modo`` the row gets (a platform-defined agent is always ``linhas``)."""
    if definition_scope not in DEFINITION_SCOPES:
        raise ValueError(f"definition_scope must be one of {DEFINITION_SCOPES}; got {definition_scope!r}")
    if (definition_scope == "instancia") != (definition_agent_id is not None):
        raise ValueError("definition_agent_id is required for (and only for) an 'instancia' agent")
    return "legado" if definition_scope == "org" else "linhas"


# ── Protocol ────────────────────────────────────────────────────────────────


class StudioDefinitionStore(ConteudoStore, Protocol):
    # agents (studio columns)
    def list_agents(self, org_id: UUID) -> list[StudioAgentRecord]: ...
    def get_agent(self, org_id: UUID, key: str) -> StudioAgentRecord: ...
    def create_studio_agent(
        self, org_id: UUID, key: str, nome: str, descricao: str | None, *, kind: str = "runtime",
        runtime: str = "claude_sdk", owner_product: str | None = None,
        definition_scope: str = "org", definition_agent_id: UUID | None = None,
        escopo_qualificacao: str | None = None, padrao_qualificacao: str | None = None,
        rascunho_padrao: dict[str, Any] | None = None, instanciavel: bool = False, papel: str | None = None,
    ) -> StudioAgentRecord:
        """``definition_mode='studio'``, ``ativo=false``, ``runtime`` (default
        ``claude_sdk`` — the studio UI's only choice; ``llm`` is created by the
        seeded provider-neutral agents), ``kind`` (017; immutable afterwards).
        Raises ``StudioConflict('key_taken')``."""
        ...
    def is_platform_org(self, org_id: UUID) -> bool:
        """``organizations.is_platform`` of ``org_id`` (where platform definitions live)."""
        ...
    def update_definicao(self, org_id: UUID, key: str, fields: dict[str, Any]) -> StudioAgentRecord:
        """Write the DATA a platform definition carries (:data:`_DEFINICAO_FIELDS`: nome / descricao / runtime /
        owner_product / escopo + padrao de qualificação / first-draft settings / instanciavel). Only a
        ``definition_scope='plataforma'`` row; anything else raises ``ValueError``."""
        ...
    def update_agent(
        self, org_id: UUID, key: str, fields: dict[str, Any], *, actor: UUID | None = None
    ) -> StudioAgentRecord:
        """A ``publicacao_limiar`` change goes through
        ``agents.set_agent_publicacao_limiar`` so the audit row carries
        ``actor``; floor :data:`PUBLICACAO_LIMIAR_MIN` (ValueError below)."""
        ...
    def list_audit_log(self, org_id: UUID, agent_id: UUID) -> list[AuditRecord]:
        """Newest first."""
        ...
    def delete_agent(self, org_id: UUID, agent_id: UUID, *, actor: UUID | None = None) -> None:
        """Delete the agent and its (draft-only) dependents; its audit rows survive with ``agent_id`` NULL plus an
        ``agente_excluido`` tombstone (048 ``agents.excluir_agente``). Raises ``NotFound`` or
        ``StudioConflict`` with ``code`` in :data:`EXCLUSAO_CODIGOS` (``publicado`` / ``tem_instancias`` /
        ``tem_conversas`` / ``tem_canal`` / ``ativo``)."""
        ...

    # versions
    def list_versions(self, org_id: UUID, agent_id: UUID) -> list[VersionRecord]:
        """Newest first."""
        ...
    def get_version(self, org_id: UUID, version_id: UUID) -> VersionRecord: ...
    def get_draft(self, org_id: UUID, agent_id: UUID) -> VersionRecord | None: ...
    def get_active_version(self, org_id: UUID, agent_id: UUID) -> VersionRecord | None: ...
    def create_draft(
        self, org_id: UUID, agent_id: UUID, source_version_id: UUID | None, created_by: UUID
    ) -> VersionRecord:
        """``agents.create_agent_draft``. Raises ``StudioConflict('draft_exists')``."""
        ...
    def update_draft(self, org_id: UUID, version_id: UUID, fields: dict[str, Any]) -> VersionRecord:
        """Raises ``ValueError`` on an allowlist violation, :class:`VersionImmutable`
        on a non-draft."""
        ...
    def set_compiled_hash(
        self, org_id: UUID, version_id: UUID, compiled_hash: str, *, expected_updated_at: Any = None,
    ) -> VersionRecord:
        """Stamp a draft's hash. With ``expected_updated_at`` it is a
        compare-and-set: a row whose ``updated_at`` moved since the caller
        read it (a concurrent content write) raises
        ``StudioConflict('draft_changed')`` instead of stamping a hash
        computed from stale content (M1)."""
        ...
    def publish_version(
        self, org_id: UUID, version_id: UUID, published_by: UUID,
        eval_run_id: UUID | None, override_reason: str | None, *, expected_hash: str,
        texto: str, manifest: list[dict[str, Any]],
    ) -> VersionRecord:
        """``agents.publish_agent_version`` — ONE transaction that stores the
        proof-of-use ``compiled_prompts`` row (``texto``/``manifest`` under
        ``expected_hash``, idempotent by hash), flips the versions,
        snapshots ``limiar_aplicado`` + ``eval_score`` and writes the audit
        row. Raises ``StudioConflict('draft_changed')`` unless
        ``expected_hash`` is the draft's current ``compiled_hash``,
        ``StudioConflict('eval_required')`` when the DB-side gate re-check
        fails."""
        ...
    def discard_draft(self, org_id: UUID, version_id: UUID, *, actor: UUID | None = None) -> None: ...

    # sections
    def list_sections(self, org_id: UUID, version_id: UUID) -> list[SectionRecord]: ...
    def replace_sections(
        self, org_id: UUID, version_id: UUID, secoes: list[SectionInput]
    ) -> list[SectionRecord]:
        """Full replace in ONE transaction (``agents.replace_draft_sections``);
        an input ``id`` of an existing section of THIS version keeps that id,
        anything else gets a new one."""
        ...
    def replace_draft_bundle(
        self, org_id: UUID, version_id: UUID, secoes: list[Any], skills: list[Any],
    ) -> DraftBundleResult:
        """ATOMIC replacement of a draft's sections + skills + skill files
        (``agents.replace_draft_bundle`` — one transaction; the importer's
        write). ``secoes`` items: :class:`SectionInput` or mappings with
        ``chave, titulo, ordem, conteudo, ativo``; ``skills`` items:
        :class:`SkillBundleInput` or mappings with ``nome, descricao, corpo,
        ordem, ativo, arquivos: [{caminho, titulo, conteudo}]``."""
        ...

    # skills + files
    def list_skills(self, org_id: UUID, version_id: UUID) -> list[SkillRecord]: ...
    def get_skill(self, org_id: UUID, skill_id: UUID) -> SkillRecord: ...
    def create_skill(
        self, org_id: UUID, version_id: UUID, *, nome: str, descricao: str, corpo: str,
        ordem: int = 0, ativo: bool = True,
    ) -> SkillRecord:
        """Raises ``StudioConflict('skill_exists')``."""
        ...
    def update_skill(
        self, org_id: UUID, skill_id: UUID, fields: dict[str, Any], *, expected_hash: str | None = None,
    ) -> SkillRecord:
        """``expected_hash`` (the draft's ``compiled_hash`` as last read) is the optimistic lock (041
        ``update_draft_skill``): a different current hash raises ``StudioConflict('conflito_de_versao')`` and nothing
        is written. ``None`` = no check."""
        ...
    def delete_skill(self, org_id: UUID, skill_id: UUID) -> None: ...
    def list_version_skill_files(self, org_id: UUID, version_id: UUID) -> list[SkillFileRecord]: ...
    def get_skill_file(self, org_id: UUID, file_id: UUID) -> SkillFileRecord: ...
    def upsert_skill_file(
        self, org_id: UUID, skill_id: UUID, *, caminho: str, titulo: str | None, conteudo: str
    ) -> SkillFileRecord: ...
    def delete_skill_file(self, org_id: UUID, file_id: UUID) -> None: ...

    # clients
    def list_clients(self, org_id: UUID, agent_id: UUID) -> list[ClientRecord]: ...
    def get_client(self, org_id: UUID, client_id: UUID) -> ClientRecord: ...
    def create_client(
        self, org_id: UUID, agent_id: UUID, *, slug: str, nome: str, resumo: str = "", ativo: bool = True
    ) -> ClientRecord:
        """Raises ``StudioConflict('client_exists')``."""
        ...
    def update_client(self, org_id: UUID, client_id: UUID, fields: dict[str, Any]) -> ClientRecord: ...
    def list_client_entries(self, org_id: UUID, client_id: UUID) -> list[ClientEntryRecord]:
        """Oldest first (``created_at``, ``id``) — the compiler keeps this order."""
        ...
    def get_client_entry(self, org_id: UUID, entry_id: UUID) -> ClientEntryRecord: ...
    def create_client_entry(
        self, org_id: UUID, client_id: UUID, *, tipo: str, titulo: str, conteudo: str = "",
        status: str = "ativo",
    ) -> ClientEntryRecord: ...
    def update_client_entry(self, org_id: UUID, entry_id: UUID, fields: dict[str, Any]) -> ClientEntryRecord: ...
    def delete_client_entry(self, org_id: UUID, entry_id: UUID) -> None: ...

    # compiled prompts (write-once)
    def save_compiled_prompt(
        self, org_id: UUID, *, hash: str, version_id: UUID, client_id: UUID | None,
        texto: str, manifest: list[dict[str, Any]],
    ) -> CompiledPromptRecord:
        """Idempotent by ``(org_id, hash)`` — an existing row is returned
        untouched (never updated)."""
        ...
    def get_compiled_prompt(self, org_id: UUID, hash: str) -> CompiledPromptRecord: ...
    # package tree (017) — the materialised Claude Code tree of a version
    def get_package_tree(self, org_id: UUID, version_id: UUID) -> list[dict[str, str]] | None:
        """``[{"caminho", "conteudo"}]`` or ``None`` when the version has none."""
        ...
    def set_package_tree(
        self, org_id: UUID, agent_id: UUID, version_id: UUID, files: list[dict[str, str]]
    ) -> None:
        """Replace the tree of a DRAFT (raises :class:`VersionImmutable` otherwise)."""
        ...
    def erase_client_compiled_prompts(self, org_id: UUID, client_id: UUID) -> int:
        """LGPD erasure (``agents.erase_compiled_prompts``) — the ONLY
        deletion path for compiled prompts. Returns the rows erased."""
        ...


# ── Fake ────────────────────────────────────────────────────────────────────


class FakeStudioDefinitionStore(FakeConteudoMixin):
    """In-memory :class:`StudioDefinitionStore`.

    Emulates 012: the partial uniques (one rascunho / one ativa), the
    immutability triggers (children of a non-draft raise
    :class:`VersionImmutable`), the draft-hash invalidation (every content
    write NULLs the draft's ``compiled_hash`` and moves its ``updated_at``),
    the client-entry cap, the deep-copy of ``create_agent_draft``, and
    ``publish_agent_version``'s hash check + DB-side gate re-check + snapshot
    + audit. The eval runs the DB function reads live in BE-KE's tables —
    tests register the ones publish may see with :meth:`register_eval_run`.

    ``agents`` rows are keyed by ``(org_id, key)``. Tests that also exercise
    legacy agents seed them with :meth:`add_legacy_agent` (the legacy rows
    otherwise live in ``AgentStore``'s own Fake).
    """

    def __init__(self) -> None:
        self._agents: dict[tuple[UUID, str], StudioAgentRecord] = {}
        self._versions: dict[UUID, VersionRecord] = {}
        self._sections: dict[UUID, SectionRecord] = {}
        self._skills: dict[UUID, SkillRecord] = {}
        self._files: dict[UUID, SkillFileRecord] = {}
        self._clients: dict[UUID, ClientRecord] = {}
        self._entries: dict[UUID, ClientEntryRecord] = {}
        self._compiled: dict[tuple[UUID, str], CompiledPromptRecord] = {}
        self._audit: list[AuditRecord] = []
        #: version_id -> the 017 `agent_package_trees.files` of that version.
        self._trees: dict[UUID, list[dict[str, str]]] = {}
        #: run_id -> the `eval_runs` columns publish_agent_version reads.
        self._eval_runs: dict[UUID, dict[str, Any]] = {}
        #: agent_id -> number of active eval cases (publish needs >= 1).
        self._active_cases: dict[UUID, int] = {}
        self._seq = 0
        #: agents whose history lives in stores this Fake does not model (048 guards, see ``mark_*``).
        self._com_mensagens: set[UUID] = set()
        self._com_canal: set[UUID] = set()
        #: orgs flagged ``organizations.is_platform`` (031: a platform definition lives there).
        self._platform_orgs: set[UUID] = set()
        self._init_conteudo()

    def _now(self) -> datetime:
        # Strictly increasing timestamps keep "newest first"/"oldest first"
        # orderings deterministic within one fast test.
        from datetime import timedelta

        self._seq += 1
        return utcnow() + timedelta(microseconds=self._seq)

    # ── test helpers
    def register_eval_run(
        self, org_id: UUID, version_id: UUID, *, score: float | None, compiled_hash: str,
        completa: bool = True, total: int = 1, status: str = "concluida", active_cases: int = 1,
        run_id: UUID | None = None,
    ) -> UUID:
        """Make an ``eval_runs`` row visible to :meth:`publish_version`'s
        DB-side gate re-check (the Real function reads BE-KE's table)."""
        v = self.get_version(org_id, version_id)
        rid = run_id or uuid4()
        self._eval_runs[rid] = {
            "org_id": org_id, "version_id": version_id, "score": score, "compiled_hash": compiled_hash,
            "completa": completa, "total": total, "status": status,
        }
        self._active_cases[v.agent_id] = active_cases
        return rid

    def _audit_append(
        self, org_id: UUID, agent_id: UUID, actor: UUID | None, acao: str,
        antes: dict[str, Any] | None, depois: dict[str, Any] | None,
    ) -> None:
        # 048 `audit_log_snapshot_agent` BEFORE INSERT trigger.
        agent = next((a for a in self._agents.values() if a.id == agent_id), None)
        self._audit.append(AuditRecord(
            id=uuid4(), org_id=org_id, agent_id=agent_id, actor=actor, acao=acao,
            antes=antes, depois=depois, created_at=self._now(),
            agent_key=agent.key if agent else None, agent_nome=agent.nome if agent else None,
        ))

    def _touch_draft(self, version_id: UUID) -> None:
        """012 child triggers: a content write under a draft NULLs its
        ``compiled_hash`` (and, being an UPDATE, moves ``updated_at``)."""
        v = self._versions.get(version_id)
        if v is not None and v.status == "rascunho":
            self._versions[version_id] = replace(v, compiled_hash=None, updated_at=self._now())

    def mark_agent_has_messages(self, agent_id: UUID) -> None:
        """Test helper: the agent has a conversation with >= 1 message (``excluir_agente`` -> ``tem_conversas``)."""
        self._com_mensagens.add(agent_id)

    def mark_agent_has_channel(self, agent_id: UUID) -> None:
        """Test helper: an active channel token names the agent as principal (``excluir_agente`` -> ``tem_canal``)."""
        self._com_canal.add(agent_id)

    def audit_log_all(self) -> list[AuditRecord]:
        """Test helper: every audit row of the Fake, oldest first (including tombstones with ``agent_id`` None)."""
        return list(self._audit)

    def mark_platform_org(self, org_id: UUID) -> None:
        """Test helper: flag ``org_id`` as the platform org (``organizations.is_platform``)."""
        self._platform_orgs.add(org_id)

    def is_platform_org(self, org_id: UUID) -> bool:
        return org_id in self._platform_orgs

    def add_legacy_agent(self, org_id: UUID, key: str, nome: str) -> StudioAgentRecord:
        return self.seed_agent(org_id, key, nome=nome, definition_mode="legacy", ativo=False)

    def seed_agent(
        self, org_id: UUID, key: str, *, agent_id: UUID | None = None, nome: str | None = None,
        definition_mode: str = "studio", ativo: bool = True, publicacao_limiar: float = 0.8,
        kind: str = "runtime", conteudo_modo: str = "legado", definition_scope: str = "org",
    ) -> StudioAgentRecord:
        """Test helper: an ``agents.agents`` row with explicit columns (the
        knowledge/eval router suites resolve agents through this store)."""
        now = self._now()
        rec = StudioAgentRecord(
            id=agent_id or uuid4(), org_id=org_id, key=key, nome=nome or key, descricao=None,
            definition_mode=definition_mode, runtime="claude_sdk", ativo=ativo,
            publicacao_limiar=publicacao_limiar, created_at=now, updated_at=now, kind=kind,
            conteudo_modo=conteudo_modo, definition_scope=definition_scope,
        )
        self._agents[(org_id, key)] = rec
        return rec

    # ── agents
    def list_agents(self, org_id: UUID) -> list[StudioAgentRecord]:
        return sorted(
            (a for (o, _), a in self._agents.items() if o == org_id), key=lambda a: a.key
        )

    def get_agent(self, org_id: UUID, key: str) -> StudioAgentRecord:
        rec = self._agents.get((org_id, key))
        if rec is None:
            raise NotFound(f"agent {key!r} not found")
        return rec

    def create_studio_agent(
        self, org_id: UUID, key: str, nome: str, descricao: str | None, *, kind: str = "runtime",
        runtime: str = "claude_sdk", owner_product: str | None = None,
        definition_scope: str = "org", definition_agent_id: UUID | None = None,
        escopo_qualificacao: str | None = None, padrao_qualificacao: str | None = None,
        rascunho_padrao: dict[str, Any] | None = None, instanciavel: bool = False, papel: str | None = None,
    ) -> StudioAgentRecord:
        if kind not in AGENT_KINDS:
            raise ValueError(f"kind must be one of {AGENT_KINDS}; got {kind!r}")
        if runtime not in STUDIO_RUNTIMES:
            raise ValueError(f"runtime must be one of {STUDIO_RUNTIMES}; got {runtime!r}")
        modo = _validate_scope(definition_scope, definition_agent_id)
        attrs = {
            "escopo_qualificacao": escopo_qualificacao, "padrao_qualificacao": padrao_qualificacao,
            "rascunho_padrao": rascunho_padrao, "papel": papel,
        }
        if definition_scope != "plataforma" and any(v is not None for v in attrs.values()):
            raise ValueError("escopo/padrao de qualificação and rascunho_padrao belong to a platform definition")
        _validate_definicao_fields({k: v for k, v in attrs.items() if v is not None})
        if (org_id, key) in self._agents:
            raise StudioConflict("key_taken", f"agent key {key!r} already exists")
        # 031 `guard_agent_definition_scope`
        if definition_scope == "plataforma":
            if org_id not in self._platform_orgs:
                raise StudioConflict("definition_not_platform", "a platform definition lives in the platform org")
            if self.get_platform_definition(key) is not None:
                raise StudioConflict("key_taken", f"platform definition {key!r} already exists")
        elif definition_scope == "instancia":
            definition = self.get_agent_by_id(definition_agent_id)
            if definition.definition_scope != "plataforma" or definition.key != key:
                raise StudioConflict("definition_invalid", "the definition must be the platform row of the same key")
            # 050 `guard_agent_definition_scope`: a closed definition is held only by granted orgs
            if not definition.instanciavel and not self.is_definition_granted(definition.id, org_id):
                raise StudioConflict("definition_not_granted", "the org was not granted this definition")
        if definition_scope == "plataforma":
            _check_not_owned_and_open(owner_product, instanciavel)
        now = self._now()
        rec = StudioAgentRecord(
            id=uuid4(), org_id=org_id, key=key, nome=nome, descricao=descricao,
            definition_mode="studio", runtime=runtime, ativo=False,
            publicacao_limiar=0.8, created_at=now, updated_at=now, kind=kind,
            owner_product=owner_product, definition_scope=definition_scope,
            definition_agent_id=definition_agent_id, conteudo_modo=modo,
            escopo_qualificacao=escopo_qualificacao, padrao_qualificacao=padrao_qualificacao,
            rascunho_padrao=dict(rascunho_padrao) if rascunho_padrao is not None else None,
            instanciavel=instanciavel, papel=papel,
        )
        self._agents[(org_id, key)] = rec
        return rec

    def update_definicao(self, org_id: UUID, key: str, fields: dict[str, Any]) -> StudioAgentRecord:
        _validate_definicao_fields(fields)
        before = self.get_agent(org_id, key)
        if before.definition_scope != "plataforma":
            raise ValueError("only a platform definition carries these fields")
        _check_not_owned_and_open(
            fields.get("owner_product", before.owner_product), bool(fields.get("instanciavel", before.instanciavel)),
        )
        if fields.get("papel") == "gerador" and any(
            d.papel == "gerador" and d.id != before.id for d in self.list_platform_definitions()
        ):
            raise StudioConflict("gerador_ja_existe", "another platform definition already is the generator")
        rec = replace(before, **fields, updated_at=self._now())
        self._agents[(org_id, key)] = rec
        return rec

    def update_agent(
        self, org_id: UUID, key: str, fields: dict[str, Any], *, actor: UUID | None = None
    ) -> StudioAgentRecord:
        _validate_agent_fields(fields)
        before = self.get_agent(org_id, key)
        rec = replace(before, **fields, updated_at=self._now())
        self._agents[(org_id, key)] = rec
        if "publicacao_limiar" in fields and float(fields["publicacao_limiar"]) != before.publicacao_limiar:
            # 012 `audit_agent_limiar_change` trigger.
            self._audit_append(
                org_id, rec.id, actor, "limiar_alterado",
                {"publicacao_limiar": before.publicacao_limiar},
                {"publicacao_limiar": float(fields["publicacao_limiar"])},
            )
        return rec

    def list_audit_log(self, org_id: UUID, agent_id: UUID) -> list[AuditRecord]:
        return sorted(
            (a for a in self._audit if a.org_id == org_id and a.agent_id == agent_id),
            key=lambda a: a.created_at, reverse=True,
        )

    def delete_agent(self, org_id: UUID, agent_id: UUID, *, actor: UUID | None = None) -> None:
        """048 ``agents.excluir_agente``: the same guards, in the same order, then the cascade + tombstone."""
        agent = self._agent_by_id(org_id, agent_id)
        versions = [v for v in self._versions.values() if v.agent_id == agent_id]
        if any(v.status != "rascunho" for v in versions):
            raise StudioConflict("publicado", "excluir_agente_publicado")
        if agent.definition_scope == "plataforma" and any(
            a.definition_agent_id == agent_id for a in self._agents.values()
        ):
            raise StudioConflict("tem_instancias", "excluir_agente_tem_instancias")
        if agent_id in self._com_mensagens:
            raise StudioConflict("tem_conversas", "excluir_agente_tem_conversas")
        if agent_id in self._com_canal:
            raise StudioConflict("tem_canal", "excluir_agente_tem_canal")
        if agent.ativo:
            raise StudioConflict("ativo", "excluir_agente_ativo")
        for v in versions:
            for cid in [k for k, c in self._compiled.items() if c.version_id == v.id]:
                del self._compiled[cid]
            self._drop_draft_rows(v.id)
        for cid in [c.id for c in self._clients.values() if c.agent_id == agent_id]:
            for eid in [e.id for e in self._entries.values() if e.client_id == cid]:
                del self._entries[eid]
            del self._clients[cid]
        # FK ON DELETE SET NULL: the older rows keep their snapshot, lose the id; then the tombstone.
        self._audit = [replace(a, agent_id=None) if a.agent_id == agent_id else a for a in self._audit]
        self._audit.append(AuditRecord(
            id=uuid4(), org_id=org_id, agent_id=None, actor=actor, acao="agente_excluido",
            antes={"id": str(agent.id), "key": agent.key, "nome": agent.nome,
                   "definition_scope": agent.definition_scope, "conteudo_modo": agent.conteudo_modo},
            depois=None, created_at=self._now(), agent_key=agent.key, agent_nome=agent.nome,
        ))
        del self._agents[(org_id, agent.key)]

    def _agent_by_id(self, org_id: UUID, agent_id: UUID) -> StudioAgentRecord:
        for (o, _), a in self._agents.items():
            if o == org_id and a.id == agent_id:
                return a
        raise NotFound(f"agent {agent_id} not found")

    # ── versions
    def list_versions(self, org_id: UUID, agent_id: UUID) -> list[VersionRecord]:
        return sorted(
            (v for v in self._versions.values() if v.org_id == org_id and v.agent_id == agent_id),
            key=lambda v: v.versao, reverse=True,
        )

    def get_version(self, org_id: UUID, version_id: UUID) -> VersionRecord:
        v = self._versions.get(version_id)
        if v is None or v.org_id != org_id:
            raise NotFound(f"version {version_id} not found")
        return v

    def _by_status(self, org_id: UUID, agent_id: UUID, status: str) -> VersionRecord | None:
        for v in self._versions.values():
            if v.org_id == org_id and v.agent_id == agent_id and v.status == status:
                return v
        return None

    def get_draft(self, org_id: UUID, agent_id: UUID) -> VersionRecord | None:
        return self._by_status(org_id, agent_id, "rascunho")

    def get_active_version(self, org_id: UUID, agent_id: UUID) -> VersionRecord | None:
        return self._by_status(org_id, agent_id, "ativa")

    def create_draft(
        self, org_id: UUID, agent_id: UUID, source_version_id: UUID | None, created_by: UUID
    ) -> VersionRecord:
        self._agent_by_id(org_id, agent_id)
        if self.get_draft(org_id, agent_id) is not None:
            raise StudioConflict("draft_exists", "a draft already exists")
        versao = max(
            (v.versao for v in self._versions.values() if v.agent_id == agent_id), default=0
        ) + 1
        now = self._now()
        if source_version_id is None:
            settings = dict(DRAFT_DEFAULTS)
            settings["tool_policy"] = dict(DRAFT_DEFAULTS["tool_policy"])
            based_on = None
            src = None
        else:
            src = self._versions.get(source_version_id)
            if src is None or src.org_id != org_id or src.agent_id != agent_id:
                raise NotFound(f"version {source_version_id} not found")
            settings = {
                "provider": src.provider, "model": src.model, "effort": src.effort,
                "max_turns": src.max_turns,
                "idioma": src.idioma, "tool_policy": dict(src.tool_policy),
            }
            based_on = src.id
        draft = VersionRecord(
            id=uuid4(), org_id=org_id, agent_id=agent_id, versao=versao, status="rascunho",
            notas=None, based_on_version_id=based_on, created_by=created_by,
            published_by=None, published_at=None, compiled_hash=None, eval_run_id=None,
            publish_override_reason=None, created_at=now, updated_at=now,
            # 040 `agent_versions_inherit_qualificacao`: a draft inherits the pin of the version it is based on.
            qualificacao_versao_id=src.qualificacao_versao_id if src is not None else None, **settings,
        )
        self._versions[draft.id] = draft
        if src is not None:
            for s in self._sections_of(src.id):
                nid = uuid4()
                self._sections[nid] = replace(s, id=nid, version_id=draft.id, created_at=now, updated_at=now)
            for sk in self._skills_of(src.id):
                nsk = uuid4()
                self._skills[nsk] = replace(sk, id=nsk, version_id=draft.id, created_at=now, updated_at=now)
                for f in [f for f in self._files.values() if f.skill_id == sk.id]:
                    nf = uuid4()
                    self._files[nf] = replace(f, id=nf, skill_id=nsk, created_at=now, updated_at=now)
            # 031 `copy_version_conteudo` trigger
            self._copy_conteudo(src.id, draft.id, org_id)
        return draft

    def _require_draft(self, org_id: UUID, version_id: UUID) -> VersionRecord:
        v = self.get_version(org_id, version_id)
        if v.status != "rascunho":
            raise VersionImmutable(f"version {version_id} is {v.status}")
        return v

    def update_draft(self, org_id: UUID, version_id: UUID, fields: dict[str, Any]) -> VersionRecord:
        v = self._require_draft(org_id, version_id)
        _validate_draft_fields(fields, current_provider=v.provider, current_model=v.model)
        changed = any(k in fields and fields[k] != getattr(v, k) for k in _COMPILED_SETTINGS)
        v = replace(v, **fields, updated_at=self._now())
        if changed:
            v = replace(v, compiled_hash=None)
        self._versions[v.id] = v
        return v

    def set_compiled_hash(
        self, org_id: UUID, version_id: UUID, compiled_hash: str, *, expected_updated_at: Any = None,
    ) -> VersionRecord:
        v = self._require_draft(org_id, version_id)
        if expected_updated_at is not None and v.updated_at != expected_updated_at:
            raise StudioConflict("draft_changed", "the draft changed since it was read")
        v = replace(v, compiled_hash=compiled_hash, updated_at=self._now())
        self._versions[v.id] = v
        return v

    def publish_version(
        self, org_id: UUID, version_id: UUID, published_by: UUID,
        eval_run_id: UUID | None, override_reason: str | None, *, expected_hash: str,
        texto: str, manifest: list[dict[str, Any]],
    ) -> VersionRecord:
        v = self._require_draft(org_id, version_id)
        if expected_hash is None or v.compiled_hash != expected_hash:
            raise StudioConflict("draft_changed", "the draft changed since the gate was checked")
        limiar = self._agent_by_id(org_id, v.agent_id).publicacao_limiar
        score: float | None = None
        reason = override_reason.strip() if override_reason is not None else None
        if eval_run_id is not None:
            run = self._eval_runs.get(eval_run_id)
            ok = (
                run is not None and run["org_id"] == org_id and run["version_id"] == version_id
                and run["status"] == "concluida" and run["completa"] and run["total"] >= 1
                and run["compiled_hash"] == expected_hash and run["score"] is not None
                and run["score"] >= limiar and self._active_cases.get(v.agent_id, 0) >= 1
            )
            if not ok:
                raise StudioConflict("eval_required", "the eval gate did not pass")
            score = run["score"]
            reason = None
        elif not override_reason_ok(reason):
            raise StudioConflict("eval_required", "no passing eval run and no valid override reason")
        # Proof of use (§A7) in the same "transaction" as the flip.
        self.save_compiled_prompt(
            org_id, hash=expected_hash, version_id=version_id, client_id=None, texto=texto, manifest=manifest,
        )
        now = self._now()
        current = self.get_active_version(org_id, v.agent_id)
        if current is not None:
            self._versions[current.id] = replace(current, status="substituida", updated_at=now)
        v = replace(
            v, status="ativa", published_by=published_by, published_at=now,
            eval_run_id=eval_run_id, publish_override_reason=reason, updated_at=now,
            limiar_aplicado=limiar, eval_score=score,
        )
        self._versions[v.id] = v
        self._audit_append(
            org_id, v.agent_id, published_by,
            "publicado" if eval_run_id is not None else "publicado_override",
            {"version_id": str(current.id), "versao": current.versao} if current is not None else None,
            {
                "version_id": str(v.id), "versao": v.versao, "compiled_hash": v.compiled_hash,
                "eval_run_id": str(eval_run_id) if eval_run_id else None, "eval_score": score,
                "limiar_aplicado": limiar, "override_reason": reason,
            },
        )
        return v

    def _drop_draft_rows(self, version_id: UUID) -> None:
        """The version row and everything that cascades from it (012/013/017/031)."""
        for sk in self._skills_of(version_id):
            for fid in [f.id for f in self._files.values() if f.skill_id == sk.id]:
                del self._files[fid]
            del self._skills[sk.id]
        for sec in self._sections_of(version_id):
            del self._sections[sec.id]
        self._drop_conteudo(version_id)
        # 013 `eval_runs.version_id ON DELETE CASCADE`.
        for rid in [r for r, row in self._eval_runs.items() if row["version_id"] == version_id]:
            del self._eval_runs[rid]
        # 017 `agent_package_trees.version_id ON DELETE CASCADE`.
        self._trees.pop(version_id, None)
        del self._versions[version_id]

    def discard_draft(self, org_id: UUID, version_id: UUID, *, actor: UUID | None = None) -> None:
        v = self._require_draft(org_id, version_id)
        if any(c.version_id == version_id for c in self._compiled.values()):
            raise StudioConflict("draft_referenced", "the draft is referenced by a stored compiled prompt")
        self._drop_draft_rows(version_id)
        self._audit_append(
            org_id, v.agent_id, actor, "rascunho_descartado",
            {"version_id": str(v.id), "versao": v.versao, "compiled_hash": v.compiled_hash}, None,
        )

    # ── sections
    def _sections_of(self, version_id: UUID) -> list[SectionRecord]:
        return sorted(
            (s for s in self._sections.values() if s.version_id == version_id),
            key=lambda s: (s.ordem, s.chave),
        )

    def list_sections(self, org_id: UUID, version_id: UUID) -> list[SectionRecord]:
        self.get_version(org_id, version_id)
        return self._sections_of(version_id)

    def replace_sections(
        self, org_id: UUID, version_id: UUID, secoes: list[SectionInput]
    ) -> list[SectionRecord]:
        self._require_draft(org_id, version_id)
        chaves = [s.chave for s in secoes]
        if len(set(chaves)) != len(chaves):
            raise StudioConflict("chave_conflict", "duplicate chave in payload")
        for s in secoes:
            _validate_section(s)
        existing = {s.id: s for s in self._sections_of(version_id)}
        for sid in existing:
            del self._sections[sid]
        now = self._now()
        for s in secoes:
            keep = s.id is not None and s.id in existing
            sid = s.id if keep else uuid4()
            created = existing[sid].created_at if keep else now
            self._sections[sid] = SectionRecord(
                id=sid, org_id=org_id, version_id=version_id, chave=s.chave, titulo=s.titulo,
                ordem=s.ordem, conteudo=s.conteudo, ativo=s.ativo, created_at=created, updated_at=now,
            )
        self._touch_draft(version_id)
        return self._sections_of(version_id)

    def replace_draft_bundle(
        self, org_id: UUID, version_id: UUID, secoes: list[Any], skills: list[Any],
    ) -> DraftBundleResult:
        self._require_draft(org_id, version_id)
        sec_in = [_as_section_input(s) for s in secoes]
        sk_in = [_as_skill_input(s) for s in skills]
        _validate_bundle(sec_in, sk_in)
        # Validated in full above — the mutation below cannot fail midway,
        # which is the Fake's equivalent of the RPC's single transaction.
        for sk in self._skills_of(version_id):
            for fid in [f.id for f in self._files.values() if f.skill_id == sk.id]:
                del self._files[fid]
            del self._skills[sk.id]
        for sec in self._sections_of(version_id):
            del self._sections[sec.id]
        now = self._now()
        n_files = 0
        for sec in sec_in:
            sid = uuid4()
            self._sections[sid] = SectionRecord(
                id=sid, org_id=org_id, version_id=version_id, chave=sec.chave, titulo=sec.titulo,
                ordem=sec.ordem, conteudo=sec.conteudo, ativo=sec.ativo, created_at=now, updated_at=now,
            )
        for sk in sk_in:
            skid = uuid4()
            self._skills[skid] = SkillRecord(
                id=skid, org_id=org_id, version_id=version_id, nome=sk.nome, descricao=sk.descricao,
                corpo=sk.corpo, ordem=sk.ordem, ativo=sk.ativo, created_at=now, updated_at=now,
            )
            for f in sk.arquivos:
                fid = uuid4()
                self._files[fid] = SkillFileRecord(
                    id=fid, org_id=org_id, skill_id=skid, caminho=f.caminho, titulo=f.titulo,
                    conteudo=f.conteudo, created_at=now, updated_at=now,
                )
                n_files += 1
        self._touch_draft(version_id)
        return DraftBundleResult(secoes=len(sec_in), skills=len(sk_in), arquivos=n_files)

    # ── skills
    def _skills_of(self, version_id: UUID) -> list[SkillRecord]:
        return sorted(
            (s for s in self._skills.values() if s.version_id == version_id),
            key=lambda s: (s.ordem, s.nome),
        )

    def list_skills(self, org_id: UUID, version_id: UUID) -> list[SkillRecord]:
        self.get_version(org_id, version_id)
        return self._skills_of(version_id)

    def get_skill(self, org_id: UUID, skill_id: UUID) -> SkillRecord:
        sk = self._skills.get(skill_id)
        if sk is None or sk.org_id != org_id:
            raise NotFound(f"skill {skill_id} not found")
        return sk

    def create_skill(
        self, org_id: UUID, version_id: UUID, *, nome: str, descricao: str, corpo: str,
        ordem: int = 0, ativo: bool = True,
    ) -> SkillRecord:
        self._require_draft(org_id, version_id)
        _validate_skill_fields({"corpo": corpo})
        if any(s.nome == nome for s in self._skills_of(version_id)):
            raise StudioConflict("skill_exists", f"skill {nome!r} already exists")
        now = self._now()
        sk = SkillRecord(
            id=uuid4(), org_id=org_id, version_id=version_id, nome=nome, descricao=descricao,
            corpo=corpo, ordem=ordem, ativo=ativo, created_at=now, updated_at=now,
        )
        self._skills[sk.id] = sk
        self._touch_draft(version_id)
        return sk

    def update_skill(
        self, org_id: UUID, skill_id: UUID, fields: dict[str, Any], *, expected_hash: str | None = None,
    ) -> SkillRecord:
        _check_fields(fields, _SKILL_FIELDS, "skill")
        _validate_skill_fields(fields)
        sk = self.get_skill(org_id, skill_id)
        draft = self._require_draft(org_id, sk.version_id)
        # 041 `update_draft_skill(p_expected_hash)`: the compare and the update are one step
        if expected_hash is not None and draft.compiled_hash != expected_hash:
            raise StudioConflict("conflito_de_versao", "the draft changed since it was read")
        if "nome" in fields and fields["nome"] != sk.nome and any(
            s.nome == fields["nome"] for s in self._skills_of(sk.version_id)
        ):
            raise StudioConflict("skill_exists", f"skill {fields['nome']!r} already exists")
        sk = replace(sk, **fields, updated_at=self._now())
        self._skills[sk.id] = sk
        self._touch_draft(sk.version_id)
        return sk

    def delete_skill(self, org_id: UUID, skill_id: UUID) -> None:
        sk = self.get_skill(org_id, skill_id)
        self._require_draft(org_id, sk.version_id)
        for fid in [f.id for f in self._files.values() if f.skill_id == skill_id]:
            del self._files[fid]
        del self._skills[skill_id]
        self._touch_draft(sk.version_id)

    def list_version_skill_files(self, org_id: UUID, version_id: UUID) -> list[SkillFileRecord]:
        ids = {s.id for s in self.list_skills(org_id, version_id)}
        return sorted(
            (f for f in self._files.values() if f.skill_id in ids),
            key=lambda f: (str(f.skill_id), f.caminho),
        )

    def get_skill_file(self, org_id: UUID, file_id: UUID) -> SkillFileRecord:
        f = self._files.get(file_id)
        if f is None or f.org_id != org_id:
            raise NotFound(f"skill file {file_id} not found")
        return f

    def upsert_skill_file(
        self, org_id: UUID, skill_id: UUID, *, caminho: str, titulo: str | None, conteudo: str
    ) -> SkillFileRecord:
        _check_cap(conteudo, "skill_file.conteudo", "skill file conteudo")
        sk = self.get_skill(org_id, skill_id)
        self._require_draft(org_id, sk.version_id)
        now = self._now()
        self._touch_draft(sk.version_id)
        for f in self._files.values():
            if f.skill_id == skill_id and f.caminho == caminho:
                nf = replace(f, titulo=titulo, conteudo=conteudo, updated_at=now)
                self._files[f.id] = nf
                return nf
        nf = SkillFileRecord(
            id=uuid4(), org_id=org_id, skill_id=skill_id, caminho=caminho, titulo=titulo,
            conteudo=conteudo, created_at=now, updated_at=now,
        )
        self._files[nf.id] = nf
        return nf

    def delete_skill_file(self, org_id: UUID, file_id: UUID) -> None:
        f = self.get_skill_file(org_id, file_id)
        sk = self.get_skill(org_id, f.skill_id)
        self._require_draft(org_id, sk.version_id)
        del self._files[file_id]
        self._touch_draft(sk.version_id)

    # ── clients
    def list_clients(self, org_id: UUID, agent_id: UUID) -> list[ClientRecord]:
        out = []
        for c in self._clients.values():
            if c.org_id == org_id and c.agent_id == agent_id:
                n = sum(1 for e in self._entries.values() if e.client_id == c.id)
                out.append(replace(c, total_entradas=n))
        return sorted(out, key=lambda c: c.slug)

    def get_client(self, org_id: UUID, client_id: UUID) -> ClientRecord:
        c = self._clients.get(client_id)
        if c is None or c.org_id != org_id:
            raise NotFound(f"client {client_id} not found")
        return c

    def create_client(
        self, org_id: UUID, agent_id: UUID, *, slug: str, nome: str, resumo: str = "", ativo: bool = True
    ) -> ClientRecord:
        _validate_client_fields({"resumo": resumo})
        if any(c.agent_id == agent_id and c.slug == slug for c in self._clients.values()):
            raise StudioConflict("client_exists", f"client {slug!r} already exists")
        now = self._now()
        c = ClientRecord(
            id=uuid4(), org_id=org_id, agent_id=agent_id, slug=slug, nome=nome, resumo=resumo,
            ativo=ativo, created_at=now, updated_at=now,
        )
        self._clients[c.id] = c
        return c

    def update_client(self, org_id: UUID, client_id: UUID, fields: dict[str, Any]) -> ClientRecord:
        _check_fields(fields, _CLIENT_FIELDS, "client")
        _validate_client_fields(fields)
        c = self.get_client(org_id, client_id)
        if "slug" in fields and fields["slug"] != c.slug and any(
            o.agent_id == c.agent_id and o.slug == fields["slug"] for o in self._clients.values()
        ):
            raise StudioConflict("client_exists", f"client {fields['slug']!r} already exists")
        c = replace(c, **fields, updated_at=self._now())
        self._clients[c.id] = c
        return c

    def list_client_entries(self, org_id: UUID, client_id: UUID) -> list[ClientEntryRecord]:
        self.get_client(org_id, client_id)
        return sorted(
            (e for e in self._entries.values() if e.client_id == client_id),
            key=lambda e: (e.created_at, str(e.id)),
        )

    def get_client_entry(self, org_id: UUID, entry_id: UUID) -> ClientEntryRecord:
        e = self._entries.get(entry_id)
        if e is None or e.org_id != org_id:
            raise NotFound(f"client entry {entry_id} not found")
        return e

    def create_client_entry(
        self, org_id: UUID, client_id: UUID, *, tipo: str, titulo: str, conteudo: str = "",
        status: str = "ativo",
    ) -> ClientEntryRecord:
        _validate_entry({"tipo": tipo, "status": status})
        _validate_entry_caps({"titulo": titulo, "conteudo": conteudo})
        self.get_client(org_id, client_id)
        if status == "ativo":
            self._check_entry_cap(client_id, exclude=None)
        now = self._now()
        e = ClientEntryRecord(
            id=uuid4(), org_id=org_id, client_id=client_id, tipo=tipo, titulo=titulo,
            conteudo=conteudo, status=status, created_at=now, updated_at=now,
        )
        self._entries[e.id] = e
        return e

    def update_client_entry(self, org_id: UUID, entry_id: UUID, fields: dict[str, Any]) -> ClientEntryRecord:
        _check_fields(fields, _ENTRY_FIELDS, "entry")
        _validate_entry(fields)
        _validate_entry_caps(fields)
        e = self.get_client_entry(org_id, entry_id)
        if fields.get("status") == "ativo" and e.status != "ativo":
            self._check_entry_cap(e.client_id, exclude=e.id)
        e = replace(e, **fields, updated_at=self._now())
        self._entries[e.id] = e
        return e

    def delete_client_entry(self, org_id: UUID, entry_id: UUID) -> None:
        self.get_client_entry(org_id, entry_id)
        del self._entries[entry_id]

    def _check_entry_cap(self, client_id: UUID, *, exclude: UUID | None) -> None:
        """012 ``guard_client_entry_cap``."""
        ativas = sum(
            1 for e in self._entries.values()
            if e.client_id == client_id and e.status == "ativo" and e.id != exclude
        )
        if ativas >= LIMITS["client.active_entries"]:
            raise StudioConflict(
                "client_entries_cap",
                f"a client may hold at most {LIMITS['client.active_entries']} active entries",
            )

    # ── compiled prompts
    def save_compiled_prompt(
        self, org_id: UUID, *, hash: str, version_id: UUID, client_id: UUID | None,
        texto: str, manifest: list[dict[str, Any]],
    ) -> CompiledPromptRecord:
        existing = self._compiled.get((org_id, hash))
        if existing is not None:
            return existing
        self.get_version(org_id, version_id)
        rec = CompiledPromptRecord(
            id=uuid4(), org_id=org_id, hash=hash, version_id=version_id, client_id=client_id,
            texto=texto, manifest=list(manifest), created_at=self._now(),
        )
        self._compiled[(org_id, hash)] = rec
        return rec

    def get_compiled_prompt(self, org_id: UUID, hash: str) -> CompiledPromptRecord:
        rec = self._compiled.get((org_id, hash))
        if rec is None:
            raise NotFound(f"compiled prompt {hash} not found")
        return rec

    # ── package trees (017)
    def get_package_tree(self, org_id: UUID, version_id: UUID) -> list[dict[str, str]] | None:
        v = self._versions.get(version_id)
        if v is None or v.org_id != org_id:
            return None
        tree = self._trees.get(version_id)
        return [dict(f) for f in tree] if tree is not None else None

    def set_package_tree(
        self, org_id: UUID, agent_id: UUID, version_id: UUID, files: list[dict[str, str]]
    ) -> None:
        # 017 `guard_package_tree_immutable`: only a draft's tree is writable.
        self._require_draft(org_id, version_id)
        self._trees[version_id] = [{"caminho": f["caminho"], "conteudo": f["conteudo"]} for f in files]

    def erase_client_compiled_prompts(self, org_id: UUID, client_id: UUID) -> int:
        keys = [k for k, c in self._compiled.items() if c.org_id == org_id and c.client_id == client_id]
        for k in keys:
            del self._compiled[k]
        return len(keys)


# ── Real ────────────────────────────────────────────────────────────────────


def _uuid_or_none(v: Any) -> UUID | None:
    return UUID(str(v)) if v is not None else None


def _float(v: Any) -> float:
    return float(Decimal(str(v)))


class SupabaseStudioDefinitionStore(SupabaseConteudoMixin):
    """Real :class:`StudioDefinitionStore` — Postgres via the admin client.

    Bare table names through ``client.schema("agents").table(...)`` — never
    ``"agents.x"`` (``KB § PATTERNS/backend/postgrest-schema-targeting.md``).
    """

    def __init__(self, client: Any) -> None:
        self._client = client

    def _t(self, table: str):
        return self._client.schema(_SCHEMA).table(table)

    def _rpc(self, fn: str, params: dict[str, Any], *, fk_code: str | None = None):
        return exec_rpc(self._client, _SCHEMA, fn, params, fk_code=fk_code)

    def _exec(self, query, *, unique_code: str | None = None, fk_code: str | None = None):
        return exec_query(query, unique_code=unique_code, fk_code=fk_code)

    def _paged(self, build, *, label: str, order: tuple[str, ...]) -> list[dict[str, Any]]:
        def fetch(start: int, end: int):
            q = build()
            for col in order:
                q = q.order(col)
            return q.order("id").range(start, end).execute().data

        return list(iter_paged_rows(fetch, label=label))

    @staticmethod
    def _one(resp, what: str) -> dict[str, Any]:
        rows = resp.data or []
        if isinstance(rows, dict):
            return rows
        if not rows:
            raise NotFound(f"{what} not found")
        return rows[0]

    # ── records
    @staticmethod
    def _agent(row: dict[str, Any]) -> StudioAgentRecord:
        return StudioAgentRecord(
            id=UUID(str(row["id"])), org_id=UUID(str(row["org_id"])), key=row["key"],
            nome=row["nome"], descricao=row.get("descricao"),
            definition_mode=row.get("definition_mode") or "legacy", runtime=row["runtime"],
            ativo=bool(row.get("ativo", False)),
            publicacao_limiar=_float(row.get("publicacao_limiar", 0.8)),
            created_at=row["created_at"], updated_at=row["updated_at"],
            kind=row.get("kind") or "runtime", owner_product=row.get("owner_product"),
            definition_scope=row.get("definition_scope") or "org",
            definition_agent_id=_uuid_or_none(row.get("definition_agent_id")),
            conteudo_modo=row.get("conteudo_modo") or "legado",
            escopo_qualificacao=row.get("escopo_qualificacao"),
            padrao_qualificacao=row.get("padrao_qualificacao"),
            rascunho_padrao=dict(row["rascunho_padrao"]) if row.get("rascunho_padrao") is not None else None,
            instanciavel=bool(row.get("instanciavel", False)), papel=row.get("papel"),
        )

    @staticmethod
    def _version(row: dict[str, Any]) -> VersionRecord:
        return VersionRecord(
            id=UUID(str(row["id"])), org_id=UUID(str(row["org_id"])),
            agent_id=UUID(str(row["agent_id"])), versao=int(row["versao"]), status=row["status"],
            notas=row.get("notas"), provider=row.get("provider") or "anthropic",
            qualificacao_versao_id=_uuid_or_none(row.get("qualificacao_versao_id")),
            model=row["model"], effort=row["effort"],
            max_turns=int(row["max_turns"]), idioma=row["idioma"],
            tool_policy=dict(row.get("tool_policy") or {}),
            based_on_version_id=_uuid_or_none(row.get("based_on_version_id")),
            created_by=UUID(str(row["created_by"])),
            published_by=_uuid_or_none(row.get("published_by")),
            published_at=row.get("published_at"), compiled_hash=row.get("compiled_hash"),
            eval_run_id=_uuid_or_none(row.get("eval_run_id")),
            publish_override_reason=row.get("publish_override_reason"),
            created_at=row["created_at"], updated_at=row["updated_at"],
            limiar_aplicado=_float(row["limiar_aplicado"]) if row.get("limiar_aplicado") is not None else None,
            eval_score=_float(row["eval_score"]) if row.get("eval_score") is not None else None,
            versao_semver=row.get("versao_semver"), package_sha=row.get("package_sha"),
        )

    @staticmethod
    def _section(row: dict[str, Any]) -> SectionRecord:
        return SectionRecord(
            id=UUID(str(row["id"])), org_id=UUID(str(row["org_id"])),
            version_id=UUID(str(row["version_id"])), chave=row["chave"], titulo=row["titulo"],
            ordem=int(row["ordem"]), conteudo=row.get("conteudo") or "",
            ativo=bool(row.get("ativo", True)), created_at=row["created_at"], updated_at=row["updated_at"],
        )

    @staticmethod
    def _skill(row: dict[str, Any]) -> SkillRecord:
        return SkillRecord(
            id=UUID(str(row["id"])), org_id=UUID(str(row["org_id"])),
            version_id=UUID(str(row["version_id"])), nome=row["nome"], descricao=row["descricao"],
            corpo=row.get("corpo") or "", ordem=int(row.get("ordem") or 0),
            ativo=bool(row.get("ativo", True)), created_at=row["created_at"], updated_at=row["updated_at"],
        )

    @staticmethod
    def _file(row: dict[str, Any]) -> SkillFileRecord:
        return SkillFileRecord(
            id=UUID(str(row["id"])), org_id=UUID(str(row["org_id"])),
            skill_id=UUID(str(row["skill_id"])), caminho=row["caminho"], titulo=row.get("titulo"),
            conteudo=row.get("conteudo") or "", created_at=row["created_at"], updated_at=row["updated_at"],
        )

    @staticmethod
    def _client_rec(row: dict[str, Any], total: int | None = None) -> ClientRecord:
        return ClientRecord(
            id=UUID(str(row["id"])), org_id=UUID(str(row["org_id"])),
            agent_id=UUID(str(row["agent_id"])), slug=row["slug"], nome=row["nome"],
            resumo=row.get("resumo") or "", ativo=bool(row.get("ativo", True)),
            created_at=row["created_at"], updated_at=row["updated_at"], total_entradas=total,
        )

    @staticmethod
    def _entry(row: dict[str, Any]) -> ClientEntryRecord:
        return ClientEntryRecord(
            id=UUID(str(row["id"])), org_id=UUID(str(row["org_id"])),
            client_id=UUID(str(row["client_id"])), tipo=row["tipo"], titulo=row["titulo"],
            conteudo=row.get("conteudo") or "", status=row["status"],
            created_at=row["created_at"], updated_at=row["updated_at"],
        )

    @staticmethod
    def _compiled(row: dict[str, Any]) -> CompiledPromptRecord:
        return CompiledPromptRecord(
            id=UUID(str(row["id"])), org_id=UUID(str(row["org_id"])), hash=row["hash"],
            version_id=UUID(str(row["version_id"])), client_id=_uuid_or_none(row.get("client_id")),
            texto=row["texto"], manifest=list(row.get("manifest") or []), created_at=row["created_at"],
        )

    # ── agents
    def list_agents(self, org_id: UUID) -> list[StudioAgentRecord]:
        rows = self._paged(
            lambda: self._t("agents").select("*").eq("org_id", str(org_id)),
            label=f"studio agents org_id={org_id}", order=("key",),
        )
        return [self._agent(r) for r in rows]

    def get_agent(self, org_id: UUID, key: str) -> StudioAgentRecord:
        resp = self._t("agents").select("*").eq("org_id", str(org_id)).eq("key", key).execute()
        return self._agent(self._one(resp, f"agent {key!r}"))

    def create_studio_agent(
        self, org_id: UUID, key: str, nome: str, descricao: str | None, *, kind: str = "runtime",
        runtime: str = "claude_sdk", owner_product: str | None = None,
        definition_scope: str = "org", definition_agent_id: UUID | None = None,
        escopo_qualificacao: str | None = None, padrao_qualificacao: str | None = None,
        rascunho_padrao: dict[str, Any] | None = None, instanciavel: bool = False, papel: str | None = None,
    ) -> StudioAgentRecord:
        if kind not in AGENT_KINDS:
            raise ValueError(f"kind must be one of {AGENT_KINDS}; got {kind!r}")
        if runtime not in STUDIO_RUNTIMES:
            raise ValueError(f"runtime must be one of {STUDIO_RUNTIMES}; got {runtime!r}")
        modo = _validate_scope(definition_scope, definition_agent_id)
        attrs = {
            "escopo_qualificacao": escopo_qualificacao, "padrao_qualificacao": padrao_qualificacao,
            "rascunho_padrao": rascunho_padrao, "papel": papel,
        }
        if definition_scope != "plataforma" and any(v is not None for v in attrs.values()):
            raise ValueError("escopo/padrao de qualificação and rascunho_padrao belong to a platform definition")
        _validate_definicao_fields({k: v for k, v in attrs.items() if v is not None})
        if definition_scope == "plataforma":
            _check_not_owned_and_open(owner_product, instanciavel)
        payload = {
            "org_id": str(org_id), "key": key, "nome": nome, "descricao": descricao,
            "runtime": runtime, "definition_mode": "studio", "ativo": False, "kind": kind,
            "owner_product": owner_product, "definition_scope": definition_scope,
            "definition_agent_id": str(definition_agent_id) if definition_agent_id else None,
            "conteudo_modo": modo, "escopo_qualificacao": escopo_qualificacao,
            "padrao_qualificacao": padrao_qualificacao, "rascunho_padrao": rascunho_padrao,
            "instanciavel": instanciavel, "papel": papel,
        }
        resp = self._exec(self._t("agents").insert(payload), unique_code="key_taken")
        return self._agent(self._one(resp, f"agent {key!r}"))

    def is_platform_org(self, org_id: UUID) -> bool:
        resp = self._client.schema("public").table("organizations").select("is_platform").eq("id", str(org_id)).execute()
        rows = resp.data or []
        return bool(rows and rows[0].get("is_platform"))

    def update_definicao(self, org_id: UUID, key: str, fields: dict[str, Any]) -> StudioAgentRecord:
        _validate_definicao_fields(fields)
        before = self.get_agent(org_id, key)
        if before.definition_scope != "plataforma":
            raise ValueError("only a platform definition carries these fields")
        _check_not_owned_and_open(
            fields.get("owner_product", before.owner_product), bool(fields.get("instanciavel", before.instanciavel)),
        )
        if fields.get("papel") == "gerador" and any(
            d.papel == "gerador" and d.id != before.id for d in self.list_platform_definitions()
        ):
            raise StudioConflict("gerador_ja_existe", "another platform definition already is the generator")
        if not fields:
            return before
        resp = self._exec(self._t("agents").update(fields).eq("org_id", str(org_id)).eq("key", key))
        return self._agent(self._one(resp, f"agent {key!r}"))

    def update_agent(
        self, org_id: UUID, key: str, fields: dict[str, Any], *, actor: UUID | None = None
    ) -> StudioAgentRecord:
        _validate_agent_fields(fields)
        agent = self.get_agent(org_id, key)
        rest = {k: v for k, v in fields.items() if k != "publicacao_limiar"}
        if "publicacao_limiar" in fields:
            # Through the function so the audit trigger knows the actor (H2).
            self._rpc("set_agent_publicacao_limiar", {
                "p_org_id": str(org_id), "p_agent_id": str(agent.id),
                "p_limiar": float(fields["publicacao_limiar"]),
                "p_actor": str(actor) if actor else None,
            })
        if not rest:
            return self.get_agent(org_id, key)
        resp = self._exec(
            self._t("agents").update(rest).eq("org_id", str(org_id)).eq("key", key)
        )
        return self._agent(self._one(resp, f"agent {key!r}"))

    def delete_agent(self, org_id: UUID, agent_id: UUID, *, actor: UUID | None = None) -> None:
        self._rpc("excluir_agente", {
            "p_org_id": str(org_id), "p_agent_id": str(agent_id), "p_actor": str(actor) if actor else None,
        })

    def list_audit_log(self, org_id: UUID, agent_id: UUID) -> list[AuditRecord]:
        rows = self._paged(
            lambda: self._t("agent_audit_log").select("*")
            .eq("org_id", str(org_id)).eq("agent_id", str(agent_id)),
            label=f"agent_audit_log agent_id={agent_id}", order=("created_at",),
        )
        recs = [
            AuditRecord(
                id=UUID(str(r["id"])), org_id=UUID(str(r["org_id"])), agent_id=UUID(str(r["agent_id"])),
                actor=_uuid_or_none(r.get("actor")), acao=r["acao"], antes=r.get("antes"),
                depois=r.get("depois"), created_at=r["created_at"],
            )
            for r in rows
        ]
        return list(reversed(recs))

    # ── versions
    def list_versions(self, org_id: UUID, agent_id: UUID) -> list[VersionRecord]:
        rows = self._paged(
            lambda: self._t("agent_versions").select("*")
            .eq("org_id", str(org_id)).eq("agent_id", str(agent_id)),
            label=f"agent_versions agent_id={agent_id}", order=("versao",),
        )
        return sorted((self._version(r) for r in rows), key=lambda v: v.versao, reverse=True)

    def get_version(self, org_id: UUID, version_id: UUID) -> VersionRecord:
        resp = (
            self._t("agent_versions").select("*")
            .eq("org_id", str(org_id)).eq("id", str(version_id)).execute()
        )
        return self._version(self._one(resp, f"version {version_id}"))

    def _by_status(self, org_id: UUID, agent_id: UUID, status: str) -> VersionRecord | None:
        resp = (
            self._t("agent_versions").select("*").eq("org_id", str(org_id))
            .eq("agent_id", str(agent_id)).eq("status", status).execute()
        )
        rows = resp.data or []
        return self._version(rows[0]) if rows else None

    def get_draft(self, org_id: UUID, agent_id: UUID) -> VersionRecord | None:
        return self._by_status(org_id, agent_id, "rascunho")

    def get_active_version(self, org_id: UUID, agent_id: UUID) -> VersionRecord | None:
        return self._by_status(org_id, agent_id, "ativa")

    def create_draft(
        self, org_id: UUID, agent_id: UUID, source_version_id: UUID | None, created_by: UUID
    ) -> VersionRecord:
        resp = self._rpc("create_agent_draft", {
            "p_org_id": str(org_id),
            "p_agent_id": str(agent_id),
            "p_source_version_id": str(source_version_id) if source_version_id else None,
            "p_created_by": str(created_by),
        })
        new_id = resp.data
        if isinstance(new_id, list):
            new_id = new_id[0]
        if isinstance(new_id, dict):
            new_id = next(iter(new_id.values()))
        return self.get_version(org_id, UUID(str(new_id)))

    def update_draft(self, org_id: UUID, version_id: UUID, fields: dict[str, Any]) -> VersionRecord:
        if not fields:
            _validate_draft_fields(fields)
            return self.get_version(org_id, version_id)
        if ("model" in fields) != ("provider" in fields):
            current = self.get_version(org_id, version_id)
            _validate_draft_fields(
                fields, current_provider=current.provider, current_model=current.model
            )
        else:
            _validate_draft_fields(fields)
        body = {k: (str(v) if isinstance(v, UUID) else v) for k, v in fields.items()}
        resp = self._exec(
            self._t("agent_versions").update(body)
            .eq("org_id", str(org_id)).eq("id", str(version_id)).eq("status", "rascunho")
        )
        rows = resp.data or []
        if not rows:
            # Either missing (NotFound) or not a draft (immutable) — tell which.
            v = self.get_version(org_id, version_id)
            raise VersionImmutable(f"version {version_id} is {v.status}")
        return self._version(rows[0])

    def set_compiled_hash(
        self, org_id: UUID, version_id: UUID, compiled_hash: str, *, expected_updated_at: Any = None,
    ) -> VersionRecord:
        q = (
            self._t("agent_versions").update({"compiled_hash": compiled_hash})
            .eq("org_id", str(org_id)).eq("id", str(version_id)).eq("status", "rascunho")
        )
        if expected_updated_at is not None:
            ts = expected_updated_at.isoformat() if isinstance(expected_updated_at, datetime) else str(expected_updated_at)
            q = q.eq("updated_at", ts)
        resp = self._exec(q)
        rows = resp.data or []
        if not rows:
            # Missing (NotFound), not a draft (immutable) or moved (CAS) — tell which.
            v = self.get_version(org_id, version_id)
            if v.status != "rascunho":
                raise VersionImmutable(f"version {version_id} is {v.status}")
            raise StudioConflict("draft_changed", f"draft {version_id} changed since it was read")
        return self._version(rows[0])

    def publish_version(
        self, org_id: UUID, version_id: UUID, published_by: UUID,
        eval_run_id: UUID | None, override_reason: str | None, *, expected_hash: str,
        texto: str, manifest: list[dict[str, Any]],
    ) -> VersionRecord:
        self._rpc("publish_agent_version", {
            "p_org_id": str(org_id),
            "p_version_id": str(version_id),
            "p_published_by": str(published_by),
            "p_eval_run_id": str(eval_run_id) if eval_run_id else None,
            "p_override_reason": override_reason,
            "p_expected_hash": expected_hash,
            "p_texto": texto,
            "p_manifest": manifest,
        })
        return self.get_version(org_id, version_id)

    def discard_draft(self, org_id: UUID, version_id: UUID, *, actor: UUID | None = None) -> None:
        self._rpc(
            "discard_agent_draft",
            {"p_org_id": str(org_id), "p_version_id": str(version_id), "p_actor": str(actor) if actor else None},
            fk_code="draft_referenced",
        )

    # ── sections
    def list_sections(self, org_id: UUID, version_id: UUID) -> list[SectionRecord]:
        rows = self._paged(
            lambda: self._t("agent_prompt_sections").select("*")
            .eq("org_id", str(org_id)).eq("version_id", str(version_id)),
            label=f"agent_prompt_sections version_id={version_id}", order=("ordem", "chave"),
        )
        return [self._section(r) for r in rows]

    def replace_sections(
        self, org_id: UUID, version_id: UUID, secoes: list[SectionInput]
    ) -> list[SectionRecord]:
        """ONE ``agents.replace_draft_sections`` call = one transaction (the
        previous delete-then-upsert sequence could half-apply)."""
        chaves = [s.chave for s in secoes]
        if len(set(chaves)) != len(chaves):
            raise StudioConflict("chave_conflict", "duplicate chave in payload")
        for sec in secoes:
            _validate_section(sec)
        self._rpc("replace_draft_sections", {
            "p_org_id": str(org_id),
            "p_version_id": str(version_id),
            "p_secoes": [
                {
                    "id": str(sec.id) if sec.id else None, "chave": sec.chave, "titulo": sec.titulo,
                    "ordem": sec.ordem, "conteudo": sec.conteudo, "ativo": sec.ativo,
                }
                for sec in secoes
            ],
        })
        return self.list_sections(org_id, version_id)

    def replace_draft_bundle(
        self, org_id: UUID, version_id: UUID, secoes: list[Any], skills: list[Any],
    ) -> DraftBundleResult:
        sec_in = [_as_section_input(x) for x in secoes]
        sk_in = [_as_skill_input(x) for x in skills]
        _validate_bundle(sec_in, sk_in)
        self._rpc("replace_draft_bundle", {
            "p_org_id": str(org_id),
            "p_version_id": str(version_id),
            "p_secoes": [
                {"chave": x.chave, "titulo": x.titulo, "ordem": x.ordem, "conteudo": x.conteudo, "ativo": x.ativo}
                for x in sec_in
            ],
            "p_skills": [
                {
                    "nome": sk.nome, "descricao": sk.descricao, "corpo": sk.corpo, "ordem": sk.ordem,
                    "ativo": sk.ativo,
                    "arquivos": [{"caminho": f.caminho, "titulo": f.titulo, "conteudo": f.conteudo} for f in sk.arquivos],
                }
                for sk in sk_in
            ],
        })
        return DraftBundleResult(
            secoes=len(sec_in), skills=len(sk_in), arquivos=sum(len(sk.arquivos) for sk in sk_in),
        )

    # ── skills
    def list_skills(self, org_id: UUID, version_id: UUID) -> list[SkillRecord]:
        rows = self._paged(
            lambda: self._t("agent_skills").select("*")
            .eq("org_id", str(org_id)).eq("version_id", str(version_id)),
            label=f"agent_skills version_id={version_id}", order=("ordem", "nome"),
        )
        return [self._skill(r) for r in rows]

    def get_skill(self, org_id: UUID, skill_id: UUID) -> SkillRecord:
        resp = self._t("agent_skills").select("*").eq("org_id", str(org_id)).eq("id", str(skill_id)).execute()
        return self._skill(self._one(resp, f"skill {skill_id}"))

    def create_skill(
        self, org_id: UUID, version_id: UUID, *, nome: str, descricao: str, corpo: str,
        ordem: int = 0, ativo: bool = True,
    ) -> SkillRecord:
        _validate_skill_fields({"corpo": corpo})
        payload = {
            "org_id": str(org_id), "version_id": str(version_id), "nome": nome,
            "descricao": descricao, "corpo": corpo, "ordem": ordem, "ativo": ativo,
        }
        resp = self._exec(self._t("agent_skills").insert(payload), unique_code="skill_exists")
        return self._skill(self._one(resp, f"skill {nome!r}"))

    def update_skill(
        self, org_id: UUID, skill_id: UUID, fields: dict[str, Any], *, expected_hash: str | None = None,
    ) -> SkillRecord:
        _check_fields(fields, _SKILL_FIELDS, "skill")
        _validate_skill_fields(fields)
        if expected_hash is not None:
            # ONE transaction: lock the parent version, compare its hash, update (041). Only called WITH a hash,
            # so a pre-041 database keeps serving the unlocked PATCH below.
            resp = exec_rpc(self._client, _SCHEMA, "update_draft_skill", {
                "p_org_id": str(org_id), "p_skill_id": str(skill_id), "p_campos": dict(fields),
                "p_expected_hash": expected_hash,
            }, unique_code="skill_exists")
            return self._skill(self._one(resp, f"skill {skill_id}"))
        if not fields:
            return self.get_skill(org_id, skill_id)
        resp = self._exec(
            self._t("agent_skills").update(dict(fields)).eq("org_id", str(org_id)).eq("id", str(skill_id)),
            unique_code="skill_exists",
        )
        return self._skill(self._one(resp, f"skill {skill_id}"))

    def delete_skill(self, org_id: UUID, skill_id: UUID) -> None:
        self.get_skill(org_id, skill_id)
        self._exec(self._t("agent_skills").delete().eq("org_id", str(org_id)).eq("id", str(skill_id)))

    def list_version_skill_files(self, org_id: UUID, version_id: UUID) -> list[SkillFileRecord]:
        # Embedded resource: one request per skills page, no `.in_()` id list.
        rows = self._paged(
            lambda: self._t("agent_skills").select("id, agent_skill_files(*)")
            .eq("org_id", str(org_id)).eq("version_id", str(version_id)),
            label=f"agent_skill_files version_id={version_id}", order=(),
        )
        files = [self._file(f) for r in rows for f in (r.get("agent_skill_files") or [])]
        return sorted(files, key=lambda f: (str(f.skill_id), f.caminho))

    def get_skill_file(self, org_id: UUID, file_id: UUID) -> SkillFileRecord:
        resp = self._t("agent_skill_files").select("*").eq("org_id", str(org_id)).eq("id", str(file_id)).execute()
        return self._file(self._one(resp, f"skill file {file_id}"))

    def upsert_skill_file(
        self, org_id: UUID, skill_id: UUID, *, caminho: str, titulo: str | None, conteudo: str
    ) -> SkillFileRecord:
        _check_cap(conteudo, "skill_file.conteudo", "skill file conteudo")
        self.get_skill(org_id, skill_id)
        payload = {
            "org_id": str(org_id), "skill_id": str(skill_id), "caminho": caminho,
            "titulo": titulo, "conteudo": conteudo,
        }
        resp = self._exec(self._t("agent_skill_files").upsert(payload, on_conflict="skill_id,caminho"))
        return self._file(self._one(resp, f"skill file {caminho!r}"))

    def delete_skill_file(self, org_id: UUID, file_id: UUID) -> None:
        self.get_skill_file(org_id, file_id)
        self._exec(self._t("agent_skill_files").delete().eq("org_id", str(org_id)).eq("id", str(file_id)))

    # ── clients
    def list_clients(self, org_id: UUID, agent_id: UUID) -> list[ClientRecord]:
        rows = self._paged(
            lambda: self._t("agent_clients").select("*, agent_client_entries(count)")
            .eq("org_id", str(org_id)).eq("agent_id", str(agent_id)),
            label=f"agent_clients agent_id={agent_id}", order=("slug",),
        )
        out = []
        for r in rows:
            agg = r.get("agent_client_entries") or [{"count": 0}]
            out.append(self._client_rec(r, int(agg[0].get("count", 0))))
        return out

    def get_client(self, org_id: UUID, client_id: UUID) -> ClientRecord:
        resp = self._t("agent_clients").select("*").eq("org_id", str(org_id)).eq("id", str(client_id)).execute()
        return self._client_rec(self._one(resp, f"client {client_id}"))

    def create_client(
        self, org_id: UUID, agent_id: UUID, *, slug: str, nome: str, resumo: str = "", ativo: bool = True
    ) -> ClientRecord:
        _validate_client_fields({"resumo": resumo})
        payload = {
            "org_id": str(org_id), "agent_id": str(agent_id), "slug": slug, "nome": nome,
            "resumo": resumo, "ativo": ativo,
        }
        resp = self._exec(self._t("agent_clients").insert(payload), unique_code="client_exists")
        return self._client_rec(self._one(resp, f"client {slug!r}"))

    def update_client(self, org_id: UUID, client_id: UUID, fields: dict[str, Any]) -> ClientRecord:
        _check_fields(fields, _CLIENT_FIELDS, "client")
        _validate_client_fields(fields)
        if not fields:
            return self.get_client(org_id, client_id)
        resp = self._exec(
            self._t("agent_clients").update(dict(fields)).eq("org_id", str(org_id)).eq("id", str(client_id)),
            unique_code="client_exists",
        )
        return self._client_rec(self._one(resp, f"client {client_id}"))

    def list_client_entries(self, org_id: UUID, client_id: UUID) -> list[ClientEntryRecord]:
        rows = self._paged(
            lambda: self._t("agent_client_entries").select("*")
            .eq("org_id", str(org_id)).eq("client_id", str(client_id)),
            label=f"agent_client_entries client_id={client_id}", order=("created_at",),
        )
        return [self._entry(r) for r in rows]

    def get_client_entry(self, org_id: UUID, entry_id: UUID) -> ClientEntryRecord:
        resp = (
            self._t("agent_client_entries").select("*")
            .eq("org_id", str(org_id)).eq("id", str(entry_id)).execute()
        )
        return self._entry(self._one(resp, f"client entry {entry_id}"))

    def create_client_entry(
        self, org_id: UUID, client_id: UUID, *, tipo: str, titulo: str, conteudo: str = "",
        status: str = "ativo",
    ) -> ClientEntryRecord:
        _validate_entry({"tipo": tipo, "status": status})
        _validate_entry_caps({"titulo": titulo, "conteudo": conteudo})
        payload = {
            "org_id": str(org_id), "client_id": str(client_id), "tipo": tipo,
            "titulo": titulo, "conteudo": conteudo, "status": status,
        }
        resp = self._exec(self._t("agent_client_entries").insert(payload))
        return self._entry(self._one(resp, "client entry"))

    def update_client_entry(self, org_id: UUID, entry_id: UUID, fields: dict[str, Any]) -> ClientEntryRecord:
        _check_fields(fields, _ENTRY_FIELDS, "entry")
        _validate_entry(fields)
        _validate_entry_caps(fields)
        if not fields:
            return self.get_client_entry(org_id, entry_id)
        resp = self._exec(
            self._t("agent_client_entries").update(dict(fields))
            .eq("org_id", str(org_id)).eq("id", str(entry_id))
        )
        return self._entry(self._one(resp, f"client entry {entry_id}"))

    def delete_client_entry(self, org_id: UUID, entry_id: UUID) -> None:
        self.get_client_entry(org_id, entry_id)
        self._exec(
            self._t("agent_client_entries").delete().eq("org_id", str(org_id)).eq("id", str(entry_id))
        )

    # ── compiled prompts
    def save_compiled_prompt(
        self, org_id: UUID, *, hash: str, version_id: UUID, client_id: UUID | None,
        texto: str, manifest: list[dict[str, Any]],
    ) -> CompiledPromptRecord:
        payload = {
            "org_id": str(org_id), "hash": hash, "version_id": str(version_id),
            "client_id": str(client_id) if client_id else None, "texto": texto, "manifest": manifest,
        }
        # ON CONFLICT DO NOTHING — write-once; the existing row is re-read.
        self._exec(
            self._t("compiled_prompts").upsert(payload, on_conflict="org_id,hash", ignore_duplicates=True)
        )
        return self.get_compiled_prompt(org_id, hash)

    def get_compiled_prompt(self, org_id: UUID, hash: str) -> CompiledPromptRecord:
        resp = self._t("compiled_prompts").select("*").eq("org_id", str(org_id)).eq("hash", hash).execute()
        return self._compiled(self._one(resp, f"compiled prompt {hash}"))

    # ── package trees (017)
    def get_package_tree(self, org_id: UUID, version_id: UUID) -> list[dict[str, str]] | None:
        resp = (
            self._t("agent_package_trees").select("files")
            .eq("org_id", str(org_id)).eq("version_id", str(version_id)).limit(1).execute()
        )
        rows = resp.data or []
        if not rows:
            return None
        return [dict(f) for f in (rows[0].get("files") or [])]

    def set_package_tree(
        self, org_id: UUID, agent_id: UUID, version_id: UUID, files: list[dict[str, str]]
    ) -> None:
        payload = {
            "org_id": str(org_id), "agent_id": str(agent_id), "version_id": str(version_id),
            "files": [{"caminho": f["caminho"], "conteudo": f["conteudo"]} for f in files],
        }
        self._exec(self._t("agent_package_trees").upsert(payload, on_conflict="version_id"))

    def erase_client_compiled_prompts(self, org_id: UUID, client_id: UUID) -> int:
        resp = self._rpc("erase_compiled_prompts", {"p_org_id": str(org_id), "p_client_id": str(client_id)})
        data = resp.data
        if isinstance(data, list):
            data = data[0] if data else 0
        if isinstance(data, dict):
            data = next(iter(data.values()))
        return int(data or 0)


def get_studio_definition_store(settings: Any) -> StudioDefinitionStore:
    """Real when a Supabase service-role key is configured, Fake otherwise —
    same signal as :func:`app.stores.agents.get_agent_store`."""
    if not getattr(settings, "supabase_service_role_key", None):
        return FakeStudioDefinitionStore()
    from app.database import get_admin_client

    return SupabaseStudioDefinitionStore(get_admin_client())

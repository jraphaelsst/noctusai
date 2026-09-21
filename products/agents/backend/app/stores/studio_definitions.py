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

Unbounded reads page through ``iter_paged_rows`` (PostgREST caps every
response at 1000 rows silently — ``KB § PATTERNS/backend/postgrest-row-cap.md``).
Cross-parent reads (a version's skill files, a client list's entry counts)
use PostgREST resource embedding instead of an ``.in_()`` id list, so no
URL-length batching is needed.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol
from uuid import UUID, uuid4

from app.stores._util import utcnow
from app.stores.errors import Conflict, NotFound
from noctusai_lib.integrations.persistence.paging import iter_paged_rows

logger = logging.getLogger(__name__)

__all__ = [
    "MODELS",
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
    "StudioDefinitionStore",
    "FakeStudioDefinitionStore",
    "SupabaseStudioDefinitionStore",
    "get_studio_definition_store",
]

_SCHEMA = "agents"

#: 012 `model` CHECK (§A10 — same allowlist as personas).
MODELS = ("claude-opus-5", "claude-sonnet-5")
#: 012 `effort` CHECK.
EFFORTS = ("low", "medium", "high", "xhigh", "max")
VERSION_STATUSES = ("rascunho", "ativa", "substituida")
CLIENT_ENTRY_TIPOS = (
    "marca", "publico", "posicionamento", "trava", "decisao", "aprendizado", "evidencia", "nota",
)
CLIENT_ENTRY_STATUSES = ("ativo", "arquivado")
#: `create_agent_draft` with no source (012).
DRAFT_DEFAULTS = {
    "model": "claude-opus-5",
    "effort": "high",
    "max_turns": 40,
    "idioma": "pt-BR",
    "tool_policy": {"web_search": True, "knowledge": True},
}

_AGENT_FIELDS = ("nome", "descricao", "ativo", "publicacao_limiar")
_DRAFT_FIELDS = ("notas", "model", "effort", "max_turns", "idioma", "tool_policy")
_SKILL_FIELDS = ("nome", "descricao", "corpo", "ordem", "ativo")
_CLIENT_FIELDS = ("slug", "nome", "resumo", "ativo")
_ENTRY_FIELDS = ("tipo", "titulo", "conteudo", "status")


# ── errors ──────────────────────────────────────────────────────────────────


class StudioConflict(Conflict):
    """A write refused for a machine-readable reason (``code`` = the §D 409
    code: ``key_taken`` / ``draft_exists`` / ``skill_exists`` /
    ``client_exists`` / ``chave_conflict`` / ``draft_referenced``)."""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


class VersionImmutable(StudioConflict):
    """The target version (or a child of it) is not a ``rascunho``."""

    def __init__(self, message: str = "") -> None:
        super().__init__("version_immutable", message or "version_immutable")


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


# ── validation shared by Fake + Real (mirrors the 012 CHECKs) ──────────────


def _validate_draft_fields(fields: dict[str, Any]) -> None:
    unknown = set(fields) - set(_DRAFT_FIELDS)
    if unknown:
        raise ValueError(f"unknown draft fields: {sorted(unknown)}")
    if "model" in fields and fields["model"] not in MODELS:
        raise ValueError(f"model must be one of {MODELS}; got {fields['model']!r}")
    if "effort" in fields and fields["effort"] not in EFFORTS:
        raise ValueError(f"effort must be one of {EFFORTS}; got {fields['effort']!r}")
    if "max_turns" in fields and not (1 <= int(fields["max_turns"]) <= 200):
        raise ValueError(f"max_turns must be between 1 and 200; got {fields['max_turns']!r}")
    if "tool_policy" in fields and not isinstance(fields["tool_policy"], dict):
        raise ValueError("tool_policy must be an object")


def _validate_entry(fields: dict[str, Any]) -> None:
    if "tipo" in fields and fields["tipo"] not in CLIENT_ENTRY_TIPOS:
        raise ValueError(f"tipo must be one of {CLIENT_ENTRY_TIPOS}; got {fields['tipo']!r}")
    if "status" in fields and fields["status"] not in CLIENT_ENTRY_STATUSES:
        raise ValueError(f"status must be one of {CLIENT_ENTRY_STATUSES}; got {fields['status']!r}")


def _check_fields(fields: dict[str, Any], allowed: tuple[str, ...], what: str) -> None:
    unknown = set(fields) - set(allowed)
    if unknown:
        raise ValueError(f"unknown {what} fields: {sorted(unknown)}")


# ── Protocol ────────────────────────────────────────────────────────────────


class StudioDefinitionStore(Protocol):
    # agents (studio columns)
    def list_agents(self, org_id: UUID) -> list[StudioAgentRecord]: ...
    def get_agent(self, org_id: UUID, key: str) -> StudioAgentRecord: ...
    def create_studio_agent(
        self, org_id: UUID, key: str, nome: str, descricao: str | None
    ) -> StudioAgentRecord:
        """``definition_mode='studio'``, ``runtime='claude_sdk'``, ``ativo=false``.
        Raises ``StudioConflict('key_taken')``."""
        ...
    def update_agent(self, org_id: UUID, key: str, fields: dict[str, Any]) -> StudioAgentRecord: ...

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
    def set_compiled_hash(self, org_id: UUID, version_id: UUID, compiled_hash: str) -> VersionRecord: ...
    def publish_version(
        self, org_id: UUID, version_id: UUID, published_by: UUID,
        eval_run_id: UUID | None, override_reason: str | None,
    ) -> VersionRecord:
        """``agents.publish_agent_version`` — the gate is the caller's job."""
        ...
    def discard_draft(self, org_id: UUID, version_id: UUID) -> None: ...

    # sections
    def list_sections(self, org_id: UUID, version_id: UUID) -> list[SectionRecord]: ...
    def replace_sections(
        self, org_id: UUID, version_id: UUID, secoes: list[SectionInput]
    ) -> list[SectionRecord]:
        """Full replace; an input ``id`` of an existing section of THIS
        version keeps that id, anything else gets a new one."""
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
    def update_skill(self, org_id: UUID, skill_id: UUID, fields: dict[str, Any]) -> SkillRecord: ...
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


# ── Fake ────────────────────────────────────────────────────────────────────


class FakeStudioDefinitionStore:
    """In-memory :class:`StudioDefinitionStore`.

    Emulates 012: the partial uniques (one rascunho / one ativa), the
    immutability triggers (children of a non-draft raise
    :class:`VersionImmutable`), the deep-copy of ``create_agent_draft`` and
    the atomic flip of ``publish_agent_version``.

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
        self._seq = 0

    def _now(self) -> datetime:
        # Strictly increasing timestamps keep "newest first"/"oldest first"
        # orderings deterministic within one fast test.
        from datetime import timedelta

        self._seq += 1
        return utcnow() + timedelta(microseconds=self._seq)

    # ── test helper
    def add_legacy_agent(self, org_id: UUID, key: str, nome: str) -> StudioAgentRecord:
        now = self._now()
        rec = StudioAgentRecord(
            id=uuid4(), org_id=org_id, key=key, nome=nome, descricao=None,
            definition_mode="legacy", runtime="claude_sdk", ativo=False,
            publicacao_limiar=0.8, created_at=now, updated_at=now,
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
        self, org_id: UUID, key: str, nome: str, descricao: str | None
    ) -> StudioAgentRecord:
        if (org_id, key) in self._agents:
            raise StudioConflict("key_taken", f"agent key {key!r} already exists")
        now = self._now()
        rec = StudioAgentRecord(
            id=uuid4(), org_id=org_id, key=key, nome=nome, descricao=descricao,
            definition_mode="studio", runtime="claude_sdk", ativo=False,
            publicacao_limiar=0.8, created_at=now, updated_at=now,
        )
        self._agents[(org_id, key)] = rec
        return rec

    def update_agent(self, org_id: UUID, key: str, fields: dict[str, Any]) -> StudioAgentRecord:
        _check_fields(fields, _AGENT_FIELDS, "agent")
        rec = self.get_agent(org_id, key)
        if "publicacao_limiar" in fields and not (0 <= float(fields["publicacao_limiar"]) <= 1):
            raise ValueError("publicacao_limiar must be between 0 and 1")
        rec = replace(rec, **fields, updated_at=self._now())
        self._agents[(org_id, key)] = rec
        return rec

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
                "model": src.model, "effort": src.effort, "max_turns": src.max_turns,
                "idioma": src.idioma, "tool_policy": dict(src.tool_policy),
            }
            based_on = src.id
        draft = VersionRecord(
            id=uuid4(), org_id=org_id, agent_id=agent_id, versao=versao, status="rascunho",
            notas=None, based_on_version_id=based_on, created_by=created_by,
            published_by=None, published_at=None, compiled_hash=None, eval_run_id=None,
            publish_override_reason=None, created_at=now, updated_at=now, **settings,
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
        return draft

    def _require_draft(self, org_id: UUID, version_id: UUID) -> VersionRecord:
        v = self.get_version(org_id, version_id)
        if v.status != "rascunho":
            raise VersionImmutable(f"version {version_id} is {v.status}")
        return v

    def update_draft(self, org_id: UUID, version_id: UUID, fields: dict[str, Any]) -> VersionRecord:
        _validate_draft_fields(fields)
        v = self._require_draft(org_id, version_id)
        v = replace(v, **fields, updated_at=self._now())
        self._versions[v.id] = v
        return v

    def set_compiled_hash(self, org_id: UUID, version_id: UUID, compiled_hash: str) -> VersionRecord:
        v = self._require_draft(org_id, version_id)
        v = replace(v, compiled_hash=compiled_hash, updated_at=self._now())
        self._versions[v.id] = v
        return v

    def publish_version(
        self, org_id: UUID, version_id: UUID, published_by: UUID,
        eval_run_id: UUID | None, override_reason: str | None,
    ) -> VersionRecord:
        v = self._require_draft(org_id, version_id)
        now = self._now()
        current = self.get_active_version(org_id, v.agent_id)
        if current is not None:
            self._versions[current.id] = replace(current, status="substituida", updated_at=now)
        v = replace(
            v, status="ativa", published_by=published_by, published_at=now,
            eval_run_id=eval_run_id, publish_override_reason=override_reason, updated_at=now,
        )
        self._versions[v.id] = v
        return v

    def discard_draft(self, org_id: UUID, version_id: UUID) -> None:
        self._require_draft(org_id, version_id)
        if any(c.version_id == version_id for c in self._compiled.values()):
            raise StudioConflict("draft_referenced", "the draft is referenced by a stored compiled prompt")
        for sk in self._skills_of(version_id):
            for fid in [f.id for f in self._files.values() if f.skill_id == sk.id]:
                del self._files[fid]
            del self._skills[sk.id]
        for s in self._sections_of(version_id):
            del self._sections[s.id]
        del self._versions[version_id]

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
        return self._sections_of(version_id)

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
        if any(s.nome == nome for s in self._skills_of(version_id)):
            raise StudioConflict("skill_exists", f"skill {nome!r} already exists")
        now = self._now()
        sk = SkillRecord(
            id=uuid4(), org_id=org_id, version_id=version_id, nome=nome, descricao=descricao,
            corpo=corpo, ordem=ordem, ativo=ativo, created_at=now, updated_at=now,
        )
        self._skills[sk.id] = sk
        return sk

    def update_skill(self, org_id: UUID, skill_id: UUID, fields: dict[str, Any]) -> SkillRecord:
        _check_fields(fields, _SKILL_FIELDS, "skill")
        sk = self.get_skill(org_id, skill_id)
        self._require_draft(org_id, sk.version_id)
        if "nome" in fields and fields["nome"] != sk.nome and any(
            s.nome == fields["nome"] for s in self._skills_of(sk.version_id)
        ):
            raise StudioConflict("skill_exists", f"skill {fields['nome']!r} already exists")
        sk = replace(sk, **fields, updated_at=self._now())
        self._skills[sk.id] = sk
        return sk

    def delete_skill(self, org_id: UUID, skill_id: UUID) -> None:
        sk = self.get_skill(org_id, skill_id)
        self._require_draft(org_id, sk.version_id)
        for fid in [f.id for f in self._files.values() if f.skill_id == skill_id]:
            del self._files[fid]
        del self._skills[skill_id]

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
        sk = self.get_skill(org_id, skill_id)
        self._require_draft(org_id, sk.version_id)
        now = self._now()
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
        self.get_client(org_id, client_id)
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
        e = self.get_client_entry(org_id, entry_id)
        e = replace(e, **fields, updated_at=self._now())
        self._entries[e.id] = e
        return e

    def delete_client_entry(self, org_id: UUID, entry_id: UUID) -> None:
        self.get_client_entry(org_id, entry_id)
        del self._entries[entry_id]

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


# ── Real ────────────────────────────────────────────────────────────────────


def _uuid_or_none(v: Any) -> UUID | None:
    return UUID(str(v)) if v is not None else None


def _float(v: Any) -> float:
    return float(Decimal(str(v)))


def _api_error_text(exc: Exception) -> tuple[str | None, str]:
    code = getattr(exc, "code", None)
    msg = getattr(exc, "message", None) or str(exc)
    return code, msg


def _map_db_error(exc: Exception, *, unique_code: str | None = None) -> Exception:
    """Translate a PostgREST error into the store's typed error. The 012
    triggers/functions raise with the machine code AS the message."""
    code, msg = _api_error_text(exc)
    if "version_immutable" in msg:
        return VersionImmutable(msg)
    if "compiled_prompt_immutable" in msg:
        return StudioConflict("compiled_prompt_immutable", msg)
    if "draft_exists" in msg:
        return StudioConflict("draft_exists", msg)
    if "version_not_found" in msg or "agent_not_found" in msg:
        return NotFound(msg)
    if code == "23505" and unique_code is not None:
        return StudioConflict(unique_code, msg)
    if code == "23503":
        return StudioConflict("draft_referenced", msg)
    return exc


class SupabaseStudioDefinitionStore:
    """Real :class:`StudioDefinitionStore` — Postgres via the admin client.

    Bare table names through ``client.schema("agents").table(...)`` — never
    ``"agents.x"`` (``KB § PATTERNS/backend/postgrest-schema-targeting.md``).
    """

    def __init__(self, client: Any) -> None:
        self._client = client

    def _t(self, table: str):
        return self._client.schema(_SCHEMA).table(table)

    def _rpc(self, fn: str, params: dict[str, Any]):
        try:
            return self._client.schema(_SCHEMA).rpc(fn, params).execute()
        except Exception as exc:
            mapped = _map_db_error(exc)
            if mapped is exc:
                raise
            raise mapped from exc

    def _exec(self, query, *, unique_code: str | None = None):
        try:
            return query.execute()
        except Exception as exc:
            mapped = _map_db_error(exc, unique_code=unique_code)
            if mapped is exc:
                raise
            raise mapped from exc

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
        )

    @staticmethod
    def _version(row: dict[str, Any]) -> VersionRecord:
        return VersionRecord(
            id=UUID(str(row["id"])), org_id=UUID(str(row["org_id"])),
            agent_id=UUID(str(row["agent_id"])), versao=int(row["versao"]), status=row["status"],
            notas=row.get("notas"), model=row["model"], effort=row["effort"],
            max_turns=int(row["max_turns"]), idioma=row["idioma"],
            tool_policy=dict(row.get("tool_policy") or {}),
            based_on_version_id=_uuid_or_none(row.get("based_on_version_id")),
            created_by=UUID(str(row["created_by"])),
            published_by=_uuid_or_none(row.get("published_by")),
            published_at=row.get("published_at"), compiled_hash=row.get("compiled_hash"),
            eval_run_id=_uuid_or_none(row.get("eval_run_id")),
            publish_override_reason=row.get("publish_override_reason"),
            created_at=row["created_at"], updated_at=row["updated_at"],
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
        self, org_id: UUID, key: str, nome: str, descricao: str | None
    ) -> StudioAgentRecord:
        payload = {
            "org_id": str(org_id), "key": key, "nome": nome, "descricao": descricao,
            "runtime": "claude_sdk", "definition_mode": "studio", "ativo": False,
        }
        resp = self._exec(self._t("agents").insert(payload), unique_code="key_taken")
        return self._agent(self._one(resp, f"agent {key!r}"))

    def update_agent(self, org_id: UUID, key: str, fields: dict[str, Any]) -> StudioAgentRecord:
        _check_fields(fields, _AGENT_FIELDS, "agent")
        if not fields:
            return self.get_agent(org_id, key)
        resp = self._exec(
            self._t("agents").update(dict(fields)).eq("org_id", str(org_id)).eq("key", key)
        )
        return self._agent(self._one(resp, f"agent {key!r}"))

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
        _validate_draft_fields(fields)
        if not fields:
            return self.get_version(org_id, version_id)
        resp = self._exec(
            self._t("agent_versions").update(dict(fields))
            .eq("org_id", str(org_id)).eq("id", str(version_id)).eq("status", "rascunho")
        )
        rows = resp.data or []
        if not rows:
            # Either missing (NotFound) or not a draft (immutable) — tell which.
            v = self.get_version(org_id, version_id)
            raise VersionImmutable(f"version {version_id} is {v.status}")
        return self._version(rows[0])

    def set_compiled_hash(self, org_id: UUID, version_id: UUID, compiled_hash: str) -> VersionRecord:
        resp = self._exec(
            self._t("agent_versions").update({"compiled_hash": compiled_hash})
            .eq("org_id", str(org_id)).eq("id", str(version_id)).eq("status", "rascunho")
        )
        rows = resp.data or []
        if not rows:
            v = self.get_version(org_id, version_id)
            raise VersionImmutable(f"version {version_id} is {v.status}")
        return self._version(rows[0])

    def publish_version(
        self, org_id: UUID, version_id: UUID, published_by: UUID,
        eval_run_id: UUID | None, override_reason: str | None,
    ) -> VersionRecord:
        self._rpc("publish_agent_version", {
            "p_org_id": str(org_id),
            "p_version_id": str(version_id),
            "p_published_by": str(published_by),
            "p_eval_run_id": str(eval_run_id) if eval_run_id else None,
            "p_override_reason": override_reason,
        })
        return self.get_version(org_id, version_id)

    def discard_draft(self, org_id: UUID, version_id: UUID) -> None:
        self._rpc("discard_agent_draft", {"p_org_id": str(org_id), "p_version_id": str(version_id)})

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
        """Delete the sections no longer present, then upsert the payload by
        id (new rows get a pre-generated id). Not one transaction — but
        every step is guarded by the draft-only trigger, and a failure
        surfaces (never swallowed); the caller still holds the full payload
        to retry. A chave SWAP between two existing rows hits the unique
        constraint mid-upsert → ``StudioConflict('chave_conflict')``."""
        draft = self.get_version(org_id, version_id)
        if draft.status != "rascunho":
            raise VersionImmutable(f"version {version_id} is {draft.status}")
        chaves = [s.chave for s in secoes]
        if len(set(chaves)) != len(chaves):
            raise StudioConflict("chave_conflict", "duplicate chave in payload")
        existing = {s.id for s in self.list_sections(org_id, version_id)}
        keep_ids = {s.id for s in secoes if s.id is not None and s.id in existing}
        for sid in existing - keep_ids:
            self._exec(
                self._t("agent_prompt_sections").delete()
                .eq("org_id", str(org_id)).eq("id", str(sid))
            )
        # A removed row's chave is free again here (deleted above), so a new
        # row may reuse it; only a swap between two KEPT rows can collide.
        rows = []
        for s in secoes:
            sid = s.id if s.id in keep_ids else uuid4()
            rows.append({
                "id": str(sid), "org_id": str(org_id), "version_id": str(version_id),
                "chave": s.chave, "titulo": s.titulo, "ordem": s.ordem,
                "conteudo": s.conteudo, "ativo": s.ativo,
            })
        if rows:
            self._exec(
                self._t("agent_prompt_sections").upsert(rows, on_conflict="id"),
                unique_code="chave_conflict",
            )
        return self.list_sections(org_id, version_id)

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
        payload = {
            "org_id": str(org_id), "version_id": str(version_id), "nome": nome,
            "descricao": descricao, "corpo": corpo, "ordem": ordem, "ativo": ativo,
        }
        resp = self._exec(self._t("agent_skills").insert(payload), unique_code="skill_exists")
        return self._skill(self._one(resp, f"skill {nome!r}"))

    def update_skill(self, org_id: UUID, skill_id: UUID, fields: dict[str, Any]) -> SkillRecord:
        _check_fields(fields, _SKILL_FIELDS, "skill")
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
        payload = {
            "org_id": str(org_id), "agent_id": str(agent_id), "slug": slug, "nome": nome,
            "resumo": resumo, "ativo": ativo,
        }
        resp = self._exec(self._t("agent_clients").insert(payload), unique_code="client_exists")
        return self._client_rec(self._one(resp, f"client {slug!r}"))

    def update_client(self, org_id: UUID, client_id: UUID, fields: dict[str, Any]) -> ClientRecord:
        _check_fields(fields, _CLIENT_FIELDS, "client")
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
        payload = {
            "org_id": str(org_id), "client_id": str(client_id), "tipo": tipo,
            "titulo": titulo, "conteudo": conteudo, "status": status,
        }
        resp = self._exec(self._t("agent_client_entries").insert(payload))
        return self._entry(self._one(resp, "client entry"))

    def update_client_entry(self, org_id: UUID, entry_id: UUID, fields: dict[str, Any]) -> ClientEntryRecord:
        _check_fields(fields, _ENTRY_FIELDS, "entry")
        _validate_entry(fields)
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


def get_studio_definition_store(settings: Any) -> StudioDefinitionStore:
    """Real when a Supabase service-role key is configured, Fake otherwise —
    same signal as :func:`app.stores.agents.get_agent_store`."""
    if not getattr(settings, "supabase_service_role_key", None):
        return FakeStudioDefinitionStore()
    from app.database import get_admin_client

    return SupabaseStudioDefinitionStore(get_admin_client())

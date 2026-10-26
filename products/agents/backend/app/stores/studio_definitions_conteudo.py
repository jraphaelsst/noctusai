"""Julia v2 content layer of the Agent Studio definitions store (CONTRACT §2.2, §2.6).

Structure in code, content in rows. This module holds, for BOTH the Fake and the Real store
(mixed into ``FakeStudioDefinitionStore`` / ``SupabaseStudioDefinitionStore``, which stay the one
``StudioDefinitionStore``):

* the four version-scoped content tables of migration 031 — ``agent_version_textos`` (system
  texts), ``agent_version_ferramentas`` (tool descriptions), ``agent_version_decisoes`` (typed
  decisions), ``agent_version_specs`` (the org-spec DECLARATIONS) — written with REPLACE-SET
  semantics on a DRAFT only (a published version is immutable; every write NULLs the draft's
  ``compiled_hash``), validated here before any write so the Fake and the Real refuse the same
  inputs;
* ``agent_org_specs`` — the per-org VALUES of the declared specs (live org data, upserted);
* ``textos_plataforma`` — platform-wide texts (judge prompt, template content);
* the platform-definition lookups (``get_agent_by_id`` / ``get_platform_definition``) the
  resolution API (``app.studio.resolucao``) is built on, and ``append_audit``.

Every method takes ``org_id`` and filters by it, exactly like the rest of the store.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID, uuid4

from app.stores._db_errors import StudioConflict
from app.stores.errors import NotFound
from app.studio.especificacoes import SPEC_CHAVE_RE
from app.studio.ferramentas_registry import ferramenta_conhecida
from app.studio.models import LIMITS, SPEC_TIPOS
from app.studio.textos_registry import TEXTOS
from noctusai_lib.integrations.persistence.paging import iter_paged_rows

logger = logging.getLogger(__name__)

__all__ = [
    "TextoInput",
    "TextoRecord",
    "FerramentaInput",
    "FerramentaRecord",
    "DecisaoInput",
    "DecisaoRecord",
    "SpecDefInput",
    "SpecDefRecord",
    "OrgSpecRecord",
    "PlataformaTextoRecord",
    "ConteudoStore",
    "FakeConteudoMixin",
    "SupabaseConteudoMixin",
]

_FERRAMENTA_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
_DECISAO_CHAVE_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_PLAT_CHAVE_RE = re.compile(r"^[a-z0-9]+(\.[a-z0-9_]+)+$")
#: ``replace_draft_conteudo``'s ``p_tabela`` values (migration 031).
_TABELAS = ("textos", "ferramentas", "decisoes", "specs")


# ── records / inputs ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TextoInput:
    chave: str
    conteudo: str = ""


@dataclass(frozen=True)
class TextoRecord:
    id: UUID
    org_id: UUID
    version_id: UUID
    chave: str
    conteudo: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class FerramentaInput:
    ferramenta: str
    descricao: str
    ativo: bool = True
    parametros: dict[str, str] = field(default_factory=dict)
    obrigatoria_skill: str | None = None


@dataclass(frozen=True)
class FerramentaRecord:
    id: UUID
    org_id: UUID
    version_id: UUID
    ferramenta: str
    ativo: bool
    descricao: str
    parametros: dict[str, Any]
    obrigatoria_skill: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class DecisaoInput:
    chave: str
    titulo: str
    regra: str = ""
    #: ``[{"valor", "rotulo", "padrao"}]`` — ``[]`` (options still to set) or ≥ 1 with unique
    #: valores and EXACTLY ONE ``padrao`` (the answer used when the asker cannot be served).
    opcoes: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class DecisaoRecord:
    id: UUID
    org_id: UUID
    version_id: UUID
    chave: str
    titulo: str
    regra: str
    opcoes: list[dict[str, Any]]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class SpecDefInput:
    chave: str
    rotulo: str
    descricao: str = ""
    tipo: str = "texto"
    obrigatoria: bool = True
    exemplo: str | None = None


@dataclass(frozen=True)
class SpecDefRecord:
    id: UUID
    org_id: UUID
    version_id: UUID
    chave: str
    rotulo: str
    descricao: str
    tipo: str
    obrigatoria: bool
    exemplo: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class OrgSpecRecord:
    id: UUID
    org_id: UUID
    agent_key: str
    chave: str
    valor: str
    updated_by: UUID | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class PlataformaTextoRecord:
    chave: str
    conteudo: str
    updated_by: UUID | None
    updated_at: datetime


# ── validation shared by Fake + Real (mirrors the 031 CHECKs) ───────────────


def _cap(value: str | None, key: str, what: str) -> None:
    limit = LIMITS[key]
    if value is not None and len(value) > limit:
        raise ValueError(f"{what} exceeds {limit} characters ({len(value)})")


def _dups(chaves: list[str], what: str) -> None:
    if len(set(chaves)) != len(chaves):
        raise StudioConflict("chave_conflict", f"duplicate {what} in payload")


def validar_opcoes(opcoes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The 031 ``decisao_opcoes_ok``: ``[]`` or ≥ 1 ``{valor, rotulo, padrao}`` with unique
    valores and exactly one ``padrao``. Returns the normalised list."""
    if not isinstance(opcoes, list):
        raise ValueError("opcoes must be a list")
    out: list[dict[str, Any]] = []
    for o in opcoes:
        if not isinstance(o, dict):
            raise ValueError("each opcao must be an object")
        valor, rotulo, padrao = o.get("valor"), o.get("rotulo"), o.get("padrao")
        if not isinstance(valor, str) or not valor:
            raise ValueError("opcao.valor must be a non-empty string")
        if not isinstance(rotulo, str):
            raise ValueError("opcao.rotulo must be a string")
        if not isinstance(padrao, bool):
            raise ValueError("opcao.padrao must be a boolean")
        out.append({"valor": valor, "rotulo": rotulo, "padrao": padrao})
    if out:
        if len({o["valor"] for o in out}) != len(out):
            raise ValueError("opcao.valor must be unique")
        if sum(1 for o in out if o["padrao"]) != 1:
            raise ValueError("exactly one opcao must be padrao")
    return out


def validar_textos(itens: list[TextoInput]) -> None:
    _dups([t.chave for t in itens], "texto chave")
    for t in itens:
        if t.chave not in TEXTOS:
            raise ValueError(f"texto chave {t.chave!r} is not in the registry")
        _cap(t.conteudo, "texto.conteudo", "texto conteudo")


def validar_ferramentas(itens: list[FerramentaInput]) -> None:
    _dups([f.ferramenta for f in itens], "ferramenta")
    for f in itens:
        if not _FERRAMENTA_RE.match(f.ferramenta):
            raise ValueError(f"invalid ferramenta name {f.ferramenta!r}")
        if not ferramenta_conhecida(f.ferramenta):
            raise ValueError(f"ferramenta {f.ferramenta!r} is not in the code registry")
        if not (1 <= len(f.descricao.strip()) and len(f.descricao) <= LIMITS["ferramenta.descricao"]):
            raise ValueError(f"ferramenta descricao must have 1..{LIMITS['ferramenta.descricao']} characters")
        if not isinstance(f.parametros, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in f.parametros.items()
        ):
            raise ValueError("ferramenta parametros must map parameter name -> description (strings)")
        for v in f.parametros.values():
            _cap(v, "ferramenta.descricao", "parametro descricao")


def validar_decisoes(itens: list[DecisaoInput]) -> list[DecisaoInput]:
    _dups([d.chave for d in itens], "decisao chave")
    out = []
    for d in itens:
        if not _DECISAO_CHAVE_RE.match(d.chave):
            raise ValueError(f"invalid decisao chave {d.chave!r}")
        _cap(d.regra, "decisao.regra", "decisao regra")
        out.append(replace(d, opcoes=validar_opcoes(list(d.opcoes))))
    return out


def validar_specs(itens: list[SpecDefInput]) -> None:
    _dups([s.chave for s in itens], "spec chave")
    for s in itens:
        if not SPEC_CHAVE_RE.match(s.chave):
            raise ValueError(f"invalid spec chave {s.chave!r}")
        if not s.rotulo.strip():
            raise ValueError("spec rotulo must not be blank")
        if s.tipo not in SPEC_TIPOS:
            raise ValueError(f"spec tipo must be one of {SPEC_TIPOS}; got {s.tipo!r}")
        _cap(s.descricao, "spec.descricao", "spec descricao")
        _cap(s.exemplo, "spec.exemplo", "spec exemplo")


def validar_org_specs(valores: dict[str, str]) -> None:
    for chave, valor in valores.items():
        if not SPEC_CHAVE_RE.match(chave):
            raise ValueError(f"invalid spec chave {chave!r}")
        if not isinstance(valor, str):
            raise ValueError(f"spec {chave!r} value must be a string")
        _cap(valor, "org_spec.valor.texto_longo", f"spec {chave!r} valor")


def validar_textos_plataforma(itens: dict[str, str]) -> None:
    for chave, conteudo in itens.items():
        if not _PLAT_CHAVE_RE.match(chave):
            raise ValueError(f"invalid texto chave {chave!r}")
        _cap(conteudo, "texto.conteudo", "texto conteudo")


# ── Protocol ────────────────────────────────────────────────────────────────


class ConteudoStore(Protocol):
    # platform definition lookups (resolution API)
    def get_agent_by_id(self, agent_id: UUID) -> Any:
        """The ``agents.agents`` row with this id — ANY org (the instance → definition hop)."""
        ...

    def get_platform_definition(self, key: str) -> Any | None:
        """The ``definition_scope='plataforma'`` row of ``key`` (at most one), or ``None``."""
        ...

    def list_platform_definitions(self) -> list[Any]:
        """Every ``definition_scope='plataforma'`` row (the platform org's), newest key order. The data-driven
        replacement of the old code registry: org-instance creation iterates this."""
        ...

    # org grants (050): the allow-list of orgs that may hold an INSTANCE of a non-instanciavel definition
    def grant_definition_org(self, definition_id: UUID, org_id: UUID, granted_by: UUID | None = None) -> bool:
        """Allow ``org_id`` to hold an instance of the definition. Idempotent; ``True`` when newly granted."""
        ...

    def list_definition_grants(self, definition_id: UUID) -> list[UUID]:
        """The org ids granted the definition (sorted)."""
        ...

    def is_definition_granted(self, definition_id: UUID, org_id: UUID) -> bool: ...

    def append_audit(
        self, org_id: UUID, agent_id: UUID, actor: UUID | None, acao: str,
        antes: dict[str, Any] | None, depois: dict[str, Any] | None,
    ) -> None: ...

    # version-scoped content (replace-set, draft only)
    def list_textos(self, org_id: UUID, version_id: UUID) -> list[TextoRecord]: ...
    def replace_textos(self, org_id: UUID, version_id: UUID, itens: list[TextoInput], *, expected_hash: str | None = None) -> list[TextoRecord]: ...
    def list_ferramentas(self, org_id: UUID, version_id: UUID) -> list[FerramentaRecord]: ...
    def replace_ferramentas(
        self, org_id: UUID, version_id: UUID, itens: list[FerramentaInput], *, expected_hash: str | None = None,
    ) -> list[FerramentaRecord]: ...
    def list_decisoes(self, org_id: UUID, version_id: UUID) -> list[DecisaoRecord]: ...
    def replace_decisoes(
        self, org_id: UUID, version_id: UUID, itens: list[DecisaoInput], *, expected_hash: str | None = None,
    ) -> list[DecisaoRecord]: ...
    def list_spec_defs(self, org_id: UUID, version_id: UUID) -> list[SpecDefRecord]: ...
    def replace_spec_defs(
        self, org_id: UUID, version_id: UUID, itens: list[SpecDefInput], *, expected_hash: str | None = None,
    ) -> list[SpecDefRecord]: ...

    # per-org spec values
    def list_org_specs(self, org_id: UUID, agent_key: str) -> list[OrgSpecRecord]: ...
    def upsert_org_specs(
        self, org_id: UUID, agent_key: str, valores: dict[str, str], *, actor: UUID | None = None,
    ) -> list[OrgSpecRecord]: ...

    # platform-wide texts
    def list_textos_plataforma(self) -> list[PlataformaTextoRecord]: ...
    def set_textos_plataforma(
        self, itens: dict[str, str], *, actor: UUID | None = None,
    ) -> list[PlataformaTextoRecord]: ...


# ── Fake ────────────────────────────────────────────────────────────────────


class FakeConteudoMixin:
    """In-memory content layer. Mixed into ``FakeStudioDefinitionStore`` (it uses that class's
    ``_versions`` / ``_agents`` / ``_require_draft`` / ``_touch_draft`` / ``_now`` /
    ``_audit_append``). Emulates 031: draft-only writes that NULL the draft's hash, the
    based-on copy trigger (:meth:`_copy_conteudo`) and the version cascade (:meth:`_drop_conteudo`)."""

    def _init_conteudo(self) -> None:
        self._textos: dict[UUID, TextoRecord] = {}
        self._ferramentas: dict[UUID, FerramentaRecord] = {}
        self._decisoes: dict[UUID, DecisaoRecord] = {}
        self._specs: dict[UUID, SpecDefRecord] = {}
        self._org_specs: dict[tuple[UUID, str, str], OrgSpecRecord] = {}
        self._textos_plat: dict[str, PlataformaTextoRecord] = {}

    # platform definition lookups
    def get_agent_by_id(self, agent_id: UUID):
        for rec in self._agents.values():
            if rec.id == agent_id:
                return rec
        raise NotFound(f"agent {agent_id} not found")

    def get_platform_definition(self, key: str):
        for rec in self._agents.values():
            if rec.key == key and rec.definition_scope == "plataforma":
                return rec
        return None

    def list_platform_definitions(self):
        return sorted((r for r in self._agents.values() if r.definition_scope == "plataforma"), key=lambda r: r.key)

    def grant_definition_org(self, definition_id, org_id, granted_by=None) -> bool:
        grants = self.__dict__.setdefault("_grants", set())
        if (definition_id, org_id) in grants:
            return False
        self.get_agent_by_id(definition_id)  # FK: the definition exists
        grants.add((definition_id, org_id))
        return True

    def list_definition_grants(self, definition_id):
        return sorted(o for d, o in self.__dict__.get("_grants", set()) if d == definition_id)

    def is_definition_granted(self, definition_id, org_id) -> bool:
        return (definition_id, org_id) in self.__dict__.get("_grants", set())

    def append_audit(self, org_id, agent_id, actor, acao, antes, depois) -> None:
        self._agent_by_id(org_id, agent_id)
        self._audit_append(org_id, agent_id, actor, acao, antes, depois)

    # based-on copy / cascade (031 triggers)
    def _copy_conteudo(self, src_id: UUID, dst_id: UUID, org_id: UUID) -> None:
        now = self._now()
        for store in (self._textos, self._ferramentas, self._decisoes, self._specs):
            for r in [r for r in store.values() if r.version_id == src_id]:
                nid = uuid4()
                store[nid] = replace(r, id=nid, version_id=dst_id, org_id=org_id, created_at=now, updated_at=now)

    def _drop_conteudo(self, version_id: UUID) -> None:
        for store in (self._textos, self._ferramentas, self._decisoes, self._specs):
            for rid in [rid for rid, r in store.items() if r.version_id == version_id]:
                del store[rid]

    def _replace(self, store: dict, org_id: UUID, version_id: UUID, key_of, build, expected_hash: str | None = None) -> None:
        draft = self._require_draft(org_id, version_id)
        # 040 `replace_draft_conteudo(p_expected_hash)`: the compare and the replace are one step
        if expected_hash is not None and draft.compiled_hash != expected_hash:
            raise StudioConflict("conflito_de_versao", "the draft changed since it was read")
        old = {key_of(r): r for r in store.values() if r.version_id == version_id}
        for rid in [rid for rid, r in store.items() if r.version_id == version_id]:
            del store[rid]
        now = self._now()
        for new in build(old, now):
            store[new.id] = new
        self._touch_draft(version_id)

    # textos
    def list_textos(self, org_id: UUID, version_id: UUID) -> list[TextoRecord]:
        self.get_version(org_id, version_id)
        return sorted((r for r in self._textos.values() if r.version_id == version_id), key=lambda r: r.chave)

    def replace_textos(self, org_id, version_id, itens, *, expected_hash=None):
        validar_textos(itens)
        self._replace(
            self._textos, org_id, version_id, lambda r: r.chave,
            lambda old, now: [
                TextoRecord(
                    id=uuid4(), org_id=org_id, version_id=version_id, chave=i.chave, conteudo=i.conteudo,
                    created_at=old[i.chave].created_at if i.chave in old else now, updated_at=now,
                )
                for i in itens
            ],
            expected_hash=expected_hash,
        )
        return self.list_textos(org_id, version_id)

    # ferramentas
    def list_ferramentas(self, org_id: UUID, version_id: UUID) -> list[FerramentaRecord]:
        self.get_version(org_id, version_id)
        return sorted(
            (r for r in self._ferramentas.values() if r.version_id == version_id), key=lambda r: r.ferramenta,
        )

    def replace_ferramentas(self, org_id, version_id, itens, *, expected_hash=None):
        validar_ferramentas(itens)
        self._replace(
            self._ferramentas, org_id, version_id, lambda r: r.ferramenta,
            lambda old, now: [
                FerramentaRecord(
                    id=uuid4(), org_id=org_id, version_id=version_id, ferramenta=i.ferramenta, ativo=i.ativo,
                    descricao=i.descricao, parametros=dict(i.parametros), obrigatoria_skill=i.obrigatoria_skill,
                    created_at=old[i.ferramenta].created_at if i.ferramenta in old else now, updated_at=now,
                )
                for i in itens
            ],
            expected_hash=expected_hash,
        )
        return self.list_ferramentas(org_id, version_id)

    # decisoes
    def list_decisoes(self, org_id: UUID, version_id: UUID) -> list[DecisaoRecord]:
        self.get_version(org_id, version_id)
        return sorted((r for r in self._decisoes.values() if r.version_id == version_id), key=lambda r: r.chave)

    def replace_decisoes(self, org_id, version_id, itens, *, expected_hash=None):
        itens = validar_decisoes(itens)
        self._replace(
            self._decisoes, org_id, version_id, lambda r: r.chave,
            lambda old, now: [
                DecisaoRecord(
                    id=uuid4(), org_id=org_id, version_id=version_id, chave=i.chave, titulo=i.titulo,
                    regra=i.regra, opcoes=[dict(o) for o in i.opcoes],
                    created_at=old[i.chave].created_at if i.chave in old else now, updated_at=now,
                )
                for i in itens
            ],
            expected_hash=expected_hash,
        )
        return self.list_decisoes(org_id, version_id)

    # spec declarations
    def list_spec_defs(self, org_id: UUID, version_id: UUID) -> list[SpecDefRecord]:
        self.get_version(org_id, version_id)
        return sorted((r for r in self._specs.values() if r.version_id == version_id), key=lambda r: r.chave)

    def replace_spec_defs(self, org_id, version_id, itens, *, expected_hash=None):
        validar_specs(itens)
        self._replace(
            self._specs, org_id, version_id, lambda r: r.chave,
            lambda old, now: [
                SpecDefRecord(
                    id=uuid4(), org_id=org_id, version_id=version_id, chave=i.chave, rotulo=i.rotulo,
                    descricao=i.descricao, tipo=i.tipo, obrigatoria=i.obrigatoria, exemplo=i.exemplo,
                    created_at=old[i.chave].created_at if i.chave in old else now, updated_at=now,
                )
                for i in itens
            ],
            expected_hash=expected_hash,
        )
        return self.list_spec_defs(org_id, version_id)

    # per-org spec values
    def list_org_specs(self, org_id: UUID, agent_key: str) -> list[OrgSpecRecord]:
        return sorted(
            (r for (o, k, _), r in self._org_specs.items() if o == org_id and k == agent_key),
            key=lambda r: r.chave,
        )

    def upsert_org_specs(self, org_id, agent_key, valores, *, actor=None):
        validar_org_specs(valores)
        now = self._now()
        for chave, valor in valores.items():
            cur = self._org_specs.get((org_id, agent_key, chave))
            self._org_specs[(org_id, agent_key, chave)] = OrgSpecRecord(
                id=cur.id if cur else uuid4(), org_id=org_id, agent_key=agent_key, chave=chave, valor=valor,
                updated_by=actor, created_at=cur.created_at if cur else now, updated_at=now,
            )
        return self.list_org_specs(org_id, agent_key)

    # platform texts
    def list_textos_plataforma(self) -> list[PlataformaTextoRecord]:
        return sorted(self._textos_plat.values(), key=lambda r: r.chave)

    def set_textos_plataforma(self, itens, *, actor=None):
        validar_textos_plataforma(itens)
        for chave, conteudo in itens.items():
            self._textos_plat[chave] = PlataformaTextoRecord(
                chave=chave, conteudo=conteudo, updated_by=actor, updated_at=self._now(),
            )
        return self.list_textos_plataforma()


# ── Real ────────────────────────────────────────────────────────────────────


def _uuid(v: Any) -> UUID | None:
    return UUID(str(v)) if v is not None else None


class SupabaseConteudoMixin:
    """PostgREST content layer. Mixed into ``SupabaseStudioDefinitionStore`` (uses its ``_t`` /
    ``_rpc`` / ``_exec`` / ``_paged`` / ``_one`` / ``_agent``). A replace-set is ONE
    ``agents.replace_draft_conteudo`` call = one transaction."""

    # platform definition lookups
    def get_agent_by_id(self, agent_id: UUID):
        resp = self._t("agents").select("*").eq("id", str(agent_id)).execute()
        return self._agent(self._one(resp, f"agent {agent_id}"))

    def get_platform_definition(self, key: str):
        resp = (
            self._t("agents").select("*").eq("key", key).eq("definition_scope", "plataforma").limit(1).execute()
        )
        rows = resp.data or []
        return self._agent(rows[0]) if rows else None

    def list_platform_definitions(self):
        rows = self._paged(
            lambda: self._t("agents").select("*").eq("definition_scope", "plataforma"),
            label="platform definitions", order=("key",),
        )
        return [self._agent(r) for r in rows]

    def grant_definition_org(self, definition_id, org_id, granted_by=None) -> bool:
        if self.is_definition_granted(definition_id, org_id):
            return False
        self._exec(self._t("definition_org_grants").insert({
            "definition_id": str(definition_id), "org_id": str(org_id),
            "granted_by": str(granted_by) if granted_by else None,
        }))
        return True

    def list_definition_grants(self, definition_id):
        rows = self._paged(
            lambda: self._t("definition_org_grants").select("org_id").eq("definition_id", str(definition_id)),
            label="definition grants", order=("org_id",),
        )
        return [UUID(str(r["org_id"])) for r in rows]

    def is_definition_granted(self, definition_id, org_id) -> bool:
        resp = (
            self._t("definition_org_grants").select("org_id").eq("definition_id", str(definition_id))
            .eq("org_id", str(org_id)).limit(1).execute()
        )
        return bool(resp.data)

    def append_audit(self, org_id, agent_id, actor, acao, antes, depois) -> None:
        self._exec(self._t("agent_audit_log").insert({
            "org_id": str(org_id), "agent_id": str(agent_id), "actor": str(actor) if actor else None,
            "acao": acao, "antes": antes, "depois": depois,
        }))

    def _version_rows(self, table: str, org_id: UUID, version_id: UUID, order: str) -> list[dict[str, Any]]:
        return self._paged(
            lambda: self._t(table).select("*").eq("org_id", str(org_id)).eq("version_id", str(version_id)),
            label=f"{table} version_id={version_id}", order=(order,),
        )

    def _replace_rpc(
        self, org_id: UUID, version_id: UUID, tabela: str, itens: list[dict[str, Any]],
        expected_hash: str | None = None,
    ) -> None:
        params: dict[str, Any] = {
            "p_org_id": str(org_id), "p_version_id": str(version_id), "p_tabela": tabela, "p_itens": itens,
        }
        if expected_hash is not None:  # NULL = no check; omitted so a pre-040 database (4-arg function) still works
            params["p_expected_hash"] = expected_hash
        self._rpc("replace_draft_conteudo", params)

    # textos
    def list_textos(self, org_id: UUID, version_id: UUID) -> list[TextoRecord]:
        return [
            TextoRecord(
                id=UUID(str(r["id"])), org_id=UUID(str(r["org_id"])), version_id=UUID(str(r["version_id"])),
                chave=r["chave"], conteudo=r.get("conteudo") or "",
                created_at=r["created_at"], updated_at=r["updated_at"],
            )
            for r in self._version_rows("agent_version_textos", org_id, version_id, "chave")
        ]

    def replace_textos(self, org_id, version_id, itens, *, expected_hash=None):
        validar_textos(itens)
        self._replace_rpc(
            org_id, version_id, "textos", [{"chave": i.chave, "conteudo": i.conteudo} for i in itens], expected_hash)
        return self.list_textos(org_id, version_id)

    # ferramentas
    def list_ferramentas(self, org_id: UUID, version_id: UUID) -> list[FerramentaRecord]:
        return [
            FerramentaRecord(
                id=UUID(str(r["id"])), org_id=UUID(str(r["org_id"])), version_id=UUID(str(r["version_id"])),
                ferramenta=r["ferramenta"], ativo=bool(r.get("ativo", True)), descricao=r["descricao"],
                parametros=dict(r.get("parametros") or {}), obrigatoria_skill=r.get("obrigatoria_skill"),
                created_at=r["created_at"], updated_at=r["updated_at"],
            )
            for r in self._version_rows("agent_version_ferramentas", org_id, version_id, "ferramenta")
        ]

    def replace_ferramentas(self, org_id, version_id, itens, *, expected_hash=None):
        validar_ferramentas(itens)
        self._replace_rpc(org_id, version_id, "ferramentas", [
            {
                "ferramenta": i.ferramenta, "ativo": i.ativo, "descricao": i.descricao,
                "parametros": dict(i.parametros), "obrigatoria_skill": i.obrigatoria_skill,
            }
            for i in itens
        ], expected_hash)
        return self.list_ferramentas(org_id, version_id)

    # decisoes
    def list_decisoes(self, org_id: UUID, version_id: UUID) -> list[DecisaoRecord]:
        return [
            DecisaoRecord(
                id=UUID(str(r["id"])), org_id=UUID(str(r["org_id"])), version_id=UUID(str(r["version_id"])),
                chave=r["chave"], titulo=r["titulo"], regra=r.get("regra") or "",
                opcoes=[dict(o) for o in (r.get("opcoes") or [])],
                created_at=r["created_at"], updated_at=r["updated_at"],
            )
            for r in self._version_rows("agent_version_decisoes", org_id, version_id, "chave")
        ]

    def replace_decisoes(self, org_id, version_id, itens, *, expected_hash=None):
        itens = validar_decisoes(itens)
        self._replace_rpc(org_id, version_id, "decisoes", [
            {"chave": i.chave, "titulo": i.titulo, "regra": i.regra, "opcoes": list(i.opcoes)} for i in itens
        ], expected_hash)
        return self.list_decisoes(org_id, version_id)

    # spec declarations
    def list_spec_defs(self, org_id: UUID, version_id: UUID) -> list[SpecDefRecord]:
        return [
            SpecDefRecord(
                id=UUID(str(r["id"])), org_id=UUID(str(r["org_id"])), version_id=UUID(str(r["version_id"])),
                chave=r["chave"], rotulo=r["rotulo"], descricao=r.get("descricao") or "",
                tipo=r.get("tipo") or "texto", obrigatoria=bool(r.get("obrigatoria", True)),
                exemplo=r.get("exemplo"), created_at=r["created_at"], updated_at=r["updated_at"],
            )
            for r in self._version_rows("agent_version_specs", org_id, version_id, "chave")
        ]

    def replace_spec_defs(self, org_id, version_id, itens, *, expected_hash=None):
        validar_specs(itens)
        self._replace_rpc(org_id, version_id, "specs", [
            {
                "chave": i.chave, "rotulo": i.rotulo, "descricao": i.descricao, "tipo": i.tipo,
                "obrigatoria": i.obrigatoria, "exemplo": i.exemplo,
            }
            for i in itens
        ], expected_hash)
        return self.list_spec_defs(org_id, version_id)

    # per-org spec values
    def list_org_specs(self, org_id: UUID, agent_key: str) -> list[OrgSpecRecord]:
        rows = self._paged(
            lambda: self._t("agent_org_specs").select("*").eq("org_id", str(org_id)).eq("agent_key", agent_key),
            label=f"agent_org_specs org_id={org_id} key={agent_key}", order=("chave",),
        )
        return [
            OrgSpecRecord(
                id=UUID(str(r["id"])), org_id=UUID(str(r["org_id"])), agent_key=r["agent_key"], chave=r["chave"],
                valor=r.get("valor") or "", updated_by=_uuid(r.get("updated_by")),
                created_at=r["created_at"], updated_at=r["updated_at"],
            )
            for r in rows
        ]

    def upsert_org_specs(self, org_id, agent_key, valores, *, actor=None):
        validar_org_specs(valores)
        if valores:
            self._exec(self._t("agent_org_specs").upsert(
                [
                    {
                        "org_id": str(org_id), "agent_key": agent_key, "chave": chave, "valor": valor,
                        "updated_by": str(actor) if actor else None,
                    }
                    for chave, valor in valores.items()
                ],
                on_conflict="org_id,agent_key,chave",
            ))
        return self.list_org_specs(org_id, agent_key)

    # platform texts
    def list_textos_plataforma(self) -> list[PlataformaTextoRecord]:
        def fetch(start: int, end: int):
            return self._t("textos_plataforma").select("*").order("chave").range(start, end).execute().data

        rows = list(iter_paged_rows(fetch, label="textos_plataforma"))
        return [
            PlataformaTextoRecord(
                chave=r["chave"], conteudo=r.get("conteudo") or "", updated_by=_uuid(r.get("updated_by")),
                updated_at=r["updated_at"],
            )
            for r in rows
        ]

    def set_textos_plataforma(self, itens, *, actor=None):
        validar_textos_plataforma(itens)
        if itens:
            self._exec(self._t("textos_plataforma").upsert(
                [
                    {"chave": c, "conteudo": v, "updated_by": str(actor) if actor else None}
                    for c, v in itens.items()
                ],
                on_conflict="chave",
            ))
        return self.list_textos_plataforma()

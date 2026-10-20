"""Shared skill library store (migration 039) -- Julia v2 CONTRACT D7/D8.

Seed IO shape: ``SkillsBibliotecaStore`` Protocol + ``FakeSkillsBibliotecaStore`` +
``SupabaseSkillsBibliotecaStore`` (Real) + ``get_skills_store(settings)`` factory. The library is
platform-wide (no org on a skill); the PINS (``agent_version_skill_refs``) belong to an agent
version. A published skill version is immutable; the Fake reproduces the triggers so route tests
exercise the same refusals the database gives.

It also implements :class:`app.studio.skills_contract.SkillsRuntime` -- the tiny interface the
runtime and the compiler consume.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID, uuid4

from app.studio.especificacoes import placeholders_org
from app.studio.skills_contract import SkillAberta, SkillArquivo, SkillRef
from app.stores._db_errors import StudioConflict, VersionImmutable, exec_query, exec_rpc
from app.stores._util import utcnow
from app.stores.errors import NotFound

__all__ = [
    "SKILL_CHAVE_RE",
    "TOOL_NAME_RE",
    "SkillRecord",
    "SkillVersaoMeta",
    "SkillVersao",
    "RefRecord",
    "SkillsBibliotecaStore",
    "FakeSkillsBibliotecaStore",
    "SupabaseSkillsBibliotecaStore",
    "get_skills_store",
]

_SCHEMA = "agents"
SKILL_CHAVE_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
TOOL_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
_MAX_OBRIGATORIA_PARA = 32
_MAX = {"descricao_modelo": 1024, "corpo": 60_000, "notas": 2000, "arquivo": 120_000}


@dataclass(frozen=True)
class SkillRecord:
    id: UUID
    chave: str
    nome: str
    descricao: str | None
    created_at: datetime


@dataclass(frozen=True)
class SkillVersaoMeta:
    id: UUID
    skill_id: UUID
    versao: int
    status: str
    notas: str | None
    publicada_em: datetime | None
    publicada_por: UUID | None


@dataclass(frozen=True)
class SkillVersao:
    meta: SkillVersaoMeta
    skill_chave: str
    descricao_modelo: str
    corpo: str
    arquivos: tuple[SkillArquivo, ...] = ()


@dataclass(frozen=True)
class RefRecord:
    """One pin of an agent version, with the "new version available" signal."""

    id: UUID
    version_id: UUID
    skill_id: UUID
    skill_chave: str
    skill_versao_id: UUID
    versao: int
    obrigatoria_para: tuple[str, ...]
    ordem: int
    #: The current ``publicada`` version when it is newer than the pinned one, else ``None``.
    nova_versao: int | None = None
    nova_versao_id: UUID | None = None


class SkillsBibliotecaStore(Protocol):
    # library
    def listar_skills(self) -> list[SkillRecord]: ...
    def obter_skill(self, chave: str) -> SkillRecord:
        """Raises :class:`NotFound`."""
        ...
    def criar_skill(self, chave: str, nome: str, descricao: str | None) -> SkillRecord:
        """Raises ``StudioConflict('chave_taken')``."""
        ...
    def atualizar_skill(self, chave: str, nome: str | None, descricao: str | None, set_descricao: bool) -> SkillRecord: ...
    def listar_versoes(self, skill_id: UUID) -> list[SkillVersaoMeta]: ...
    def obter_versao(self, versao_id: UUID) -> SkillVersao:
        """Content included. Raises :class:`NotFound`."""
        ...
    def obter_versao_publicada(self, chave: str) -> SkillVersao:
        """Raises :class:`NotFound` when the skill has no published version."""
        ...
    def criar_rascunho(self, skill_id: UUID, notas: str | None, copiar_de: UUID | None) -> UUID:
        """Raises ``StudioConflict('draft_exists')``."""
        ...
    def salvar_rascunho(self, versao_id: UUID, campos: dict[str, Any]) -> None:
        """Partial update of ``descricao_modelo`` / ``corpo`` / ``notas``. Raises :class:`VersionImmutable`."""
        ...
    def salvar_arquivo(self, versao_id: UUID, caminho: str, titulo: str | None, conteudo: str) -> None: ...
    def remover_arquivo(self, versao_id: UUID, caminho: str) -> None: ...
    def publicar(self, versao_id: UUID, user_id: UUID) -> None:
        """Draft -> publicada, the previous publicada -> archived (one transaction)."""
        ...
    def descartar_rascunho(self, versao_id: UUID) -> None: ...
    # pins
    def listar_refs(self, version_id: UUID) -> list[RefRecord]: ...
    def fixar_ref(
        self, org_id: UUID, version_id: UUID, skill_versao_id: UUID, obrigatoria_para: list[str], ordem: int,
    ) -> RefRecord:
        """Pin (or re-pin, one version per skill) a non-draft skill version to an agent version."""
        ...
    def remover_ref(self, version_id: UUID, skill_chave: str) -> None:
        """Raises :class:`NotFound`."""
        ...
    # runtime (SkillsRuntime)
    def skill_refs_for(self, version_id: UUID) -> list[SkillRef]: ...
    def abrir(self, skill_key: str, skill_versao_id: UUID) -> SkillAberta | None: ...


def validar_obrigatoria_para(itens: list[str]) -> tuple[str, ...]:
    """Tool names, unique and shape-checked (the DB CHECK is the backstop). ``ValueError`` -> 422."""
    if len(itens) > _MAX_OBRIGATORIA_PARA:
        raise ValueError("obrigatoria_para tem itens demais")
    bad = [i for i in itens if not TOOL_NAME_RE.match(i)]
    if bad:
        raise ValueError("obrigatoria_para tem nome de ferramenta invalido")
    return tuple(dict.fromkeys(itens))


def _check_len(campo: str, valor: str | None, limite: int) -> None:
    if valor is not None and len(valor) > limite:
        raise ValueError(f"{campo} excede {limite} caracteres")


def _check_campos(campos: dict[str, Any]) -> dict[str, Any]:
    unknown = set(campos) - {"descricao_modelo", "corpo", "notas"}
    if unknown:
        raise ValueError("campo desconhecido")
    for k in ("descricao_modelo", "corpo"):
        if k in campos:
            if campos[k] is None:
                raise ValueError(f"{k} nao pode ser nulo")
            _check_len(k, campos[k], _MAX[k])
    if "notas" in campos:
        _check_len("notas", campos["notas"], _MAX["notas"])
    return campos


def _placeholders(*textos: str | None) -> tuple[str, ...]:
    """The ``{{org.chave}}`` keys a pinned skill version's texts use (sorted, unique)."""
    out: set[str] = set()
    for t in textos:
        out |= placeholders_org(t)
    return tuple(sorted(out))


# ── Fake ────────────────────────────────────────────────────────────────────

class FakeSkillsBibliotecaStore:
    def __init__(self) -> None:
        self._skills: dict[UUID, SkillRecord] = {}
        self._versoes: dict[UUID, SkillVersaoMeta] = {}
        self._texto: dict[UUID, dict[str, Any]] = {}  # versao_id -> {descricao_modelo, corpo}
        self._arquivos: dict[UUID, dict[str, SkillArquivo]] = {}
        # (version_id, skill_id) -> row  -- the agent_version_skill_refs table
        self._refs: dict[tuple[UUID, UUID], dict[str, Any]] = {}

    # library reads
    def listar_skills(self):
        return sorted(self._skills.values(), key=lambda s: s.chave)

    def obter_skill(self, chave):
        for s in self._skills.values():
            if s.chave == chave:
                return s
        raise NotFound(f"skill {chave!r}")

    def criar_skill(self, chave, nome, descricao):
        if not SKILL_CHAVE_RE.match(chave) or len(chave) > 64:
            raise ValueError("chave invalida")
        if not nome.strip() or len(nome) > 200:
            raise ValueError("nome invalido")
        _check_len("descricao", descricao, 1024)
        if any(s.chave == chave for s in self._skills.values()):
            raise StudioConflict("chave_taken", chave)
        rec = SkillRecord(uuid4(), chave, nome, descricao, utcnow())
        self._skills[rec.id] = rec
        return rec

    def atualizar_skill(self, chave, nome, descricao, set_descricao):
        rec = self.obter_skill(chave)
        if nome is not None:
            if not nome.strip() or len(nome) > 200:
                raise ValueError("nome invalido")
            rec = replace(rec, nome=nome)
        if set_descricao:
            _check_len("descricao", descricao, 1024)
            rec = replace(rec, descricao=descricao)
        self._skills[rec.id] = rec
        return rec

    def listar_versoes(self, skill_id):
        return sorted((v for v in self._versoes.values() if v.skill_id == skill_id), key=lambda v: -v.versao)

    def _meta(self, versao_id: UUID) -> SkillVersaoMeta:
        try:
            return self._versoes[versao_id]
        except KeyError:
            raise NotFound(f"versao {versao_id}") from None

    def obter_versao(self, versao_id):
        meta = self._meta(versao_id)
        t = self._texto[versao_id]
        return SkillVersao(
            meta=meta, skill_chave=self._skills[meta.skill_id].chave,
            descricao_modelo=t["descricao_modelo"], corpo=t["corpo"],
            arquivos=tuple(sorted(self._arquivos.get(versao_id, {}).values(), key=lambda a: a.caminho)),
        )

    def obter_versao_publicada(self, chave):
        skill = self.obter_skill(chave)
        for v in self._versoes.values():
            if v.skill_id == skill.id and v.status == "publicada":
                return self.obter_versao(v.id)
        raise NotFound(f"skill {chave!r} sem versao publicada")

    # library writes
    def criar_rascunho(self, skill_id, notas, copiar_de):
        if skill_id not in self._skills:
            raise NotFound(f"skill {skill_id}")
        if any(v.skill_id == skill_id and v.status == "rascunho" for v in self._versoes.values()):
            raise StudioConflict("draft_exists", "draft_exists")
        if copiar_de is not None and self._meta(copiar_de).skill_id != skill_id:
            raise NotFound(f"versao {copiar_de}")
        _check_len("notas", notas, _MAX["notas"])
        numero = max((v.versao for v in self._versoes.values() if v.skill_id == skill_id), default=0) + 1
        vid = uuid4()
        self._versoes[vid] = SkillVersaoMeta(vid, skill_id, numero, "rascunho", notas, None, None)
        origem = self._texto.get(copiar_de) if copiar_de else None
        self._texto[vid] = dict(origem) if origem else {"descricao_modelo": "", "corpo": ""}
        self._arquivos[vid] = dict(self._arquivos.get(copiar_de, {})) if copiar_de else {}
        return vid

    def _rascunho(self, versao_id: UUID) -> SkillVersaoMeta:
        meta = self._meta(versao_id)
        if meta.status != "rascunho":
            raise VersionImmutable()
        return meta

    def salvar_rascunho(self, versao_id, campos):
        meta = self._rascunho(versao_id)
        campos = _check_campos(dict(campos))
        if "notas" in campos:
            self._versoes[versao_id] = replace(meta, notas=campos.pop("notas"))
        self._texto[versao_id].update(campos)

    def salvar_arquivo(self, versao_id, caminho, titulo, conteudo):
        self._rascunho(versao_id)
        if not re.match(r"^[a-z0-9][a-z0-9._/-]*$", caminho) or ".." in caminho:
            raise ValueError("caminho invalido")
        _check_len("arquivo", conteudo, _MAX["arquivo"])
        self._arquivos.setdefault(versao_id, {})[caminho] = SkillArquivo(caminho, titulo, conteudo)

    def remover_arquivo(self, versao_id, caminho):
        self._rascunho(versao_id)
        if self._arquivos.get(versao_id, {}).pop(caminho, None) is None:
            raise NotFound(f"arquivo {caminho!r}")

    def publicar(self, versao_id, user_id):
        meta = self._meta(versao_id)
        if meta.status != "rascunho":
            raise VersionImmutable()
        t = self._texto[versao_id]
        if not t["corpo"].strip() or not t["descricao_modelo"].strip():
            raise ValueError("invalid_payload")
        for vid, v in list(self._versoes.items()):
            if v.skill_id == meta.skill_id and v.status == "publicada":
                self._versoes[vid] = replace(v, status="arquivada")
        self._versoes[versao_id] = replace(meta, status="publicada", publicada_em=utcnow(), publicada_por=user_id)

    def descartar_rascunho(self, versao_id):
        self._rascunho(versao_id)
        del self._versoes[versao_id]
        self._texto.pop(versao_id, None)
        self._arquivos.pop(versao_id, None)

    # pins
    def fixar_ref(self, org_id, version_id, skill_versao_id, obrigatoria_para, ordem):
        meta = self._meta(skill_versao_id)
        if meta.status == "rascunho":
            raise ValueError("invalid_payload")  # trigger guard_agent_version_skill_ref
        para = validar_obrigatoria_para(obrigatoria_para)
        key = (version_id, meta.skill_id)
        old = self._refs.get(key)
        self._refs[key] = {
            "id": old["id"] if old else uuid4(), "org_id": org_id, "skill_versao_id": skill_versao_id,
            "obrigatoria_para": para, "ordem": ordem,
        }
        return next(r for r in self.listar_refs(version_id) if r.skill_id == meta.skill_id)

    def remover_ref(self, version_id, skill_chave):
        skill = self.obter_skill(skill_chave)
        if self._refs.pop((version_id, skill.id), None) is None:
            raise NotFound(f"pin {skill_chave!r}")

    def copiar_refs(self, origem: UUID, destino: UUID, org_id: UUID) -> None:
        """What the AFTER INSERT trigger does on a new draft (tests call it where the DB would)."""
        for (vid, sid), row in list(self._refs.items()):
            if vid == origem:
                self._refs[(destino, sid)] = {**row, "id": uuid4(), "org_id": org_id}

    def listar_refs(self, version_id):
        out: list[RefRecord] = []
        for (vid, sid), row in self._refs.items():
            if vid != version_id:
                continue
            meta = self._meta(row["skill_versao_id"])
            atual = next(
                (v for v in self._versoes.values() if v.skill_id == sid and v.status == "publicada"), None,
            )
            nova = atual if atual is not None and atual.versao > meta.versao else None
            out.append(RefRecord(
                id=row["id"], version_id=vid, skill_id=sid, skill_chave=self._skills[sid].chave,
                skill_versao_id=row["skill_versao_id"], versao=meta.versao,
                obrigatoria_para=tuple(row["obrigatoria_para"]), ordem=row["ordem"],
                nova_versao=nova.versao if nova else None, nova_versao_id=nova.id if nova else None,
            ))
        return sorted(out, key=lambda r: (r.ordem, r.skill_chave))

    # runtime
    def skill_refs_for(self, version_id):
        out = []
        for r in self.listar_refs(version_id):
            v = self.obter_versao(r.skill_versao_id)
            out.append(SkillRef(
                skill_key=r.skill_chave, skill_versao_id=r.skill_versao_id, obrigatoria_para=r.obrigatoria_para,
                descricao=v.descricao_modelo, ordem=r.ordem, corpo_chars=len(v.corpo),
                arquivos=tuple((a.caminho, len(a.conteudo)) for a in v.arquivos),
                placeholders=_placeholders(v.descricao_modelo, v.corpo, *(a.conteudo for a in v.arquivos)),
            ))
        return out

    def abrir(self, skill_key, skill_versao_id):
        meta = self._versoes.get(skill_versao_id)
        if meta is None or self._skills[meta.skill_id].chave != skill_key or meta.status == "rascunho":
            return None
        v = self.obter_versao(skill_versao_id)
        return SkillAberta(skill_key, skill_versao_id, v.corpo, v.arquivos)


# ── Real ────────────────────────────────────────────────────────────────────

def _uuid(v: Any) -> UUID:
    return UUID(str(v))


class SupabaseSkillsBibliotecaStore:
    """Real :class:`SkillsBibliotecaStore` -- Postgres through the admin client."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def _t(self, name: str):
        return self._client.schema(_SCHEMA).table(name)

    def _rpc(self, fn: str, params: dict[str, Any]):
        return exec_rpc(self._client, _SCHEMA, fn, params)

    @staticmethod
    def _skill(r: dict[str, Any]) -> SkillRecord:
        return SkillRecord(_uuid(r["id"]), r["chave"], r["nome"], r.get("descricao"), r["created_at"])

    @staticmethod
    def _meta_row(r: dict[str, Any]) -> SkillVersaoMeta:
        return SkillVersaoMeta(
            _uuid(r["id"]), _uuid(r["skill_id"]), r["versao"], r["status"], r.get("notas"),
            r.get("publicada_em"), _uuid(r["publicada_por"]) if r.get("publicada_por") else None,
        )

    # library reads
    def listar_skills(self):
        resp = self._t("skills_biblioteca").select("*").order("chave").execute()
        return [self._skill(r) for r in resp.data or []]

    def obter_skill(self, chave):
        resp = self._t("skills_biblioteca").select("*").eq("chave", chave).limit(1).execute()
        if not resp.data:
            raise NotFound(f"skill {chave!r}")
        return self._skill(resp.data[0])

    def criar_skill(self, chave, nome, descricao):
        resp = exec_query(
            self._t("skills_biblioteca").insert({"chave": chave, "nome": nome, "descricao": descricao}),
            unique_code="chave_taken",
        )
        return self._skill(resp.data[0])

    def atualizar_skill(self, chave, nome, descricao, set_descricao):
        patch: dict[str, Any] = {}
        if nome is not None:
            patch["nome"] = nome
        if set_descricao:
            patch["descricao"] = descricao
        if patch:
            exec_query(self._t("skills_biblioteca").update(patch).eq("chave", chave))
        return self.obter_skill(chave)

    def listar_versoes(self, skill_id):
        resp = (
            self._t("skill_versoes").select("*").eq("skill_id", str(skill_id)).order("versao", desc=True).execute()
        )
        return [self._meta_row(r) for r in resp.data or []]

    def _arquivos(self, versao_id: UUID) -> tuple[SkillArquivo, ...]:
        resp = (
            self._t("skill_versao_arquivos").select("caminho,titulo,conteudo")
            .eq("skill_versao_id", str(versao_id)).order("caminho").execute()
        )
        return tuple(SkillArquivo(r["caminho"], r.get("titulo"), r.get("conteudo") or "") for r in resp.data or [])

    def obter_versao(self, versao_id):
        vr = self._t("skill_versoes").select("*").eq("id", str(versao_id)).limit(1).execute()
        if not vr.data:
            raise NotFound(f"versao {versao_id}")
        row = vr.data[0]
        meta = self._meta_row(row)
        sr = self._t("skills_biblioteca").select("chave").eq("id", str(meta.skill_id)).limit(1).execute()
        return SkillVersao(
            meta=meta, skill_chave=sr.data[0]["chave"], descricao_modelo=row.get("descricao_modelo") or "",
            corpo=row.get("corpo") or "", arquivos=self._arquivos(versao_id),
        )

    def obter_versao_publicada(self, chave):
        skill = self.obter_skill(chave)
        resp = (
            self._t("skill_versoes").select("id").eq("skill_id", str(skill.id)).eq("status", "publicada")
            .limit(1).execute()
        )
        if not resp.data:
            raise NotFound(f"skill {chave!r} sem versao publicada")
        return self.obter_versao(_uuid(resp.data[0]["id"]))

    # library writes
    def criar_rascunho(self, skill_id, notas, copiar_de):
        _check_len("notas", notas, _MAX["notas"])
        resp = self._rpc("criar_rascunho_skill", {
            "p_skill_id": str(skill_id), "p_notas": notas,
            "p_copiar_de": str(copiar_de) if copiar_de else None,
        })
        return _uuid(resp.data)

    def salvar_rascunho(self, versao_id, campos):
        campos = _check_campos(dict(campos))
        if campos:
            exec_query(self._t("skill_versoes").update(campos).eq("id", str(versao_id)))

    def salvar_arquivo(self, versao_id, caminho, titulo, conteudo):
        _check_len("arquivo", conteudo, _MAX["arquivo"])
        row = {"skill_versao_id": str(versao_id), "caminho": caminho, "titulo": titulo, "conteudo": conteudo}
        exec_query(self._t("skill_versao_arquivos").upsert(row, on_conflict="skill_versao_id,caminho"))

    def remover_arquivo(self, versao_id, caminho):
        resp = exec_query(
            self._t("skill_versao_arquivos").delete().eq("skill_versao_id", str(versao_id)).eq("caminho", caminho)
        )
        if not resp.data:
            raise NotFound(f"arquivo {caminho!r}")

    def publicar(self, versao_id, user_id):
        self._rpc("publicar_skill_versao", {"p_versao_id": str(versao_id), "p_user_id": str(user_id)})

    def descartar_rascunho(self, versao_id):
        exec_query(self._t("skill_versoes").delete().eq("id", str(versao_id)))

    # pins
    def listar_refs(self, version_id):
        rows = self._t("agent_version_skill_refs").select("*").eq("version_id", str(version_id)).execute().data or []
        if not rows:
            return []
        skill_ids = sorted({str(r["skill_id"]) for r in rows})
        versao_ids = sorted({str(r["skill_versao_id"]) for r in rows})
        skills = {
            str(r["id"]): r["chave"]
            for r in self._t("skills_biblioteca").select("id,chave").in_("id", skill_ids).execute().data or []
        }
        versoes = {
            str(r["id"]): r["versao"]
            for r in self._t("skill_versoes").select("id,versao").in_("id", versao_ids).execute().data or []
        }
        atuais = {
            str(r["skill_id"]): r
            for r in self._t("skill_versoes").select("id,skill_id,versao")
            .in_("skill_id", skill_ids).eq("status", "publicada").execute().data or []
        }
        out: list[RefRecord] = []
        for r in rows:
            sid, vid = str(r["skill_id"]), str(r["skill_versao_id"])
            versao = versoes[vid]
            atual = atuais.get(sid)
            nova = atual if atual is not None and atual["versao"] > versao else None
            out.append(RefRecord(
                id=_uuid(r["id"]), version_id=_uuid(r["version_id"]), skill_id=_uuid(sid), skill_chave=skills[sid],
                skill_versao_id=_uuid(vid), versao=versao, obrigatoria_para=tuple(r.get("obrigatoria_para") or ()),
                ordem=r.get("ordem", 0),
                nova_versao=nova["versao"] if nova else None, nova_versao_id=_uuid(nova["id"]) if nova else None,
            ))
        return sorted(out, key=lambda x: (x.ordem, x.skill_chave))

    def fixar_ref(self, org_id, version_id, skill_versao_id, obrigatoria_para, ordem):
        para = validar_obrigatoria_para(obrigatoria_para)
        sv = self._t("skill_versoes").select("skill_id").eq("id", str(skill_versao_id)).limit(1).execute()
        if not sv.data:
            raise NotFound(f"versao {skill_versao_id}")
        skill_id = _uuid(sv.data[0]["skill_id"])
        row = {
            "org_id": str(org_id), "version_id": str(version_id), "skill_id": str(skill_id),
            "skill_versao_id": str(skill_versao_id), "obrigatoria_para": list(para), "ordem": ordem,
        }
        exec_query(self._t("agent_version_skill_refs").upsert(row, on_conflict="version_id,skill_id"))
        return next(r for r in self.listar_refs(version_id) if r.skill_id == skill_id)

    def remover_ref(self, version_id, skill_chave):
        skill = self.obter_skill(skill_chave)
        resp = exec_query(
            self._t("agent_version_skill_refs").delete().eq("version_id", str(version_id)).eq("skill_id", str(skill.id))
        )
        if not resp.data:
            raise NotFound(f"pin {skill_chave!r}")

    # runtime
    def skill_refs_for(self, version_id):
        refs = self.listar_refs(version_id)
        if not refs:
            return []
        ids = sorted({str(r.skill_versao_id) for r in refs})
        textos = {
            str(r["id"]): r
            for r in self._t("skill_versoes").select("id,descricao_modelo,corpo").in_("id", ids).execute().data or []
        }
        arquivos: dict[str, list[tuple[str, int]]] = {}
        textos_arquivos: dict[str, list[str]] = {}
        for r in (
            self._t("skill_versao_arquivos").select("skill_versao_id,caminho,conteudo")
            .in_("skill_versao_id", ids).execute().data or []
        ):
            arquivos.setdefault(str(r["skill_versao_id"]), []).append((r["caminho"], len(r.get("conteudo") or "")))
            textos_arquivos.setdefault(str(r["skill_versao_id"]), []).append(r.get("conteudo") or "")
        return [
            SkillRef(
                skill_key=r.skill_chave, skill_versao_id=r.skill_versao_id, obrigatoria_para=r.obrigatoria_para,
                descricao=textos[str(r.skill_versao_id)].get("descricao_modelo") or "", ordem=r.ordem,
                corpo_chars=len(textos[str(r.skill_versao_id)].get("corpo") or ""),
                arquivos=tuple(sorted(arquivos.get(str(r.skill_versao_id), []))),
                placeholders=_placeholders(
                    textos[str(r.skill_versao_id)].get("descricao_modelo"), textos[str(r.skill_versao_id)].get("corpo"),
                    *textos_arquivos.get(str(r.skill_versao_id), []),
                ),
            )
            for r in refs
        ]

    def abrir(self, skill_key, skill_versao_id):
        try:
            v = self.obter_versao(skill_versao_id)
        except NotFound:
            return None
        if v.skill_chave != skill_key or v.meta.status == "rascunho":
            return None
        return SkillAberta(skill_key, skill_versao_id, v.corpo, v.arquivos)


def get_skills_store(settings: Any) -> SkillsBibliotecaStore:
    """Real when a Supabase service-role key is configured, Fake otherwise."""
    if not getattr(settings, "supabase_service_role_key", None):
        return FakeSkillsBibliotecaStore()
    from app.database import get_admin_client

    return SupabaseSkillsBibliotecaStore(get_admin_client())

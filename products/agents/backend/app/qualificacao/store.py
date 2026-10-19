"""Library store — the platform-wide qualification standards (migration 032).

Seed IO shape: ``PadraoStore`` Protocol + ``FakePadraoStore`` +
``SupabasePadraoStore`` (Real) + ``get_padrao_store(settings)`` factory. There is
NO org on any of these rows: the standard is the same for every org (owner
decision Q2, 2026-10-19). A published version is immutable; the Fake reproduces
the triggers so route tests exercise the same refusals the database gives.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID, uuid4

from app.qualificacao.models import (
    CriterioDef,
    EstagioDef,
    Opcao,
    ParametrosDef,
    VersaoPadrao,
)
from app.stores._db_errors import StudioConflict, VersionImmutable, exec_query, exec_rpc
from app.stores._util import utcnow, utcnow_iso
from app.stores.errors import NotFound

__all__ = [
    "PadraoRecord",
    "VersaoMeta",
    "PadraoStore",
    "FakePadraoStore",
    "SupabasePadraoStore",
    "get_padrao_store",
]

_SCHEMA = "agents"


@dataclass(frozen=True)
class PadraoRecord:
    id: UUID
    chave: str
    nome: str
    descricao: str | None
    created_at: datetime


@dataclass(frozen=True)
class VersaoMeta:
    id: UUID
    padrao_id: UUID
    versao: int
    status: str
    notas: str | None
    publicada_em: datetime | None
    publicada_por: UUID | None


class PadraoStore(Protocol):
    def listar_padroes(self) -> list[PadraoRecord]: ...
    def obter_padrao(self, chave: str) -> PadraoRecord:
        """Raises :class:`NotFound`."""
        ...
    def criar_padrao(self, chave: str, nome: str, descricao: str | None) -> PadraoRecord:
        """Raises ``StudioConflict('chave_taken')``."""
        ...
    def listar_versoes(self, padrao_id: UUID) -> list[VersaoMeta]: ...
    def obter_versao(self, versao_id: UUID) -> VersaoPadrao:
        """Content included. Raises :class:`NotFound`."""
        ...
    def tem_parametros(self, versao_id: UUID) -> bool:
        """Whether the version has its ``qualificacao_parametros`` row yet."""
        ...
    def obter_versao_publicada(self, chave: str) -> VersaoPadrao:
        """The current ``publicada`` version of a standard. Raises :class:`NotFound`."""
        ...
    def criar_rascunho(self, padrao_id: UUID, notas: str | None, copiar_de: UUID | None) -> UUID:
        """New draft (optionally copying a version). Raises ``StudioConflict('draft_exists')``."""
        ...
    def salvar_criterio(self, versao_id: UUID, criterio: CriterioDef) -> None:
        """Upsert by ``chave``. Raises :class:`VersionImmutable` on a non-draft."""
        ...
    def remover_criterio(self, versao_id: UUID, chave: str) -> None: ...
    def salvar_estagio(self, versao_id: UUID, estagio: EstagioDef) -> None: ...
    def remover_estagio(self, versao_id: UUID, chave: str) -> None: ...
    def salvar_parametros(self, versao_id: UUID, parametros: ParametrosDef) -> None: ...
    def atualizar_notas(self, versao_id: UUID, notas: str | None) -> None: ...
    def publicar(self, versao_id: UUID, user_id: UUID) -> None:
        """Draft -> publicada, the previous publicada -> arquivada (one transaction)."""
        ...
    def descartar_rascunho(self, versao_id: UUID) -> None: ...


# ── Fake ────────────────────────────────────────────────────────────────────

class FakePadraoStore:
    def __init__(self) -> None:
        self._padroes: dict[UUID, PadraoRecord] = {}
        self._versoes: dict[UUID, VersaoMeta] = {}
        self._criterios: dict[UUID, dict[str, CriterioDef]] = {}
        self._estagios: dict[UUID, dict[str, EstagioDef]] = {}
        self._params: dict[UUID, ParametrosDef] = {}

    # reads
    def listar_padroes(self):
        return sorted(self._padroes.values(), key=lambda p: p.chave)

    def obter_padrao(self, chave):
        for p in self._padroes.values():
            if p.chave == chave:
                return p
        raise NotFound(f"padrao {chave!r}")

    def criar_padrao(self, chave, nome, descricao):
        if any(p.chave == chave for p in self._padroes.values()):
            raise StudioConflict("chave_taken", chave)
        rec = PadraoRecord(uuid4(), chave, nome, descricao, utcnow())
        self._padroes[rec.id] = rec
        return rec

    def listar_versoes(self, padrao_id):
        return sorted(
            (v for v in self._versoes.values() if v.padrao_id == padrao_id),
            key=lambda v: v.versao, reverse=True,
        )

    def _meta(self, versao_id: UUID) -> VersaoMeta:
        try:
            return self._versoes[versao_id]
        except KeyError:
            raise NotFound(f"versao {versao_id}") from None

    def obter_versao(self, versao_id):
        meta = self._meta(versao_id)
        padrao = self._padroes[meta.padrao_id]
        params = self._params.get(versao_id) or ParametrosDef(minimo_para_ofertar={"todos": []})
        return VersaoPadrao(
            id=versao_id, padrao_chave=padrao.chave, versao=meta.versao, status=meta.status,
            notas=meta.notas, publicada_em=meta.publicada_em,
            criterios=tuple(sorted(self._criterios.get(versao_id, {}).values(), key=lambda c: (c.ordem, c.chave))),
            estagios=tuple(sorted(self._estagios.get(versao_id, {}).values(), key=lambda e: e.ordem)),
            parametros=params,
        )

    def tem_parametros(self, versao_id: UUID) -> bool:
        return versao_id in self._params

    def obter_versao_publicada(self, chave):
        padrao = self.obter_padrao(chave)
        for v in self._versoes.values():
            if v.padrao_id == padrao.id and v.status == "publicada":
                return self.obter_versao(v.id)
        raise NotFound(f"padrao {chave!r} sem versao publicada")

    # writes
    def criar_rascunho(self, padrao_id, notas, copiar_de):
        if padrao_id not in self._padroes:
            raise NotFound(f"padrao {padrao_id}")
        if any(v.padrao_id == padrao_id and v.status == "rascunho" for v in self._versoes.values()):
            raise StudioConflict("draft_exists", "draft_exists")
        if copiar_de is not None and self._meta(copiar_de).padrao_id != padrao_id:
            raise NotFound(f"versao {copiar_de}")
        numero = max((v.versao for v in self._versoes.values() if v.padrao_id == padrao_id), default=0) + 1
        vid = uuid4()
        self._versoes[vid] = VersaoMeta(vid, padrao_id, numero, "rascunho", notas, None, None)
        self._criterios[vid] = {}
        self._estagios[vid] = {}
        if copiar_de is not None:
            self._criterios[vid] = {k: replace(c, id=uuid4()) for k, c in self._criterios.get(copiar_de, {}).items()}
            self._estagios[vid] = {k: replace(e, id=uuid4()) for k, e in self._estagios.get(copiar_de, {}).items()}
            if copiar_de in self._params:
                self._params[vid] = copy.deepcopy(self._params[copiar_de])
        return vid

    def _rascunho(self, versao_id: UUID) -> VersaoMeta:
        meta = self._meta(versao_id)
        if meta.status != "rascunho":
            raise VersionImmutable()
        return meta

    def salvar_criterio(self, versao_id, criterio):
        self._rascunho(versao_id)
        self._criterios.setdefault(versao_id, {})[criterio.chave] = replace(criterio, id=criterio.id or uuid4())

    def remover_criterio(self, versao_id, chave):
        self._rascunho(versao_id)
        if self._criterios.get(versao_id, {}).pop(chave, None) is None:
            raise NotFound(f"criterio {chave!r}")

    def salvar_estagio(self, versao_id, estagio):
        self._rascunho(versao_id)
        self._estagios.setdefault(versao_id, {})[estagio.chave] = replace(estagio, id=estagio.id or uuid4())

    def remover_estagio(self, versao_id, chave):
        self._rascunho(versao_id)
        if self._estagios.get(versao_id, {}).pop(chave, None) is None:
            raise NotFound(f"estagio {chave!r}")

    def salvar_parametros(self, versao_id, parametros):
        self._rascunho(versao_id)
        self._params[versao_id] = parametros

    def atualizar_notas(self, versao_id, notas):
        meta = self._rascunho(versao_id)
        self._versoes[versao_id] = replace(meta, notas=notas)

    def publicar(self, versao_id, user_id):
        meta = self._meta(versao_id)
        if meta.status != "rascunho":
            raise VersionImmutable()
        if versao_id not in self._params:
            raise ValueError("invalid_payload")
        for vid, v in list(self._versoes.items()):
            if v.padrao_id == meta.padrao_id and v.status == "publicada":
                self._versoes[vid] = replace(v, status="arquivada")
        self._versoes[versao_id] = replace(meta, status="publicada", publicada_em=utcnow(), publicada_por=user_id)

    def descartar_rascunho(self, versao_id):
        self._rascunho(versao_id)
        del self._versoes[versao_id]
        self._criterios.pop(versao_id, None)
        self._estagios.pop(versao_id, None)
        self._params.pop(versao_id, None)


# ── Real ────────────────────────────────────────────────────────────────────

def _opcoes_out(opcoes: tuple[Opcao, ...]) -> list[dict[str, Any]]:
    return [
        {"valor": o.valor, "rotulo": o.rotulo, "descricao_modelo": o.descricao_modelo,
         **({"sinonimos": list(o.sinonimos)} if o.sinonimos else {})}
        for o in opcoes
    ]


def _opcoes_in(raw: Any) -> tuple[Opcao, ...]:
    return tuple(
        Opcao(
            valor=o["valor"], rotulo=o.get("rotulo", ""), descricao_modelo=o.get("descricao_modelo", ""),
            sinonimos=tuple(o.get("sinonimos") or ()),
        )
        for o in (raw or [])
    )


def criterio_from_row(r: dict[str, Any]) -> CriterioDef:
    return CriterioDef(
        id=UUID(str(r["id"])) if r.get("id") else None, chave=r["chave"], grupo=r["grupo"], rotulo=r["rotulo"],
        descricao_modelo=r.get("descricao_modelo") or "", tipo=r["tipo"], opcoes=_opcoes_in(r.get("opcoes")),
        unidade=r.get("unidade"), sensivel=r.get("sensivel"), pontuacao=r.get("pontuacao") or {},
        ordem=r.get("ordem", 0), ativo=r.get("ativo", True), eixo=r.get("eixo"),
        validade_dias=r.get("validade_dias"),
    )


def estagio_from_row(r: dict[str, Any]) -> EstagioDef:
    return EstagioDef(
        id=UUID(str(r["id"])) if r.get("id") else None, chave=r["chave"], rotulo=r["rotulo"],
        descricao=r.get("descricao") or "", ordem=r["ordem"], regra=r["regra"],
        conclusivo=bool(r.get("conclusivo")), terminal=bool(r.get("terminal")),
    )


class SupabasePadraoStore:
    """Real :class:`PadraoStore` — Postgres through the admin client."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def _t(self, name: str):
        return self._client.schema(_SCHEMA).table(name)

    def _rpc(self, fn: str, params: dict[str, Any]):
        return exec_rpc(self._client, _SCHEMA, fn, params)

    @staticmethod
    def _padrao(r: dict[str, Any]) -> PadraoRecord:
        return PadraoRecord(UUID(str(r["id"])), r["chave"], r["nome"], r.get("descricao"), r["created_at"])

    @staticmethod
    def _meta_row(r: dict[str, Any]) -> VersaoMeta:
        return VersaoMeta(
            UUID(str(r["id"])), UUID(str(r["padrao_id"])), r["versao"], r["status"], r.get("notas"),
            r.get("publicada_em"), UUID(str(r["publicada_por"])) if r.get("publicada_por") else None,
        )

    def listar_padroes(self):
        resp = self._t("qualificacao_padroes").select("*").order("chave").execute()
        return [self._padrao(r) for r in resp.data or []]

    def obter_padrao(self, chave):
        resp = self._t("qualificacao_padroes").select("*").eq("chave", chave).limit(1).execute()
        if not resp.data:
            raise NotFound(f"padrao {chave!r}")
        return self._padrao(resp.data[0])

    def criar_padrao(self, chave, nome, descricao):
        resp = exec_query(
            self._t("qualificacao_padroes").insert({"chave": chave, "nome": nome, "descricao": descricao}),
            unique_code="chave_taken",
        )
        return self._padrao(resp.data[0])

    def listar_versoes(self, padrao_id):
        resp = (
            self._t("qualificacao_versoes").select("*").eq("padrao_id", str(padrao_id))
            .order("versao", desc=True).execute()
        )
        return [self._meta_row(r) for r in resp.data or []]

    def obter_versao(self, versao_id):
        vr = self._t("qualificacao_versoes").select("*").eq("id", str(versao_id)).limit(1).execute()
        if not vr.data:
            raise NotFound(f"versao {versao_id}")
        meta = self._meta_row(vr.data[0])
        pr = self._t("qualificacao_padroes").select("chave").eq("id", str(meta.padrao_id)).limit(1).execute()
        crit = self._t("qualificacao_criterios").select("*").eq("versao_id", str(versao_id)).order("ordem").execute()
        est = self._t("qualificacao_estagios").select("*").eq("versao_id", str(versao_id)).order("ordem").execute()
        par = self._t("qualificacao_parametros").select("*").eq("versao_id", str(versao_id)).limit(1).execute()
        prow = (par.data or [None])[0]
        parametros = (
            ParametrosDef(prow["minimo_para_ofertar"], prow.get("lote_ofertas", 3), prow.get("score_max", 100))
            if prow else ParametrosDef(minimo_para_ofertar={"todos": []})
        )
        return VersaoPadrao(
            id=versao_id, padrao_chave=pr.data[0]["chave"], versao=meta.versao, status=meta.status,
            notas=meta.notas, publicada_em=meta.publicada_em,
            criterios=tuple(criterio_from_row(r) for r in crit.data or []),
            estagios=tuple(estagio_from_row(r) for r in est.data or []),
            parametros=parametros,
        )

    def tem_parametros(self, versao_id: UUID) -> bool:
        resp = self._t("qualificacao_parametros").select("versao_id").eq("versao_id", str(versao_id)).limit(1).execute()
        return bool(resp.data)

    def obter_versao_publicada(self, chave):
        padrao = self.obter_padrao(chave)
        resp = (
            self._t("qualificacao_versoes").select("id").eq("padrao_id", str(padrao.id))
            .eq("status", "publicada").limit(1).execute()
        )
        if not resp.data:
            raise NotFound(f"padrao {chave!r} sem versao publicada")
        return self.obter_versao(UUID(str(resp.data[0]["id"])))

    def criar_rascunho(self, padrao_id, notas, copiar_de):
        resp = self._rpc("criar_rascunho_qualificacao", {
            "p_padrao_id": str(padrao_id), "p_notas": notas,
            "p_copiar_de": str(copiar_de) if copiar_de else None,
        })
        return UUID(str(resp.data))

    def salvar_criterio(self, versao_id, c):
        row = {
            "versao_id": str(versao_id), "chave": c.chave, "grupo": c.grupo, "rotulo": c.rotulo,
            "descricao_modelo": c.descricao_modelo, "tipo": c.tipo, "opcoes": _opcoes_out(c.opcoes),
            "unidade": c.unidade, "sensivel": c.sensivel, "pontuacao": c.pontuacao, "ordem": c.ordem,
            "ativo": c.ativo, "eixo": c.eixo, "validade_dias": c.validade_dias,
        }
        exec_query(self._t("qualificacao_criterios").upsert(row, on_conflict="versao_id,chave"))

    def remover_criterio(self, versao_id, chave):
        resp = exec_query(
            self._t("qualificacao_criterios").delete().eq("versao_id", str(versao_id)).eq("chave", chave)
        )
        if not resp.data:
            raise NotFound(f"criterio {chave!r}")

    def salvar_estagio(self, versao_id, e):
        row = {
            "versao_id": str(versao_id), "chave": e.chave, "rotulo": e.rotulo, "descricao": e.descricao,
            "ordem": e.ordem, "regra": e.regra, "conclusivo": e.conclusivo, "terminal": e.terminal,
        }
        exec_query(self._t("qualificacao_estagios").upsert(row, on_conflict="versao_id,chave"))

    def remover_estagio(self, versao_id, chave):
        resp = exec_query(
            self._t("qualificacao_estagios").delete().eq("versao_id", str(versao_id)).eq("chave", chave)
        )
        if not resp.data:
            raise NotFound(f"estagio {chave!r}")

    def salvar_parametros(self, versao_id, p):
        row = {
            "versao_id": str(versao_id), "minimo_para_ofertar": p.minimo_para_ofertar,
            "lote_ofertas": p.lote_ofertas, "score_max": p.score_max, "updated_at": utcnow_iso(),
        }
        exec_query(self._t("qualificacao_parametros").upsert(row, on_conflict="versao_id"))

    def atualizar_notas(self, versao_id, notas):
        exec_query(self._t("qualificacao_versoes").update({"notas": notas}).eq("id", str(versao_id)))

    def publicar(self, versao_id, user_id):
        self._rpc("publicar_qualificacao_versao", {"p_versao_id": str(versao_id), "p_user_id": str(user_id)})

    def descartar_rascunho(self, versao_id):
        exec_query(self._t("qualificacao_versoes").delete().eq("id", str(versao_id)))


def get_padrao_store(settings: Any) -> PadraoStore:
    """Real when a Supabase service-role key is configured, Fake otherwise."""
    if not getattr(settings, "supabase_service_role_key", None):
        return FakePadraoStore()
    from app.database import get_admin_client

    return SupabasePadraoStore(get_admin_client())

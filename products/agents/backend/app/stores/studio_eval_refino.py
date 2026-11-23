"""The eval-loop refine WRITE (migration 092): one bounded draft-row edit + the loop's spend + the immutable event, in ONE transaction.

Event-oriented (KB § PATTERNS/architect/event-oriented-architecture.md): there is no edit without its ``refinamento_proposto`` event and no
such event for an edit that did not land. A step that wrote nothing is still an event (``refinamento_recusado``: why + the cost already
spent), because the spend must reach the loop budget either way.

``Fake`` + ``Supabase`` + factory (seed rule). The Real is one ``agents.aplicar_refinamento_loop`` RPC (a targeted UPDATE guarded by
compare-and-set on the draft's ``compiled_hash`` and on the row's old text); the Fake does the same checks over the in-memory
definition + loop stores, then writes through the SAME store methods the Studio uses. Raises :class:`StudioConflict` with
``conflito_de_versao`` (the draft changed since the round) / ``linha_alterada`` / ``loop_encerrado`` / ``refino_ja_registrado``.

Migration 093 (red-team hardening) makes the RPC refuse by itself, whatever the caller sends: a protective row (``linha_protegida``), a base
layer (``camada_base``: platform-scope agent or one that is the parent of another), a version of ANOTHER agent (``versao_de_outro_agente``),
a fourth edit in a loop (``limite_de_refinos``) and a second edit of one row (``linha_ja_refinada``). ``revisar`` is the human review of an
edit (``refinamento_revisado``): ``aceito`` records it, ``revertido`` puts the row back through the SAME compare-and-set path.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Protocol
from uuid import UUID, uuid4

from app.stores._db_errors import StudioConflict, VersionImmutable, exec_rpc
from app.stores._util import utcnow
from app.stores.errors import NotFound
from app.stores.studio_definitions import SectionInput
from app.stores.studio_definitions_conteudo import FerramentaInput, TextoInput
from app.studio.eval_loop_refino_protegido import linha_e_protegida, protegidas_para_rpc

__all__ = ["EscritaLinha", "RefinoStore", "FakeRefinoStore", "SupabaseRefinoStore", "get_refino_store", "MAX_REFINOS_POR_LOOP"]

_SCHEMA = "agents"
_EVENTOS = ("refinamento_proposto", "refinamento_recusado", "refinamento_sem_edicao")
#: kept equal to ``eval_loop_refino.MAX_REFINOS_POR_LOOP`` (a test): the store cannot import the validator module without a cycle
MAX_REFINOS_POR_LOOP = 3


@dataclass(frozen=True)
class EscritaLinha:
    """The ONE row edit: ``tipo`` secao | texto | ferramenta; ``antes`` is what the row must hold right now (compare-and-set)."""

    version_id: UUID
    tipo: str
    chave: str
    antes: str
    depois: str
    expected_hash: str


class RefinoStore(Protocol):
    def registrar(
        self, org_id: UUID, loop_id: UUID, rodada_seq: int, *, evento: str, detalhe: dict[str, Any], custo_usd: float,
        escrita: EscritaLinha | None,
    ) -> UUID:
        """Record one refine decision (``refinamento_proposto`` needs ``escrita``; ``refinamento_recusado`` / ``refinamento_sem_edicao``
        must not carry one) and add ``custo_usd`` to the loop's spend, atomically. Returns the event id."""
        ...

    def revisar(
        self, org_id: UUID, loop_id: UUID, rodada_seq: int, *, decisao: str, ator: UUID, detalhe: dict[str, Any],
        escrita: EscritaLinha | None,
    ) -> UUID:
        """Record the human review of the edit proposed after ``rodada_seq`` (``refinamento_revisado``): ``aceito`` (no ``escrita``) or
        ``revertido`` (``escrita`` = the row put back: ``antes`` is what it holds now, ``depois`` what it held before the edit; same
        compare-and-set as the edit). One review per edit; ``refino_nao_encontrado`` when there is no edit to review."""
        ...


class FakeRefinoStore:
    def __init__(self, defs: Any, loops: Any) -> None:
        self._defs = defs
        self._loops = loops

    def registrar(
        self, org_id: UUID, loop_id: UUID, rodada_seq: int, *, evento: str, detalhe: dict[str, Any], custo_usd: float,
        escrita: EscritaLinha | None,
    ) -> UUID:
        loop = self._loops.loops.get(loop_id)
        if loop is None or loop.org_id != org_id:
            raise NotFound(f"loop {loop_id} not found")
        if evento not in _EVENTOS or custo_usd < 0 or (evento == "refinamento_proposto") != (escrita is not None):
            raise ValueError("invalid_payload")
        if any(e["loop_id"] == loop_id and e["rodada_seq"] == rodada_seq and e["evento"] in _EVENTOS for e in self._loops.eventos):
            raise StudioConflict("refino_ja_registrado")
        if escrita is not None:
            if loop.status != "ativo":
                raise StudioConflict("loop_encerrado")
            self._guardas(org_id, loop, escrita)
            self._escrever(org_id, escrita)
        self._loops.loops[loop_id] = replace(loop, gasto_usd=round(loop.gasto_usd + custo_usd, 4))
        eid = uuid4()
        self._loops.eventos.append({
            "id": eid, "org_id": org_id, "loop_id": loop_id, "evento": evento, "run_id": None, "rodada_seq": rodada_seq,
            "detalhe": dict(detalhe), "ator": None, "created_at": utcnow()})
        return eid

    def revisar(
        self, org_id: UUID, loop_id: UUID, rodada_seq: int, *, decisao: str, ator: UUID, detalhe: dict[str, Any],
        escrita: EscritaLinha | None,
    ) -> UUID:
        loop = self._loops.loops.get(loop_id)
        if loop is None or loop.org_id != org_id:
            raise NotFound(f"loop {loop_id} not found")
        if decisao not in ("aceito", "revertido") or (decisao == "revertido") != (escrita is not None):
            raise ValueError("invalid_payload")
        if not any(e["loop_id"] == loop_id and e["rodada_seq"] == rodada_seq and e["evento"] == "refinamento_proposto"
                   for e in self._loops.eventos):
            raise StudioConflict("refino_nao_encontrado")
        if any(e["loop_id"] == loop_id and e["rodada_seq"] == rodada_seq and e["evento"] == "refinamento_revisado"
               for e in self._loops.eventos):
            raise StudioConflict("refino_ja_revisado")
        if escrita is not None:
            if self._defs.get_version(org_id, escrita.version_id).agent_id != loop.agent_id:
                raise StudioConflict("versao_de_outro_agente")
            self._escrever(org_id, escrita)
        eid = uuid4()
        self._loops.eventos.append({
            "id": eid, "org_id": org_id, "loop_id": loop_id, "evento": "refinamento_revisado", "run_id": None, "rodada_seq": rodada_seq,
            "detalhe": {**detalhe, "decisao": decisao}, "ator": ator, "created_at": utcnow()})
        return eid

    def _guardas(self, org_id: UUID, loop: Any, e: EscritaLinha) -> None:
        """The refusals migration 093 makes in SQL, over the in-memory stores (same codes)."""
        v = self._defs.get_version(org_id, e.version_id)
        if v.agent_id != loop.agent_id:
            raise StudioConflict("versao_de_outro_agente")
        agent = self._defs.get_agent_by_id(loop.agent_id)
        if any(a.pai_agent_id == agent.id for a in self._defs.list_agents(org_id)):
            raise StudioConflict("camada_base")
        regras: tuple[str, ...] = ()
        if e.tipo == "secao":
            regras = next((tuple(s.regras) for s in self._defs.list_sections(org_id, e.version_id) if s.chave == e.chave), ())
        if linha_e_protegida(e.tipo, e.chave, regras):
            raise StudioConflict("linha_protegida")
        propostos = [x for x in self._loops.eventos if x["loop_id"] == loop.id and x["evento"] == "refinamento_proposto"]
        if len(propostos) >= MAX_REFINOS_POR_LOOP:
            raise StudioConflict("limite_de_refinos")
        if any((x["detalhe"].get("alvo") or {}) == {"tipo": e.tipo, "chave": e.chave} for x in propostos):
            raise StudioConflict("linha_ja_refinada")

    def _escrever(self, org_id: UUID, e: EscritaLinha) -> None:
        v = self._defs.get_version(org_id, e.version_id)
        if v.status != "rascunho":
            raise VersionImmutable()
        if v.compiled_hash != e.expected_hash:
            raise StudioConflict("conflito_de_versao")
        if e.tipo == "secao":
            secoes = self._defs.list_sections(org_id, e.version_id)
            alvo = next((s for s in secoes if s.chave == e.chave), None)
            if alvo is None or alvo.conteudo != e.antes:
                raise StudioConflict("linha_alterada")
            self._defs.replace_sections(org_id, e.version_id, [
                SectionInput(id=s.id, chave=s.chave, titulo=s.titulo, ordem=s.ordem, ativo=s.ativo, regras=tuple(s.regras),
                             conteudo=e.depois if s is alvo else s.conteudo) for s in secoes])
        elif e.tipo == "texto":
            textos = self._defs.list_textos(org_id, e.version_id)
            if not any(t.chave == e.chave and t.conteudo == e.antes for t in textos):
                raise StudioConflict("linha_alterada")
            self._defs.replace_textos(org_id, e.version_id, [
                TextoInput(t.chave, e.depois if t.chave == e.chave else t.conteudo) for t in textos])
        elif e.tipo == "ferramenta":
            ferr = self._defs.list_ferramentas(org_id, e.version_id)
            if not any(f.ferramenta == e.chave and f.descricao == e.antes for f in ferr):
                raise StudioConflict("linha_alterada")
            self._defs.replace_ferramentas(org_id, e.version_id, [
                FerramentaInput(
                    ferramenta=f.ferramenta, descricao=e.depois if f.ferramenta == e.chave else f.descricao, ativo=f.ativo,
                    parametros=dict(f.parametros), obrigatoria_skill=f.obrigatoria_skill) for f in ferr])
        else:
            raise ValueError("invalid_payload")


class SupabaseRefinoStore:
    def __init__(self, client: Any) -> None:
        self._client = client

    def registrar(
        self, org_id: UUID, loop_id: UUID, rodada_seq: int, *, evento: str, detalhe: dict[str, Any], custo_usd: float,
        escrita: EscritaLinha | None,
    ) -> UUID:
        params: dict[str, Any] = {
            "p_org_id": str(org_id), "p_loop_id": str(loop_id), "p_rodada_seq": rodada_seq, "p_evento": evento,
            "p_detalhe": detalhe, "p_custo_usd": round(custo_usd, 4)}
        if escrita is not None:
            params.update(
                p_version_id=str(escrita.version_id), p_tipo=escrita.tipo, p_chave=escrita.chave, p_antes=escrita.antes,
                p_depois=escrita.depois, p_expected_hash=escrita.expected_hash)
        params["p_protegidas"] = protegidas_para_rpc()  # the registry-derived text keys; the SQL patterns of 093 cover sections / tools
        resp = exec_rpc(self._client, _SCHEMA, "aplicar_refinamento_loop", params, unique_code="refino_ja_registrado")
        data = resp.data
        return UUID(str(data[0] if isinstance(data, list) else data))

    def revisar(
        self, org_id: UUID, loop_id: UUID, rodada_seq: int, *, decisao: str, ator: UUID, detalhe: dict[str, Any],
        escrita: EscritaLinha | None,
    ) -> UUID:
        params: dict[str, Any] = {
            "p_org_id": str(org_id), "p_loop_id": str(loop_id), "p_rodada_seq": rodada_seq, "p_decisao": decisao, "p_ator": str(ator),
            "p_detalhe": detalhe}
        if escrita is not None:
            params.update(
                p_version_id=str(escrita.version_id), p_tipo=escrita.tipo, p_chave=escrita.chave, p_antes=escrita.antes,
                p_depois=escrita.depois, p_expected_hash=escrita.expected_hash)
        resp = exec_rpc(self._client, _SCHEMA, "revisar_refinamento_loop", params, unique_code="refino_ja_revisado")
        data = resp.data
        return UUID(str(data[0] if isinstance(data, list) else data))


def get_refino_store(settings: Any) -> RefinoStore:
    if not getattr(settings, "supabase_service_role_key", None):
        from app.stores.studio_definitions import FakeStudioDefinitionStore
        from app.stores.studio_eval_loops import FakeLoopStore

        return FakeRefinoStore(FakeStudioDefinitionStore(), FakeLoopStore())
    from app.database import get_admin_client

    return SupabaseRefinoStore(get_admin_client())

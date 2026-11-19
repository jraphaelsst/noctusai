"""The eval-loop refine WRITE (migration 091): one bounded draft-row edit + the loop's spend + the immutable event, in ONE transaction.

Event-oriented (KB § PATTERNS/architect/event-oriented-architecture.md): there is no edit without its ``refinamento_proposto`` event and no
such event for an edit that did not land. A step that wrote nothing is still an event (``refinamento_recusado``: why + the cost already
spent), because the spend must reach the loop budget either way.

``Fake`` + ``Supabase`` + factory (seed rule). The Real is one ``agents.aplicar_refinamento_loop`` RPC (a targeted UPDATE guarded by
compare-and-set on the draft's ``compiled_hash`` and on the row's old text); the Fake does the same checks over the in-memory
definition + loop stores, then writes through the SAME store methods the Studio uses. Raises :class:`StudioConflict` with
``conflito_de_versao`` (the draft changed since the round) / ``linha_alterada`` / ``loop_encerrado`` / ``refino_ja_registrado``.
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

__all__ = ["EscritaLinha", "RefinoStore", "FakeRefinoStore", "SupabaseRefinoStore", "get_refino_store"]

_SCHEMA = "agents"
_EVENTOS = ("refinamento_proposto", "refinamento_recusado")


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
        """Record one refine decision (``refinamento_proposto`` needs ``escrita``; ``refinamento_recusado`` must not carry one) and add
        ``custo_usd`` to the loop's spend, atomically. Returns the event id."""
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
            self._escrever(org_id, escrita)
        self._loops.loops[loop_id] = replace(loop, gasto_usd=round(loop.gasto_usd + custo_usd, 4))
        eid = uuid4()
        self._loops.eventos.append({
            "id": eid, "org_id": org_id, "loop_id": loop_id, "evento": evento, "run_id": None, "rodada_seq": rodada_seq,
            "detalhe": dict(detalhe), "ator": None, "created_at": utcnow()})
        return eid

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
        resp = exec_rpc(self._client, _SCHEMA, "aplicar_refinamento_loop", params, unique_code="refino_ja_registrado")
        data = resp.data
        return UUID(str(data[0] if isinstance(data, list) else data))


def get_refino_store(settings: Any) -> RefinoStore:
    if not getattr(settings, "supabase_service_role_key", None):
        from app.stores.studio_definitions import FakeStudioDefinitionStore
        from app.stores.studio_eval_loops import FakeLoopStore

        return FakeRefinoStore(FakeStudioDefinitionStore(), FakeLoopStore())
    from app.database import get_admin_client

    return SupabaseRefinoStore(get_admin_client())

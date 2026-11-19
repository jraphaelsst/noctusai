"""The human REVIEW of an eval-loop refine edit (red-team hardening, owner 2026-11-19).

The refine step writes into the DRAFT on its own. Until a person has looked at the edit, the draft cannot be published: readiness carries a
BLOCKING item (``refinamento_sem_revisao``) and publish answers 409 with the same code, for every caller (``agent_package_publish`` included).
The review is a platform-admin act -- a product token cannot acknowledge it -- and is one of two decisions, recorded as the append-only
event ``refinamento_revisado`` with who and when:

* ``aceito``: the edit stays; nothing is written;
* ``revertido``: the row is put back as it was, through the SAME compare-and-set path the edit used (the draft's hash and the row's text
  are both compared, in one transaction): if the draft or the row changed since, the revert is refused (409) and nothing is written.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from app.stores.errors import NotFound
from app.stores.studio_eval_loops import LoopStore
from app.stores.studio_eval_refino import EscritaLinha, RefinoStore
from app.studio.eval_loop_refino import EVENTOS_REFINO, MAX_DIFF_CHARS

__all__ = ["RevisaoRecusada", "revisar_refinamento"]


class RevisaoRecusada(Exception):
    """The review cannot be recorded: a fixed machine ``code`` + a pt-BR line; ``status`` is the HTTP status the route answers."""

    def __init__(self, status: int, code: str, mensagem: str) -> None:
        super().__init__(code)
        self.status = status
        self.code = code
        self.mensagem = mensagem


def revisar_refinamento(
    *, loops: LoopStore, defs: Any, refino: RefinoStore, org_id: UUID, agent: Any, loop_id: UUID, rodada: int, decisao: str, ator: UUID,
    carimbar_hash: Any,
) -> UUID:
    """Record the review of the edit proposed after round ``rodada`` of ``loop_id``. ``carimbar_hash(draft_id) -> str`` recompiles the draft
    NOW and returns its hash (the compare-and-set value of a revert). Returns the event id; raises :class:`RevisaoRecusada` or the stores'
    :class:`StudioConflict` (409)."""
    try:
        loops.get_loop(org_id, agent.id, loop_id)
    except NotFound as exc:
        raise RevisaoRecusada(404, "loop_not_found", "Loop de avaliação não encontrado.") from exc
    eventos = loops.listar_eventos(org_id, loop_id, eventos=EVENTOS_REFINO, limite=1000)
    proposto = next((e for e in eventos if e.get("evento") == "refinamento_proposto" and e.get("rodada_seq") == rodada), None)
    if proposto is None:
        raise RevisaoRecusada(404, "refino_nao_encontrado", "Não há edição automática desta rodada para revisar.")
    if any(e.get("evento") == "refinamento_revisado" and e.get("rodada_seq") == rodada for e in eventos):
        raise RevisaoRecusada(409, "refino_ja_revisado", "Esta edição automática já foi revisada.")
    d = proposto.get("detalhe") or {}
    alvo = d.get("alvo") or {}
    detalhe = {"alvo": alvo, "version_id": d.get("version_id")}
    if decisao == "aceito":
        return refino.revisar(org_id, loop_id, rodada, decisao="aceito", ator=ator, detalhe=detalhe, escrita=None)

    diff = d.get("diff") or {}
    antes, depois = diff.get("antes"), diff.get("depois")
    if not (alvo.get("tipo") and alvo.get("chave") and isinstance(antes, str) and isinstance(depois, str)) \
            or len(antes) >= MAX_DIFF_CHARS or len(depois) >= MAX_DIFF_CHARS:
        raise RevisaoRecusada(409, "reversao_indisponivel", "O texto desta edição não está completo no registro: reverta à mão no Studio.")
    draft = defs.get_draft(org_id, agent.id)
    if draft is None or (d.get("version_id") not in (None, str(draft.id))):
        raise RevisaoRecusada(409, "rascunho_diferente", "O rascunho que recebeu a edição não existe mais: não há o que reverter.")
    hash_atual = carimbar_hash(draft.id)
    escrita = EscritaLinha(
        version_id=draft.id, tipo=alvo["tipo"], chave=alvo["chave"], antes=depois, depois=antes, expected_hash=hash_atual)
    return refino.revisar(org_id, loop_id, rodada, decisao="revertido", ator=ator, detalhe=detalhe, escrita=escrita)

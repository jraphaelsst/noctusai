"""Eval-loop orchestration: admission of a round (G6/G7), opening and closing it, the mid-flight stop notification,
manual stop, and the read model. The pure rules live in :mod:`app.studio.eval_loop`; this module reads/writes them
through the :class:`~app.stores.studio_eval_loops.LoopStore` and notifies through the existing
:class:`~app.notifications.NotificationSink` (core ``public.notifications``, the bell every product shows).

Both suites share it (behaviour ``eval_runs`` and mechanism ``eval_mecanismo_runs``): the two run starts call
:meth:`EvalLoopService.admitir` then :meth:`abrir`; the two run completions call :meth:`fechar_por_run`.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from fastapi import HTTPException

from app.stores.errors import NotFound
from app.stores.studio_eval_loops import LoopRecord, LoopStore
from app.studio.eval_loop import (
    MAX_FALHAS_NA_MENSAGEM, Decisao, Recusa, Rodada, avaliar_rodada, checar_admissao, checkpoints_atingidos, ordenar,
    serie_de_scores,
)

logger = logging.getLogger(__name__)

__all__ = [
    "EvalLoopService", "RunResumo", "Admissao", "resumo_comportamento", "resumo_mecanismo", "recusa_http",
    "KIND_PARADA", "KIND_CHECKPOINT", "SUITES",
]

SUITES = ("comportamento", "mecanismo")
KIND_PARADA = "agents.eval_loop_parado"
KIND_CHECKPOINT = "agents.eval_loop_checkpoint"
_LINK = "/agentes"
_TERMINAIS = ("concluida", "falhou", "cancelada")
_ROTULO_SUITE = {"comportamento": "comportamento", "mecanismo": "mecanismo"}


@dataclass(frozen=True)
class RunResumo:
    """What closing a round needs from a finished run, read from the run stores (never trusted from a caller)."""

    run_id: UUID
    run_tipo: str
    status: str  # concluida | falhou | cancelada
    score: float | None
    custo_usd: float
    falhas: tuple[str, ...]
    compiled_hash: str


@dataclass(frozen=True)
class Admissao:
    loop: LoopRecord
    #: the cost cap the run must carry: the requested/default cap, clamped to what the loop budget has left (G7).
    limite_usd: float


def recusa_http(r: Recusa, status_code: int = 409) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"detail": r.mensagem, "code": r.code})


def resumo_comportamento(evals: Any, org_id: UUID, agent_id: UUID, run_id: UUID) -> RunResumo | None:
    """The behaviour run's resume once it ended; ``None`` while it is still ``pendente``/``executando``."""
    run = evals.get_run(org_id, agent_id, run_id)
    if run.status not in _TERMINAIS:
        return None
    falhas = tuple(sorted(
        r.case_slug for r in evals.list_results_with_cases(org_id, agent_id, run_id) if r.result.status in ("reprovado", "erro")))
    return RunResumo(
        run_id=run_id, run_tipo="comportamento", status=run.status,
        score=float(run.score) if run.score is not None else None, custo_usd=float(run.custo_usd or 0.0), falhas=falhas,
        compiled_hash=run.compiled_hash)


def resumo_mecanismo(mecanismo: Any, org_id: UUID, agent_id: UUID, run_id: UUID) -> RunResumo | None:
    """The mechanism run's resume once it ended. Score = approved cases / cases of the run (pass^k per case)."""
    run = mecanismo.get_run(org_id, run_id)
    if run is None or str(run["agent_id"]) != str(agent_id) or run["status"] not in _TERMINAIS:
        return None
    score, falhas = None, ()
    if run["status"] == "concluida":
        total = int(run.get("total_casos") or 0)
        score = (int(run.get("casos_aprovados") or 0) / total) if total else None
        slugs = {str(c.id): c.slug for c in mecanismo.list_active_cases(org_id, agent_id)}
        por_caso: dict[str, list[str]] = {}
        for e in mecanismo.list_execucoes(org_id, run_id):
            por_caso.setdefault(str(e["case_id"]), []).append(e["status"])
        falhas = tuple(sorted(
            slugs.get(cid, cid[:8]) for cid, sts in por_caso.items() if any(s != "aprovado" for s in sts)))
    return RunResumo(
        run_id=run_id, run_tipo="mecanismo", status=run["status"], score=score,
        custo_usd=float(run.get("custo_usd") or 0.0), falhas=falhas, compiled_hash=run["compiled_hash"])


def _usd(x: float) -> str:
    return f"US$ {x:,.2f}"


def _pct(x: float) -> str:
    return f"{round(x * 100)}%"


class EvalLoopService:
    def __init__(self, loops: LoopStore, sink: Any, consolidacao: Any = None,
                 avisar_dono: Callable[..., Any] | None = None) -> None:
        self._loops = loops
        self._sink = sink
        self._consol = consolidacao
        #: the owner's WhatsApp send — seed ``notify_owner`` (owner line L3) unless a test injects one.
        self._avisar_dono = avisar_dono

    @property
    def store(self) -> LoopStore:
        return self._loops

    # ── admission (G6 / G7) ────────────────────────────────────────────────

    def _limite_passes(self, org_id: UUID, agent_id: UUID, suite: str) -> int:
        """The longest clean streak any active case of the suite needs to consolidate (reuses the consolidation config and
        criticality; nothing re-derived). Without a consolidation store the normal-case streak applies."""
        if self._consol is None:
            from app.studio.consolidacao import DEFAULT_CONFIG

            return int(DEFAULT_CONFIG["consolidar_normal"])
        cfg = self._consol.config()
        metas = [m for m in self._consol.list_meta(org_id, agent_id, suite).values() if m.ativo]
        return max([cfg.limite("em_validacao", m.criticidade) for m in metas] or [cfg.limite("em_validacao", "normal")])

    def admitir(
        self, org_id: UUID, agent_id: UUID, loop_id: UUID, *, suite: str, compiled_hash: str, limite_usd: float,
        ler_resumo: Callable[[UUID], RunResumo | None] | None = None,
    ) -> Admissao:
        """Check a run start against its loop or raise 409 (``loop_encerrado`` / ``rodada_em_andamento`` /
        ``orcamento_do_loop_atingido`` / ``rodadas_esgotadas`` / ``hash_inalterado``) and 404 ``loop_not_found`` / 422
        ``loop_suite_invalida``. ``ler_resumo`` reconciles a round whose run already ended but whose close hook never ran
        (a crashed process, a run cancelled before it was claimed): it is closed first, so a stuck round never blocks forever."""
        try:
            rec = self._loops.get_loop(org_id, agent_id, loop_id)
        except NotFound as exc:
            raise HTTPException(404, detail={"detail": "Loop de avaliação não encontrado.", "code": "loop_not_found"}) from exc
        if rec.suite != suite:
            raise HTTPException(422, detail={
                "detail": f"Este loop é da suíte de {_ROTULO_SUITE[rec.suite]}, não de {_ROTULO_SUITE[suite]}.",
                "code": "loop_suite_invalida"})
        rodadas = self._loops.list_rodadas(org_id, loop_id)
        if ler_resumo is not None and any(r.aberta for r in rodadas):
            for r in [r for r in rodadas if r.aberta]:
                resumo = ler_resumo(r.run_id)
                if resumo is not None:
                    self.fechar_por_run(org_id, resumo)
            rec = self._loops.get_loop(org_id, agent_id, loop_id)
            rodadas = self._loops.list_rodadas(org_id, loop_id)
        recusa = checar_admissao(
            rec.definicao(), rodadas, compiled_hash=compiled_hash,
            limite_passes_consolidacao=self._limite_passes(org_id, agent_id, suite))
        if recusa is not None:
            raise recusa_http(recusa)
        return Admissao(loop=rec, limite_usd=round(min(limite_usd, rec.definicao().restante_usd), 2))

    def abrir(
        self, org_id: UUID, loop_id: UUID, *, run_id: UUID, run_tipo: str, compiled_hash: str, partes: dict[str, str] | None,
    ) -> Rodada:
        from app.stores._db_errors import StudioConflict, mensagem_conflito

        try:
            return self._loops.abrir_rodada(
                org_id, loop_id, run_id=run_id, run_tipo=run_tipo, compiled_hash=compiled_hash, partes=partes)
        except StudioConflict as exc:
            raise HTTPException(409, detail={"detail": mensagem_conflito(exc), "code": exc.code}) from exc

    # ── closing a round (G3 / G4 / G5 / G7) ───────────────────────────────

    def fechar_por_run(self, org_id: UUID, resumo: RunResumo) -> Decisao | None:
        """Close the round of a finished run: flag it, add its cost to the loop, apply the stop rules and notify. ``None`` =
        the run belongs to no loop, or its round was already closed. Idempotent."""
        achado = self._loops.rodada_do_run(org_id, resumo.run_id, resumo.run_tipo)
        if achado is None:
            return None
        rec, rodada = achado
        if not rodada.aberta:
            return None
        todas = self._loops.list_rodadas(org_id, rec.id)
        decisao = avaliar_rodada(
            rec.definicao(), todas, seq=rodada.seq, status=resumo.status, score=resumo.score, custo_usd=resumo.custo_usd,
            falhas=resumo.falhas, compiled_hash=rodada.compiled_hash, partes=rodada.partes)
        escreveu = self._loops.fechar_rodada(
            org_id, rec.id, resumo.run_id, resumo.run_tipo, status=resumo.status, score=resumo.score, custo_usd=resumo.custo_usd,
            falhas=list(resumo.falhas), melhorou=decisao.melhorou, overcall=decisao.overcall, gasto_usd=decisao.gasto_usd,
            parada=decisao.parada)
        if not escreveu:
            return None
        if decisao.overcall:
            logger.warning(
                "agents.eval_loop.overcall loop_id=%s seq=%s score=%s custo_usd=%s", rec.id, rodada.seq, resumo.score, resumo.custo_usd)
        final = self._loops.get_loop(org_id, rec.agent_id, rec.id)
        rodadas = self._loops.list_rodadas(org_id, rec.id)
        if decisao.parada is not None:
            self._notificar(final, self._mensagem_parada(final, rodadas, resumo), KIND_PARADA, f"eval_loop:{rec.id}:parada",
                            {"motivo": final.motivo_parada, **self._payload(final, rodadas, resumo)})
        elif decisao.checkpoint is not None:
            cp = decisao.checkpoint
            self._notificar(final, self._mensagem_checkpoint(final, rodadas, cp), KIND_CHECKPOINT, f"eval_loop:{rec.id}:cp{cp}",
                            {"checkpoint": cp, **self._payload(final, rodadas, resumo)})
        return decisao

    def fechar_sem_falhar(self, org_id: UUID, ler: Callable[[], RunResumo | None], *, run_id: UUID, run_tipo: str) -> None:
        """The completion-hook entry point: never raises into a finished run (its verdict is stored). A failure is logged
        with the exception; the round stays open and the NEXT admission reconciles it (``admitir(ler_resumo=...)``), so the
        loop can neither silently continue nor silently lose the round."""
        try:
            resumo = ler()
            if resumo is not None:
                self.fechar_por_run(org_id, resumo)
        except Exception:
            logger.exception("agents.eval_loop.fechar_rodada_falhou org_id=%s run_id=%s run_tipo=%s", org_id, run_id, run_tipo)

    # ── manual stop ────────────────────────────────────────────────────────

    def parar(self, org_id: UUID, agent_id: UUID, loop_id: UUID, *, motivo: str | None) -> LoopRecord:
        try:
            rec = self._loops.get_loop(org_id, agent_id, loop_id)
        except NotFound as exc:
            raise HTTPException(404, detail={"detail": "Loop de avaliação não encontrado.", "code": "loop_not_found"}) from exc
        detalhe = {"motivo_texto": motivo} if motivo else None
        if not self._loops.parar_loop(org_id, agent_id, loop_id, motivo="parado_manualmente", status="parado", detalhe=detalhe):
            raise HTTPException(409, detail={"detail": f"O loop já foi encerrado ({rec.motivo_parada or rec.status}).", "code": "loop_ja_encerrado"})
        return self._loops.get_loop(org_id, agent_id, loop_id)

    # ── read model ─────────────────────────────────────────────────────────

    def estado(self, org_id: UUID, agent_id: UUID, loop_id: UUID) -> dict[str, Any]:
        try:
            rec = self._loops.get_loop(org_id, agent_id, loop_id)
        except NotFound as exc:
            raise HTTPException(404, detail={"detail": "Loop de avaliação não encontrado.", "code": "loop_not_found"}) from exc
        return self.montar_estado(rec, self._loops.list_rodadas(org_id, loop_id))

    @staticmethod
    def montar_estado(rec: LoopRecord, rodadas: list[Rodada]) -> dict[str, Any]:
        rs = ordenar(rodadas)
        serie = serie_de_scores(rs)
        melhor = max(serie) if serie else None
        overcalls = [r for r in rs if r.overcall]
        d = rec.definicao()
        return {
            "id": rec.id, "agente_chave": rec.agente_chave, "suite": rec.suite, "status": rec.status,
            "motivo_parada": rec.motivo_parada, "detalhe_parada": rec.detalhe_parada,
            "rodadas_planejadas": rec.rodadas_planejadas, "rodadas_feitas": sum(1 for r in rs if not r.aberta),
            "alvo": rec.alvo, "piso": rec.piso, "orcamento_usd": rec.orcamento_usd, "gasto_usd": rec.gasto_usd,
            "restante_usd": d.restante_usd, "melhor_score": melhor, "score_atual": serie[-1] if serie else None,
            "acima_do_piso": (melhor >= rec.piso) if melhor is not None else None,
            "started_at": rec.started_at, "stopped_at": rec.stopped_at,
            "serie": [{
                "rodada": r.seq, "run_id": r.run_id, "status": r.status, "score": r.score, "custo_usd": r.custo_usd,
                "compiled_hash": r.compiled_hash, "melhorou": r.melhorou, "overcall": r.overcall, "falhas": list(r.falhas),
            } for r in rs],
            "overcalls": [{"rodada": r.seq, "run_id": r.run_id, "score": r.score, "custo_usd": r.custo_usd} for r in overcalls],
            "custo_overcalls_usd": round(sum(r.custo_usd for r in overcalls), 4),
            "checkpoints": checkpoints_atingidos(d, rs),
        }

    # ── notification text ──────────────────────────────────────────────────

    def _payload(self, rec: LoopRecord, rodadas: list[Rodada], resumo: RunResumo) -> dict[str, Any]:
        rs = ordenar([r for r in rodadas if not r.aberta])
        return {
            "loop_id": str(rec.id), "agente_chave": rec.agente_chave, "suite": rec.suite,
            "serie": serie_de_scores(rs), "hashes": [r.compiled_hash for r in rs],
            "casos_falhando": list(resumo.falhas), "gasto_usd": rec.gasto_usd, "orcamento_usd": rec.orcamento_usd,
            "rodadas_feitas": len(rs), "rodadas_planejadas": rec.rodadas_planejadas,
            "overcalls": [{"rodada": r.seq, "custo_usd": r.custo_usd} for r in rs if r.overcall],
            "detalhe": rec.detalhe_parada,
        }

    def _mensagem_parada(self, rec: LoopRecord, rodadas: list[Rodada], resumo: RunResumo) -> tuple[str, str]:
        rs = ordenar([r for r in rodadas if not r.aberta])
        n = len(rs)
        serie = " → ".join(_pct(s) for s in serie_de_scores(rs)) or "sem nota"
        titulo = f"Loop de avaliação parado: {rec.agente_chave} ({_ROTULO_SUITE[rec.suite]})"
        if rec.motivo_parada == "alvo_atingido":
            return (f"Loop concluído: {rec.agente_chave} ({_ROTULO_SUITE[rec.suite]})",
                    f"A rodada {n} chegou a {_pct(serie_de_scores(rs)[-1])} (alvo {_pct(rec.alvo)}). Notas: {serie}. "
                    f"Gasto {_usd(rec.gasto_usd)} de {_usd(rec.orcamento_usd)}.")
        if rec.motivo_parada == "orcamento_atingido":
            return (titulo, f"O orçamento do loop foi atingido na rodada {n}: {_usd(rec.gasto_usd)} de {_usd(rec.orcamento_usd)}. "
                            f"Notas: {serie}. Decisão do dono: aumentar o orçamento em um novo loop ou encerrar. "
                            f"{self._falhando(resumo)}")
        if rec.motivo_parada == "rodadas_esgotadas":
            return (titulo, f"As {rec.rodadas_planejadas} rodadas planejadas acabaram sem chegar a {_pct(rec.alvo)}. Notas: {serie}. "
                            f"Gasto {_usd(rec.gasto_usd)}. {self._falhando(resumo)}")
        det = rec.detalhe_parada or {}
        if det.get("conteudo_mudou") is False:
            mudou = "O conteúdo não mudou entre as duas últimas rodadas (mesmo hash): a rodada foi repetida sem correção."
        elif det.get("partes_alteradas"):
            mudou = "Mudou entre as duas últimas rodadas: " + ", ".join(det["partes_alteradas"][:MAX_FALHAS_NA_MENSAGEM]) + "."
        else:
            mudou = "O conteúdo mudou entre as duas últimas rodadas (hash diferente), sem melhora na nota."
        piso = "abaixo" if (max(serie_de_scores(rs) or [0.0]) < rec.piso) else "acima"
        return (titulo, f"Parou na rodada {n} de {rec.rodadas_planejadas}: 2 rodadas seguidas sem melhora da nota "
                        f"(piso {_pct(rec.piso)}, alvo {_pct(rec.alvo)}; melhor nota {piso} do piso). Notas: {serie}. {mudou} "
                        f"{self._falhando(resumo)} Gasto {_usd(rec.gasto_usd)} de {_usd(rec.orcamento_usd)}.")

    @staticmethod
    def _falhando(resumo: RunResumo) -> str:
        if not resumo.falhas:
            return "Nenhum caso falhando na última rodada."
        nomes = ", ".join(resumo.falhas[:MAX_FALHAS_NA_MENSAGEM])
        extra = len(resumo.falhas) - MAX_FALHAS_NA_MENSAGEM
        return f"Casos ainda falhando ({len(resumo.falhas)}): {nomes}" + (f" e mais {extra}." if extra > 0 else ".")

    def _mensagem_checkpoint(self, rec: LoopRecord, rodadas: list[Rodada], cp: int) -> tuple[str, str]:
        rs = ordenar([r for r in rodadas if not r.aberta])
        serie = serie_de_scores(rs)
        over = [r for r in rs if r.overcall]
        return (f"Loop de avaliação: checkpoint da rodada {cp} ({rec.agente_chave}, {_ROTULO_SUITE[rec.suite]})",
                f"Rodada {cp} de {rec.rodadas_planejadas}. Notas: {' → '.join(_pct(s) for s in serie) or 'sem nota'}. "
                f"Gasto {_usd(rec.gasto_usd)} de {_usd(rec.orcamento_usd)}. Rodadas sem melhora: {len(over)} "
                f"({_usd(sum(r.custo_usd for r in over))}).")

    def _notificar(self, rec: LoopRecord, texto: tuple[str, str], kind: str, dedup: str, metadata: dict[str, Any]) -> None:
        """In-app notification to every platform admin (the owner is one). A delivery failure is logged with the exception
        and never undoes the stop (the stop is already stored; the state endpoint carries the same reason)."""
        titulo, mensagem = texto
        try:
            admins = self._sink.platform_admin_ids()
            if not admins:
                logger.error("agents.eval_loop.notificacao_sem_destinatario loop_id=%s kind=%s", rec.id, kind)
                return
            for uid in admins:
                if self._sink.already_sent(uid, dedup):
                    continue
                self._sink.send(uid, kind=kind, title=titulo, message=mensagem,
                                metadata={"dedup_key": dedup, "product": "agents", "link": _LINK, **_json_safe(metadata)})
        except Exception:
            logger.exception("agents.eval_loop.notificacao_falhou loop_id=%s kind=%s", rec.id, kind)
        self._avisar_dono_whatsapp(rec, kind, dedup, metadata)

    def _avisar_dono_whatsapp(self, rec: LoopRecord, kind: str, dedup: str, metadata: dict[str, Any]) -> None:
        """The owner's WhatsApp notice, from NoctusAI's own line (seed ``notify_owner``; catalog kinds ``eval_loop_parada`` /
        ``eval_loop_checkpoint`` declared in ``app/notification_kinds.py``; scripted texts in ``app/studio/eval_loop_whatsapp.py``).

        Once per transition: ``fechar_por_run`` only reaches here after its conditional round-close write succeeded, so a retried
        close never re-sends (``dedup`` is kept in the log line for tracing). ``notify_owner`` records every outcome (switch off,
        no recipient, line not configured, partial) in core's send ledger; a failure here is logged and never undoes the stop."""
        from app.notification_kinds import KIND_EVAL_LOOP_CHECKPOINT, KIND_EVAL_LOOP_PARADA, PRODUCT
        from app.studio.eval_loop_whatsapp import texto_checkpoint, texto_parada

        serie = [s for s in (metadata.get("serie") or []) if s is not None]
        melhor = max(serie) if serie else None
        comum = {"agente": rec.agente_chave, "suite": _ROTULO_SUITE.get(rec.suite, rec.suite), "melhor_nota": melhor,
                 "gasto_usd": rec.gasto_usd, "orcamento_usd": rec.orcamento_usd}
        try:
            if kind == KIND_PARADA:
                catalogo = KIND_EVAL_LOOP_PARADA
                texto = texto_parada(motivo=str(metadata.get("motivo") or rec.motivo_parada or ""),
                                     rodadas_feitas=int(metadata.get("rodadas_feitas") or 0), **comum)
            elif kind == KIND_CHECKPOINT:
                catalogo = KIND_EVAL_LOOP_CHECKPOINT
                texto = texto_checkpoint(rodada=int(metadata["checkpoint"]), rodadas_planejadas=rec.rodadas_planejadas,
                                         rodadas_sem_melhora=len(metadata.get("overcalls") or []), **comum)
            else:
                logger.error("agents.eval_loop.whatsapp_kind_desconhecido loop_id=%s kind=%s", rec.id, kind)
                return
            avisar = self._avisar_dono
            if avisar is None:
                from noctusai_lib.domain.notification_catalog import notify_owner as avisar
            avisar(PRODUCT, catalogo, texto, org_id=rec.org_id)
        except Exception:
            logger.exception("agents.eval_loop.whatsapp_falhou loop_id=%s kind=%s dedup=%s", rec.id, kind, dedup)

def _json_safe(o: Any) -> Any:
    if isinstance(o, dict):
        return {k: _json_safe(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_json_safe(v) for v in o]
    if isinstance(o, UUID):
        return str(o)
    return o

"""Product implementations of the ``domain.media_production`` ports (criacao-pipeline-contract.md sections 2, 5).

* :class:`SupabaseLedger`  -- ``LedgerPort`` over ``cs_criacao_jobs`` through the definer RPC
  ``cs_criacao_passo_registrar`` (the only writer: forward-only status + the step's ``cs_post_eventos`` row, one
  transaction). ``carregar`` reads the same rows back: the ledger IS the graph state, so a restarted worker resumes
  from it.
* :class:`SupabaseQuota`   -- ``QuotaPort`` over ``cs_criacao_cota_estado`` (US$15 / org / month by default).
* :class:`SupabaseMover`   -- ``MoverPort``: moves the card with the seed ``move_card`` as the system actor
  (``motivo='auto:<evento>'``) and writes the projection + its events through ``cs_post_criacao_projetar`` (one tx).
* :class:`VozConsentimento` -- which voice a marca may use and the ``ConsentChecker`` the seed TTS client calls.
* ``ProgressPort`` is the seed default ``BusProgress`` -- built in :mod:`criacao_service`, nothing to implement here.

Every DB call is a blocking PostgREST call: each port method runs it in a thread, never on the event loop.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from decimal import Decimal
from typing import Any, Callable, Optional

from noctusai_lib.domain.media_production import PassoRow, QuotaExceeded, StepError
from noctusai_lib.domain.media_production.runner import EVENTO_CONCLUIDA, EVENTO_PASSO_FALHOU
from noctusai_lib.domain.media_production.types import CONCLUIDO, EXECUTANDO, FALHOU
from noctusai_lib.domain.pipeline import list_stages, move_card

from app.modules.media_creation.criacao_rotas import resolver_rota
from app.modules.media_creation.esteira_config import PIPELINE_ESTEIRA, ROLE_APROVACAO_MIDIA, ROLE_EDICAO

logger = logging.getLogger(__name__)

LEDGER = "cs_criacao_jobs"
POSTS = "cs_posts"

#: The actor of every automatic move / event (``pipeline_movimentos.responsavel_id`` is a plain uuid, no FK).
SISTEMA_ATOR_ID = "00000000-0000-4000-8000-0000000c5e51"

#: Status names the DB uses that differ from the seed runner's.
_PARA_DB = {EXECUTANDO: "em_andamento"}
_DE_DB = {"em_andamento": EXECUTANDO}

#: Conservative USD per credit used ONLY for the quota pre-flight when the org's real price is not configured.
CRIACAO_USD_POR_CREDITO_TETO = Decimal("0.0003")

ESTADO_NA_FILA = "na_fila"
ESTADO_GERANDO = "gerando"
ESTADO_AGUARDANDO_EDICAO = "aguardando_edicao"
ESTADO_AGUARDANDO_MIDIA = "aguardando_aprovacao_midia"
ESTADO_FALHOU = "falhou"
CODIGO_ETAPA_AUSENTE = "etapa_destino_ausente"


def _jsonable(v: Any) -> Any:
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, dict):
        return {k: _jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    return v


def _uuid_or_none(v: Any) -> Optional[str]:
    try:
        return str(uuid.UUID(str(v)))
    except (ValueError, TypeError):
        return None


def _dec(v: Any) -> Optional[Decimal]:
    return None if v is None else Decimal(str(v))


# ── ledger ──────────────────────────────────────────────────────────────────────────────────────────────────────────


class SupabaseLedger:
    """``LedgerPort`` over ``cs_criacao_jobs`` (RPC writer, table reader)."""

    def __init__(self, db: Any) -> None:
        self._db = db

    async def registrar(self, row: PassoRow) -> None:
        await asyncio.to_thread(self._registrar, row)

    async def carregar(self, org_id: str, post_id: str) -> list[PassoRow]:
        return await asyncio.to_thread(self._carregar, org_id, post_id)

    # -- internals (blocking) --
    def _linhas(self, org_id: str, post_id: str) -> list[dict]:
        return (
            self._db.table(LEDGER).select("*").eq("org_id", org_id).eq("post_id", post_id)
            .order("rodada").order("created_at").execute().data or []
        )

    def _registrar(self, row: PassoRow) -> None:
        dados: dict[str, Any] = {}
        # the graph edges: step NAMES in the runner, row ids in the ledger -- resolved against the post's own rows
        if row.depende_de:
            por_passo: dict[str, str] = {}
            for r in self._linhas(row.org_id, row.post_id):
                if r["rodada"] <= row.rodada:
                    por_passo[r["passo"]] = r["id"]  # ordered by rodada: the latest wins
            ids = [por_passo[p] for p in row.depende_de if p in por_passo]
            if ids:
                dados["depende_de"] = ids
        if (job := _uuid_or_none(row.job_id)):
            dados["job_id"] = job
        for k in ("vendor", "modelo", "request_id", "erro_codigo"):
            if getattr(row, k) is not None:
                dados[k] = getattr(row, k)
        if row.cpu_s is not None:
            dados["cpu_s"] = round(row.cpu_s, 3)
        if row.custo_usd is not None:
            dados["custo_usd"] = str(row.custo_usd)
        if row.unidades is not None:
            dados["unidades"] = _jsonable(row.unidades)
        if row.medicoes is not None:
            dados["medicoes"] = _jsonable(row.medicoes)
            if row.medicoes.get("velocidade_render_x") is not None:
                dados["velocidade_render_x"] = row.medicoes["velocidade_render_x"]
        if row.resultado is not None:
            dados["resultado"] = _jsonable(row.resultado)
        nao_medido = list(row.nao_medido)
        if row.status == CONCLUIDO:
            # a finished step is measured or DECLARED unmeasured -- never a silent zero (the table CHECK says so too)
            if row.custo_usd is None and "custo_usd" not in nao_medido:
                nao_medido.append("custo_usd")
            if row.cpu_s is None and "cpu_s" not in nao_medido:
                nao_medido.append("cpu_s")
        if nao_medido:
            dados["nao_medido"] = nao_medido
        self._db.rpc(
            "cs_criacao_passo_registrar",
            {
                "p_org": row.org_id, "p_post": row.post_id, "p_rodada": row.rodada, "p_passo": row.passo,
                "p_status": _PARA_DB.get(row.status, row.status), "p_dados": dados,
            },
        ).execute()
        if row.status == EXECUTANDO:
            # the sub-state projection: queued -> generating (only from the queue; a re-run sets `na_fila` first)
            self._db.rpc(
                "cs_post_criacao_projetar",
                {"p_org": row.org_id, "p_post": row.post_id, "p_estado": ESTADO_GERANDO, "p_falha": None,
                 "p_eventos": [], "p_somente_de": [ESTADO_NA_FILA]},
            ).execute()

    def _carregar(self, org_id: str, post_id: str) -> list[PassoRow]:
        linhas = self._linhas(org_id, post_id)
        nome_por_id = {r["id"]: r["passo"] for r in linhas}
        out: list[PassoRow] = []
        for r in linhas:
            out.append(PassoRow(
                org_id=r["org_id"], post_id=r["post_id"], rodada=r["rodada"], passo=r["passo"],
                depende_de=tuple(nome_por_id[d] for d in (r.get("depende_de") or []) if d in nome_por_id),
                status=_DE_DB.get(r["status"], r["status"]),
                job_id=r.get("job_id"),
                duracao_s=None if r.get("duracao_s") is None else float(r["duracao_s"]),
                cpu_s=None if r.get("cpu_s") is None else float(r["cpu_s"]),
                vendor=r.get("vendor"), modelo=r.get("modelo"), request_id=r.get("request_id"),
                unidades=r.get("unidades") or None,
                custo_usd=_dec(r.get("custo_usd")),
                medicoes=r.get("medicoes") or None,
                resultado=r.get("resultado") or None,
                erro_codigo=r.get("erro_codigo"),
                nao_medido=tuple(r.get("nao_medido") or ()),
            ))
        return out


# ── quota ───────────────────────────────────────────────────────────────────────────────────────────────────────────


class SupabaseQuota:
    """``QuotaPort``: the pre-flight read is ``cs_criacao_cota_estado`` (limit, month-to-date spend from the ledger)."""

    def __init__(self, db: Any) -> None:
        self._db = db

    async def verificar(self, org_id: str, estimativa_usd: Decimal) -> None:
        try:
            res = await asyncio.to_thread(
                lambda: self._db.rpc("cs_criacao_cota_estado", {"p_org": org_id}).execute()
            )
            est = res.data if isinstance(res.data, dict) else (res.data or [None])[0]
            restante = Decimal(str(est["restante_usd"]))
            limite = Decimal(str(est["limite_usd_mes"]))
        except Exception as exc:  # noqa: BLE001 - an unreadable quota is a visible, retryable failure, never a pass
            logger.exception("criacao: cota ilegível org=%s", org_id)
            raise StepError("cota_indisponivel", "não foi possível ler a cota mensal", retryable=True) from exc
        if estimativa_usd > restante:
            raise QuotaExceeded(
                f"cota mensal de criação excedida: estimativa US${estimativa_usd}, restante US${restante} de US${limite}"
            )


# ── mover ───────────────────────────────────────────────────────────────────────────────────────────────────────────


class SupabaseMover:
    """``MoverPort``. Idempotent: the move is a no-op when the card is already there, and the projection RPC writes
    nothing when the sub-state already equals the target -- so a retried job never double-moves or double-logs."""

    def __init__(self, db: Any, cfg: Any = PIPELINE_ESTEIRA) -> None:
        self._db, self._cfg = db, cfg

    async def mover(self, post_id: str, evento: str) -> None:
        await asyncio.to_thread(self._mover, post_id, evento)

    def _post(self, post_id: str) -> dict:
        rows = (
            self._db.table(POSTS).select("id,org_id,etapa_id,formato,criacao_rota").eq("id", post_id).execute().data
        )
        if not rows:
            raise LookupError(f"post {post_id} não encontrado")
        return rows[0]

    def _projetar(self, org: str, post: str, estado: str, falha: Optional[str], eventos: list[dict]) -> None:
        self._db.rpc(
            "cs_post_criacao_projetar",
            {"p_org": org, "p_post": post, "p_estado": estado, "p_falha": falha, "p_eventos": eventos,
             "p_somente_de": None},
        ).execute()

    def _mover(self, post_id: str, evento: str) -> None:
        post = self._post(post_id)
        org = str(post["org_id"])
        if evento == EVENTO_PASSO_FALHOU:
            falhos = [
                r for r in (
                    self._db.table(LEDGER).select("passo,rodada,erro_codigo,terminado_em")
                    .eq("org_id", org).eq("post_id", post_id).eq("status", FALHOU)
                    .order("terminado_em", desc=True).limit(1).execute().data or []
                )
            ]
            codigo = (falhos[0]["erro_codigo"] if falhos else None) or "erro_interno"
            self._projetar(org, post_id, ESTADO_FALHOU, codigo, [])  # the card stays in Criação, with the visible code
            return
        if evento != EVENTO_CONCLUIDA:
            raise ValueError(f"evento de criação desconhecido: {evento}")

        rota = resolver_rota(post.get("formato") or "reel", post.get("criacao_rota"))
        papel_destino = ROLE_EDICAO if rota.edicao else ROLE_APROVACAO_MIDIA
        etapas = list_stages(self._db, self._cfg, org_id=org)
        destino = next((s for s in etapas if s.get("papel") == papel_destino), None)
        if destino is None:
            logger.error("criacao: sem etapa com papel %s na org %s (migração 362 aplicada?)", papel_destino, org)
            self._projetar(org, post_id, ESTADO_FALHOU, CODIGO_ETAPA_AUSENTE, [])
            return
        de_etapa = str(post["etapa_id"]) if post.get("etapa_id") else None
        mudou = de_etapa != str(destino["id"])
        if mudou:
            ids = [str(s["id"]) for s in etapas]
            if not rota.edicao:
                # the skipped Edição stage is traversed, visibly (contract 1: `rota:pulado`)
                edicao = next((s for s in etapas if s.get("papel") == ROLE_EDICAO), None)
                if (
                    edicao is not None and de_etapa in ids and str(edicao["id"]) != de_etapa
                    and ids.index(de_etapa) < ids.index(str(edicao["id"])) < ids.index(str(destino["id"]))
                ):
                    move_card(
                        self._db, self._cfg, card_id=post_id, to_stage_id=str(edicao["id"]), user_id=SISTEMA_ATOR_ID,
                        motivo="rota:pulado", org_id=org,
                    )
            move_card(
                self._db, self._cfg, card_id=post_id, to_stage_id=str(destino["id"]), user_id=SISTEMA_ATOR_ID,
                motivo=f"auto:{EVENTO_CONCLUIDA}", org_id=org,
            )
        eventos = [{"tipo": EVENTO_CONCLUIDA, "dados": {"rota": rota.chave}}]
        if mudou:
            eventos.append({
                "tipo": "card_movido_automaticamente",
                "dados": {"de_etapa_id": de_etapa, "para_etapa_id": str(destino["id"]), "motivo": f"auto:{EVENTO_CONCLUIDA}"},
            })
        self._projetar(
            org, post_id, ESTADO_AGUARDANDO_EDICAO if rota.edicao else ESTADO_AGUARDANDO_MIDIA, None, eventos
        )


# ── voice + consent ─────────────────────────────────────────────────────────────────────────────────────────────────


class VozConsentimento:
    """Which voice a marca may use (``cs_consentimentos_voz``) and the seed ``ConsentChecker`` over the one derivation
    of "cleared" (``cs_consentimento_voz_vigente``: newest grant, not revoked, not expired)."""

    VENDOR = "elevenlabs"

    def __init__(self, db: Any) -> None:
        self._db = db

    def vigente_id(self, org_id: str, marca_id: str, voice_id: str) -> Optional[str]:
        res = self._db.rpc(
            "cs_consentimento_voz_vigente",
            {"p_org": org_id, "p_marca": marca_id, "p_vendor": self.VENDOR, "p_voice_id": voice_id},
        ).execute()
        return res.data or None

    def voz_da_marca(self, org_id: str, marca_id: str) -> Optional[tuple[str, str]]:
        """``(voice_id, consent_id)`` of the newest voice of the marca with a valid consent, else ``None``."""
        grants = (
            self._db.table("cs_consentimentos_voz").select("id,voice_id")
            .eq("org_id", org_id).eq("marca_id", marca_id).eq("vendor", self.VENDOR).eq("fase", "concedido")
            .order("created_at", desc=True).execute().data or []
        )
        vistos: set[str] = set()
        for g in grants:
            if g["voice_id"] in vistos:
                continue
            vistos.add(g["voice_id"])
            cid = self.vigente_id(org_id, marca_id, g["voice_id"])
            if cid:
                return g["voice_id"], str(cid)
        return None

    def checker(self, marca_id: str) -> Callable[[Optional[str], str], bool]:
        """The seed ``ConsentChecker`` bound to one marca: ``vigente(org, voice_id) -> bool``."""

        class _Checker:
            def vigente(_self, org: Optional[str], voice_id: str) -> bool:  # noqa: N805 - Protocol method
                return bool(org and self.vigente_id(org, marca_id, voice_id))

        return _Checker()  # type: ignore[return-value]

"""Product implementations of the ``domain.media_production`` ports (criacao-pipeline-contract.md sections 2, 5).

* :class:`SupabaseLedger`  -- ``LedgerPort`` over ``cs_criacao_jobs`` through the definer RPC
  ``cs_criacao_passo_registrar`` (the only writer: forward-only status + the step's ``cs_post_eventos`` row, one
  transaction). ``carregar`` reads the same rows back: the ledger IS the graph state, so a restarted worker resumes
  from it. The first running step moves the card's sub-state ``na_fila -> gerando`` through the system mover.
* :class:`SupabaseQuota`   -- ``QuotaPort`` over ``cs_criacao_cota_estado`` (US$15 / org / month by default).
* :class:`SistemaMover`    -- ``MoverPort`` over S5's :class:`CriacaoMover` (the ONE system mover: the Criação gate, the
  history row, the sub-state projection + its event, the live stream). Finish -> Edição / Aprovação final; failure ->
  ``falhou`` with the failed step's code.
* :class:`ProgressoComposto` -- ``ProgressPort``: the per-rodada job scope (the progress SSE), the per-post scope
  (``/posts/{id}/criacao/progress``) and the card's live ``pipeline.card_state``.
* :class:`VozConsentimento` -- which voice a marca may use and the ``ConsentChecker`` the seed TTS client calls.

Every DB call is a blocking PostgREST call: each port method runs it in a thread, never on the event loop.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from decimal import Decimal
from typing import Any, Callable, Optional

from noctusai_lib.domain.media_production import PassoRow, QuotaExceeded, StepError
from noctusai_lib.domain.media_production.ports import BusProgress
from noctusai_lib.domain.media_production.runner import EVENTO_CONCLUIDA, EVENTO_PASSO_FALHOU
from noctusai_lib.domain.media_production.types import CONCLUIDO, EXECUTANDO, FALHOU
from noctusai_lib.realtime import JobProgress, RealtimeBus, publish_job_progress

from app.modules.media_creation import criacao_estado as est
from app.modules.media_creation.services.criacao_mover import CriacaoMover

logger = logging.getLogger(__name__)

LEDGER = "cs_criacao_jobs"
POSTS = "cs_posts"

#: Status names the DB uses that differ from the seed runner's.
_PARA_DB = {EXECUTANDO: "em_andamento"}
_DE_DB = {"em_andamento": EXECUTANDO}

#: Conservative USD per credit used ONLY for the quota pre-flight when the org's real price is not configured.
CRIACAO_USD_POR_CREDITO_TETO = Decimal("0.0003")


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

    def __init__(self, db: Any, on_inicio: Optional[Callable[[str, str], None]] = None) -> None:
        self._db = db
        #: called (blocking, in the same thread) the moment a step starts running: ``(org_id, post_id)``
        self._on_inicio = on_inicio

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
        if row.status == EXECUTANDO and self._on_inicio is not None:
            self._on_inicio(row.org_id, row.post_id)

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


# ── mover + progress ────────────────────────────────────────────────────────────────────────────────────────────────


class SistemaMover:
    """``MoverPort`` over S5's ``CriacaoMover``. Idempotent where the mover is: a retried job re-reads the post."""

    def __init__(self, db: Any, bus: Optional[RealtimeBus] = None, factory: Optional[Callable[[str], Any]] = None) -> None:
        self._db, self._bus = db, bus
        #: ``org_id -> CriacaoMover`` (the DI seam: tests pass one over their own DB)
        self._factory = factory or (lambda org: CriacaoMover(db, org, bus=bus))

    def _mover(self, org_id: str) -> CriacaoMover:
        return self._factory(org_id)

    def _org_do_post(self, post_id: str) -> str:
        rows = self._db.table("cs_posts").select("id,org_id").eq("id", post_id).execute().data
        if not rows:
            raise LookupError(f"post {post_id} não encontrado")
        return str(rows[0]["org_id"])

    def iniciar(self, org_id: str, post_id: str) -> None:
        """``na_fila -> gerando`` (only from the queue: a later step / a retry finds ``gerando`` already)."""
        post = self._db.table("cs_posts").select("criacao_estado").eq("id", post_id).eq("org_id", org_id).execute().data
        if post and post[0].get("criacao_estado") == est.NA_FILA:
            self._mover(org_id).iniciar_geracao(post_id)

    async def mover(self, post_id: str, evento: str) -> None:
        await asyncio.to_thread(self._mover_sync, post_id, evento)

    def _mover_sync(self, post_id: str, evento: str) -> None:
        org = self._org_do_post(post_id)
        mv = self._mover(org)
        if evento == EVENTO_CONCLUIDA:
            mv.concluir_geracao(post_id)
            return
        if evento != EVENTO_PASSO_FALHOU:
            raise ValueError(f"evento de criação desconhecido: {evento}")
        falhos = (
            self._db.table(LEDGER).select("passo,rodada,erro_codigo,terminado_em")
            .eq("org_id", org).eq("post_id", post_id).eq("status", FALHOU)
            .order("terminado_em", desc=True).limit(1).execute().data or []
        )
        codigo = (falhos[0]["erro_codigo"] if falhos else None) or "erro_interno"
        mv.falhar(post_id, codigo=codigo, mensagem=f"Falhou: {falhos[0]['passo'] if falhos else 'criação'} ({codigo})")


class ProgressoComposto:
    """``ProgressPort``: job scope ``{post}:{rodada}`` (seed ``BusProgress``), post scope ``{post}`` (latest rodada) and the
    card's live state (``pipeline.card_state``, best-effort)."""

    def __init__(self, bus: RealtimeBus, factory: Optional[Callable[[str], Any]] = None) -> None:
        self._bus, self._por_rodada, self._factory = bus, BusProgress(bus), factory

    async def publicar(self, org_id, post_id, rodada, stage, progress, message, terminal) -> None:
        await self._por_rodada.publicar(org_id, post_id, rodada, stage, progress, message, terminal)
        await publish_job_progress(
            self._bus, org_id, post_id,
            JobProgress("concluido" if terminal else "executando", progress, stage, message, terminal),
        )
        if self._factory is not None and not terminal:  # the terminal card_state is the mover's (it knows the new stage)
            await asyncio.to_thread(
                self._factory(org_id).progresso,
                post_id, passo=stage, rodada=rodada, progresso=progress, mensagem=message,
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

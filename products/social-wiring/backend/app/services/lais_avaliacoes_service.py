"""Lais > Avaliacoes no Google (wave 13, lais-build-contract 15/17).

THE RULE. When an interacao closes with desfecho `qualificado`, the contato's latest feedback is not a dislike
(wave 7 `lais_feedback`) and the org configured `google_review_url`, Julia sends ONE review-ask message over the
contato's own 1:1 line -- inside the 24 h window only (A6: never a mass send, never a template through WAHA) --
at most once per contato per 90 days. The text is deterministic (`montar_texto`; copy becomes configurable later).

HOW. `agendar_apos_fechar` is bound (via `registrar`) to `lais_acoes_service.POS_FECHAR`, so BOTH close paths (the
`encerrar` action and the 24 h-silence close at the next inbound) reach it. It only enqueues a `lais_avaliacao_pedir`
job (the stale guard of contract 0.2: `gen`); every condition is re-read at FIRE time by `executar_pedido`, so a
reply that arrived meanwhile, a late dislike or a second close can never double-send. A skipped ask writes nothing;
a send that fails writes a `status='erro'` row (it does not count toward the 90 days: the person was not asked).

REVIEWS. `sincronizar` mirrors the Google Business Profile reviews into `lais_avaliacoes_cache` through the
`ReviewsProvider` seam (Fake / Real / not-configured). `painel` renders the page: KPIs of the month, the 1..5
distribution, mean, total and the latest reviews. A7: the asks (they hang off a contato) are filtered to the
contatos the caller owns; reviews are public Google data of the org and are shown to every member.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Optional
from uuid import UUID

from noctusai_lib.domain.jobs import Job
from noctusai_lib.integrations.persistence.paging import iter_paged_rows
from noctusai_lib.primitives.exceptions import AppException

from app.services import lais_acesso
from app.services import lais_contatos_service as contatos
from app.services import lais_painel_service as painel_svc
from app.services.lais_envio_service import telefone_do_contato
from app.services.lais_reviews_provider import Review, ReviewsNaoConfigurado, ReviewsProvider

logger = logging.getLogger(__name__)

T_CONFIG = "lais_avaliacao_config"
T_PEDIDOS = "lais_avaliacao_pedidos"
T_CACHE = "lais_avaliacoes_cache"
T_FEEDBACK = "lais_feedback"
T_INTERACOES = contatos.T_INTERACOES

JOB_PEDIR = "lais_avaliacao_pedir"
JOB_MAX_RETRIES = 2
DESFECHO_QUALIFICADO = "qualificado"
INTERVALO_PEDIDO = timedelta(days=90)
JANELA_WHATSAPP = timedelta(hours=24)
SYNC_MIN_INTERVALO = timedelta(minutes=15)
ULTIMAS = 10
CONFIG_PADRAO: dict[str, Any] = {"google_review_url": None, "gbp_location_id": None, "capi_ativo": False, "capi_pixel_id": None}
_URL_RE = re.compile(r"^https://\S+$")
_PIXEL_RE = re.compile(r"^[0-9]{5,20}$")

#: Sends the review ask: `async (contato, texto) -> None`, raising when it could not leave. Production builds it
#: from the contato's WhatsApp connection (`enviador_padrao`); tests inject a fake.
Enviador = Callable[[dict[str, Any], str], Awaitable[None]]

# The job repository of the running Lais worker (set by `lais_reengajamento_worker.build_worker`).
_repo: Any = None


def registrar_repo(repo: Any) -> None:
    global _repo
    _repo = repo


def _agora(agora: Optional[datetime] = None) -> datetime:
    return agora or datetime.now(timezone.utc)


# ── config ───────────────────────────────────────────────────────────────────
def obter_config(db: Any, org_id: UUID | str) -> dict[str, Any]:
    rows = db.table(T_CONFIG).select("*").eq("org_id", str(org_id)).limit(1).execute().data or []
    row = rows[0] if rows else {}
    return {k: row.get(k, v) for k, v in CONFIG_PADRAO.items()}


def validar_config(valores: dict[str, Any]) -> dict[str, Any]:
    """Normalise + validate the writable keys (mirrors the DB CHECKs: 422 here, never a bare 500 from them)."""
    out: dict[str, Any] = {}
    for chave, valor in valores.items():
        if chave not in CONFIG_PADRAO:
            continue
        if isinstance(valor, str):
            valor = valor.strip() or None
        if chave == "google_review_url" and valor is not None and (not _URL_RE.match(valor) or len(valor) > 500):
            raise AppException("config_invalida", "O link de avaliação deve começar com https://.", status_code=422)
        if chave == "capi_pixel_id" and valor is not None and not _PIXEL_RE.match(valor):
            raise AppException("config_invalida", "O pixel deve conter apenas números (5 a 20 dígitos).", status_code=422)
        if chave == "gbp_location_id" and valor is not None and len(valor) > 200:
            raise AppException("config_invalida", "Identificador do local muito longo.", status_code=422)
        if chave == "capi_ativo":
            valor = bool(valor)
        out[chave] = valor
    return out


def salvar_config(db: Any, org_id: UUID | str, valores: dict[str, Any]) -> dict[str, Any]:
    novo = {**obter_config(db, org_id), **validar_config(valores)}
    db.table(T_CONFIG).upsert(
        {"org_id": str(org_id), **novo, "updated_at": _agora().isoformat()}, on_conflict="org_id",
    ).execute()
    return novo


# ── the ask: rule ──────────────────────────────────────────────────────────────
def montar_texto(nome: Optional[str], link: str) -> str:
    """Deterministic ask copy (`{nome}` = first name, `{link}` = the org review link)."""
    primeiro = (nome or "").strip().split(" ")[0] if (nome or "").strip() else ""
    saudacao = f"Oi, {primeiro}!" if primeiro else "Oi!"
    return f"{saudacao} Foi um prazer te atender por aqui. Se puder, deixe uma avaliação rápida pra gente no Google, ajuda muito: {link}"


def ts(valor: Any) -> Optional[datetime]:
    if isinstance(valor, datetime):
        dt = valor
    elif isinstance(valor, str) and valor:
        try:
            dt = datetime.fromisoformat(valor.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def linhas(db: Any, tabela: str, colunas: str, **eq: Any) -> list[dict[str, Any]]:
    """Every row of `tabela` matching the equalities (paged: PostgREST caps an unbounded select at 1000)."""
    def pagina(a: int, b: int) -> Any:
        q = db.table(tabela).select(colunas)
        for campo, valor in eq.items():
            q = q.eq(campo, str(valor))
        return q.order("id").range(a, b).execute().data

    return list(iter_paged_rows(pagina, label=tabela))


def mais_recente(rows: list[dict[str, Any]], campo: str) -> Optional[dict[str, Any]]:
    """The row with the greatest timestamp in `campo` (sorted client-side: the set is a handful of rows)."""
    validas = [r for r in rows if ts(r.get(campo)) is not None]
    return max(validas, key=lambda r: ts(r[campo])) if validas else None  # type: ignore[arg-type,return-value]


def ultimo_feedback_negativo(db: Any, org_id: UUID | str, contato_id: UUID | str) -> bool:
    """The contato's LATEST feedback is a dislike (a later like overrides an old dislike)."""
    ultimo = mais_recente(linhas(db, T_FEEDBACK, "id, nota, created_at", org_id=org_id, contato_id=contato_id), "created_at")
    return ultimo is not None and ultimo.get("nota") == "dislike"


def pedido_recente(db: Any, org_id: UUID | str, contato_id: UUID | str, agora: datetime) -> bool:
    """A review ask went out to this contato within the last 90 days (failed asks do not count)."""
    desde = (agora - INTERVALO_PEDIDO).isoformat()
    rows = (
        db.table(T_PEDIDOS).select("id").eq("org_id", str(org_id)).eq("contato_id", str(contato_id))
        .eq("status", "enviado").gte("enviado_at", desde).limit(1).execute().data or []
    )
    return bool(rows)


def dentro_da_janela(contato: dict[str, Any], agora: datetime) -> bool:
    ultimo = ts(contato.get("ultimo_inbound_at"))
    return ultimo is not None and timedelta(0) <= agora - ultimo <= JANELA_WHATSAPP


def motivo_para_nao_pedir(
    db: Any, org_id: UUID | str, contato: dict[str, Any], interacao_id: Optional[UUID | str], agora: datetime,
) -> Optional[str]:
    """None when the ask may go out now; otherwise the reason it must not (the first failing check)."""
    if interacao_id is None:
        return "sem_interacao"
    inter = (
        db.table(T_INTERACOES).select("desfecho").eq("id", str(interacao_id)).eq("org_id", str(org_id)).limit(1).execute().data or []
    )
    if not inter or inter[0].get("desfecho") != DESFECHO_QUALIFICADO:
        return "desfecho_nao_qualificado"
    if not obter_config(db, org_id)["google_review_url"]:
        return "sem_link"
    if ultimo_feedback_negativo(db, org_id, contato["id"]):
        return "feedback_negativo"
    if pedido_recente(db, org_id, contato["id"], agora):
        return "ja_pediu_90_dias"
    if telefone_do_contato(contato) is None:
        return "sem_telefone"
    if not dentro_da_janela(contato, agora):
        return "fora_da_janela_24h"
    return None


# ── the ask: hook (enqueue) + job (send) ─────────────────────────────────────────
async def agendar_apos_fechar(
    db: Any, org_id: UUID | str, contato: dict[str, Any], interacao: dict[str, Any],
) -> Optional[str]:
    """`POS_FECHAR` hook: enqueue the ask job when the closed interacao was `qualificado` and the org has a link.
    Cheap pre-checks only; the full rule is re-read at fire time. Returns the job id, or None when nothing queued."""
    if interacao.get("desfecho") != DESFECHO_QUALIFICADO:
        return None
    if not obter_config(db, org_id)["google_review_url"]:
        return None
    if _repo is None:
        logger.warning("lais avaliacoes: no job repository registered -- the review ask for contato=%s is not queued", contato.get("id"))
        return None
    # re-read: `encerrar` bumped `gen` before the close, the handler's contato dict predates it
    rows = db.table(contatos.T_CONTATOS).select("*").eq("id", str(contato["id"])).limit(1).execute().data or []
    atual = rows[0] if rows else contato
    from app.services import lais_reengajamento_service

    job = await _repo.enqueue(
        type=JOB_PEDIR,
        payload={
            **contatos.payload_job(atual, lais_reengajamento_service.chave_do_chat(atual["connection_id"], atual["chat_id"])),
            "contato_id": str(atual["id"]), "interacao_id": str(interacao["id"]),
        },
        max_retries=JOB_MAX_RETRIES, scheduled_for=_agora(),
        dedupe_key=f"lais:avaliacao:{interacao['id']}",
    )
    return str(getattr(job, "id", "")) or None


def _registrar_pedido(db: Any, org_id: UUID | str, contato_id: Any, interacao_id: Any, status: str, erro: Optional[str], agora: datetime) -> None:
    db.table(T_PEDIDOS).insert({
        "org_id": str(org_id), "contato_id": str(contato_id), "interacao_id": str(interacao_id) if interacao_id else None,
        "enviado_at": agora.isoformat(), "status": status, "erro": erro,
    }).execute()


async def executar_pedido(job: Job, *, client: Any, enviar: Enviador, agora: Optional[datetime] = None) -> str:
    """`lais_avaliacao_pedir` at fire time. Returns the outcome (`enviado`, `obsoleto`, `ignorado:<motivo>`, `erro:<tipo>`)."""
    p = job.payload or {}
    org_id, contato_id = p.get("org_id"), p.get("contato_id")
    if not (org_id and contato_id):
        return "payload_invalido"
    if contatos.job_obsoleto(client, org_id, contato_id, int(p.get("gen") or 0)):
        return "obsoleto"
    rows = client.table(contatos.T_CONTATOS).select("*").eq("org_id", str(org_id)).eq("id", str(contato_id)).limit(1).execute().data or []
    if not rows:
        return "obsoleto"
    contato = rows[0]
    agora = _agora(agora)
    motivo = motivo_para_nao_pedir(client, org_id, contato, p.get("interacao_id"), agora)
    if motivo is not None:
        return f"ignorado:{motivo}"
    texto = montar_texto(contato.get("nome"), obter_config(client, org_id)["google_review_url"])
    try:
        await enviar(contato, texto)
    except Exception as exc:
        logger.exception("lais avaliacoes: review ask failed (org=%s contato=%s)", org_id, contato_id)
        _registrar_pedido(client, org_id, contato_id, p.get("interacao_id"), "erro", type(exc).__name__, agora)
        return f"erro:{type(exc).__name__}"
    _registrar_pedido(client, org_id, contato_id, p.get("interacao_id"), "enviado", None, agora)
    contatos.atualizar_contato(client, contato_id, {"ultimo_outbound_at": agora.isoformat()})
    return "enviado"


def enviador_padrao(connection_lookup: Callable[[UUID], Any], waha_factory: Callable[..., Any]) -> Enviador:
    """The production sender: the contato's own connection; WAHA free text (1:1, A6) or a configured Cloud one."""
    from app.services import lais_transporte

    async def enviar(contato: dict[str, Any], texto: str) -> None:
        record = connection_lookup(UUID(str(contato["connection_id"])))
        if record is None:
            raise RuntimeError("conexao_nao_encontrada")
        if getattr(record, "transporte", lais_transporte.TRANSPORTE_WAHA) == lais_transporte.TRANSPORTE_CLOUD:
            if not lais_transporte.cloud_configurada(record):
                raise RuntimeError("transporte_indisponivel")
            await lais_transporte.transporte_da_conexao(record).enviar_texto(telefone_do_contato(contato) or "", texto)
            return
        waha = waha_factory(base_url=record.base_url or None, api_key=record.api_key, session=record.session_name)
        await waha.send_text(contato["chat_id"], texto)

    return enviar


def handlers(
    *, client_provider: Callable[[], Any], enviar_factory: Callable[[], Enviador],
) -> dict[str, Callable[[Job], Any]]:
    """`{job type: handler}` merged into the Lais worker; collaborators are built at FIRE time."""

    async def _pedir(job: Job) -> None:
        outcome = await executar_pedido(job, client=client_provider(), enviar=enviar_factory())
        logger.info("lais avaliacoes %s job=%s -> %s", job.type, job.id, outcome)

    return {JOB_PEDIR: _pedir}


# ── reviews (GBP) ──────────────────────────────────────────────────────────────
def _linha_cache(org_id: UUID | str, r: Review, agora: datetime) -> dict[str, Any]:
    return {
        "org_id": str(org_id), "external_id": r.external_id, "autor": r.autor, "nota": r.nota, "texto": r.texto,
        "publicado_at": r.publicado_at.isoformat() if r.publicado_at else None, "link": r.link, "fetched_at": agora.isoformat(),
    }


def _ultima_sync(db: Any, org_id: UUID | str) -> Optional[datetime]:
    ultima = mais_recente(linhas(db, T_CACHE, "id, fetched_at", org_id=org_id), "fetched_at")
    return ts(ultima["fetched_at"]) if ultima else None


async def sincronizar(
    db: Any, org_id: UUID | str, provider: ReviewsProvider, *, agora: Optional[datetime] = None, forcar: bool = False,
) -> dict[str, Any]:
    """Mirror the org's GBP reviews into the cache. Best effort: returns `{estado, novas}` and NEVER raises, so
    the page always renders from the cache (estado: sincronizada | recente | sem_local | nao_configurado | erro)."""
    cfg = obter_config(db, org_id)
    if not cfg["gbp_location_id"]:
        return {"estado": "sem_local", "novas": 0}
    agora = _agora(agora)
    ultima = _ultima_sync(db, org_id)
    if not forcar and ultima is not None and agora - ultima < SYNC_MIN_INTERVALO:
        return {"estado": "recente", "novas": 0}
    try:
        reviews = list(await provider.listar(cfg["gbp_location_id"]))
    except ReviewsNaoConfigurado:
        return {"estado": "nao_configurado", "novas": 0}
    except Exception as exc:  # a provider failure (incl. ReviewsErro) must not break the page
        logger.exception("lais avaliacoes: GBP sync failed (org=%s): %s", org_id, type(exc).__name__)
        return {"estado": "erro", "novas": 0}
    existentes = {r["external_id"] for r in linhas(db, T_CACHE, "id, external_id", org_id=org_id)}
    novas = sum(1 for r in reviews if r.external_id not in existentes)
    if reviews:
        db.table(T_CACHE).upsert([_linha_cache(org_id, r, agora) for r in reviews], on_conflict="org_id,external_id").execute()
    return {"estado": "sincronizada", "novas": novas}


def _varrer_pedidos(db: Any, org_id: UUID | str, ini: datetime, fim: datetime) -> list[dict[str, Any]]:
    def pagina(a: int, b: int) -> Any:
        return (
            db.table(T_PEDIDOS).select("id, contato_id, status, enviado_at").eq("org_id", str(org_id)).eq("status", "enviado")
            .gte("enviado_at", ini.astimezone(timezone.utc).isoformat()).lt("enviado_at", fim.astimezone(timezone.utc).isoformat())
            .order("id").range(a, b).execute().data
        )

    return list(iter_paged_rows(pagina, label="lais_avaliacao_pedidos"))


def _mes_do(valor: Any) -> Optional[str]:
    dt = ts(valor)
    if dt is None:
        return None
    dt = dt.astimezone(painel_svc.TZ)
    return f"{dt.year:04d}-{dt.month:02d}"


def painel(db: Any, ctx: lais_acesso.AcessoCtx, *, mes: str, gbp_configurado: bool) -> dict[str, Any]:
    ini, fim = painel_svc.janela(mes)
    cfg = obter_config(db, ctx.org_id)
    pedidos = lais_acesso.filtrar_por_contato(db, ctx, _varrer_pedidos(db, ctx.org_id, ini, fim))  # A7
    cache = linhas(db, T_CACHE, "*", org_id=ctx.org_id)
    distribuicao = {str(n): 0 for n in range(1, 6)}
    for r in cache:
        distribuicao[str(int(r["nota"]))] += 1
    total = len(cache)
    media = round(sum(int(r["nota"]) for r in cache) / total, 2) if total else None
    ordenadas = sorted(cache, key=lambda r: ts(r.get("publicado_at")) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return {
        "mes": mes,
        "pedidos_enviados": len(pedidos),
        "novas_avaliacoes": sum(1 for r in cache if _mes_do(r.get("publicado_at")) == mes),
        "distribuicao": distribuicao,
        "media": media,
        "total": total,
        "ultimas": [
            {"autor": r.get("autor"), "data": r.get("publicado_at"), "nota": int(r["nota"]), "texto": r.get("texto"), "link": r.get("link")}
            for r in ordenadas[:ULTIMAS]
        ],
        "configurado": {"review_url": bool(cfg["google_review_url"]), "gbp": bool(gbp_configurado and cfg["gbp_location_id"])},
    }


# ── wiring ─────────────────────────────────────────────────────────────────────
def registrar() -> None:
    """Bind the `POS_FECHAR` hook (idempotent); called once at import of the router."""
    from app.services import lais_acoes_service

    lais_acoes_service.registrar_pos_fechar(_pos_fechar)


async def _pos_fechar(client: Any, org_id: UUID | str, contato: dict[str, Any], interacao: dict[str, Any], origem: str) -> None:
    if origem != "encerrar":
        # the 24 h-silence close happens because the lead just wrote again: never ask for a review in the same breath
        return
    await agendar_apos_fechar(client, org_id, contato, interacao)


__all__ = [
    "CONFIG_PADRAO", "DESFECHO_QUALIFICADO", "INTERVALO_PEDIDO", "JANELA_WHATSAPP", "JOB_PEDIR", "agendar_apos_fechar",
    "dentro_da_janela", "linhas", "mais_recente", "ts", "enviador_padrao", "executar_pedido", "handlers", "montar_texto", "motivo_para_nao_pedir",
    "obter_config", "painel", "pedido_recente", "registrar", "registrar_repo", "salvar_config", "sincronizar",
    "ultimo_feedback_negativo", "validar_config",
]

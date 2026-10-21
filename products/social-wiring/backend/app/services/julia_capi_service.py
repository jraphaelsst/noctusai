"""Julia wave 13 -- Meta Conversions API (CAPI) qualification signals (lais-build-contract 15/17).

Three signals -- `lead_qualificado` (wave 3 send / `qualificar_lead`), `visita_agendada` (wave 5 confirm) and
`resposta_cliente` (the first inbound after a reengajamento) -- go to Meta so the campaign optimises for QUALIFIED
leads, not just form fills. Rules, all enforced here:

  * ONLY for contatos whose lead came from Meta ads: `julia_contatos.lead_id -> leads.meta_lead_id ->
    meta_ads_leads.id` (migration 041/033). Anyone else records nothing and calls nothing.
  * Gated by the org's `capi_ativo` + `capi_pixel_id` (julia_avaliacao_config) AND the workspace Meta token
    (`resolve_meta_ads_config`, the existing meta_ads seam). Missing any -> the row is stored as `nao_configurado`
    and Meta is NEVER called.
  * Identifiers are SHA-256 hashed per Meta's normalisation (email: trim + lowercase; phone: digits only with
    country code, no leading zeros). They exist only inside the payload to Meta (never stored in our tables);
    `lead_id` (Meta's lead-gen id) is sent as Meta requires, unhashed.
  * One row per signal (`dedupe_key`, unique per org): a replayed hook records and sends once.

The seam: `CapiProvider` Protocol + `FakeCapiProvider` + `RealMetaCapiProvider` (the seed Graph transport
`graph_post`: pacing + retry + typed errors) + `make_capi_provider`. The send itself is a `julia_capi_enviar` job
(the hooks are called inside request handlers; the Graph call is blocking HTTP) -- fired by the Julia worker.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional, Protocol, runtime_checkable
from uuid import UUID

from noctusai_lib.domain.jobs import Job

from app.services import julia_avaliacoes_service as avaliacoes
from app.services import julia_contatos_service as contatos

logger = logging.getLogger(__name__)

T_CAPI = "julia_capi_eventos"
T_LEADS = "leads"
T_META_LEADS = "meta_ads_leads"
T_EVENTOS = "julia_eventos"
JOB_ENVIAR = "julia_capi_enviar"
JOB_MAX_RETRIES = 2

EVENTOS = ("lead_qualificado", "visita_agendada", "resposta_cliente")
#: Meta event names: Schedule / Contact are Meta standard events; `QualifiedLead` is the custom stage event.
EVENTO_META = {"lead_qualificado": "QualifiedLead", "visita_agendada": "Schedule", "resposta_cliente": "Contact"}
LEAD_EVENT_SOURCE = "Julia"
JANELA_RESPOSTA = timedelta(days=7)  # Meta rejects events older than 7 days
_NAO_DIGITO = re.compile(r"\D")


# ── hashing (Meta normalisation) ─────────────────────────────────────────────
def sha256_hex(valor: str) -> str:
    return hashlib.sha256(valor.encode("utf-8")).hexdigest()


def hash_email(email: Optional[str]) -> Optional[str]:
    """Meta: trim whitespace + lowercase, then SHA-256 (hex)."""
    limpo = (email or "").strip().lower()
    return sha256_hex(limpo) if "@" in limpo else None


def hash_telefone(telefone: Optional[str]) -> Optional[str]:
    """Meta: digits only, with the country code, no leading zeros / `+`; then SHA-256. A bare Brazilian
    number (10-11 digits) gets the `55` country code."""
    digitos = _NAO_DIGITO.sub("", telefone or "").lstrip("0")
    if len(digitos) in (10, 11):
        digitos = "55" + digitos
    return sha256_hex(digitos) if len(digitos) >= 10 else None


# ── provider seam ─────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class CapiEvento:
    nome: str
    event_id: str
    event_time: int
    user_data: dict[str, Any]
    custom_data: dict[str, Any] = field(default_factory=dict)

    def como_payload(self) -> dict[str, Any]:
        return {
            "event_name": self.nome, "event_time": self.event_time, "event_id": self.event_id,
            "action_source": "system_generated", "user_data": self.user_data, "custom_data": self.custom_data,
        }


@runtime_checkable
class CapiProvider(Protocol):
    async def enviar(self, pixel_id: str, evento: CapiEvento) -> dict[str, Any]: ...


class FakeCapiProvider:
    """Records what would have gone to Meta (tests/dev). `erro` makes every send raise."""

    def __init__(self, *, erro: Optional[Exception] = None):
        self.enviados: list[tuple[str, CapiEvento]] = []
        self.erro = erro

    async def enviar(self, pixel_id: str, evento: CapiEvento) -> dict[str, Any]:
        if self.erro is not None:
            raise self.erro
        self.enviados.append((pixel_id, evento))
        return {"events_received": 1, "fake": True}


class RealMetaCapiProvider:
    """`POST /{pixel_id}/events` over the seed Graph transport (`graph_post`: paced, retried, typed errors)."""

    def __init__(self, *, access_token: str, graph_version: Optional[str] = None, post: Optional[Callable[..., dict[str, Any]]] = None):
        self._token = access_token
        self._version = graph_version
        self._post = post

    def _enviar_sync(self, pixel_id: str, evento: CapiEvento) -> dict[str, Any]:
        post = self._post
        kw: dict[str, Any] = {}
        if post is None:
            from noctusai_lib.integrations.meta._meta_api import DEFAULT_GRAPH_VERSION, graph_post

            post, kw["version"] = graph_post, self._version or DEFAULT_GRAPH_VERSION
        return post(f"{pixel_id}/events", access_token=self._token, data={"data": json.dumps([evento.como_payload()])}, **kw)

    async def enviar(self, pixel_id: str, evento: CapiEvento) -> dict[str, Any]:
        return await asyncio.to_thread(self._enviar_sync, pixel_id, evento)


def make_capi_provider(*, access_token: Optional[str], use_fake: bool = False, graph_version: Optional[str] = None) -> Optional[CapiProvider]:
    """Fake when asked; Real when a token exists; None when CAPI cannot be called (no token)."""
    if use_fake:
        return FakeCapiProvider()
    if not access_token:
        return None
    return RealMetaCapiProvider(access_token=access_token, graph_version=graph_version)


def token_padrao() -> Optional[str]:
    """The workspace Meta token of the existing meta_ads seam (DB-first, env fallback)."""
    from app.services.app_config_store import resolve_meta_ads_config

    return resolve_meta_ads_config()[0]


# ── who is a Meta-ads lead ─────────────────────────────────────────────────────
def lead_meta_do_contato(db: Any, org_id: UUID | str, contato: dict[str, Any]) -> Optional[dict[str, Any]]:
    """The `meta_ads_leads` row behind this contato (contato.lead_id -> leads.meta_lead_id -> meta_ads_leads.id), else None."""
    if not contato.get("lead_id"):
        return None
    leads = db.table(T_LEADS).select("id, meta_lead_id").eq("org_id", str(org_id)).eq("id", str(contato["lead_id"])).limit(1).execute().data or []
    meta_id = leads[0].get("meta_lead_id") if leads else None
    if not meta_id:
        return None
    rows = db.table(T_META_LEADS).select("*").eq("org_id", str(org_id)).eq("id", str(meta_id)).limit(1).execute().data or []
    return rows[0] if rows else None


def montar_evento(evento: str, event_id: str, event_time: datetime, contato: dict[str, Any], meta_lead: dict[str, Any]) -> CapiEvento:
    user: dict[str, Any] = {"lead_id": str(meta_lead["id"])}
    ph = hash_telefone(meta_lead.get("phone") or contato.get("telefone_e164"))
    em = hash_email(meta_lead.get("email") or contato.get("email"))
    if ph:
        user["ph"] = [ph]
    if em:
        user["em"] = [em]
    return CapiEvento(
        nome=EVENTO_META[evento], event_id=event_id, event_time=int(event_time.timestamp()), user_data=user,
        custom_data={"event_source": "crm", "lead_event_source": LEAD_EVENT_SOURCE},
    )


# ── recording + job ────────────────────────────────────────────────────────────
# The job repository of the running Julia worker (set by `julia_reengajamento_worker.build_worker`).
_repo: Any = None
_token_resolver: Callable[[], Optional[str]] = token_padrao


def registrar_repo(repo: Any) -> None:
    global _repo
    _repo = repo


def registrar_token_resolver(fn: Optional[Callable[[], Optional[str]]]) -> None:
    global _token_resolver
    _token_resolver = fn or token_padrao


def _token() -> Optional[str]:
    try:
        return _token_resolver()
    except Exception as exc:
        logger.error("julia capi: could not resolve the Meta token (%s)", type(exc).__name__)
        return None


def configurado(db: Any, org_id: UUID | str) -> bool:
    cfg = avaliacoes.obter_config(db, org_id)
    return bool(cfg["capi_ativo"] and cfg["capi_pixel_id"] and _token())


def _atualizar(db: Any, row_id: Any, patch: dict[str, Any]) -> None:
    db.table(T_CAPI).update(patch).eq("id", str(row_id)).execute()


async def registrar_evento(
    db: Any, org_id: UUID | str, contato_id: UUID | str, evento: str, *, referencia: str = "", agora: Optional[datetime] = None,
) -> dict[str, Any]:
    """Record one signal and (when configured) queue its send. NEVER raises -- a signal is observability of
    a business event, it must not undo it. Returns `{estado, ...}`: nao_meta | repetido | nao_configurado |
    pendente | erro."""
    try:
        return await _registrar(db, org_id, contato_id, evento, referencia, agora or datetime.now(timezone.utc))
    except Exception as exc:
        logger.error("julia capi: could not record %s (org=%s contato=%s) (%s)", evento, org_id, contato_id, type(exc).__name__)
        return {"estado": "erro", "erro": "falha_interna"}


async def _registrar(db: Any, org_id: UUID | str, contato_id: UUID | str, evento: str, referencia: str, agora: datetime) -> dict[str, Any]:
    if evento not in EVENTOS:
        raise ValueError(f"evento CAPI desconhecido: {evento!r}")
    rows = db.table(contatos.T_CONTATOS).select("*").eq("org_id", str(org_id)).eq("id", str(contato_id)).limit(1).execute().data or []
    if not rows or lead_meta_do_contato(db, org_id, rows[0]) is None:
        return {"estado": "nao_meta"}
    dedupe = f"{evento}:{contato_id}" + (f":{referencia}" if referencia else "")
    ok = configurado(db, org_id)
    linha = {
        "org_id": str(org_id), "contato_id": str(contato_id), "evento": evento, "dedupe_key": dedupe,
        "status": "pendente" if ok else "nao_configurado",
    }
    inseridas = db.table(T_CAPI).upsert(linha, on_conflict="org_id,dedupe_key", ignore_duplicates=True).execute().data or []
    if not inseridas:
        return {"estado": "repetido"}
    row = inseridas[0]
    if not ok:
        return {"estado": "nao_configurado", "id": str(row["id"])}
    if _repo is None:
        logger.error("julia capi: no job repository registered -- signal %s stays unsent (org=%s)", row["id"], org_id)
        _atualizar(db, row["id"], {"status": "erro", "erro": "sem_fila"})
        return {"estado": "erro", "erro": "sem_fila", "id": str(row["id"])}
    await _repo.enqueue(
        type=JOB_ENVIAR, payload={"org_id": str(org_id), "evento_id": str(row["id"])},
        max_retries=JOB_MAX_RETRIES, scheduled_for=agora, dedupe_key=f"julia:capi:{row['id']}",
    )
    return {"estado": "pendente", "id": str(row["id"])}


async def registrar_resposta(
    db: Any, org_id: UUID | str, contato: dict[str, Any], *, agora: Optional[datetime] = None,
) -> dict[str, Any]:
    """`resposta_cliente`: the contato just wrote; counts only when a reengajamento (template / nudge) went out
    to them in the last 7 days -- one signal per reengajamento (the event id is the dedupe reference)."""
    agora = agora or datetime.now(timezone.utc)
    try:
        ultimo = avaliacoes.mais_recente(
            avaliacoes.linhas(db, T_EVENTOS, "id, created_at", org_id=org_id, contato_id=contato["id"], tipo="reengajamento"), "created_at",
        )
    except Exception as exc:
        logger.error("julia capi: could not read the reengajamento events (org=%s) (%s)", org_id, type(exc).__name__)
        return {"estado": "erro", "erro": "falha_interna"}
    evs = [ultimo] if ultimo else []
    if not evs:
        return {"estado": "sem_reengajamento"}
    quando = avaliacoes.ts(evs[0].get("created_at"))
    if quando is None or not (timedelta(0) <= agora - quando <= JANELA_RESPOSTA):
        return {"estado": "sem_reengajamento"}
    return await registrar_evento(db, org_id, contato["id"], "resposta_cliente", referencia=str(evs[0]["id"]), agora=agora)


async def executar_envio(
    job: Job, *, client: Any, provider_factory: Callable[[Optional[str]], Optional[CapiProvider]] = lambda t: make_capi_provider(access_token=t),
    agora: Optional[datetime] = None,
) -> str:
    """`julia_capi_enviar` at fire time: re-reads the row, the gate and the lead; sends; stores the outcome."""
    p = job.payload or {}
    org_id, evento_id = p.get("org_id"), p.get("evento_id")
    if not (org_id and evento_id):
        return "payload_invalido"
    rows = client.table(T_CAPI).select("*").eq("org_id", str(org_id)).eq("id", str(evento_id)).limit(1).execute().data or []
    if not rows:
        return "obsoleto"
    row = rows[0]
    if row["status"] != "pendente":
        return "ja_tratado"
    cfg = avaliacoes.obter_config(client, org_id)
    token = _token()
    provider = provider_factory(token) if (cfg["capi_ativo"] and cfg["capi_pixel_id"]) else None
    if provider is None:
        _atualizar(client, evento_id, {"status": "nao_configurado"})
        return "nao_configurado"
    crows = client.table(contatos.T_CONTATOS).select("*").eq("org_id", str(org_id)).eq("id", str(row["contato_id"])).limit(1).execute().data or []
    meta_lead = lead_meta_do_contato(client, org_id, crows[0]) if crows else None
    if meta_lead is None:
        _atualizar(client, evento_id, {"status": "erro", "erro": "lead_meta_ausente"})
        return "erro:lead_meta_ausente"
    quando = avaliacoes.ts(row.get("created_at")) or (agora or datetime.now(timezone.utc))
    evento = montar_evento(row["evento"], str(row["dedupe_key"]), quando, crows[0], meta_lead)
    try:
        await provider.enviar(cfg["capi_pixel_id"], evento)
    except Exception as exc:
        logger.error("julia capi: send failed (org=%s evento=%s) (%s)", org_id, evento_id, type(exc).__name__)
        _atualizar(client, evento_id, {"status": "erro", "erro": type(exc).__name__})
        return f"erro:{type(exc).__name__}"
    _atualizar(client, evento_id, {"status": "enviado", "enviado_at": (agora or datetime.now(timezone.utc)).isoformat(), "erro": None})
    return "enviado"


def handlers(
    *, client_provider: Callable[[], Any],
    provider_factory: Callable[[Optional[str]], Optional[CapiProvider]] = lambda t: make_capi_provider(access_token=t),
) -> dict[str, Callable[[Job], Any]]:
    async def _enviar(job: Job) -> None:
        outcome = await executar_envio(job, client=client_provider(), provider_factory=provider_factory)
        logger.info("julia capi %s job=%s -> %s", job.type, job.id, outcome)

    return {JOB_ENVIAR: _enviar}


__all__ = [
    "CapiEvento", "CapiProvider", "EVENTOS", "EVENTO_META", "FakeCapiProvider", "JOB_ENVIAR", "RealMetaCapiProvider",
    "configurado", "executar_envio", "handlers", "hash_email", "hash_telefone", "lead_meta_do_contato",
    "make_capi_provider", "montar_evento", "registrar_evento", "registrar_repo", "registrar_resposta",
    "registrar_token_resolver", "sha256_hex",
]

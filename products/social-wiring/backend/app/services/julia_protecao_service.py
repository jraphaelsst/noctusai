"""Abuse protection for Julia's PUBLIC WhatsApp number -- SW's side (owner 2026-10-21: "set limits and rate limitings ... so we
protect our operation from someone trying to break our system on purpose"; GUARDRAILS B5).

Four things, all per ORG and all data (migration 298), nothing a lead message can influence:

  1. an inbound RATE LIMIT per number, applied BEFORE agents is called (Redis sliding window, the same `SlidingWindowLimiter`
     the per-chat turn limit uses). Over it the message is stored (the team can read it) and nothing else happens;
  2. a MEDIA AI BUDGET per chat and per connection per day: a Whisper / vision call is the expensive thing a stranger can force.
     Over it there is no AI call and the lead path gets a placeholder;
  3. a per-org BLOCKLIST of numbers (manual: admin + reason; automatic: TEMPORARY, from the thresholds). A blocked number's
     inbound is recorded and never reaches agents or an AI call;
  4. an AUTOMATIC TEMPORARY BLOCK: a number that trips an abuse signal `limiar` times inside `janela` (its own inbound flood, or
     agents' `limite_taxa` / `loop_detectado`) is blocked for `duracao`; the org admins are notified and an admin can lift it.

`obter_config` returns the org's row merged over `PADRAO` (a missing row = the defaults, and the UI shows which). The keys
here (`julia:prot:*`) are Redis-side counters only; the durable record is the blocklist row.

Nothing here deletes: a lift sets `ativo=false` (rows are history), and an expired automatic block lifts itself on the next read.
Logs carry ids and counts only -- a chat id is HASHED (`ref`), never the number.
"""
from __future__ import annotations

import hashlib
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

from noctusai_lib.domain.notifications import write_in_app
from noctusai_lib.primitives.exceptions import AppException

from app.services.julia_agente_service import SlidingWindowLimiter, phone_digits, is_lid
from app.services.julia_notificacoes_service import admins_da_org

logger = logging.getLogger(__name__)

T_CONFIG = "julia_protecao_config"
T_BLOQUEIOS = "julia_numeros_bloqueados"
GATILHOS_AUTO = ("entrada_flood", "limite_taxa", "loop_detectado")
KIND_BLOQUEIO = "julia_bloqueio_automatico"
MOTIVO_MAX = 300
DIA_S = 86400
LINK_PROTECAO = "/julia/protecao"

#: The defaults (also the migration's column defaults): what an org without a row gets.
PADRAO: dict[str, Any] = {
    "entrada_limite": 20,
    "entrada_janela_s": 60,
    "midia_limite_chat_dia": 10,
    "midia_limite_conexao_dia": 200,
    "bloqueio_auto_ativo": True,
    "bloqueio_auto_limiar": 3,
    "bloqueio_auto_janela_min": 60,
    "bloqueio_auto_duracao_min": 1440,
    "prompt_documento_lead": None,
}
#: field -> (min, max): the same ranges as the migration's CHECKs (the UI form is built from this too)
FAIXAS: dict[str, tuple[int, int]] = {
    "entrada_limite": (1, 500),
    "entrada_janela_s": (10, 3600),
    "midia_limite_chat_dia": (0, 10000),
    "midia_limite_conexao_dia": (0, 100000),
    "bloqueio_auto_limiar": (1, 100),
    "bloqueio_auto_janela_min": (1, 1440),
    "bloqueio_auto_duracao_min": (1, 43200),
}
PROMPT_MIN, PROMPT_MAX = 20, 4000


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def ref(valor: str) -> str:
    """A log-safe reference for a number / chat id / LID: 10 hex chars of its SHA-256 (never the identifier)."""
    return hashlib.sha256((valor or "").encode("utf-8")).hexdigest()[:10]


def _parse(valor: Any) -> Optional[datetime]:
    if not valor:
        return None
    try:
        d = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


# ── config ──────────────────────────────────────────────────────────────────
def obter_config(client: Any, org_id: UUID | str) -> dict[str, Any]:
    """The org's limits merged over `PADRAO`; `padrao` is True when the org has no row (everything is a default)."""
    rows = client.table(T_CONFIG).select("*").eq("org_id", str(org_id)).limit(1).execute().data or []
    row = rows[0] if rows else {}
    cfg = {k: (row.get(k) if (row.get(k) is not None or k == "prompt_documento_lead") and k in row else v) for k, v in PADRAO.items()}
    return {**cfg, "padrao": not rows, "atualizado_em": row.get("updated_at")}


def salvar_config(client: Any, org_id: UUID | str, user_id: str, campos: dict[str, Any]) -> dict[str, Any]:
    """Upsert the org's row. Only the keys present change; each is validated against `FAIXAS` (the DB CHECKs are the backstop)."""
    patch: dict[str, Any] = {}
    for k, (lo, hi) in FAIXAS.items():
        if k in campos and campos[k] is not None:
            v = campos[k]
            if isinstance(v, bool) or not isinstance(v, int) or not lo <= v <= hi:
                raise AppException("valor_invalido", f"{k}: use um número inteiro de {lo} a {hi}.", status_code=422)
            patch[k] = v
    if "bloqueio_auto_ativo" in campos and campos["bloqueio_auto_ativo"] is not None:
        patch["bloqueio_auto_ativo"] = bool(campos["bloqueio_auto_ativo"])
    if "prompt_documento_lead" in campos:
        p = campos["prompt_documento_lead"]
        p = (p or "").strip() or None
        if p is not None and not PROMPT_MIN <= len(p) <= PROMPT_MAX:
            raise AppException("prompt_invalido", f"O texto do documento deve ter de {PROMPT_MIN} a {PROMPT_MAX} caracteres (ou ficar vazio para o padrão).", status_code=422)
        patch["prompt_documento_lead"] = p
    existe = client.table(T_CONFIG).select("org_id").eq("org_id", str(org_id)).limit(1).execute().data or []
    agora = _agora().isoformat()
    if existe:
        if patch:
            client.table(T_CONFIG).update({**patch, "atualizado_por": str(user_id), "updated_at": agora}).eq("org_id", str(org_id)).execute()
    else:
        client.table(T_CONFIG).insert({"org_id": str(org_id), **patch, "atualizado_por": str(user_id)}).execute()
    return obter_config(client, org_id)


# ── identifiers ─────────────────────────────────────────────────────────────
def chave_numero(chat_id: str) -> Optional[str]:
    """The blocklist key of a chat id: the phone's digits, or `<digits>@lid` for a LID; None for a group / anything else."""
    raw = (chat_id or "").strip().lower()
    d = phone_digits(raw)
    if d:
        return d
    if is_lid(raw):
        digitos = raw[: -len("@lid")]
        return raw if digitos.isdigit() else None
    return None


# ── blocklist ───────────────────────────────────────────────────────────────
def _agora_iso() -> str:
    return _agora().isoformat()


def bloqueio_ativo(client: Any, org_id: UUID | str, chaves: list[str]) -> Optional[dict[str, Any]]:
    """The ACTIVE block of any of `chaves` (an expired automatic block is lifted here and does not count)."""
    for chave in chaves:
        rows = client.table(T_BLOQUEIOS).select("*").eq("org_id", str(org_id)).eq("numero", chave).eq("ativo", True).limit(1).execute().data or []
        if not rows:
            continue
        linha = rows[0]
        expira = _parse(linha.get("expira_em"))
        if expira is not None and expira <= _agora():
            client.table(T_BLOQUEIOS).update({"ativo": False, "desbloqueado_em": _agora_iso()}).eq("id", str(linha["id"])).execute()
            continue
        return linha
    return None


def _motivo(motivo: Optional[str]) -> str:
    m = " ".join((motivo or "").split())
    if not 1 <= len(m) <= MOTIVO_MAX:
        raise AppException("motivo_obrigatorio", f"Informe o motivo (até {MOTIVO_MAX} caracteres).", status_code=422)
    return m


def bloquear(client: Any, org_id: UUID | str, ator_user_id: str, *, numero: str, motivo: str, expira_em: Optional[datetime] = None) -> dict[str, Any]:
    """A manual block by an admin. A number on the org's staff list cannot be blocked (it would silence a colleague)."""
    from app.services import julia_staff_service as staff

    d = staff.normalizar_telefone(numero)
    chave = d or chave_numero(numero)
    if chave is None:
        raise AppException("numero_invalido", "Informe um número de WhatsApp com DDI e DDD.", status_code=422)
    if staff.buscar_por_telefone(client, org_id, [chave]) is not None:
        raise AppException("numero_da_equipe", "Este número é da equipe. Remova-o da equipe antes de bloquear.", status_code=409)
    if bloqueio_ativo(client, org_id, [chave]) is not None:
        raise AppException("numero_ja_bloqueado", "Este número já está bloqueado.", status_code=409)
    linha = {
        "id": str(uuid.uuid4()), "org_id": str(org_id), "numero": chave, "motivo": _motivo(motivo), "origem": "manual", "gatilho": "manual",
        "criado_por": str(ator_user_id), "expira_em": expira_em.isoformat() if expira_em else None, "ativo": True,
    }
    res = client.table(T_BLOQUEIOS).insert(linha).execute().data or []
    if not res:
        raise RuntimeError("julia: block not stored")
    logger.info("julia: number blocked by an admin org=%s ref=%s", org_id, ref(chave))
    return res[0]


def desbloquear(client: Any, org_id: UUID | str, ator_user_id: str, bloqueio_id: UUID | str) -> dict[str, Any]:
    rows = client.table(T_BLOQUEIOS).select("*").eq("id", str(bloqueio_id)).eq("org_id", str(org_id)).limit(1).execute().data or []
    if not rows:
        raise AppException("bloqueio_nao_encontrado", "Bloqueio não encontrado.", status_code=404)
    if not rows[0].get("ativo"):
        raise AppException("bloqueio_ja_desfeito", "Este bloqueio já foi desfeito.", status_code=409)
    patch = {"ativo": False, "desbloqueado_por": str(ator_user_id), "desbloqueado_em": _agora_iso()}
    client.table(T_BLOQUEIOS).update(patch).eq("id", str(bloqueio_id)).eq("org_id", str(org_id)).execute()
    logger.info("julia: block lifted by an admin org=%s ref=%s", org_id, ref(rows[0]["numero"]))
    return {**rows[0], **patch}


def listar_bloqueios(client: Any, org_id: UUID | str, *, somente_ativos: bool = True) -> list[dict[str, Any]]:
    q = client.table(T_BLOQUEIOS).select("*").eq("org_id", str(org_id))
    if somente_ativos:
        q = q.eq("ativo", True)
    rows = q.execute().data or []
    agora = _agora()
    if somente_ativos:  # an expired automatic block is not "active" any more
        rows = [r for r in rows if not (_parse(r.get("expira_em")) and _parse(r["expira_em"]) <= agora)]
    return sorted(rows, key=lambda r: str(r.get("criado_em") or ""), reverse=True)


# ── per-number inbound rate limit ───────────────────────────────────────────
def permitir_entrada(redis: Any, config: dict[str, Any], *, org_id: UUID | str, connection_id: UUID | str, chave: str) -> bool:
    """Count one inbound from `chave`; False = over the org's per-number limit (the caller stores the message and stops)."""
    return SlidingWindowLimiter(redis).allow(
        f"julia:prot:in:{org_id}:{connection_id}:{chave}", limit=int(config["entrada_limite"]), window_s=int(config["entrada_janela_s"]),
    )


# ── media AI budget ─────────────────────────────────────────────────────────
def _contagem(redis: Any, key: str, janela_s: int, agora: float) -> int:
    return len(redis.zrangebyscore(key, agora - janela_s, "+inf"))


def reservar_midia(redis: Any, config: dict[str, Any], *, connection_id: UUID | str, chat_id: str, agora: Optional[float] = None) -> Optional[str]:
    """Reserve ONE media AI call for this chat and connection (24 h sliding windows). None = reserved; otherwise the refusing scope
    (`chat` | `conexao`) -- no AI call may be made. Both counters are checked before either is consumed."""
    now = time.time() if agora is None else agora
    k_chat = f"julia:prot:midia:chat:{connection_id}:{chat_id}"
    k_con = f"julia:prot:midia:conn:{connection_id}"
    for key in (k_chat, k_con):
        stale = redis.zrangebyscore(key, "-inf", now - DIA_S)
        if stale:
            redis.zrem(key, *stale)
    if _contagem(redis, k_chat, DIA_S, now) >= int(config["midia_limite_chat_dia"]):
        return "chat"
    if _contagem(redis, k_con, DIA_S, now) >= int(config["midia_limite_conexao_dia"]):
        return "conexao"
    membro = f"{now}:{uuid.uuid4().hex[:8]}"
    for key in (k_chat, k_con):
        redis.zadd(key, {membro: now})
        redis.expire(key, DIA_S + 60)
    return None


# ── abuse infractions -> automatic temporary block ──────────────────────────
def registrar_infracao(
    redis: Any, client: Any, core: Any, config: dict[str, Any], *, org_id: UUID | str, connection_id: UUID | str, chave: str,
    gatilho: str, agora: Optional[float] = None,
) -> Optional[dict[str, Any]]:
    """Count one abuse signal for `chave`. When the org's threshold (`limiar` inside `janela`) is reached, block the number for
    `duracao`, notify the admins and return the new block row; otherwise None. Never raises (a failure is logged: abuse protection
    failing must not take the lead path down, and the per-turn limits still apply)."""
    if gatilho not in GATILHOS_AUTO:
        raise ValueError(f"unknown abuse trigger {gatilho!r}")
    if not config.get("bloqueio_auto_ativo", True):
        return None
    try:
        now = time.time() if agora is None else agora
        janela = int(config["bloqueio_auto_janela_min"]) * 60
        key = f"julia:prot:inf:{org_id}:{chave}"
        stale = redis.zrangebyscore(key, "-inf", now - janela)
        if stale:
            redis.zrem(key, *stale)
        redis.zadd(key, {f"{now}:{gatilho}:{uuid.uuid4().hex[:6]}": now})
        redis.expire(key, janela + 60)
        total = len(redis.zrangebyscore(key, now - janela, "+inf"))
        if total < int(config["bloqueio_auto_limiar"]):
            return None
        if bloqueio_ativo(client, org_id, [chave]) is not None:
            return None
        from app.services import julia_staff_service as staff

        if staff.buscar_por_telefone(client, org_id, [chave]) is not None:  # never lock a colleague out by accident
            return None
        expira = datetime.fromtimestamp(now, tz=timezone.utc) + timedelta(minutes=int(config["bloqueio_auto_duracao_min"]))
        linha = {
            "id": str(uuid.uuid4()), "org_id": str(org_id), "numero": chave, "origem": "automatico", "gatilho": gatilho, "ativo": True,
            "motivo": f"Bloqueio automático: {total} sinais de abuso em {int(config['bloqueio_auto_janela_min'])} min (último: {gatilho}).",
            "criado_por": None, "expira_em": expira.isoformat(),
        }
        res = client.table(T_BLOQUEIOS).insert(linha).execute().data or []
        if not res:
            raise RuntimeError("automatic block not stored")
        redis.delete(key)
        logger.warning("julia: automatic temporary block org=%s ref=%s trigger=%s signals=%s", org_id, ref(chave), gatilho, total)
        return notificar_bloqueio(client, core, org_id, res[0])
    except Exception:
        logger.exception("julia: abuse infraction bookkeeping failed org=%s ref=%s", org_id, ref(chave))
        return None


def notificar_bloqueio(client: Any, core: Any, org_id: UUID | str, linha: dict[str, Any]) -> dict[str, Any]:
    """Tell the org admins (in-app); the outcome is stored on the row (a notice that did not land is VISIBLE, never swallowed)."""
    try:
        admins = admins_da_org(core, org_id)
        if not admins:
            raise RuntimeError("sem_destinatarios")
        write_in_app(
            core, user_ids=admins, kind=KIND_BLOQUEIO, org_id=org_id,
            title="Número bloqueado automaticamente",
            message="Um número atingiu o limite de sinais de abuso na linha da Julia e foi bloqueado por um período. Você pode desbloqueá-lo na página Proteção.",
            metadata={"product": "social-wiring", "link": LINK_PROTECAO, "bloqueio_id": str(linha["id"])},
        )
        status = "enviada"
    except Exception:
        logger.exception("julia: automatic-block notice failed org=%s block=%s", org_id, linha.get("id"))
        status = "falhou"
    try:
        client.table(T_BLOQUEIOS).update({"notificacao_status": status}).eq("id", str(linha["id"])).execute()
    except Exception:
        logger.exception("julia: automatic-block notice status not stored block=%s", linha.get("id"))
    return {**linha, "notificacao_status": status}


# ── the inbound triage (the webhook's first question about a stranger) ───────
@dataclass(frozen=True)
class Triagem:
    """What the webhook learned about an inbound BEFORE any media AI call or agents call.

    `estado`: `livre` (a lead, under every limit) | `bloqueado` (on the org blocklist) | `limitado` (over the per-number inbound
    rate limit) | `erro` (the protection data could not be read: nothing expensive may run, text still flows)."""

    estado: str
    config: dict[str, Any]
    chave: Optional[str]
    org_id: Any
    connection_id: Any

    @property
    def bloqueia_ia(self) -> bool:
        return self.estado != "livre"

    def reservar_midia(self, redis: Any, chat_id: str) -> Optional[str]:
        return reservar_midia(redis, self.config, connection_id=self.connection_id, chat_id=chat_id)


def eh_numero_da_lista(lista: Any, remetente: str) -> bool:
    """Light check of a sender against a connection's `authorized_numbers` by phone digits (no LID cache, no network)."""
    from app.services import julia_staff_service as staff

    d = staff.normalizar_telefone(remetente)
    return bool(d) and any(staff.normalizar_telefone(n) == d for n in (lista or []))


def triar_entrada(
    client: Any, redis: Any, core: Any, connection: Any, *, chat_id: str, sender: str,
) -> Triagem:
    """Triage an inbound that may be a LEAD on a Julia line: blocklist first, then the per-number rate limit (a limited message
    counts as an abuse signal and may trip the automatic temporary block). A sender on the staff list is never triaged here (the
    caller decides staff first). Never raises: an unreadable config is `erro` (the expensive work is refused, the text proceeds)."""
    org_id, connection_id = connection.org_id, connection.id
    chave = chave_numero(chat_id) or chave_numero(sender)
    try:
        config = obter_config(client, org_id)
    except Exception as exc:
        logger.error("julia: protection config unreadable org=%s (%s) -- no media AI for this inbound", org_id, type(exc).__name__)
        return Triagem("erro", dict(PADRAO), chave, org_id, connection_id)
    if chave is None:
        return Triagem("livre", config, None, org_id, connection_id)
    try:
        if bloqueio_ativo(client, org_id, [chave]) is not None:
            logger.info("julia: inbound from a blocked number org=%s ref=%s -- recorded only", org_id, ref(chave))
            return Triagem("bloqueado", config, chave, org_id, connection_id)
        if not permitir_entrada(redis, config, org_id=org_id, connection_id=connection_id, chave=chave):
            logger.warning("julia: inbound rate limit hit org=%s ref=%s -- recorded only", org_id, ref(chave))
            registrar_infracao(redis, client, core, config, org_id=org_id, connection_id=connection_id, chave=chave, gatilho="entrada_flood")
            return Triagem("limitado", config, chave, org_id, connection_id)
    except Exception as exc:
        logger.error("julia: inbound triage failed org=%s (%s) -- no media AI for this inbound", org_id, type(exc).__name__)
        return Triagem("erro", config, chave, org_id, connection_id)
    return Triagem("livre", config, chave, org_id, connection_id)


__all__ = [
    "FAIXAS", "GATILHOS_AUTO", "PADRAO", "Triagem", "eh_numero_da_lista", "triar_entrada", "bloquear", "bloqueio_ativo", "chave_numero", "desbloquear", "listar_bloqueios",
    "notificar_bloqueio", "obter_config", "permitir_entrada", "ref", "registrar_infracao", "reservar_midia", "salvar_config",
]

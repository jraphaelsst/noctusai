"""Receiver sink for the platform grant that wires an org to the `agents` product (Julia-line D2-D5).

`agents` MINTS the channel token and DELIVERS it (`PUT /api/platform/grants/agents`, one-shot delivery token);
nobody pastes it. This module is the product half of that call:

* `on_grant`  -> the credential becomes the org's `api_key:agents` (the SAME row `agents_token_for_org` reads),
  and the grant's non-secret metadata becomes a second row `grant:agents` in the same encrypted store
  (no new table) -- that is what `GET /api/julia/agente` shows as `conexao_plataforma`.
* `on_revoke` -> both rows are deleted (the page then reads "ainda nao conectada pela plataforma").

The credential is a secret: it is never logged, never echoed. The tools token is minted by agents itself
(issuer `agents`, scope `social-wiring:lais-tools`); SW mints nothing here.
"""
from __future__ import annotations

import inspect
import logging
import time
from datetime import datetime, timezone
from typing import Any, Callable, Optional
from uuid import UUID

from noctusai_lib.api.auth._blocking import run_blocking
from noctusai_seed.platform_grants_router import GrantReceived, GrantRevoked, create_platform_grants_router

from app.clients.agents import AgentsTimeout, AgentsTokenInvalid, AgentsUpstreamError
from app.services import api_keys_store
from app.services.julia_agente_service import AGENTS_KEY_NAME, DEFAULT_AGENT_KEY

logger = logging.getLogger(__name__)

#: Provider name of the metadata row (`credentials.provider`), next to `api_key:agents`.
GRANT_PROVIDER = f"grant:{AGENTS_KEY_NAME}"
_META_FIELDS = ("grant_id", "agent_key", "token_prefix", "scopes", "expires_at")

# DI slot (never a import-time singleton): ``None`` = build the real encrypted store per call.
_store_factory: Optional[Callable[[], Any]] = None


def configure_grant_sink(store_factory: Optional[Callable[[], Any]] = None) -> None:
    """Set (or, with ``None``, reset) the credential-store factory the sink uses."""
    global _store_factory
    _store_factory = store_factory


def _store() -> Any:
    if _store_factory is not None:
        return _store_factory()
    from app.config import settings

    return api_keys_store.build_api_key_store(encryption_key=settings.encryption_key)


def on_grant(grant: GrantReceived) -> None:
    """Store the delivered channel token as `api_key:agents` + the grant metadata as `grant:agents`.
    A (re)grant starts a fresh health record: any earlier failure / revocation is forgotten."""
    store = _store()
    org = str(grant.org_id)
    api_keys_store.put_api_key(store, org, AGENTS_KEY_NAME, grant.credential)
    meta: dict[str, Any] = {k: grant.metadata.get(k) for k in _META_FIELDS if grant.metadata.get(k) is not None}
    meta["agent_id"] = grant.agent_id
    meta["agent_key"] = meta.get("agent_key") or DEFAULT_AGENT_KEY
    meta["conectada_em"] = _now().isoformat()
    store.put(org, GRANT_PROVIDER, meta)
    _ultimo_ok.pop(org, None)
    logger.info("julia: platform grant stored org=%s grant_id=%s", org, meta.get("grant_id"))


def on_revoke(revoked: GrantRevoked) -> None:
    """Drop the channel token (idempotent). The metadata row stays, stamped `revogada_em`, so the page can say
    "revogada" instead of pretending it was never connected."""
    store = _store()
    org = str(revoked.org_id)
    api_keys_store.delete_api_key(store, org, AGENTS_KEY_NAME)
    row = store.get(org, GRANT_PROVIDER)
    if row is not None:
        store.put(org, GRANT_PROVIDER, {**(row.tokens or {}), "revogada_em": _now().isoformat()})
    _ultimo_ok.pop(org, None)
    logger.info("julia: platform grant revoked org=%s", org)


# ── health: what the Agente page shows as the token's status ─────────────────
STATUS_NAO_CONFIGURADA = "nao_configurada"
STATUS_ATIVA = "ativa"
STATUS_COM_FALHA = "com_falha"
STATUS_REVOGADA = "revogada"
STATUS_EXPIRADA = "expirada"
MOTIVO_TOKEN_REJEITADO = "token_rejeitado"
MOTIVO_AGENTS_INDISPONIVEL = "agents_indisponivel"

#: A success is re-recorded at most this often (it is a DB write on the hot path of every agents call).
_OK_WRITE_INTERVAL_S = 300.0
_ultimo_ok: dict[str, float] = {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def motivo_da_falha(exc: BaseException) -> Optional[str]:
    """Map an agents-call exception to a health `motivo`, or None when the call proves the token WORKS
    (a domain answer such as `agent_not_found` / 409 / 422 means agents authenticated us)."""
    if isinstance(exc, AgentsTokenInvalid):
        return MOTIVO_TOKEN_REJEITADO
    if isinstance(exc, (AgentsTimeout, AgentsUpstreamError)):
        return MOTIVO_AGENTS_INDISPONIVEL
    return None


def mascarar_token(token: Optional[str]) -> Optional[str]:
    """First 4 + last 4 only (owner request). Too short to mask safely -> bullets. Never logged."""
    if not token:
        return None
    return f"{token[:4]}...{token[-4:]}" if len(token) > 8 else "••••"


def registrar_resultado(
    org_id: UUID | str, motivo_falha: Optional[str], *, store: Any = None, force: bool = False,
) -> None:
    """Record the outcome of ONE real agents call in the grant row (no row = nothing to record). Never raises."""
    org = str(org_id)
    try:
        if motivo_falha is None and not force:
            ultimo = _ultimo_ok.get(org)
            if ultimo is not None and time.monotonic() - ultimo < _OK_WRITE_INTERVAL_S:
                return
        store = store or _store()
        row = store.get(org, GRANT_PROVIDER)
        if row is None:
            return
        meta = dict(row.tokens or {})
        if meta.get("revogada_em"):
            return  # a revoked grant has no token to judge
        agora = _now().isoformat()
        if motivo_falha is None:
            meta["verificada_em"] = agora
            meta.pop("falha_motivo", None)
        else:
            meta["ultima_falha_em"] = agora
            meta["falha_motivo"] = motivo_falha
        store.put(org, GRANT_PROVIDER, meta)
        if motivo_falha is None:
            _ultimo_ok[org] = time.monotonic()
        else:
            _ultimo_ok.pop(org, None)
    except Exception as exc:  # health memory is best-effort: it must never break the call it observes
        logger.error("julia: could not record the agents health org=%s (%s)", org, type(exc).__name__)


def reset_health_throttle() -> None:
    _ultimo_ok.clear()


def _expirada(expires_at: Any) -> bool:
    if not expires_at:
        return False
    try:
        when = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
    except ValueError:
        logger.warning("julia: unparseable grant expires_at (ignored)")
        return False
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when <= _now()


def conexao_plataforma(org_id: UUID | str, store: Any = None) -> dict[str, Any]:
    """The read-only status the Agente page shows. The token itself never leaves: only `token_mascarado`.

    `status`: nao_configurada | ativa | com_falha | revogada | expirada. `conectada` is true while a usable grant
    is stored (ativa or com_falha). `motivo` names why (com_falha: token_rejeitado | agents_indisponivel).
    """
    out: dict[str, Any] = {
        "status": STATUS_NAO_CONFIGURADA, "conectada": False, "motivo": None, "token_prefix": None,
        "token_mascarado": None, "conectada_em": None, "agent_key": None, "verificada_em": None,
        "ultima_falha_em": None, "expires_at": None,
    }
    try:
        store = store or _store()
        row = store.get(str(org_id), GRANT_PROVIDER)
        token = api_keys_store.read_local_api_key(store, str(org_id), AGENTS_KEY_NAME)
    except Exception as exc:
        logger.error("julia: could not read the platform grant org=%s (%s)", org_id, type(exc).__name__)
        return out
    if row is None:
        return out
    meta = row.tokens or {}
    out.update(
        token_prefix=meta.get("token_prefix"), conectada_em=meta.get("conectada_em"), agent_key=meta.get("agent_key"),
        verificada_em=meta.get("verificada_em"), ultima_falha_em=meta.get("ultima_falha_em"),
        expires_at=meta.get("expires_at"),
    )
    if meta.get("revogada_em"):
        out["status"] = STATUS_REVOGADA
        return out
    valor = (token.tokens or {}).get("value") if token else None
    if not valor:
        return out  # grant row without a token (removed by hand): not configured
    out["token_mascarado"] = mascarar_token(valor)
    if _expirada(meta.get("expires_at")):
        out["status"] = STATUS_EXPIRADA
        return out
    out["conectada"] = True
    if meta.get("falha_motivo"):
        out.update(status=STATUS_COM_FALHA, motivo=meta["falha_motivo"])
    else:
        out["status"] = STATUS_ATIVA
    return out


class HealthRecordingAgentsClient:
    """Transparent proxy over a REAL `AgentsClient`: every awaited call records its outcome via `registrar_resultado`
    (token rejected / agents unavailable / ok), then returns or re-raises untouched."""

    def __init__(self, inner: Any, org_id: UUID | str, store: Any = None):
        self._inner, self._org, self._store_ref = inner, str(org_id), store

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._inner, name)
        if not inspect.iscoroutinefunction(attr):
            return attr

        async def call(*args: Any, **kwargs: Any) -> Any:
            try:
                result = await attr(*args, **kwargs)
            except Exception as exc:
                await run_blocking(registrar_resultado, self._org, motivo_da_falha(exc), store=self._store_ref)
                raise
            await run_blocking(registrar_resultado, self._org, None, store=self._store_ref)
            return result

        return call


def build_router(get_auth_context: Callable[..., Any]):
    """The seed receiver (`PUT/DELETE /api/platform/grants/agents`) wired to this sink."""
    return create_platform_grants_router(
        get_auth_context=get_auth_context, on_grant=on_grant, on_revoke=on_revoke, issuer="agents",
    )

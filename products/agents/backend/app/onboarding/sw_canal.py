"""The onboarding interviewer's channel to social-wiring: a service token that provisions itself (owner 2026-11-18).

No human ever creates, copies or pastes it. Same mechanism the platform already uses for its other service tokens
(``noctusai_lib.api.auth.session`` ``ProductTokenAdmin`` writing ``social_wiring.api_tokens``, secret kept encrypted in
``agents.app_integration_config`` -- the store the academia token lives in), with the registry (``SW_ONBOARDING_TOKEN``)
fixing scope, issuer and lifetime server-side, so no request can widen them:

  1. ``garantir``: reuse the stored token while it is valid with more than ``RENOVAR_ANTES`` left; otherwise (none yet,
     expiring, expired, revoked, deleted at the other end) MINT a new one -- scope ``social-wiring:onboarding-settings``,
     issuer ``noctus-platform``, ``TTL`` days -- and PROBE it against social-wiring's ``whoami`` BEFORE storing it, so a
     token that does not work is revoked and never replaces a working one; then store it, then revoke the old one.
     Idempotent: a valid stored token is never re-minted.
  2. Every provisioning, rotation, connection test and apply call is an append-only event (``sw_canal_eventos``).
  3. Failure is a NAMED state (``CanalErro.codigo``), never a silent fallback: the apply report carries it per item and
     the Studio card shows it.

The secret is only ever put in an ``Authorization`` header. It is never logged, never in an exception message, never in
a result, never in a URL; ``CanalStatus`` has no field that could carry it.

Seed IO shape for the HTTP edge: the ``transport`` seam (``httpx.MockTransport`` in tests); the token admin, the config
store and the event store are the seed/agents Protocols with their Fakes.

NOC-REMEDIATE[sw-canal-multiworker-mint]: two workers that find the token due at the same instant can each mint one; the
loser's token (onboarding scope only, 30 days) is orphaned until it expires. A process lock stops it within one worker;
closing it across workers needs an advisory lock in the store -- 2026-12-18.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Literal, Protocol
from uuid import UUID

import httpx

from noctusai_lib.api.auth.session import ApiTokenInfo, ProductTokenAdmin
from noctusai_lib.config.credentials import invalidate_credential_cache
from noctusai_lib.config.deploy_config import is_deploy_context
from noctusai_lib.security.app_config import AppConfigDecryptError

from app.credentials.prober import ProbeResult, classify_status
from app.credentials.registry import SW_ONBOARDING_TOKEN
from app.credentials.resolver import ConfigStoreHandle
from app.stores.sw_canal_eventos import EventoCanal, SwCanalEventStore

logger = logging.getLogger(__name__)

__all__ = [
    "CanalErro", "CanalStatus", "FakeSwCanal", "SwCanal", "SwCanalPort", "TTL", "RENOVAR_ANTES", "TesteConexao",
    "WHOAMI_PATH", "get_sw_canal",
]

TTL = timedelta(days=30)
#: A token with less than this left is replaced on its next use (rotation by use, no scheduler needed).
RENOVAR_ANTES = timedelta(days=7)
WHOAMI_PATH = "/api/julia/onboarding/whoami"
_TIMEOUT_SECONDS = 10.0

Estado = Literal["provisionado", "ausente", "expirado", "erro"]


class CanalErro(Exception):
    """A named, visible failure of the channel. ``codigo`` is stable (UI / apply report); ``mensagem`` is pt-BR and
    never carries a secret."""

    def __init__(self, codigo: str, mensagem: str) -> None:
        super().__init__(mensagem)
        self.codigo = codigo
        self.mensagem = mensagem


@dataclass(frozen=True)
class CanalStatus:
    estado: Estado
    escopo: str
    emissor: str
    expira_em: datetime | None = None
    dias_restantes: int | None = None
    ultima_chamada_ok: EventoCanal | None = None
    ultimo_erro: EventoCanal | None = None
    codigo: str | None = None
    mensagem: str | None = None


@dataclass(frozen=True)
class TesteConexao:
    ok: bool
    codigo: str | None
    mensagem: str


class SwCanalPort(Protocol):
    """What the settings client needs from the channel: a token to use now, and a place to report the outcome."""

    def token_para_uso(self) -> str:
        """A valid token (provisioning / rotating it when due). Raises :class:`CanalErro`."""
        ...

    def registrar_chamada(self, *, ok: bool, codigo: str | None, mensagem: str | None) -> None: ...


class FakeSwCanal:
    """In-memory port for tests: a fixed token (``None`` = not provisioned) and the calls reported."""

    def __init__(self, token: str | None = "noc_fake") -> None:
        self.token = token
        self.chamadas: list[tuple[bool, str | None]] = []

    def token_para_uso(self) -> str:
        if not self.token:
            raise CanalErro("canal_sw_nao_provisionado", "O canal da equipe com o social-wiring não está provisionado.")
        return self.token

    def registrar_chamada(self, *, ok: bool, codigo: str | None, mensagem: str | None) -> None:
        self.chamadas.append((ok, codigo))


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class _Vinculado:
    """The channel bound to who is acting (the org the token row belongs to, the staff user)."""

    def __init__(self, canal: "SwCanal", org_id: UUID, ator: UUID | None) -> None:
        self._canal, self._org_id, self._ator = canal, org_id, ator

    def token_para_uso(self) -> str:
        return self._canal.garantir(self._org_id, self._ator)

    def registrar_chamada(self, *, ok: bool, codigo: str | None, mensagem: str | None) -> None:
        self._canal.registrar_chamada(ok=ok, codigo=codigo, mensagem=mensagem, ator=self._ator)


class SwCanal:
    def __init__(
        self, *, handle: ConfigStoreHandle, token_admin: ProductTokenAdmin, eventos: SwCanalEventStore,
        base_url: Callable[[], str | None], clock: Callable[[], datetime] = _utcnow,
        transport: httpx.BaseTransport | None = None, timeout: float = _TIMEOUT_SECONDS,
    ) -> None:
        self._handle = handle
        self._admin = token_admin
        self._eventos = eventos
        self._base_url = base_url
        self._clock = clock
        self._transport = transport
        self._timeout = timeout
        self._lock = threading.Lock()
        self._spec = SW_ONBOARDING_TOKEN

    def como(self, org_id: UUID, ator: UUID | None) -> SwCanalPort:
        return _Vinculado(self, org_id, ator)

    # -- reads ---------------------------------------------------------------------------------------------------

    def _armazenado(self) -> str | None:
        if not self._handle.persistent and is_deploy_context():
            raise CanalErro(
                "armazenamento_indisponivel",
                f"Armazenamento de credenciais indisponível ({self._handle.reason}).",
            )
        try:
            return self._handle.store.get(self._spec.store_key) or None
        except (AppConfigDecryptError, ValueError) as exc:
            logger.error("agents.sw_canal.unreadable error=%s", type(exc).__name__)
            raise CanalErro(
                "armazenamento_ilegivel",
                "O valor armazenado está ilegível (ENCRYPTION_KEY trocada?); o canal vai gerar outro no próximo uso.",
            ) from exc

    def _linha(self, segredo: str) -> ApiTokenInfo | None:
        try:
            return self._admin.find_by_secret(self._spec.target_schema or "", segredo)
        except Exception as exc:
            logger.warning("agents.sw_canal.lookup_failed error=%s", type(exc).__name__)
            raise CanalErro("sw_indisponivel", "Não foi possível consultar o social-wiring.") from exc

    def status(self) -> CanalStatus:
        base: dict[str, Any] = dict(escopo=self._spec.scopes[0], emissor=self._spec.issuer)
        ok, erro = self._eventos.ultimo(ok=True), self._eventos.ultimo(ok=False)
        base.update(ultima_chamada_ok=ok, ultimo_erro=erro)
        try:
            segredo = self._armazenado()
            if not segredo:
                return CanalStatus(estado="ausente", **base)
            info = self._linha(segredo)
        except CanalErro as exc:
            return CanalStatus(estado="erro", codigo=exc.codigo, mensagem=exc.mensagem, **base)
        if info is None:
            return CanalStatus(
                estado="erro", codigo="token_nao_encontrado",
                mensagem="O token armazenado não existe mais no social-wiring; será gerado outro no próximo uso.", **base)
        if info.revoked_at is not None:
            return CanalStatus(
                estado="erro", codigo="token_revogado", expira_em=info.expires_at,
                mensagem="O token foi revogado; será gerado outro no próximo uso.", **base)
        agora = self._clock()
        dias = (info.expires_at - agora).days if info.expires_at else None
        if info.expires_at is not None and info.expires_at <= agora:
            return CanalStatus(
                estado="expirado", expira_em=info.expires_at, dias_restantes=0, codigo="token_expirado",
                mensagem="O token expirou; será renovado no próximo uso.", **base)
        return CanalStatus(estado="provisionado", expira_em=info.expires_at, dias_restantes=dias, **base)

    # -- provisioning --------------------------------------------------------------------------------------------

    def _registrar(self, evento: str, **campos: Any) -> None:
        try:
            self._eventos.registrar(evento, **campos)
        except Exception as exc:
            # The channel's own work stands; the measurement gap is loud, never silent.
            logger.error("agents.sw_canal.event_write_failed evento=%s error=%s", evento, type(exc).__name__)

    def _whoami(self, segredo: str) -> ProbeResult:
        base = (self._base_url() or "").rstrip("/")
        if not base:
            return ProbeResult.of("error", None, "O endereço do social-wiring não está configurado.")
        try:
            with httpx.Client(timeout=self._timeout, transport=self._transport) as http:
                resp = http.get(f"{base}{WHOAMI_PATH}", headers={"Authorization": f"Bearer {segredo}"})
        except httpx.HTTPError as exc:
            logger.warning("agents.sw_canal.whoami_unreachable error=%s", type(exc).__name__)
            return ProbeResult.of("unreachable")
        resultado = classify_status(resp.status_code, not_found_is_ok=False)
        if resultado.ok:
            try:
                corpo = resp.json().get("data") or {}
            except (ValueError, AttributeError):
                corpo = {}
            if corpo.get("ok") is not True or corpo.get("escopo") != self._spec.scopes[0]:
                return ProbeResult.of("error", resp.status_code)
        return resultado

    def _revogar(self, info: ApiTokenInfo, motivo: str) -> bool:
        try:
            if self._admin.revoke(self._spec.target_schema or "", info.id, org_id=info.org_id):
                return True
        except Exception as exc:
            logger.error("agents.sw_canal.revoke_failed token_id=%s motivo=%s error=%s", info.id, motivo, type(exc).__name__)
            return False
        logger.error("agents.sw_canal.revoke_noop token_id=%s motivo=%s", info.id, motivo)
        return False

    def garantir(self, org_id: UUID, ator: UUID | None) -> str:
        """The stored token if it is valid for longer than ``RENOVAR_ANTES``; otherwise a freshly minted, probed and
        stored one. Idempotent. Raises :class:`CanalErro` (named, pt-BR) and records the failure."""
        with self._lock:
            try:
                segredo = self._armazenado()
            except CanalErro as exc:
                if exc.codigo != "armazenamento_ilegivel":
                    self._registrar("sw_canal_provisionamento_falhou", ok=False, codigo=exc.codigo, mensagem=exc.mensagem, ator=ator)
                    raise
                segredo = None  # unreadable ciphertext: replace it (the old token, unreachable, expires on its own)
            antigo: ApiTokenInfo | None = None
            if segredo:
                try:
                    antigo = self._linha(segredo)
                except CanalErro as exc:
                    self._registrar("sw_canal_provisionamento_falhou", ok=False, codigo=exc.codigo, mensagem=exc.mensagem, ator=ator)
                    raise  # without the old row we cannot tell valid from gone: no blind re-mint next to a live token
                agora = self._clock()
                if (
                    antigo is not None and antigo.revoked_at is None
                    and (antigo.expires_at is None or antigo.expires_at - agora > RENOVAR_ANTES)
                ):
                    return segredo
            return self._emitir(org_id, ator, antigo)

    def _emitir(self, org_id: UUID, ator: UUID | None, antigo: ApiTokenInfo | None) -> str:
        spec = self._spec
        expira = self._clock() + TTL
        try:
            novo = self._admin.mint(
                spec.target_schema or "", org_id=org_id, label=spec.token_label or spec.label,
                scopes=list(spec.scopes), expires_at=expira, issuer=spec.issuer, minted_by=ator,
            )
        except Exception as exc:
            logger.error("agents.sw_canal.mint_failed error=%s", type(exc).__name__)
            self._registrar("sw_canal_provisionamento_falhou", ok=False, codigo="emissao_falhou",
                            mensagem="Falha ao emitir o token no social-wiring.", ator=ator)
            raise CanalErro("emissao_falhou", "Falha ao emitir o token no social-wiring.") from exc
        prova = self._whoami(novo.secret)
        if not prova.ok:
            self._revogar(novo.info, "novo_token_reprovado_no_teste")
            codigo = f"sw_{prova.status}"
            mensagem = f"O token novo não passou no teste: {prova.detail}"
            self._registrar("sw_canal_provisionamento_falhou", ok=False, codigo=codigo, mensagem=mensagem, ator=ator)
            raise CanalErro(codigo, mensagem)
        try:
            self._handle.store.put(spec.store_key, novo.secret)
        except Exception as exc:
            logger.error("agents.sw_canal.store_failed error=%s", type(exc).__name__)
            self._revogar(novo.info, "nao_foi_possivel_armazenar")
            self._registrar("sw_canal_provisionamento_falhou", ok=False, codigo="armazenamento_falhou",
                            mensagem="Não foi possível guardar o token.", ator=ator)
            raise CanalErro("armazenamento_falhou", "Não foi possível guardar o token.") from exc
        invalidate_credential_cache()
        renovado = antigo is not None
        if antigo is not None and antigo.revoked_at is None and not self._revogar(antigo, "substituido"):
            logger.error("agents.sw_canal.old_token_left_live token_id=%s", antigo.id)
        self._registrar(
            "sw_canal_renovado" if renovado else "sw_canal_provisionado", ok=True, ator=ator,
            token_id=novo.info.id, expira_em=expira)
        logger.info("agents.sw_canal.%s token_id=%s", "renewed" if renovado else "provisioned", novo.info.id)
        return novo.secret

    # -- use + test ----------------------------------------------------------------------------------------------

    def registrar_chamada(self, *, ok: bool, codigo: str | None, mensagem: str | None, ator: UUID | None) -> None:
        self._registrar("sw_canal_chamada_concluida", ok=ok, codigo=codigo, mensagem=mensagem, ator=ator)

    def testar(self, org_id: UUID, ator: UUID | None) -> tuple[TesteConexao, CanalStatus]:
        """Harmless read-only authenticated call (``whoami``) with the channel's own token, provisioning it first if it
        is not there. Records ``sw_canal_conexao_testada`` either way."""
        try:
            segredo = self.garantir(org_id, ator)
        except CanalErro as exc:
            self._registrar("sw_canal_conexao_testada", ok=False, codigo=exc.codigo, mensagem=exc.mensagem, ator=ator)
            return TesteConexao(False, exc.codigo, exc.mensagem), self.status()
        prova = self._whoami(segredo)
        if prova.ok:
            self._registrar("sw_canal_conexao_testada", ok=True, ator=ator)
            return TesteConexao(True, None, "Conexão com o Social Wiring funcionando."), self.status()
        codigo = f"sw_{prova.status}"
        self._registrar("sw_canal_conexao_testada", ok=False, codigo=codigo, mensagem=prova.detail, ator=ator)
        return TesteConexao(False, codigo, prova.detail), self.status()


def get_sw_canal(settings: Any) -> SwCanal:
    """Production composition: the encrypted config store the other platform credentials use, the service-role token
    admin pinned to a STRICT allow-list of exactly this scope, the event store, and social-wiring's URL."""
    from noctusai_lib.api.auth.session import TokenScopeAllowList, make_product_token_admin
    from noctusai_lib.config.product_urls import resolve_product_url

    from app.credentials.resolver import get_config_store_handle
    from app.stores.sw_canal_eventos import get_sw_canal_event_store

    admin_client = None
    if getattr(settings, "supabase_service_role_key", ""):
        from app.dependencies import get_admin_client

        admin_client = get_admin_client()

    def base_url() -> str | None:
        try:
            return resolve_product_url("social-wiring")
        except ValueError:
            return None

    return SwCanal(
        handle=get_config_store_handle(settings),
        token_admin=make_product_token_admin(admin_client, scope_allow_list=TokenScopeAllowList(SW_ONBOARDING_TOKEN.scopes)),
        eventos=get_sw_canal_event_store(settings), base_url=base_url,
    )

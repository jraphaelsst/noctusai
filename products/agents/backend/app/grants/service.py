"""Platform grant orchestration (Julia-line CONTRACT D2 / D4).

create  = channel token (agents.api_tokens, target org) + tools token (<product schema>.api_tokens, secret kept in
          agents' per-org encrypted store) + one-shot delivery token (5 min) -> ``GrantDelivery.deliver`` ->
          revoke the delivery token.
rotate  = the same mint+deliver for a NEW pair, THEN revoke the old pair (overlapping: the product never sees a gap).
revoke  = revoke both tokens, drop the stored tools secret, best-effort ``GrantDelivery.revoke``.

Every failure revokes every token minted in that attempt, restores the tools secret, records ``last_error`` (an error
CLASS and stage, never a secret) and raises a :class:`GrantError` -- nothing is silent. Secrets exist only inside one
call: they are handed to the store / the delivery and never logged, returned or persisted in the ledger.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from uuid import UUID

from noctusai_lib.api.auth.grants import GrantDelivery, GrantDeliveryError, GrantPayload
from noctusai_lib.api.auth.session import GRANT_RECEIVE_SCOPE, MintedApiToken, ProductTokenAdmin
from noctusai_lib.security.api_keys import (
    EncryptionNotConfigured,
    delete_api_key,
    put_api_key,
    read_local_api_key,
)

from app.channels.token_audit import TokenAudit
from app.grants.orgs import OrgDirectory
from app.grants.registry import GRANT_CHANNEL_SCOPES, GRANT_ISSUER, GrantProduct, get_grant_product
from app.grants.store import Grant, GrantExists, GrantStore
from app.stores.errors import NotFound

logger = logging.getLogger(__name__)

__all__ = ["DELIVERY_TOKEN_TTL", "GrantError", "GrantService"]

#: Lifetime of the one-shot delivery token (CONTRACT D2 step 3). It is revoked right after the call anyway.
DELIVERY_TOKEN_TTL = timedelta(minutes=5)
_AGENTS_SCHEMA = "agents"


class GrantError(Exception):
    """A grant operation failed. ``status`` / ``code`` / ``message`` map 1:1 onto the HTTP error."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


@dataclass
class _Minted:
    schema: str
    token_id: UUID
    what: str  # channel | tools | delivery
    agent_key: str | None = None


class _Stage(Exception):
    """Internal: a failure tagged with the stage it happened in (the cause is chained)."""

    def __init__(self, stage: str) -> None:
        super().__init__(stage)
        self.stage = stage


_STAGE_CODES = {
    "mint_channel": ("mint_failed", "Falha ao emitir o token do canal."),
    "audit_channel": ("audit_failed", "Falha ao registrar a emissão do token."),
    "mint_tools": ("mint_failed", "Falha ao emitir o token de ferramentas."),
    "store_tools": ("tools_store_failed", "Falha ao guardar o token de ferramentas."),
    "mint_delivery": ("mint_failed", "Falha ao emitir o token de entrega."),
    "deliver": ("delivery_failed", "O produto não aceitou a entrega da credencial."),
}


def _error_text(stage: str, exc: BaseException | None) -> str:
    """``stage: ExceptionClass[ (HTTP n)]`` -- a class name and a status, never a message (messages may echo input)."""
    cause = exc.__cause__ if isinstance(exc, _Stage) and exc.__cause__ else exc
    out = f"{stage}: {type(cause).__name__}" if cause is not None else stage
    code = getattr(cause, "status_code", None)
    if code:
        out += f" (HTTP {code})"
    return out


class GrantService:
    def __init__(
        self,
        *,
        grants: GrantStore,
        orgs: OrgDirectory,
        token_admin: ProductTokenAdmin,
        delivery: GrantDelivery,
        tools_store_factory: Callable[[], Any],
        studio_store: Any,
        audit: TokenAudit,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._grants = grants
        self._orgs = orgs
        self._admin = token_admin
        self._delivery = delivery
        self._tools_store_factory = tools_store_factory
        self._studio = studio_store
        self._audit = audit
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    # ── reads ────────────────────────────────────────────────────────────────
    def list(self) -> list[tuple[Grant, str | None]]:
        """Every grant, newest first, with its org's name (looked up once per distinct org)."""
        grants = self._grants.list()
        names = {org_id: self.org_name(org_id) for org_id in {g.org_id for g in grants}}
        return [(g, names[g.org_id]) for g in grants]

    def channel_prefixes(self, grants: list[Grant]) -> dict[UUID, str]:
        """``channel_token_id`` -> the token's stored prefix (``agents.api_tokens.token_prefix``), one lookup per
        distinct org. The prefix is all agents can honestly show (only the hash of the secret is stored); a failed
        lookup just leaves the prefix out."""
        wanted = {g.channel_token_id for g in grants if g.channel_token_id}
        found: dict[UUID, str] = {}
        if not wanted:
            return found
        for org_id in {g.org_id for g in grants if g.channel_token_id}:
            try:
                infos = self._admin.list_tokens("agents", org_id=org_id)
            except Exception as exc:
                logger.warning("agents.grants.prefix_lookup_failed org_id=%s error=%s", org_id, type(exc).__name__)
                continue
            found.update({i.id: i.prefix for i in infos if i.id in wanted and i.prefix})
        return found

    def org_name(self, org_id: UUID) -> str | None:
        try:
            ref = self._orgs.get(org_id)
        except Exception as exc:
            logger.warning("agents.grants.org_lookup_failed org_id=%s error=%s", org_id, type(exc).__name__)
            return None
        return ref.nome if ref else None

    # ── create ───────────────────────────────────────────────────────────────
    def create(self, *, agent_key: str, product: str, org_id: UUID, actor: UUID | None, expires_at: datetime | None = None) -> Grant:
        spec = self._spec(product, agent_key)
        if self._orgs.get(org_id) is None:
            raise GrantError(404, "org_not_found", "Organização não encontrada.")
        agent = self._agent(org_id, agent_key)
        prior = self._read_tools_secret(spec, org_id)
        try:
            grant = self._grants.begin(
                org_id=org_id, agent_id=agent.id, agent_key=agent_key, product=product,
                expires_at=expires_at, created_by=actor,
            )
        except GrantExists as exc:
            raise GrantError(409, "grant_exists", "Já existe um grant ativo para este agente, produto e organização.") from exc

        minted: list[_Minted] = []
        try:
            channel, tools = self._issue_and_deliver(
                spec=spec, grant=grant, agent_id=agent.id, actor=actor, expires_at=expires_at, minted=minted,
            )
        except _Stage as stage:
            self._abort(grant, spec, minted, stage, prior=prior)
        return self._grants.activate(grant.id, channel_token_id=channel.info.id, product_token_id=tools.info.id if tools else None)

    # ── rotate ───────────────────────────────────────────────────────────────
    def rotate(self, grant_id: UUID, *, actor: UUID | None) -> Grant:
        grant = self._active(grant_id)
        spec = self._spec(grant.product, grant.agent_key)
        old_channel, old_tools = grant.channel_token_id, grant.product_token_id
        minted: list[_Minted] = []
        prior = self._read_tools_secret(spec, grant.org_id)
        try:
            channel, tools = self._issue_and_deliver(
                spec=spec, grant=grant, agent_id=grant.agent_id, actor=actor, expires_at=grant.expires_at, minted=minted,
            )
        except _Stage as stage:
            # The OLD pair is untouched and still live: keep the grant ``ativo`` and only record why.
            self._abort(grant, spec, minted, stage, prior=prior, keep_status=True)
        updated = self._grants.activate(grant.id, channel_token_id=channel.info.id, product_token_id=tools.info.id if tools else None)
        failed = self._revoke_pair(grant.org_id, spec, old_channel, old_tools, actor=actor, agent_key=grant.agent_key)
        if failed:
            logger.error("agents.grants.rotate_old_pair_not_revoked grant_id=%s tokens=%s", grant.id, failed)
            updated = self._grants.note_error(grant.id, f"rotação feita; tokens antigos não revogados: {len(failed)}")
        return updated

    # ── revoke ───────────────────────────────────────────────────────────────
    def revoke(self, grant_id: UUID, *, actor: UUID | None) -> Grant:
        grant = self._get(grant_id)
        if grant.status == "revogado":
            return grant
        if grant.status == "pendente":
            raise GrantError(409, "grant_in_progress", "O grant está sendo criado; tente novamente em instantes.")
        spec = self._spec(grant.product, grant.agent_key)
        failed = self._revoke_pair(grant.org_id, spec, grant.channel_token_id, grant.product_token_id,
                                   actor=actor, agent_key=grant.agent_key)
        if failed:
            logger.error("agents.grants.revoke_incomplete grant_id=%s tokens=%s", grant.id, failed)
            self._grants.note_error(grant.id, f"revogação incompleta: {len(failed)} token(s) não revogados")
            raise GrantError(502, "revoke_failed", "Falha ao revogar os tokens do grant; tente novamente.")
        self._drop_tools_secret(spec, grant.org_id)
        updated = self._grants.mark_revoked(grant.id, revoked_by=actor)
        self._notify_product_revoked(spec, grant)
        return updated

    # ── internals ────────────────────────────────────────────────────────────
    def _spec(self, product: str, agent_key: str) -> GrantProduct:
        spec = get_grant_product(product)
        if spec is None:
            raise GrantError(422, "product_unknown", "Produto desconhecido.")
        if agent_key not in spec.agent_keys:
            raise GrantError(422, "agent_not_grantable", "Este agente não pode ser concedido a este produto.")
        return spec

    def _get(self, grant_id: UUID) -> Grant:
        try:
            return self._grants.get(grant_id)
        except NotFound as exc:
            raise GrantError(404, "grant_not_found", "Grant não encontrado.") from exc

    def _active(self, grant_id: UUID) -> Grant:
        grant = self._get(grant_id)
        spec = get_grant_product(grant.product)
        needs_tools = spec is None or spec.has_tools  # an unknown product keeps the strict (tools-required) reading
        if grant.status != "ativo" or grant.channel_token_id is None or (needs_tools and grant.product_token_id is None):
            raise GrantError(409, "grant_not_active", "O grant não está ativo.")
        return grant

    def _agent(self, org_id: UUID, agent_key: str):
        """The org's instance of the platform agent (created on first use), the principal the channel token binds to."""
        from app.routers.channels_router import CHANNEL_STUDIO_RUNTIME
        from app.studio.plataforma import ensure_instancia

        try:
            ensure_instancia(org_id, agent_key, studio_store=self._studio)
            agent = self._studio.get_agent(org_id, agent_key)
        except NotFound as exc:
            raise GrantError(404, "agent_not_found", "Agente não encontrado.") from exc
        if agent.definition_mode != "studio" or agent.runtime != CHANNEL_STUDIO_RUNTIME:
            raise GrantError(404, "agent_not_found", "Agente não encontrado.")
        return agent

    def _mint(self, schema: str, minted: list[_Minted], what: str, stage: str, *, agent_key: str | None = None, **kw: Any) -> MintedApiToken:
        try:
            token = self._admin.mint(schema, **kw)
        except Exception as exc:
            raise _Stage(stage) from exc
        minted.append(_Minted(schema, token.info.id, what, agent_key))
        return token

    def _issue_and_deliver(
        self, *, spec: GrantProduct, grant: Grant, agent_id: UUID, actor: UUID | None, expires_at: datetime | None,
        minted: list[_Minted],
    ) -> tuple[MintedApiToken, MintedApiToken | None]:
        """D2 steps 1-5 for ONE pair. Every minted id lands in ``minted`` as soon as it exists (the caller's
        rollback list). Returns ``(channel, tools)`` (``tools`` is ``None`` for a product without a tools token); raises :class:`_Stage`."""
        org_id = grant.org_id
        label = f"grant {spec.slug} · {grant.agent_key}"
        channel = self._mint(
            _AGENTS_SCHEMA, minted, "channel", "mint_channel", agent_key=grant.agent_key,
            org_id=org_id, label=f"canal {spec.channel_issuer} · {grant.agent_key}: {label}",
            scopes=list(GRANT_CHANNEL_SCOPES), expires_at=expires_at, principal_agent_id=agent_id,
            issuer=spec.channel_issuer, minted_by=actor,
        )
        try:
            self._audit.record(api_token_id=channel.info.id, org_id=org_id, action="MINT",
                               agent_key=grant.agent_key, actor_user_id=actor, status=201)
        except Exception as exc:
            raise _Stage("audit_channel") from exc
        tools: MintedApiToken | None = None
        if spec.has_tools:
            tools = self._mint(
                spec.schema, minted, "tools", "mint_tools",
                org_id=org_id, label=spec.tools_label, scopes=[spec.tools_scope], expires_at=expires_at,
                issuer=GRANT_ISSUER, minted_by=actor,
            )
            try:
                put_api_key(self._tools_store(), str(org_id), spec.tools_secret_name, tools.secret)
            except Exception as exc:
                raise _Stage("store_tools") from exc
        delivery_token = self._mint(
            spec.schema, minted, "delivery", "mint_delivery",
            org_id=org_id, label=f"entrega de grant · {grant.agent_key}", scopes=[GRANT_RECEIVE_SCOPE],
            expires_at=self._clock() + DELIVERY_TOKEN_TTL, issuer=GRANT_ISSUER, minted_by=actor,
        )
        payload = GrantPayload(
            credential=channel.secret, agent_id=str(agent_id),
            metadata={
                "grant_id": str(grant.id), "agent_key": grant.agent_key, "token_prefix": channel.info.prefix,
                "scopes": list(GRANT_CHANNEL_SCOPES),
                "expires_at": expires_at.isoformat() if expires_at else None,
            },
        )
        try:
            self._delivery.deliver(spec.slug, GRANT_ISSUER, payload, delivery_token=delivery_token.secret)
        except Exception as exc:
            raise _Stage("deliver") from exc
        # One-shot: the delivery token is spent. A failed revoke is bounded by its 5-minute expiry -- logged loudly.
        try:
            if not self._admin.revoke(spec.schema, delivery_token.info.id, org_id=org_id):
                raise RuntimeError("delivery token not found")
            minted[:] = [m for m in minted if m.token_id != delivery_token.info.id]
        except Exception as exc:
            logger.warning("agents.grants.delivery_token_not_revoked grant_id=%s token_id=%s error=%s (expires in %s)",
                           grant.id, delivery_token.info.id, type(exc).__name__, DELIVERY_TOKEN_TTL)
        return channel, tools

    #: Stages at/after which the stored tools secret may already be overwritten.
    _TOOLS_SECRET_STAGES = ("store_tools", "mint_delivery", "deliver")

    def _abort(
        self, grant: Grant, spec: GrantProduct, minted: list[_Minted], stage: _Stage, *, prior: str | None,
        keep_status: bool = False,
    ) -> None:
        """Undo one failed attempt and raise. Revokes everything minted, restores the stored tools secret."""
        failed = [m for m in minted if not self._revoke_one(m, grant.org_id, actor=None, audit=False)]
        if stage.stage in self._TOOLS_SECRET_STAGES:
            self._restore_tools_secret(spec, grant.org_id, prior)
        error = _error_text(stage.stage, stage)
        if failed:
            error += f"; rollback incompleto ({len(failed)} token(s))"
            logger.error("agents.grants.rollback_incomplete grant_id=%s tokens=%s", grant.id,
                         [(m.what, str(m.token_id)) for m in failed])
        logger.error("agents.grants.attempt_failed grant_id=%s org_id=%s product=%s stage=%s error=%s",
                     grant.id, grant.org_id, grant.product, stage.stage, error)
        if keep_status:
            self._grants.note_error(grant.id, error)
        else:
            self._grants.mark_failed(grant.id, error)
        code, message = _STAGE_CODES.get(stage.stage, ("grant_failed", "Falha ao concluir o grant."))
        raise GrantError(502, code, message) from stage

    def _revoke_one(self, m: _Minted, org_id: UUID, *, actor: UUID | None, audit: bool = True) -> bool:
        """Revoke one token. ``True`` unless the store RAISED (a row already revoked / gone is the state we want)."""
        try:
            self._admin.revoke(m.schema, m.token_id, org_id=org_id)
        except Exception as exc:
            logger.error("agents.grants.revoke_failed token_id=%s what=%s error=%s", m.token_id, m.what, type(exc).__name__)
            return False
        if audit and m.what == "channel" and m.agent_key:
            try:
                self._audit.record(api_token_id=m.token_id, org_id=org_id, action="REVOKE",
                                   agent_key=m.agent_key, actor_user_id=actor, status=204)
            except Exception as exc:
                logger.error("agents.grants.revoke_audit_failed token_id=%s error=%s", m.token_id, type(exc).__name__)
        return True

    def _revoke_pair(
        self, org_id: UUID, spec: GrantProduct, channel_id: UUID | None, tools_id: UUID | None, *,
        actor: UUID | None, agent_key: str,
    ) -> list[UUID]:
        """Revoke a grant's two tokens; returns the ids that could NOT be revoked."""
        pair = [
            _Minted(_AGENTS_SCHEMA, channel_id, "channel", agent_key) if channel_id else None,
            _Minted(spec.schema, tools_id, "tools") if tools_id else None,
        ]
        return [m.token_id for m in pair if m and not self._revoke_one(m, org_id, actor=actor)]

    def _notify_product_revoked(self, spec: GrantProduct, grant: Grant) -> None:
        """Best-effort DELETE on the product (it sees 401 once its credential is revoked anyway). Needs its own
        one-shot delivery token; any failure here is logged, never raised."""
        minted: list[_Minted] = []
        try:
            token = self._mint(
                spec.schema, minted, "delivery", "mint_delivery",
                org_id=grant.org_id, label=f"revogação de grant · {grant.agent_key}", scopes=[GRANT_RECEIVE_SCOPE],
                expires_at=self._clock() + DELIVERY_TOKEN_TTL, issuer=GRANT_ISSUER,
            )
            if not self._delivery.revoke(spec.slug, GRANT_ISSUER, delivery_token=token.secret):
                logger.warning("agents.grants.product_revoke_not_acknowledged grant_id=%s product=%s", grant.id, spec.slug)
        except Exception as exc:
            logger.warning("agents.grants.product_revoke_failed grant_id=%s product=%s error=%s",
                           grant.id, spec.slug, type(exc).__name__)
        finally:
            for m in minted:
                self._revoke_one(m, grant.org_id, actor=None, audit=False)

    # ── the per-org tools secret (agents' encrypted store) ──────────────────
    def _tools_store(self) -> Any:
        try:
            return self._tools_store_factory()
        except EncryptionNotConfigured as exc:
            raise GrantError(503, "encryption_not_configured", "Armazenamento seguro indisponível.") from exc

    def _read_tools_secret(self, spec: GrantProduct, org_id: UUID) -> str | None:
        """The org's current stored tools secret (so a failed attempt can put it back)."""
        if not spec.has_tools:
            return None
        store = self._tools_store()
        try:
            stored = read_local_api_key(store, str(org_id), spec.tools_secret_name)
        except Exception as exc:
            logger.error("agents.grants.tools_secret_unreadable org_id=%s error=%s", org_id, type(exc).__name__)
            raise GrantError(503, "tools_store_unavailable", "Armazenamento seguro indisponível.") from exc
        return (stored.tokens or {}).get("value") if stored else None

    def _restore_tools_secret(self, spec: GrantProduct, org_id: UUID, prior: str | None) -> None:
        if not spec.has_tools:
            return
        try:
            if prior:
                put_api_key(self._tools_store(), str(org_id), spec.tools_secret_name, prior)
            else:
                delete_api_key(self._tools_store(), str(org_id), spec.tools_secret_name)
        except Exception as exc:
            logger.error("agents.grants.tools_secret_restore_failed org_id=%s error=%s", org_id, type(exc).__name__)

    def _drop_tools_secret(self, spec: GrantProduct, org_id: UUID) -> None:
        if not spec.has_tools:
            return
        try:
            delete_api_key(self._tools_store(), str(org_id), spec.tools_secret_name)
        except Exception as exc:
            logger.error("agents.grants.tools_secret_delete_failed org_id=%s error=%s", org_id, type(exc).__name__)

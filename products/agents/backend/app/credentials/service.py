"""`CredentialService` — everything the "Credenciais e integrações" page does.

Invariant: no method returns, logs or raises with a secret value. Status
carries a display ``prefix`` (``pk_`` tokens: the seed's 11-char
``token_prefix``; the Anthropic key: its non-secret ``sk-ant-apiNN``
family marker) or a digest ``fingerprint`` (ring keys) — never more.

Renewal ("Renovar", product tokens) — ordering is the safety property:
  1. look up the CURRENT token's row in the target product (by hash);
  2. mint a new token there (same org, registry scopes, Julia principal,
     issuer ``agents``, 90 days) via the seed ``ProductTokenAdmin``;
  3. probe the NEW token live — on failure revoke it and stop (the old one
     is untouched and still in use);
  4. store the new token (the runtime picks it up on its next use);
  5. only then revoke the old token. A failed revoke is reported as a
     warning (the new token is already live), never silently dropped.
Why a service-side insert and not a target-product route: see
`noctusai_lib.api.auth.session.token_admin`'s module docstring.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Literal
from uuid import UUID

from noctusai_lib.api.auth.session import ApiTokenInfo, ProductTokenAdmin
from noctusai_lib.config.deploy_config import is_deploy_context
from noctusai_lib.security.app_config import AppConfigDecryptError
from noctusai_lib.security.key_ring import KeyRing, generate_ring_secret

from app.credentials.prober import CredentialProber, ProbeResult
from app.credentials.registry import (
    APPROVAL_RING,
    CREDENTIALS,
    ISSUER,
    JULIA_AGENT_ID,
    TOKEN_TTL_DAYS,
    CredentialSpec,
    get_spec,
)
from app.credentials.resolver import ConfigStoreHandle, CredentialResolver

logger = logging.getLogger(__name__)

__all__ = [
    "CredentialError",
    "CredentialService",
    "CredentialStatus",
    "ExpiryAlert",
    "RenewOutcome",
    "RingKeyStatus",
]

Severity = Literal["info", "warning", "critical"]


class CredentialError(Exception):
    """A refusal the route maps 1:1 to an HTTP status + ``code``."""

    def __init__(self, http_status: int, code: str, detail: str) -> None:
        super().__init__(detail)
        self.http_status = http_status
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class RingKeyStatus:
    fingerprint: str
    active_from: datetime
    retire_at: datetime | None
    signing: bool
    state: Literal["staged", "active", "retiring", "retired"]


@dataclass(frozen=True)
class CredentialStatus:
    name: str
    label: str
    kind: str
    env_var: str
    configured: bool
    source: str | None  # "db" | "env" | None
    prefix: str | None = None
    fingerprint: str | None = None
    value: str | None = None  # non-secret config only (julia_agent_id)
    expires_at: datetime | None = None
    days_left: int | None = None
    last_used_at: datetime | None = None
    revoked: bool = False
    scopes: tuple[str, ...] = ()
    renewable: bool = False
    probeable: bool = False
    writable: bool = True
    ring: tuple[RingKeyStatus, ...] = ()
    warnings: tuple[str, ...] = ()
    severity: Severity = "info"


@dataclass(frozen=True)
class RenewOutcome:
    status: CredentialStatus
    warnings: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ExpiryAlert:
    name: str
    label: str
    expires_at: datetime | None
    days_left: int | None
    reason: Literal["expiring", "expired", "revoked"]


def _anthropic_prefix(value: str) -> str:
    # `sk-ant-api03-…` → `sk-ant-api03`: the key family, zero secret bits.
    parts = value.split("-")
    return "-".join(parts[:3]) if len(parts) >= 4 and value.startswith("sk-") else value[:3]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CredentialService:
    def __init__(
        self,
        *,
        handle: ConfigStoreHandle,
        settings: Any,
        token_admin: ProductTokenAdmin,
        prober: CredentialProber,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._handle = handle
        self._settings = settings
        self._admin = token_admin
        self._prober = prober
        self._clock = clock
        self._resolver = CredentialResolver(handle.store, settings)

    @property
    def resolver(self) -> CredentialResolver:
        return self._resolver

    # ── lookup helpers ─────────────────────────────────────────────────

    def spec(self, name: str) -> CredentialSpec:
        spec = get_spec(name)
        if spec is None:
            raise CredentialError(404, "not_found", "Credencial desconhecida.")
        return spec

    def _warning_days(self) -> int:
        return int(getattr(self._settings, "credential_expiry_warning_days", 30) or 30)

    def _require_writable(self) -> None:
        if not self._handle.persistent and is_deploy_context():
            raise CredentialError(
                503,
                "store_unavailable",
                f"Armazenamento de credenciais indisponível ({self._handle.reason}).",
            )

    def _find_token(self, spec: CredentialSpec, secret: str) -> tuple[ApiTokenInfo | None, str | None]:
        try:
            return self._admin.find_by_secret(spec.target_schema or "", secret), None
        except Exception as exc:  # the status page must render even if the target is down
            logger.warning(
                "agents.credential_lookup_failed credential=%s error=%s", spec.name, type(exc).__name__
            )
            return None, f"Não foi possível ler o token em {spec.target_product}."

    # ── status ─────────────────────────────────────────────────────────

    def list_status(self) -> list[CredentialStatus]:
        return [self.status(spec.name) for spec in CREDENTIALS]

    def status(self, name: str) -> CredentialStatus:
        spec = self.spec(name)
        base: dict[str, Any] = dict(
            name=spec.name,
            label=spec.label,
            kind=spec.kind,
            env_var=spec.env_var,
            renewable=spec.renewable,
            probeable=spec.probeable,
            writable=self._handle.persistent or not is_deploy_context(),
        )
        try:
            if spec.kind == "key_ring":
                return self._ring_status(spec, base)
            value, source = self._resolver.resolve(spec)
        except (AppConfigDecryptError, ValueError) as exc:
            logger.error("agents.credential_unreadable credential=%s error=%s", spec.name, type(exc).__name__)
            return CredentialStatus(
                **base, configured=False, source="db",
                warnings=("Valor armazenado ilegível (ENCRYPTION_KEY trocada?). Defina-o novamente.",),
                severity="critical",
            )
        if not value:
            return CredentialStatus(
                **base, configured=False, source=None,
                warnings=("Não configurada.",), severity="critical",
            )
        if spec.kind == "config":
            return CredentialStatus(**base, configured=True, source=source, value=value)
        if spec.kind == "api_key":
            return CredentialStatus(**base, configured=True, source=source, prefix=_anthropic_prefix(value))
        return self._token_status(spec, base, value, source)

    def _token_status(
        self, spec: CredentialSpec, base: dict[str, Any], value: str, source: str | None
    ) -> CredentialStatus:
        warnings: list[str] = []
        severity: Severity = "info"
        info, lookup_warning = self._find_token(spec, value)
        if lookup_warning:
            warnings.append(lookup_warning)
            severity = "warning"
        prefix = value[:11]
        if info is None:
            if lookup_warning is None:
                warnings.append(f"Token não encontrado em {spec.target_product} (apagado ou de outro ambiente).")
                severity = "critical"
            return CredentialStatus(
                **base, configured=True, source=source, prefix=prefix,
                warnings=tuple(warnings), severity=severity,
            )
        now = self._clock()
        days_left = None
        if info.expires_at is not None:
            days_left = (info.expires_at - now).days
            if info.expires_at <= now:
                warnings.append("Token expirado — renove.")
                severity = "critical"
            elif days_left <= self._warning_days():
                warnings.append(f"Expira em {days_left} dia(s) — renove.")
                severity = "warning" if severity == "info" else severity
        if info.revoked_at is not None:
            warnings.append("Token revogado — renove.")
            severity = "critical"
        if spec.bind_principal:
            julia = self._resolver.julia_agent_id()
            if julia is not None and info.principal_agent_id != julia:
                warnings.append("principal_agent_id do token ≠ JULIA_AGENT_ID — as escritas serão recusadas.")
                severity = "critical"
        return CredentialStatus(
            **base,
            configured=True,
            source=source,
            prefix=info.prefix or prefix,
            expires_at=info.expires_at,
            days_left=days_left,
            last_used_at=info.last_used_at,
            revoked=info.revoked_at is not None,
            scopes=info.scopes,
            warnings=tuple(warnings),
            severity=severity,
        )

    def _ring_status(self, spec: CredentialSpec, base: dict[str, Any]) -> CredentialStatus:
        now = self._clock()
        value, source = self._resolver.resolve(spec)
        ring = KeyRing.from_value(value)
        signing = ring.signing_key(now)
        keys = []
        for key in ring.keys:
            if key.is_retired(now):
                state = "retired"
            elif key.active_from > now:
                state = "staged"
            elif key.retire_at is not None:
                state = "retiring"
            else:
                state = "active"
            keys.append(
                RingKeyStatus(
                    fingerprint=key.fingerprint,
                    active_from=key.active_from,
                    retire_at=key.retire_at,
                    signing=signing is not None and key.secret == signing.secret,
                    state=state,
                )
            )
        warnings: list[str] = []
        severity: Severity = "info"
        if signing is None:
            warnings.append("Nenhuma chave ativa — escritas aprovadas vão falhar.")
            severity = "critical"
        if source == "env":
            warnings.append("Chaves vindas do ambiente — importe para o banco antes de rotacionar.")
            severity = "warning" if severity == "info" else severity
        return CredentialStatus(
            **base,
            configured=signing is not None,
            source=source,
            fingerprint=signing.fingerprint if signing else None,
            ring=tuple(keys),
            warnings=tuple(warnings),
            severity=severity,
        )

    # ── writes ─────────────────────────────────────────────────────────

    def set_value(self, name: str, value: str) -> CredentialStatus:
        spec = self.spec(name)
        value = (value or "").strip()
        if spec.kind == "key_ring":
            raise CredentialError(409, "not_supported", "Use a rotação para alterar estas chaves.")
        if not value:
            raise CredentialError(422, "invalid_value", "Valor vazio.")
        if spec.kind == "product_token" and not value.startswith("pk_"):
            raise CredentialError(422, "invalid_value", "Um token de produto começa com pk_.")
        if spec.kind == "api_key" and not value.startswith("sk-"):
            raise CredentialError(422, "invalid_value", "Uma chave Anthropic começa com sk-.")
        if spec is JULIA_AGENT_ID:
            try:
                value = str(UUID(value))
            except ValueError as exc:
                raise CredentialError(422, "invalid_value", "JULIA_AGENT_ID deve ser um UUID.") from exc
        self._require_writable()
        self._handle.store.put(spec.store_key, value)
        logger.info("agents.credential_set credential=%s", spec.name)
        return self.status(spec.name)

    def import_env(self, name: str) -> CredentialStatus:
        """Copy the current env value into the store (the operator's one-time
        migration step) — the value never crosses the browser."""
        spec = self.spec(name)
        env_value = (getattr(self._settings, spec.settings_attr, "") or "").strip()
        if not env_value:
            raise CredentialError(409, "env_empty", f"{spec.env_var} não está definido no ambiente.")
        self._require_writable()
        stored = KeyRing.from_value(env_value).to_value() if spec.kind == "key_ring" else env_value
        self._handle.store.put(spec.store_key, stored)
        logger.info("agents.credential_imported_from_env credential=%s", spec.name)
        return self.status(spec.name)

    async def probe(self, name: str, *, connection_id: UUID | None = None) -> ProbeResult:
        spec = self.spec(name)
        if not spec.probeable:
            raise CredentialError(409, "not_supported", "Esta credencial não tem teste ao vivo.")
        value = self._resolver.value(spec)
        if not value:
            raise CredentialError(409, "not_configured", "Credencial não configurada.")
        return await self._prober.probe(spec, value, connection_id=connection_id)

    async def renew(
        self,
        name: str,
        *,
        actor_user_id: UUID | None,
        fallback_org_id: UUID,
        connection_id: UUID | None = None,
    ) -> RenewOutcome:
        spec = self.spec(name)
        if not spec.renewable:
            raise CredentialError(409, "not_supported", "Só tokens de produto podem ser renovados.")
        self._require_writable()
        schema = spec.target_schema or ""
        current = self._resolver.value(spec)
        old: ApiTokenInfo | None = None
        if current:
            old, lookup_warning = self._find_token(spec, current)
            if lookup_warning:
                # Without the old row we cannot keep its org or revoke it —
                # refuse rather than mint an orphan next to a live token.
                raise CredentialError(502, "lookup_failed", lookup_warning)
        org_id = old.org_id if old else fallback_org_id

        principal: UUID | None = None
        if spec.bind_principal:
            principal = self._resolver.julia_agent_id() or (old.principal_agent_id if old else None)
            if principal is None:
                raise CredentialError(
                    409, "principal_missing",
                    "Defina JULIA_AGENT_ID antes de renovar o token da academia.",
                )

        now = self._clock()
        try:
            minted = self._admin.mint(
                schema,
                org_id=org_id,
                label=spec.token_label or spec.label,
                scopes=list(spec.scopes),
                expires_at=now + timedelta(days=TOKEN_TTL_DAYS),
                principal_agent_id=principal,
                issuer=ISSUER,
                minted_by=actor_user_id,
            )
        except Exception as exc:
            logger.error("agents.credential_renew_mint_failed credential=%s error=%s", spec.name, type(exc).__name__)
            raise CredentialError(502, "mint_failed", f"Falha ao emitir o novo token em {spec.target_product}.") from exc

        probe = await self._prober.probe(spec, minted.secret, connection_id=connection_id)
        if not probe.ok:
            self._revoke_quietly(spec, minted.info, reason="new_token_failed_probe")
            raise CredentialError(
                502, "verification_failed",
                f"O novo token não passou no teste ({probe.detail}). O token atual continua em uso.",
            )

        self._handle.store.put(spec.store_key, minted.secret)
        logger.info(
            "agents.credential_renewed credential=%s new_token_id=%s old_token_id=%s",
            spec.name, minted.info.id, old.id if old else None,
        )

        warnings: list[str] = []
        if old is not None and old.revoked_at is None:
            if not self._revoke_quietly(spec, old, reason="replaced"):
                warnings.append(
                    f"O novo token está ativo, mas o antigo ({old.prefix}) não pôde ser revogado — revogue-o em {spec.target_product}."
                )
        elif old is None and current:
            warnings.append("O token anterior não foi encontrado no produto de destino; nada foi revogado.")
        return RenewOutcome(status=self.status(spec.name), warnings=tuple(warnings))

    def _revoke_quietly(self, spec: CredentialSpec, info: ApiTokenInfo, *, reason: str) -> bool:
        try:
            revoked = self._admin.revoke(spec.target_schema or "", info.id, org_id=info.org_id)
        except Exception as exc:
            logger.error(
                "agents.credential_revoke_failed credential=%s token_id=%s reason=%s error=%s",
                spec.name, info.id, reason, type(exc).__name__,
            )
            return False
        if not revoked:
            logger.error(
                "agents.credential_revoke_noop credential=%s token_id=%s reason=%s",
                spec.name, info.id, reason,
            )
        return revoked

    # ── §D ring ────────────────────────────────────────────────────────

    def _stored_ring(self) -> KeyRing:
        value, source = self._resolver.resolve(APPROVAL_RING)
        if source != "db":
            raise CredentialError(
                409, "ring_not_in_db",
                "Importe as chaves do ambiente para o banco antes de rotacionar.",
            )
        return KeyRing.from_value(value)

    def rotate_ring(self) -> CredentialStatus:
        self._require_writable()
        ring = self._stored_ring()
        now = self._clock()
        rotated = ring.prune(now).rotate(
            generate_ring_secret(),
            now=now,
            activation_delay=timedelta(
                seconds=int(getattr(self._settings, "approval_key_activation_delay_seconds", 120))
            ),
            retire_after=timedelta(
                seconds=int(getattr(self._settings, "approval_key_retire_after_seconds", 86400))
            ),
        )
        self._handle.store.put(APPROVAL_RING.store_key, rotated.to_value())
        logger.info("agents.approval_ring_rotated staged=%s", rotated.keys[0].fingerprint)
        return self.status(APPROVAL_RING.name)

    def prune_ring(self) -> CredentialStatus:
        self._require_writable()
        ring = self._stored_ring()
        pruned = ring.prune(self._clock())
        if pruned.keys != ring.keys:
            if not pruned.keys:
                raise CredentialError(409, "ring_would_be_empty", "A remoção deixaria o anel sem chaves.")
            self._handle.store.put(APPROVAL_RING.store_key, pruned.to_value())
            logger.info("agents.approval_ring_pruned removed=%s", len(ring.keys) - len(pruned.keys))
        return self.status(APPROVAL_RING.name)

    # ── expiry alerts (banner + scheduler) ─────────────────────────────

    def expiry_alerts(self) -> list[ExpiryAlert]:
        alerts: list[ExpiryAlert] = []
        now = self._clock()
        for spec in CREDENTIALS:
            if spec.kind != "product_token":
                continue
            status = self.status(spec.name)
            if status.revoked:
                alerts.append(ExpiryAlert(spec.name, spec.label, status.expires_at, status.days_left, "revoked"))
            elif status.expires_at is not None and status.expires_at <= now:
                alerts.append(ExpiryAlert(spec.name, spec.label, status.expires_at, status.days_left, "expired"))
            elif status.days_left is not None and status.days_left <= self._warning_days():
                alerts.append(ExpiryAlert(spec.name, spec.label, status.expires_at, status.days_left, "expiring"))
        return alerts

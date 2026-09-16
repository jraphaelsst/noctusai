"""Billing configuration — platform flags + encrypted gateway secrets.

Two stores, one read surface:

* **Flags** (`public.platform_settings`, plain text): which gateways are
  offered, the active gateway mode (`test` | `live`), whether the billing
  automations run, and the storage price the cost snapshot uses. Seeded
  OFF by migration 050.
* **Secrets** (`public.app_integration_config`, Fernet-encrypted via the
  seed's `noctusai_lib.security.app_config.RealAppConfigStore`): the
  Stripe secret key + webhook signing secret and the Asaas API key +
  webhook token, one row per (gateway, field, mode). Entered in Admin >
  Faturamento and NEVER returned by any endpoint — the view says only
  whether a value is configured and where it came from.

Env fallback exists only for Stripe, because Core already bills live
customers off `STRIPE_SECRET_KEY` / `STRIPE_WEBHOOK_SECRET`. The env key's
own prefix (`sk_live_` / `sk_test_`) decides which mode it serves, so an
env key can never answer for the wrong mode. A DB value always wins.

A missing `ENCRYPTION_KEY` never degrades to plaintext: reads fall back to
env only, writes raise `EncryptionNotConfigured` (routers answer 503).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Literal, Optional

from noctusai_lib.security.app_config import AppConfigStore, RealAppConfigStore

logger = logging.getLogger(__name__)

Gateway = Literal["stripe", "asaas"]
Mode = Literal["test", "live"]

GATEWAYS: tuple[str, ...] = ("stripe", "asaas")
MODES: tuple[str, ...] = ("test", "live")

#: The secret fields each gateway needs, per mode.
SECRET_FIELDS: dict[str, tuple[str, ...]] = {
    "stripe": ("secret_key", "webhook_secret"),
    "asaas": ("api_key", "webhook_token"),
}

FLAG_AUTOMATIONS = "billing_automations_enabled"
FLAG_MODE = "billing_gateway_mode"
FLAG_STRIPE = "billing_stripe_enabled"
FLAG_ASAAS = "billing_asaas_enabled"
SETTING_STORAGE_PRICE = "storage_price_usd_per_gb_month"

ASAAS_BASE_URLS: dict[str, str] = {
    "test": "https://api-sandbox.asaas.com/v3",
    "live": "https://api.asaas.com/v3",
}

_TRUE = {"true", "1", "yes", "on"}
_ASAAS_PREFIX_MODE = {"$aact_prod_": "live", "$aact_hmlg_": "test"}
_ASAAS_MIN_WEBHOOK_TOKEN = 16


class EncryptionNotConfigured(RuntimeError):
    """`ENCRYPTION_KEY` is missing or not a valid Fernet key."""


class GatewayNotConfigured(RuntimeError):
    """A gateway was asked for with no key configured for that mode."""


class InvalidSecret(ValueError):
    """A secret failed its shape check (wrong prefix / wrong mode)."""


def secret_key_name(gateway: str, field: str, mode: str) -> str:
    return f"billing.{gateway}.{field}.{mode}"


def build_config_store(db: Any, encryption_key: str) -> AppConfigStore:
    """Real encrypted store, or `EncryptionNotConfigured` — never a Fake.

    The seed factory returns a Fake when the key is absent (right for
    tests, wrong for production secrets): a Fake here would "save" the
    owner's key into process memory and lose it on restart.
    """
    if not encryption_key:
        raise EncryptionNotConfigured(
            "ENCRYPTION_KEY is not set on Core; gateway secrets cannot be stored."
        )
    from cryptography.fernet import Fernet

    try:
        Fernet(encryption_key.encode("utf-8"))
    except (ValueError, TypeError) as exc:
        raise EncryptionNotConfigured(f"ENCRYPTION_KEY is not a valid Fernet key: {exc}") from exc
    return RealAppConfigStore(db, encryption_key.encode("utf-8"), table="app_integration_config")


def _stripe_key_mode(key: str) -> Optional[str]:
    for mode in MODES:
        if key.startswith((f"sk_{mode}_", f"rk_{mode}_")):
            return mode
    return None


def validate_secret(gateway: str, field: str, mode: str, value: str) -> None:
    """Refuse a secret that is shaped for another gateway or mode."""
    if gateway not in SECRET_FIELDS or field not in SECRET_FIELDS[gateway]:
        raise InvalidSecret(f"Campo desconhecido: {gateway}.{field}")
    if mode not in MODES:
        raise InvalidSecret(f"Modo desconhecido: {mode}")
    value = value.strip()
    if gateway == "stripe" and field == "secret_key":
        key_mode = _stripe_key_mode(value)
        if key_mode is None:
            raise InvalidSecret("Chave Stripe deve começar com sk_test_/sk_live_ (ou rk_).")
        if key_mode != mode:
            raise InvalidSecret(f"Esta chave Stripe é do modo '{key_mode}', não '{mode}'.")
    elif gateway == "stripe" and field == "webhook_secret":
        if not value.startswith("whsec_"):
            raise InvalidSecret("Segredo de webhook Stripe deve começar com whsec_.")
    elif gateway == "asaas" and field == "api_key":
        for prefix, key_mode in _ASAAS_PREFIX_MODE.items():
            if value.startswith(prefix) and key_mode != mode:
                raise InvalidSecret(f"Esta chave Asaas é do modo '{key_mode}', não '{mode}'.")
        if len(value) < 20:
            raise InvalidSecret("Chave Asaas curta demais.")
    elif gateway == "asaas" and field == "webhook_token":
        if len(value) < _ASAAS_MIN_WEBHOOK_TOKEN:
            raise InvalidSecret(
                f"Token do webhook Asaas deve ter ao menos {_ASAAS_MIN_WEBHOOK_TOKEN} caracteres."
            )


@dataclass(frozen=True)
class SecretStatus:
    configured: bool
    source: Optional[str]  # "db" | "env" | None


class BillingConfig:
    """Read/write surface over flags + secrets. One instance per request/job."""

    def __init__(
        self,
        db: Any,
        *,
        store_factory: Callable[[], AppConfigStore],
        env_stripe_secret_key: str = "",
        env_stripe_webhook_secret: str = "",
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._db = db
        self._store_factory = store_factory
        self._store: Optional[AppConfigStore] = None
        self._env_secret_key = env_stripe_secret_key or ""
        self._env_webhook_secret = env_stripe_webhook_secret or ""
        self._clock = clock

    # ── platform_settings ───────────────────────────────────────────

    def _read_setting(self, key: str) -> Optional[str]:
        rows = (
            self._db.table("platform_settings").select("key, value").eq("key", key).limit(1).execute().data
            or []
        )
        return rows[0].get("value") if rows else None

    def _write_setting(self, key: str, value: str, *, user_id: Optional[str] = None) -> None:
        payload: dict[str, Any] = {"value": value, "updated_at": self._clock().isoformat()}
        if user_id:
            payload["updated_by"] = user_id
        existing = (
            self._db.table("platform_settings").select("key").eq("key", key).limit(1).execute().data or []
        )
        if existing:
            self._db.table("platform_settings").update(payload).eq("key", key).execute()
        else:
            self._db.table("platform_settings").insert({"key": key, **payload}).execute()

    def _flag(self, key: str) -> bool:
        return (self._read_setting(key) or "").strip().lower() in _TRUE

    def automations_enabled(self) -> bool:
        return self._flag(FLAG_AUTOMATIONS)

    def gateway_enabled(self, gateway: str) -> bool:
        return self._flag(FLAG_STRIPE if gateway == "stripe" else FLAG_ASAAS)

    def mode(self) -> str:
        value = (self._read_setting(FLAG_MODE) or "test").strip().lower()
        if value not in MODES:
            logger.warning("billing_config: invalid %s=%r in platform_settings; using 'test'", FLAG_MODE, value)
            return "test"
        return value

    def storage_price_usd_per_gb_month(self) -> Optional[Decimal]:
        raw = self._read_setting(SETTING_STORAGE_PRICE)
        if raw is None or raw.strip() == "":
            return None
        try:
            price = Decimal(raw.strip())
        except InvalidOperation:
            logger.error("billing_config: %s=%r is not a number", SETTING_STORAGE_PRICE, raw)
            return None
        return price if price >= 0 else None

    def update_flags(
        self,
        *,
        user_id: Optional[str],
        mode: Optional[str] = None,
        automations_enabled: Optional[bool] = None,
        stripe_enabled: Optional[bool] = None,
        asaas_enabled: Optional[bool] = None,
        storage_price_usd_per_gb_month: Optional[Decimal] = None,
    ) -> None:
        if mode is not None:
            if mode not in MODES:
                raise InvalidSecret(f"Modo desconhecido: {mode}")
            self._write_setting(FLAG_MODE, mode, user_id=user_id)
        for key, value in (
            (FLAG_AUTOMATIONS, automations_enabled),
            (FLAG_STRIPE, stripe_enabled),
            (FLAG_ASAAS, asaas_enabled),
        ):
            if value is not None:
                self._write_setting(key, "true" if value else "false", user_id=user_id)
        if storage_price_usd_per_gb_month is not None:
            self._write_setting(
                SETTING_STORAGE_PRICE, str(storage_price_usd_per_gb_month), user_id=user_id
            )

    # ── secrets ─────────────────────────────────────────────────────

    def _store_or_none(self) -> Optional[AppConfigStore]:
        if self._store is None:
            try:
                self._store = self._store_factory()
            except EncryptionNotConfigured as exc:
                logger.warning("billing_config: encrypted store unavailable (%s); env fallback only", exc)
                return None
        return self._store

    def encryption_configured(self) -> bool:
        return self._store_or_none() is not None

    def _env_secret(self, gateway: str, field: str, mode: str) -> Optional[str]:
        if gateway != "stripe" or not self._env_secret_key and not self._env_webhook_secret:
            return None
        env_mode = _stripe_key_mode(self._env_secret_key) if self._env_secret_key else None
        # A webhook secret has no mode marker; it belongs to the env key's
        # mode, and to 'live' when only the secret is set (the pre-050
        # production setup, where both lived in env).
        if env_mode is None:
            env_mode = "live"
        if env_mode != mode:
            return None
        if field == "secret_key":
            return self._env_secret_key or None
        if field == "webhook_secret":
            return self._env_webhook_secret or None
        return None

    def secret_status(self, gateway: str, field: str, mode: str) -> SecretStatus:
        store = self._store_or_none()
        if store is not None and secret_key_name(gateway, field, mode) in store.list_keys():
            return SecretStatus(True, "db")
        if self._env_secret(gateway, field, mode):
            return SecretStatus(True, "env")
        return SecretStatus(False, None)

    def get_secret(self, gateway: str, field: str, mode: str) -> Optional[str]:
        store = self._store_or_none()
        if store is not None:
            value = store.get(secret_key_name(gateway, field, mode))
            if value:
                return value
        return self._env_secret(gateway, field, mode)

    def set_secret(self, gateway: str, field: str, mode: str, value: Optional[str]) -> None:
        """Save (or clear, with an empty value) one secret. Encrypted only."""
        try:
            store = self._store_factory()
        except EncryptionNotConfigured:
            raise
        name = secret_key_name(gateway, field, mode)
        if value is None or value.strip() == "":
            store.delete(name)
            return
        validate_secret(gateway, field, mode, value)
        store.put(name, value.strip())
        self._store = store

    def secrets_by_mode(self, gateway: str, field: str) -> dict[str, str]:
        """Every configured value of one field, keyed by mode (webhooks)."""
        out: dict[str, str] = {}
        for mode in MODES:
            value = self.get_secret(gateway, field, mode)
            if value:
                out[mode] = value
        return out

    def gateway_ready(self, gateway: str, mode: str) -> bool:
        return all(self.get_secret(gateway, field, mode) for field in SECRET_FIELDS[gateway])

    # ── view ────────────────────────────────────────────────────────

    def view(self, *, webhook_base_url: str) -> dict[str, Any]:
        """Everything the admin screen shows. Never a secret value."""
        gateways: dict[str, Any] = {}
        for gateway in GATEWAYS:
            modes: dict[str, Any] = {}
            for mode in MODES:
                modes[mode] = {
                    field: vars(self.secret_status(gateway, field, mode))
                    for field in SECRET_FIELDS[gateway]
                }
            gateways[gateway] = {"enabled": self.gateway_enabled(gateway), "modes": modes}
        base = webhook_base_url.rstrip("/")
        price = self.storage_price_usd_per_gb_month()
        return {
            "mode": self.mode(),
            "automations_enabled": self.automations_enabled(),
            "encryption_configured": self.encryption_configured(),
            "storage_price_usd_per_gb_month": str(price) if price is not None else None,
            "gateways": gateways,
            "webhook_urls": {
                "stripe": f"{base}/api/billing/webhook",
                "asaas": f"{base}/api/billing/webhooks/asaas",
            },
        }


__all__ = [
    "ASAAS_BASE_URLS",
    "BillingConfig",
    "EncryptionNotConfigured",
    "GATEWAYS",
    "GatewayNotConfigured",
    "InvalidSecret",
    "MODES",
    "SECRET_FIELDS",
    "SecretStatus",
    "build_config_store",
    "secret_key_name",
    "validate_secret",
]

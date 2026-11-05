"""Core's M2M token policy: the scope allow-list, the MFA-to-mint setting, service accounts.

* **Scopes.** ``CORE_TOKEN_SCOPES`` is the ONE list of scopes a core token may carry (strict:
  mint refuses anything else). A product route that starts requiring a new scope registers it here.
* **MFA to mint.** ``platform_settings.exigir_mfa_para_tokens`` (migration 099), ``false`` until the
  owner switches it on in the admin UI -- we do not use MFA yet. It feeds the seed ``MintPolicy``:
  off -> minting/rotating needs no MFA; on -> the seed refuses an unmet ``aal2`` with
  403 ``mfa_required``. A missing row means off (the documented default); a value that is neither
  ``true`` nor ``false`` counts as ON (fail closed) and is logged.
* **Service accounts.** ``public.service_accounts`` ("noc-agent"); a token may name one.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Optional
from uuid import UUID

from fastapi import HTTPException
from noctusai_lib.api.auth.session import MintPolicy, TokenScopeAllowList

logger = logging.getLogger(__name__)

MFA_SETTING_KEY = "exigir_mfa_para_tokens"
_MFA_SETTING_DESCRIPTION = (
    "Exigir MFA (aal2) para gerar ou rotacionar tokens de API. "
    "false = não exige (padrão: ainda não usamos MFA)."
)

#: Scopes core's own routes understand. ``reminders:*`` serve the owner-reminders API (noctusai-86).
CORE_TOKEN_SCOPES = TokenScopeAllowList(
    [
        "transcription:read",
        "transcription:write",
        "reminders:read",
        "reminders:write",
    ]
)


def read_mfa_required(db: Any) -> bool:
    """The platform setting as a bool. Absent row = off; unreadable = 503 (never a silent guess)."""
    try:
        rows = (
            db.table("platform_settings").select("value").eq("key", MFA_SETTING_KEY).limit(1).execute().data
            or []
        )
    except Exception as exc:
        logger.error("token_mfa_setting_read_failed err=%s", type(exc).__name__, exc_info=True)
        raise HTTPException(status_code=503, detail="token_settings_unavailable") from exc
    if not rows:
        return False
    value = str(rows[0].get("value", "")).strip().lower()
    if value == "true":
        return True
    if value == "false":
        return False
    logger.warning("token_mfa_setting_unparseable value=%r -> treated as ON", value)
    return True


def write_mfa_required(db: Any, required: bool, user_id: Optional[str]) -> bool:
    """Persist the setting (upsert) and return what is stored."""
    row = {
        "key": MFA_SETTING_KEY,
        "value": "true" if required else "false",
        "description": _MFA_SETTING_DESCRIPTION,
        "is_secret": False,
        "updated_by": user_id,
    }
    result = db.table("platform_settings").upsert(row, on_conflict="key").execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Erro ao salvar configuração")
    logger.info("token_mfa_setting_changed required=%s by=%s", required, user_id)
    return required


def make_mint_policy(get_db: Callable[[], Any]) -> MintPolicy:
    """The seed ``MintPolicy`` wired to the platform setting (read per request, so a switch applies at once)."""
    return MintPolicy(require_mfa=lambda ctx: read_mfa_required(get_db()))


def list_service_accounts(db: Any) -> list[dict[str, Any]]:
    return (
        db.table("service_accounts")
        .select("id, slug, name, description, created_at")
        .is_("disabled_at", "null")
        .order("slug")
        .execute()
        .data
        or []
    )


def make_service_account_check(get_db: Callable[[], Any]) -> Callable[[UUID], bool]:
    def _check(service_account_id: UUID) -> bool:
        rows = (
            get_db()
            .table("service_accounts")
            .select("id")
            .eq("id", str(service_account_id))
            .is_("disabled_at", "null")
            .limit(1)
            .execute()
            .data
            or []
        )
        return bool(rows)

    return _check

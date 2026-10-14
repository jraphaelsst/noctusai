"""Store profile — the versioned legal identity of one org's store.

CNPJ is REQUIRED and check-digit validated (`primitives.identificador.cnpj_dv_valido`,
numeric AND alphanumeric CNPJ). Saves go through an optimistic-version ledger
(store `settings_service` precedent): the caller sends `expected_version`; the
write INSERTs `commerce_store_profile_versions` row `v+1` FIRST, and a primary-key
conflict means a concurrent save won -> 409 `versao_conflitante`. The profile row
is only written after the ledger row lands, and the ledger row is compensated
(deleted) if the profile write then fails, so a half-save can never wedge future
saves behind a phantom version.

`platform_fee_bps` is the noc fee (D27): only a platform admin may change it,
decided by the CALLER (`is_platform_admin`), never by client input; for anyone
else the incoming value is ignored and the stored one kept.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Mapping, Optional

from noctusai_lib.integrations.cnpj_registry import (
    CnpjNotFoundError,
    CnpjRegistryLookup,
    CnpjRegistryUpstreamError,
)
from noctusai_lib.primitives.identificador import cnpj_dv_valido
from noctusai_lib.primitives.postgrest_errors import is_unique_violation

from ._common import first, get_row, now_iso, tbl
from .errors import CNPJ_INVALIDO, VERSAO_CONFLITANTE, CommerceError

logger = logging.getLogger(__name__)

_PROFILE = "commerce_store_profiles"
_VERSIONS = "commerce_store_profile_versions"

#: Columns a client may submit (and a snapshot records).
PROFILE_FIELDS = (
    "legal_name",
    "trade_name",
    "cnpj",
    "tax_regime",
    "tax_treatment",
    "locale",
    "currency",
    "brand_tokens",
    "address",
    "contact_email",
    "contact_phone",
)


#: Card-installment knobs (D33/D41). Written only when the caller sends them (absent = keep / DB default), so a
#: host that has not applied the money migration yet still saves its profile.
INSTALLMENT_FIELDS = ("installments_max", "installments_interest_free", "installment_interest_monthly_bps")


def normalize_cnpj(raw: str) -> str:
    """Uppercase alphanumerics only (`12.ABC.345/01DE-35` -> `12ABC34501DE35`)."""
    return re.sub(r"[^0-9A-Za-z]", "", raw or "").upper()


def require_valid_cnpj(raw: str) -> str:
    cnpj = normalize_cnpj(raw)
    if not cnpj_dv_valido(cnpj):
        raise CommerceError(CNPJ_INVALIDO, "CNPJ inválido: confira os dígitos.", 422, field="cnpj")
    return cnpj


def get_profile(db: Any, org_id: Any) -> Optional[dict]:
    return get_row(db, _PROFILE, org_id, org_id, id_col="org_id")


def current_version(db: Any, org_id: Any) -> int:
    profile = get_profile(db, org_id)
    return int(profile["version"]) if profile else 0


def _plain(value: Any) -> Any:
    """Enum keys/values -> their wire strings (the stored JSONB is plain)."""
    if isinstance(value, Mapping):
        return {getattr(k, "value", k): _plain(v) for k, v in value.items()}
    return getattr(value, "value", value)


def put_profile(
    db: Any,
    org_id: Any,
    user_id: Any,
    data: Mapping[str, Any],
    *,
    expected_version: int,
    is_platform_admin: bool,
) -> dict:
    """Create/replace the org's profile at `expected_version + 1`.

    Raises `CommerceError(cnpj_invalido, 422)` / `CommerceError(versao_conflitante, 409)`.
    """
    cnpj = require_valid_cnpj(str(data.get("cnpj", "")))
    existing = get_profile(db, org_id)
    cur_v = int(existing["version"]) if existing else 0
    if int(expected_version) != cur_v:
        raise CommerceError(
            VERSAO_CONFLITANTE,
            "O perfil da loja foi alterado por outra pessoa. Recarregue e tente de novo.",
            409,
            details={"current_version": cur_v},
        )

    fee_bps = int(existing["platform_fee_bps"]) if existing else 0
    if is_platform_admin and data.get("platform_fee_bps") is not None:
        fee_bps = int(data["platform_fee_bps"])

    row: dict[str, Any] = {k: _plain(data.get(k)) for k in PROFILE_FIELDS}
    for key in INSTALLMENT_FIELDS:
        if key in data:
            row[key] = data[key]
    effective_max = row.get("installments_max") or (existing or {}).get("installments_max") or 12
    effective_free = row.get("installments_interest_free") or (existing or {}).get("installments_interest_free") or 3
    if int(effective_free) > int(effective_max):
        raise CommerceError(
            "parcelamento_invalido", "As parcelas sem juros não podem passar do máximo de parcelas.", 422,
            field="installments_interest_free",
        )
    # B2 (fiscal): `nfse_mode` is regime-dependent (a CHECK forbids 'municipal' for mei/simples), so a regime change
    # clears it back to NULL = "the regime default". Only touched when the stored row actually carries a value
    # (the column exists only once the fiscal migration is applied).
    if existing is not None and existing.get("nfse_mode") is not None and existing.get("tax_regime") != row.get("tax_regime"):
        row["nfse_mode"] = None
    now = now_iso()
    row["cnpj"] = cnpj
    row["tax_treatment"] = row.get("tax_treatment") or {}
    row["brand_tokens"] = row.get("brand_tokens") or {}
    row["address"] = row.get("address") or {}
    row.update(
        {
            "org_id": str(org_id),
            "version": cur_v + 1,
            "platform_fee_bps": fee_bps,
            "updated_at": now,
            "updated_by": str(user_id) if user_id else None,
        }
    )

    version_row = {
        "org_id": str(org_id),
        "version": cur_v + 1,
        "snapshot": dict(row),
        "changed_by": str(user_id) if user_id else None,
        "changed_at": now,
    }
    try:
        tbl(db, _VERSIONS).insert(version_row).execute()
    except Exception as exc:  # noqa: BLE001 - narrowed right below
        if is_unique_violation(exc):
            raise CommerceError(
                VERSAO_CONFLITANTE,
                "O perfil da loja foi alterado por outra pessoa. Recarregue e tente de novo.",
                409,
                details={"current_version": cur_v},
            ) from exc
        raise

    try:
        if existing is None:
            saved = first(tbl(db, _PROFILE).insert(row).execute()) or row
        else:
            updated = (
                tbl(db, _PROFILE)
                .update({k: v for k, v in row.items() if k != "org_id"})
                .eq("org_id", str(org_id))
                .eq("version", cur_v)
                .execute()
            )
            saved = first(updated)
            if saved is None:
                raise CommerceError(
                    VERSAO_CONFLITANTE,
                    "O perfil da loja foi alterado por outra pessoa. Recarregue e tente de novo.",
                    409,
                    details={"current_version": cur_v},
                )
    except Exception:
        # Compensate: an orphaned ledger row v+1 would 409 every later save.
        logger.warning("commerce profile write failed after ledger insert; compensating (org=%s v=%s)", org_id, cur_v + 1)
        tbl(db, _VERSIONS).delete().eq("org_id", str(org_id)).eq("version", cur_v + 1).execute()
        raise
    return saved


def list_versions(db: Any, org_id: Any) -> list[dict]:
    resp = tbl(db, _VERSIONS).select("*").eq("org_id", str(org_id)).order("version", desc=True).limit(100).execute()
    return [dict(r) for r in (resp.data or [])]


async def cnpj_prefill(lookup: CnpjRegistryLookup, raw_cnpj: str) -> dict:
    """Registry prefill for the profile form. Validates the check digits FIRST so
    a typo never costs a network call; a confirmed absence is 404, an unreachable
    registry is 502 -- never a guessed answer."""
    cnpj = require_valid_cnpj(raw_cnpj)
    try:
        fields = await lookup.lookup(cnpj)
    except CnpjNotFoundError as exc:
        raise CommerceError("cnpj_nao_encontrado", "CNPJ não encontrado na Receita.", 404) from exc
    except CnpjRegistryUpstreamError as exc:
        logger.warning("commerce cnpj lookup upstream failure: %s", exc)
        raise CommerceError("cnpj_indisponivel", "Consulta de CNPJ indisponível agora. Tente de novo.", 502) from exc
    return {
        "cnpj": cnpj,
        "legal_name": fields.razao_social,
        "situacao_cadastral": fields.situacao_cadastral,
        "situacao_cadastral_bruta": fields.situacao_cadastral_bruta,
        "source": fields.source,
    }


__all__ = [
    "INSTALLMENT_FIELDS",
    "PROFILE_FIELDS",
    "cnpj_prefill",
    "current_version",
    "get_profile",
    "list_versions",
    "normalize_cnpj",
    "put_profile",
    "require_valid_cnpj",
]

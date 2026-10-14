"""Store fiscal profile -- view, update, A1 certificate, approved NFS-e cutover (+ rollback).

All state lives on `commerce_store_profiles` (the fiscal columns of `fiscal_sql`); provider calls go
through the `InvoiceProvider` Protocol (Fake or Focus). Rules:

* **D37 regime rule, two layers.** `mei`/`simples` => `nacional` always; asking for `municipal`
  is 422 `nfse_nacional_obrigatorio` here AND impossible in the database (CHECK). Other regimes
  default `municipal` and reach `nacional` ONLY through `request_cutover` (D19, typed phrase,
  validation window, rollback), never through a plain `PUT /fiscal`.
* **D38 certificate.** The `.pfx` + password are opened locally (`inspect_pkcs12(expected_cnpj=)`:
  size/length bounds, CNPJ match) BEFORE anything is forwarded; they live inside
  `upload_certificate` and nowhere else -- never stored, logged, or put in an exception (the
  provider's own errors are mapped to generic pt-BR codes and raised `from None`).
* **No secret on the wire out.** The fiscal view is a whitelist; per-company provider tokens are
  in the encrypted credentials table and never reach this module.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from typing import Any, Mapping, Optional

from noctusai_lib.integrations.invoices import (
    Address,
    CompanyRequest,
    InvoiceCertificateError,
    InvoiceNotConfigured,
    InvoiceProvider,
    InvoiceProviderError,
    NfseMode,
    inspect_pkcs12,
)
from noctusai_lib.integrations.invoices.errors import InvoiceCertificateCnpjMismatch
from noctusai_lib.primitives.postgrest_errors import is_unique_violation

from ._common import digits, first, now, now_iso, tbl
from .errors import VERSAO_CONFLITANTE, CommerceError
from .fiscal_types import (
    CUTOVER_PHRASE,
    MAX_CERTIFICATE_BYTES,
    MAX_CERTIFICATE_PASSWORD_CHARS,
    ROLLBACK_PHRASE,
    VALIDATION_WINDOW_DAYS,
    effective_nfse_mode,
    forced_nacional,
)
from .profile import get_profile

logger = logging.getLogger(__name__)

_PROFILE = "commerce_store_profiles"
_VERSIONS = "commerce_store_profile_versions"

#: What a client may set through `PUT /fiscal` (the mode is validated, never trusted).
FISCAL_FIELDS = ("inscricao_municipal", "inscricao_estadual", "municipio_ibge", "nfse_mode", "auto_issue_invoices")

#: The whitelist of the fiscal view -- adding a column to the profile does not leak it here.
VIEW_FIELDS = (
    "cnpj",
    "tax_regime",
    "inscricao_municipal",
    "inscricao_estadual",
    "municipio_ibge",
    "invoice_company_ref",
    "certificate_valid_until",
    "certificate_cnpj",
    "auto_issue_invoices",
    "nfse_cutover",
    "version",
)

_REGIME_FOR_PROVIDER = {"mei": "mei", "simples": "simples"}  # everything else -> "normal"


def _parse_dt(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def map_provider_error(exc: InvoiceProviderError) -> CommerceError:
    """Provider failure -> a generic pt-BR `CommerceError` (no provider text, no secrets)."""
    if isinstance(exc, InvoiceCertificateCnpjMismatch):
        return CommerceError("certificado_cnpj_divergente", "O CNPJ do certificado não é o da loja.", 422)
    if isinstance(exc, InvoiceCertificateError):
        return CommerceError("certificado_invalido", "Certificado inválido. Confira o arquivo e a senha.", 422)
    if isinstance(exc, InvoiceNotConfigured):
        return CommerceError("provedor_fiscal_nao_configurado", "O emissor de notas fiscais não está configurado.", 503)
    return CommerceError(
        "provedor_fiscal_indisponivel",
        "O emissor de notas fiscais não respondeu. Tente de novo em instantes.",
        502,
        details={"provider_code": exc.code} if exc.code else None,
    )


# ─── view ────────────────────────────────────────────────────────────────


def certificate_status(profile: Mapping[str, Any], at: Optional[datetime] = None) -> str:
    """`ausente` | `vencido` | `divergente` | `valido`."""
    until = _parse_dt(profile.get("certificate_valid_until"))
    if until is None:
        return "ausente"
    if until <= (at or now()):
        return "vencido"
    if digits(profile.get("certificate_cnpj")) != digits(profile.get("cnpj")):
        return "divergente"
    return "valido"


def cutover_window_open(profile: Mapping[str, Any], at: Optional[datetime] = None) -> bool:
    """Rollback to `municipal` is available: nacional by cutover, window not over."""
    cutover = profile.get("nfse_cutover") or {}
    until = _parse_dt(cutover.get("validation_until"))
    return bool(
        until
        and until > (at or now())
        and cutover.get("previous_mode") == NfseMode.MUNICIPAL.value
        and not cutover.get("rolled_back_at")
        and effective_nfse_mode(dict(profile)) is NfseMode.NACIONAL
        and not forced_nacional(profile.get("tax_regime", ""))
    )


def fiscal_view(profile: Optional[Mapping[str, Any]], at: Optional[datetime] = None) -> Optional[dict]:
    """The staff-facing view of the fiscal state (`None` while the org has no profile)."""
    if profile is None:
        return None
    view = {k: profile.get(k) for k in VIEW_FIELDS}
    view["nfse_cutover"] = dict(profile.get("nfse_cutover") or {})
    view["auto_issue_invoices"] = bool(profile.get("auto_issue_invoices"))
    mode = effective_nfse_mode(dict(profile))
    forced = forced_nacional(profile.get("tax_regime", ""))
    view["nfse_mode"] = mode.value
    view["nfse_nacional_forced"] = forced
    view["certificate_status"] = certificate_status(profile, at)
    view["can_cutover"] = (not forced) and mode is NfseMode.MUNICIPAL
    view["can_rollback"] = cutover_window_open(profile, at)
    return view


def get_fiscal(db: Any, org_id: Any) -> Optional[dict]:
    return fiscal_view(get_profile(db, org_id))


# ─── versioned profile patch ─────────────────────────────────────────────


def _conflict(cur_v: int) -> CommerceError:
    return CommerceError(
        VERSAO_CONFLITANTE,
        "O perfil da loja foi alterado por outra pessoa. Recarregue e tente de novo.",
        409,
        details={"current_version": cur_v},
    )


def _require_profile(db: Any, org_id: Any) -> dict:
    profile = get_profile(db, org_id)
    if profile is None:
        raise CommerceError("perfil_ausente", "Cadastre o perfil da loja antes dos dados fiscais.", 409)
    return profile


def _save_patch(db: Any, org_id: Any, user_id: Any, profile: Mapping[str, Any], patch: Mapping[str, Any]) -> dict:
    """Apply `patch` at `version + 1` through the same ledger as `profile.put_profile`
    (ledger row first -> PK conflict = a concurrent save; compensated if the write fails)."""
    cur_v = int(profile["version"])
    stamp = now_iso()
    changes = {**dict(patch), "version": cur_v + 1, "updated_at": stamp, "updated_by": str(user_id) if user_id else None}
    row = {**dict(profile), **changes}
    ledger = {
        "org_id": str(org_id),
        "version": cur_v + 1,
        "snapshot": dict(row),
        "changed_by": str(user_id) if user_id else None,
        "changed_at": stamp,
    }
    try:
        tbl(db, _VERSIONS).insert(ledger).execute()
    except Exception as exc:  # noqa: BLE001 - narrowed right below
        if is_unique_violation(exc):
            raise _conflict(cur_v) from exc
        raise
    try:
        saved = first(tbl(db, _PROFILE).update(changes).eq("org_id", str(org_id)).eq("version", cur_v).execute())
        if saved is None:
            raise _conflict(cur_v)
    except Exception:
        logger.warning("commerce fiscal write failed after ledger insert; compensating (org=%s v=%s)", org_id, cur_v + 1)
        tbl(db, _VERSIONS).delete().eq("org_id", str(org_id)).eq("version", cur_v + 1).execute()
        raise
    return saved


# ─── update ──────────────────────────────────────────────────────────────


def _company_request(profile: Mapping[str, Any], patch: Mapping[str, Any], mode: NfseMode) -> CompanyRequest:
    merged = {**dict(profile), **dict(patch)}
    addr = merged.get("address") or {}
    treatments = {str(getattr(v, "value", v)) for v in (merged.get("tax_treatment") or {}).values()}
    return CompanyRequest(
        cnpj=digits(merged["cnpj"]),
        legal_name=merged["legal_name"],
        trade_name=merged.get("trade_name") or "",
        inscricao_municipal=merged.get("inscricao_municipal") or "",
        inscricao_estadual=merged.get("inscricao_estadual") or "",
        tax_regime=_REGIME_FOR_PROVIDER.get(str(merged.get("tax_regime")), "normal"),
        address=Address(
            street=str(addr.get("street", "")),
            number=str(addr.get("number", "")),
            complement=str(addr.get("complement", "")),
            district=str(addr.get("district", "")),
            city=str(addr.get("city", "")),
            city_ibge=str(merged.get("municipio_ibge") or addr.get("city_ibge", "")),
            state=str(addr.get("state", "")),
            zip_code=digits(str(addr.get("zip_code", ""))),
        ),
        email=merged.get("contact_email") or "",
        nfse_mode=mode,
        enable_nfe="goods_nfe" in treatments,
        company_ref=merged.get("invoice_company_ref") or None,
    )


def _check_mode_request(profile: Mapping[str, Any], requested: Optional[str]) -> None:
    if requested is None:
        return
    try:
        wanted = NfseMode(str(getattr(requested, "value", requested)))
    except ValueError:
        raise CommerceError("invalid", "Modo de NFS-e inválido.", 422, field="nfse_mode") from None
    if wanted is NfseMode.MUNICIPAL and forced_nacional(profile.get("tax_regime", "")):
        raise CommerceError(
            "nfse_nacional_obrigatorio",
            "MEI e Simples Nacional emitem NFS-e somente pelo Emissor Nacional.",
            422,
            field="nfse_mode",
        )
    if wanted is not effective_nfse_mode(dict(profile)):
        raise CommerceError(
            "nfse_mode_via_cutover",
            "A troca do modo de NFS-e só é feita pela migração aprovada (com janela de validação).",
            422,
            field="nfse_mode",
        )


def update_fiscal(
    db: Any,
    org_id: Any,
    user_id: Any,
    data: Mapping[str, Any],
    *,
    expected_version: int,
    provider: InvoiceProvider,
    at: Optional[datetime] = None,
) -> dict:
    """`PUT /fiscal`: validate -> register/update the company at the provider -> versioned save.

    `data` carries only the fields the client SENT. Raises 422 `nfse_nacional_obrigatorio` /
    `nfse_mode_via_cutover` / `municipio_invalido` / `emissao_automatica_requer_certificado`,
    409 `versao_conflitante` / `perfil_ausente`, 502/503 for the provider.
    """
    profile = _require_profile(db, org_id)
    cur_v = int(profile["version"])
    if int(expected_version) != cur_v:
        raise _conflict(cur_v)

    patch = {k: data[k] for k in FISCAL_FIELDS if k in data}
    _check_mode_request(profile, patch.pop("nfse_mode", None))
    if patch.get("municipio_ibge") is not None and not re.fullmatch(r"\d{7}", str(patch["municipio_ibge"])):
        raise CommerceError("municipio_invalido", "O código IBGE do município tem 7 dígitos.", 422, field="municipio_ibge")
    for key in ("inscricao_municipal", "inscricao_estadual"):
        if patch.get(key) is not None:
            patch[key] = str(patch[key]).strip()[:30] or None
    if "auto_issue_invoices" in patch:
        patch["auto_issue_invoices"] = bool(patch["auto_issue_invoices"])

    mode = effective_nfse_mode(profile)
    try:
        company = provider.ensure_company(_company_request(profile, patch, mode))
    except InvoiceProviderError as exc:
        raise map_provider_error(exc) from None
    patch["invoice_company_ref"] = company.ref
    if forced_nacional(profile.get("tax_regime", "")):
        patch["nfse_mode"] = NfseMode.NACIONAL.value  # persist the forced value explicitly

    if patch.get("auto_issue_invoices"):
        merged = {**profile, **patch}
        if certificate_status(merged, at) != "valido":
            raise CommerceError(
                "emissao_automatica_requer_certificado",
                "Envie um certificado A1 válido da empresa antes de ativar a emissão automática.",
                422,
                field="auto_issue_invoices",
            )
    return fiscal_view(_save_patch(db, org_id, user_id, profile, patch), at)  # type: ignore[return-value]


# ─── certificate ─────────────────────────────────────────────────────────


def upload_certificate(
    db: Any,
    org_id: Any,
    *,
    pfx: bytes,
    password: str,
    provider: InvoiceProvider,
    at: Optional[datetime] = None,
) -> dict:
    """Open the A1 locally (bounds + CNPJ match), forward it, store ONLY expiry + CNPJ.

    The bytes and the password never leave this call: not stored, not logged, not in an
    exception -- every failure is re-raised as a generic `CommerceError` `from None`.
    """
    profile = _require_profile(db, org_id)
    ref = profile.get("invoice_company_ref")
    if not ref:
        raise CommerceError("empresa_fiscal_ausente", "Salve os dados fiscais da loja antes de enviar o certificado.", 409)
    if len(pfx or b"") > MAX_CERTIFICATE_BYTES or len(password or "") > MAX_CERTIFICATE_PASSWORD_CHARS:
        raise CommerceError("certificado_invalido", "Certificado inválido. Confira o arquivo e a senha.", 422)
    expected = digits(profile["cnpj"])
    try:
        local = inspect_pkcs12(pfx, password, expected_cnpj=expected)
        if local.valid_until <= (at or now()):
            raise CommerceError("certificado_vencido", "O certificado está vencido.", 422)
        info = provider.upload_certificate(ref, pfx=pfx, password=password, expected_cnpj=expected)
    except InvoiceProviderError as exc:
        raise map_provider_error(exc) from None
    finally:
        pfx = b""
        password = ""
    stored = {
        "certificate_valid_until": info.valid_until.isoformat(),
        "certificate_cnpj": info.subject_cnpj or expected,
        "updated_at": now_iso(),
    }
    tbl(db, _PROFILE).update(stored).eq("org_id", str(org_id)).execute()
    return {"certificate_valid_until": stored["certificate_valid_until"], "certificate_cnpj": stored["certificate_cnpj"]}


# ─── approved cutover (D19) ──────────────────────────────────────────────


def _require_phrase(given: str, wanted: str) -> None:
    if given != wanted:
        raise CommerceError("confirmacao_invalida", f"Digite exatamente: {wanted}", 422, field="confirm")


def request_cutover(
    db: Any,
    org_id: Any,
    user_id: Any,
    *,
    confirm: str,
    provider: InvoiceProvider,
    at: Optional[datetime] = None,
) -> dict:
    """`municipal` -> `nacional`, on the org admin's typed approval. Opens the validation window."""
    _require_phrase(confirm, CUTOVER_PHRASE)
    profile = _require_profile(db, org_id)
    moment = at or now()
    if effective_nfse_mode(profile) is NfseMode.NACIONAL:
        raise CommerceError("nfse_ja_nacional", "A loja já emite NFS-e pelo Emissor Nacional.", 409)
    ref = profile.get("invoice_company_ref")
    if not ref:
        raise CommerceError("empresa_fiscal_ausente", "Salve os dados fiscais da loja antes de migrar.", 409)
    if certificate_status(profile, moment) != "valido":
        raise CommerceError("certificado_ausente", "Envie um certificado A1 válido antes de migrar.", 409)
    try:
        provider.set_nfse_mode(ref, NfseMode.NACIONAL)
    except InvoiceProviderError as exc:
        raise map_provider_error(exc) from None
    record = {
        "requested_at": moment.isoformat(),
        "approved_at": moment.isoformat(),
        "approved_by": str(user_id) if user_id else None,
        "previous_mode": NfseMode.MUNICIPAL.value,
        "validation_until": (moment + timedelta(days=VALIDATION_WINDOW_DAYS)).isoformat(),
    }
    return _save_switching(db, org_id, user_id, profile, ref, provider, NfseMode.NACIONAL, NfseMode.MUNICIPAL, record, moment)


def rollback_cutover(
    db: Any,
    org_id: Any,
    user_id: Any,
    *,
    confirm: str,
    provider: InvoiceProvider,
    at: Optional[datetime] = None,
) -> dict:
    """`nacional` -> `municipal`, only inside `validation_until`; recorded in `nfse_cutover`."""
    _require_phrase(confirm, ROLLBACK_PHRASE)
    profile = _require_profile(db, org_id)
    moment = at or now()
    if forced_nacional(profile.get("tax_regime", "")):
        raise CommerceError("nfse_nacional_obrigatorio", "MEI e Simples Nacional não voltam ao modo municipal.", 422)
    if not cutover_window_open(profile, moment):
        raise CommerceError("janela_rollback_encerrada", "A janela de validação da migração terminou.", 409)
    ref = profile["invoice_company_ref"]
    try:
        provider.set_nfse_mode(ref, NfseMode.MUNICIPAL)
    except InvoiceProviderError as exc:
        raise map_provider_error(exc) from None
    record = {**(profile.get("nfse_cutover") or {}), "rolled_back_at": moment.isoformat(), "rolled_back_by": str(user_id) if user_id else None}
    return _save_switching(db, org_id, user_id, profile, ref, provider, NfseMode.MUNICIPAL, NfseMode.NACIONAL, record, moment)


def _save_switching(
    db: Any, org_id: Any, user_id: Any, profile: Mapping[str, Any], ref: str, provider: InvoiceProvider,
    new_mode: NfseMode, old_mode: NfseMode, record: Mapping[str, Any], moment: datetime,
) -> dict:
    """Persist the new mode; if that fails after the provider already switched, switch it back
    (best effort, logged) so the provider and the store never disagree silently."""
    try:
        saved = _save_patch(db, org_id, user_id, profile, {"nfse_mode": new_mode.value, "nfse_cutover": dict(record)})
    except Exception:
        try:
            provider.set_nfse_mode(ref, old_mode)
        except InvoiceProviderError:
            logger.error("commerce fiscal: could not restore provider NFS-e mode after a failed save (org=%s)", org_id)
        raise
    return fiscal_view(saved, moment)  # type: ignore[return-value]


__all__ = [
    "FISCAL_FIELDS",
    "VIEW_FIELDS",
    "certificate_status",
    "cutover_window_open",
    "fiscal_view",
    "get_fiscal",
    "map_provider_error",
    "request_cutover",
    "rollback_cutover",
    "update_fiscal",
    "upload_certificate",
]

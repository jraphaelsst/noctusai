"""Enum + phrase parity: backend `fiscal_types` == the CONTRACT == the frontend `fiscalTypes.ts`."""
from __future__ import annotations

import re
from pathlib import Path

from noctusai_lib.domain.commerce import fiscal_types as ft

TS = Path(__file__).resolve().parents[3].parent / "frontend" / "src" / "commerce" / "fiscalTypes.ts"

CONTRACT = {
    "INVOICE_KINDS": ["nfe", "nfse"],
    "INVOICE_STATUSES": ["processing", "authorized", "rejected", "cancelled", "error"],
    "NFSE_MODES": ["nacional", "municipal"],
}


def _ts_array(name: str) -> list[str]:
    m = re.search(rf"export const {name} = \[(.*?)\] as const", TS.read_text(), re.S)
    assert m, name
    return re.findall(r"'([^']+)'", m.group(1))


def _ts_const(name: str):
    m = re.search(rf"export const {name} = (.+?);", TS.read_text())
    assert m, name
    return m.group(1)


def test_backend_enums_match_the_contract():
    assert [m.value for m in ft.InvoiceKind] == CONTRACT["INVOICE_KINDS"]
    assert [m.value for m in ft.InvoiceStatus] == CONTRACT["INVOICE_STATUSES"]
    assert [m.value for m in ft.NfseMode] == CONTRACT["NFSE_MODES"]


def test_frontend_arrays_equal_backend_enums():
    for name, expected in CONTRACT.items():
        assert _ts_array(name) == expected, name


def test_phrases_and_bounds_are_mirrored_exactly():
    assert _ts_const("NFSE_CUTOVER_PHRASE") == f"'{ft.CUTOVER_PHRASE}'"
    assert _ts_const("NFSE_ROLLBACK_PHRASE") == f"'{ft.ROLLBACK_PHRASE}'"
    assert ft.CUTOVER_PHRASE == "MIGRAR PARA NFS-E NACIONAL" and ft.ROLLBACK_PHRASE == "VOLTAR PARA NFS-E MUNICIPAL"
    assert _ts_const("MAX_CERTIFICATE_BYTES") == "64 * 1024" and ft.MAX_CERTIFICATE_BYTES == 64 * 1024
    assert _ts_const("MAX_CERTIFICATE_PASSWORD_CHARS") == "128" and ft.MAX_CERTIFICATE_PASSWORD_CHARS == 128


def test_view_interface_has_no_token_field():
    assert "token" not in TS.read_text().lower().replace("tokens", "")


def test_reexports_are_the_organ_owned_enums():
    from noctusai_lib.integrations.invoices import types as inv_types
    assert ft.InvoiceKind is inv_types.InvoiceKind and ft.NfseMode is inv_types.NfseMode and ft.InvoiceStatus is inv_types.InvoiceStatus


def test_forced_regimes_are_exactly_mei_and_simples():
    assert ft.NACIONAL_FORCED_REGIMES == {"mei", "simples"}
    assert ft.effective_nfse_mode({"tax_regime": "mei"}) is ft.NfseMode.NACIONAL
    assert ft.effective_nfse_mode({"tax_regime": "outro"}) is ft.NfseMode.MUNICIPAL
    assert ft.effective_nfse_mode({"tax_regime": "simples", "nfse_mode": "nacional"}) is ft.NfseMode.NACIONAL

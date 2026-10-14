"""Fiscal service: regime rule, versioning, certificate path, approved cutover + rollback."""
from __future__ import annotations

import logging
from datetime import timedelta

import pytest

from noctusai_lib.domain.commerce import fiscal as fs
from noctusai_lib.domain.commerce._common import now
from noctusai_lib.domain.commerce.errors import CommerceError
from noctusai_lib.domain.commerce.fiscal_types import CUTOVER_PHRASE, ROLLBACK_PHRASE
from noctusai_lib.integrations.invoices import FakeInvoiceProvider, InvoiceProviderError

from .conftest import ORG_A, ORG_B, USER_ID, VALID_CNPJ
from .fiscal_harness import PFX_PASSWORD, build_pfx, fh, fiscal_schema_cache, pfx_ok, seed_fiscal_org  # noqa: F401
from .conftest import seed_profile


class SpyProvider(FakeInvoiceProvider):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.uploads = 0

    def upload_certificate(self, company_ref, **kw):
        self.uploads += 1
        return super().upload_certificate(company_ref, **kw)


def code_of(excinfo) -> str:
    return excinfo.value.code


class TestRegimeRule:
    def test_simples_cannot_ask_for_municipal(self, fh):
        seed_profile(fh.db, tax_regime="simples")
        with pytest.raises(CommerceError) as e:
            fs.update_fiscal(fh.db, ORG_A, USER_ID, {"nfse_mode": "municipal"}, expected_version=1, provider=fh.provider)
        assert code_of(e) == "nfse_nacional_obrigatorio" and e.value.status_code == 422

    def test_mei_is_forced_nacional_and_persisted(self, fh):
        seed_profile(fh.db, tax_regime="mei")
        view = fs.update_fiscal(fh.db, ORG_A, USER_ID, {}, expected_version=1, provider=fh.provider)
        assert view["nfse_mode"] == "nacional" and view["nfse_nacional_forced"] and not view["can_cutover"]
        assert fs.get_profile(fh.db, ORG_A)["nfse_mode"] == "nacional"

    def test_other_regime_defaults_municipal_and_cannot_flip_by_put(self, fh):
        seed_profile(fh.db, tax_regime="lucro_presumido")
        assert fs.get_fiscal(fh.db, ORG_A)["nfse_mode"] == "municipal"
        with pytest.raises(CommerceError) as e:
            fs.update_fiscal(fh.db, ORG_A, USER_ID, {"nfse_mode": "nacional"}, expected_version=1, provider=fh.provider)
        assert code_of(e) == "nfse_mode_via_cutover"

    def test_effective_mode_reaches_the_provider(self, fh):
        seed_profile(fh.db, tax_regime="lucro_real")
        fs.update_fiscal(fh.db, ORG_A, USER_ID, {}, expected_version=1, provider=fh.provider)
        ref = fs.get_profile(fh.db, ORG_A)["invoice_company_ref"]
        assert fh.provider._companies[ref].nfse_mode.value == "municipal"


class TestUpdate:
    def test_requires_a_profile(self, fh):
        with pytest.raises(CommerceError) as e:
            fs.update_fiscal(fh.db, ORG_A, USER_ID, {}, expected_version=0, provider=fh.provider)
        assert code_of(e) == "perfil_ausente"

    def test_optimistic_version_conflict(self, fh):
        seed_profile(fh.db)
        fs.update_fiscal(fh.db, ORG_A, USER_ID, {"inscricao_municipal": "123"}, expected_version=1, provider=fh.provider)
        with pytest.raises(CommerceError) as e:
            fs.update_fiscal(fh.db, ORG_A, USER_ID, {"inscricao_municipal": "456"}, expected_version=1, provider=fh.provider)
        assert code_of(e) == "versao_conflitante" and e.value.status_code == 409

    def test_save_bumps_version_and_writes_the_ledger(self, fh):
        seed_profile(fh.db)
        view = fs.update_fiscal(fh.db, ORG_A, USER_ID, {"inscricao_municipal": " 99 ", "municipio_ibge": "3548500"}, expected_version=1, provider=fh.provider)
        assert view["version"] == 2 and view["inscricao_municipal"] == "99"
        versions = fh.db.table("commerce_store_profile_versions").select("*").eq("org_id", ORG_A).execute().data
        assert sorted(v["version"] for v in versions) == [1, 2]

    def test_ibge_must_have_7_digits(self, fh):
        seed_profile(fh.db)
        with pytest.raises(CommerceError) as e:
            fs.update_fiscal(fh.db, ORG_A, USER_ID, {"municipio_ibge": "123"}, expected_version=1, provider=fh.provider)
        assert code_of(e) == "municipio_invalido"

    def test_auto_issue_needs_a_valid_certificate(self, fh):
        seed_profile(fh.db)
        with pytest.raises(CommerceError) as e:
            fs.update_fiscal(fh.db, ORG_A, USER_ID, {"auto_issue_invoices": True}, expected_version=1, provider=fh.provider)
        assert code_of(e) == "emissao_automatica_requer_certificado"

    def test_provider_failure_is_a_generic_502_and_nothing_is_saved(self, fh):
        seed_profile(fh.db)

        class Down:
            name = "down"

            def ensure_company(self, request):
                raise InvoiceProviderError("down", "SECRET-PROVIDER-TEXT", code="x", retryable=True)

        with pytest.raises(CommerceError) as e:
            fs.update_fiscal(fh.db, ORG_A, USER_ID, {"inscricao_municipal": "1"}, expected_version=1, provider=Down())
        assert e.value.status_code == 502 and "SECRET-PROVIDER-TEXT" not in str(e.value.message)
        assert fs.get_profile(fh.db, ORG_A)["version"] == 1

    def test_view_never_carries_tokens_and_is_a_whitelist(self, fh):
        view = seed_fiscal_org(fh)
        assert not any("token" in k for k in view)
        assert set(view) >= {"nfse_mode", "certificate_status", "can_cutover", "can_rollback", "version"}


class TestCertificate:
    def test_happy_path_stores_only_expiry_and_cnpj(self, fh, pfx_ok):
        seed_fiscal_org(fh, cert=False, auto=False)
        pfx, not_after = pfx_ok
        out = fs.upload_certificate(fh.db, ORG_A, pfx=pfx, password=PFX_PASSWORD, provider=fh.provider)
        assert out["certificate_cnpj"] == VALID_CNPJ
        row = fs.get_profile(fh.db, ORG_A)
        assert row["certificate_cnpj"] == VALID_CNPJ and row["certificate_valid_until"]
        blob = repr(row)
        assert PFX_PASSWORD not in blob
        assert fs.get_fiscal(fh.db, ORG_A)["certificate_status"] == "valido"

    def test_cnpj_mismatch_is_422_before_any_provider_call(self, fh):
        fh.provider = SpyProvider()
        seed_fiscal_org(fh, cert=False, auto=False)
        pfx, _ = build_pfx(cnpj="12345678000190")
        with pytest.raises(CommerceError) as e:
            fs.upload_certificate(fh.db, ORG_A, pfx=pfx, password=PFX_PASSWORD, provider=fh.provider)
        assert code_of(e) == "certificado_cnpj_divergente" and e.value.status_code == 422 and fh.provider.uploads == 0

    @pytest.mark.parametrize("pfx,password", [(b"not-a-pfx", "x"), (b"\x00" * (64 * 1024 + 1), "x")])
    def test_garbage_or_oversize_is_generic_invalid(self, fh, pfx, password):
        seed_fiscal_org(fh, cert=False, auto=False)
        with pytest.raises(CommerceError) as e:
            fs.upload_certificate(fh.db, ORG_A, pfx=pfx, password=password, provider=fh.provider)
        assert code_of(e) == "certificado_invalido"

    def test_wrong_password_and_long_password_look_identical(self, fh, pfx_ok):
        seed_fiscal_org(fh, cert=False, auto=False)
        pfx, _ = pfx_ok
        for pw in ("wrong-password", "p" * 129):
            with pytest.raises(CommerceError) as e:
                fs.upload_certificate(fh.db, ORG_A, pfx=pfx, password=pw, provider=fh.provider)
            assert code_of(e) == "certificado_invalido"

    def test_needs_a_registered_company(self, fh, pfx_ok):
        seed_profile(fh.db)
        with pytest.raises(CommerceError) as e:
            fs.upload_certificate(fh.db, ORG_A, pfx=pfx_ok[0], password=PFX_PASSWORD, provider=fh.provider)
        assert code_of(e) == "empresa_fiscal_ausente"

    def test_expired_certificate_is_refused(self, fh):
        seed_fiscal_org(fh, cert=False, auto=False)
        pfx, _ = build_pfx(days=1)
        with pytest.raises(CommerceError) as e:
            fs.upload_certificate(fh.db, ORG_A, pfx=pfx, password=PFX_PASSWORD, provider=fh.provider, at=now() + timedelta(days=5))
        assert code_of(e) == "certificado_vencido"

    def test_no_secret_in_logs_or_exception_chain(self, fh, pfx_ok, caplog):
        seed_fiscal_org(fh, cert=False, auto=False)
        pfx, _ = pfx_ok
        caplog.set_level(logging.DEBUG)
        with pytest.raises(CommerceError) as e:
            fs.upload_certificate(fh.db, ORG_A, pfx=pfx, password="wrong-password-ZZZ", provider=fh.provider)
        text = caplog.text + repr(e.value) + str(e.value.__cause__) + str(e.value.__context__)
        assert "wrong-password-ZZZ" not in text and pfx.hex()[:64] not in text and e.value.__cause__ is None


class TestCutover:
    def _ready(self, fh):
        return seed_fiscal_org(fh, regime="lucro_presumido", auto=False)

    def test_phrase_must_match_exactly(self, fh):
        self._ready(fh)
        for bad in ("migrar para nfs-e nacional", CUTOVER_PHRASE + " ", ""):
            with pytest.raises(CommerceError) as e:
                fs.request_cutover(fh.db, ORG_A, USER_ID, confirm=bad, provider=fh.provider)
            assert code_of(e) == "confirmacao_invalida"

    def test_cutover_switches_provider_and_opens_a_60_day_window(self, fh):
        self._ready(fh)
        at = now()
        view = fs.request_cutover(fh.db, ORG_A, USER_ID, confirm=CUTOVER_PHRASE, provider=fh.provider, at=at)
        assert view["nfse_mode"] == "nacional" and view["can_rollback"] and not view["can_cutover"]
        c = view["nfse_cutover"]
        assert c["approved_by"] == USER_ID and c["previous_mode"] == "municipal"
        assert c["validation_until"].startswith((at + timedelta(days=60)).date().isoformat())
        ref = fs.get_profile(fh.db, ORG_A)["invoice_company_ref"]
        assert fh.provider._companies[ref].nfse_mode.value == "nacional"

    def test_requires_certificate_company_and_not_already_nacional(self, fh):
        seed_fiscal_org(fh, regime="lucro_real", cert=False, auto=False)
        with pytest.raises(CommerceError) as e:
            fs.request_cutover(fh.db, ORG_A, USER_ID, confirm=CUTOVER_PHRASE, provider=fh.provider)
        assert code_of(e) == "certificado_ausente"

    def test_simples_store_cannot_cutover_it_is_already_nacional(self, fh):
        seed_fiscal_org(fh, regime="simples", auto=False)
        with pytest.raises(CommerceError) as e:
            fs.request_cutover(fh.db, ORG_A, USER_ID, confirm=CUTOVER_PHRASE, provider=fh.provider)
        assert code_of(e) == "nfse_ja_nacional"

    def test_rollback_inside_the_window_is_recorded(self, fh):
        self._ready(fh)
        t0 = now()
        fs.request_cutover(fh.db, ORG_A, USER_ID, confirm=CUTOVER_PHRASE, provider=fh.provider, at=t0)
        view = fs.rollback_cutover(fh.db, ORG_A, "other-admin", confirm=ROLLBACK_PHRASE, provider=fh.provider, at=t0 + timedelta(days=59))
        assert view["nfse_mode"] == "municipal" and view["can_cutover"] and not view["can_rollback"]
        assert view["nfse_cutover"]["rolled_back_by"] == "other-admin" and view["nfse_cutover"]["rolled_back_at"]

    def test_rollback_after_the_window_is_refused(self, fh):
        self._ready(fh)
        t0 = now()
        fs.request_cutover(fh.db, ORG_A, USER_ID, confirm=CUTOVER_PHRASE, provider=fh.provider, at=t0)
        with pytest.raises(CommerceError) as e:
            fs.rollback_cutover(fh.db, ORG_A, USER_ID, confirm=ROLLBACK_PHRASE, provider=fh.provider, at=t0 + timedelta(days=61))
        assert code_of(e) == "janela_rollback_encerrada" and e.value.status_code == 409
        assert fs.get_fiscal(fh.db, ORG_A)["nfse_mode"] == "nacional"

    def test_rollback_needs_its_own_phrase_and_a_cutover(self, fh):
        self._ready(fh)
        with pytest.raises(CommerceError) as e:
            fs.rollback_cutover(fh.db, ORG_A, USER_ID, confirm=CUTOVER_PHRASE, provider=fh.provider)
        assert code_of(e) == "confirmacao_invalida"
        with pytest.raises(CommerceError) as e:
            fs.rollback_cutover(fh.db, ORG_A, USER_ID, confirm=ROLLBACK_PHRASE, provider=fh.provider)
        assert code_of(e) == "janela_rollback_encerrada"

    def test_forced_regime_never_rolls_back(self, fh):
        seed_fiscal_org(fh, regime="mei", auto=False)
        with pytest.raises(CommerceError) as e:
            fs.rollback_cutover(fh.db, ORG_A, USER_ID, confirm=ROLLBACK_PHRASE, provider=fh.provider)
        assert code_of(e) == "nfse_nacional_obrigatorio"

    def test_a_failed_save_restores_the_provider_mode(self, fh):
        from noctusai_lib.integrations.invoices import NfseMode

        self._ready(fh)
        profile = fs.get_profile(fh.db, ORG_A)
        ref = profile["invoice_company_ref"]
        fh.provider.set_nfse_mode(ref, NfseMode.NACIONAL)  # what request_cutover did just before the save
        stale = {**profile, "version": 0}  # the conditional UPDATE matches nothing -> versao_conflitante
        with pytest.raises(CommerceError) as e:
            fs._save_switching(fh.db, ORG_A, USER_ID, stale, ref, fh.provider, NfseMode.NACIONAL, NfseMode.MUNICIPAL, {}, now())
        assert code_of(e) == "versao_conflitante"
        assert fh.provider._companies[ref].nfse_mode is NfseMode.MUNICIPAL


def test_other_orgs_fiscal_data_is_invisible(fh):
    seed_fiscal_org(fh, ORG_A, auto=False)
    assert fs.get_fiscal(fh.db, ORG_B) is None

"""Store profile: CNPJ validation, the versioned ledger, 409 on conflict, platform fee gate."""
from __future__ import annotations

import pytest

from noctusai_lib.domain.commerce import CommerceError, profile
from noctusai_lib.integrations.cnpj_registry import CnpjNotFoundError, CnpjRegistryUpstreamError, FakeCnpjRegistryLookup

from .conftest import ORG_A, ORG_B, USER_ID, VALID_CNPJ, run, seed_profile


def _data(**over):
    base = {
        "legal_name": "Loja LTDA", "trade_name": "Loja", "cnpj": VALID_CNPJ, "tax_regime": "mei",
        "tax_treatment": {}, "locale": "pt-BR", "currency": "BRL", "brand_tokens": {}, "address": {},
        "contact_email": None, "contact_phone": None,
    }
    base.update(over)
    return base


class TestCnpj:
    def test_valid_cnpj_is_stored_normalised(self, db):
        saved = profile.put_profile(
            db, ORG_A, USER_ID, _data(cnpj="11.222.333/0001-81"), expected_version=0, is_platform_admin=False
        )
        assert saved["cnpj"] == VALID_CNPJ and saved["version"] == 1

    @pytest.mark.parametrize("bad", ["11222333000182", "00000000000000", "123", "", "ABCDEFGHIJKLMN"])
    def test_invalid_cnpj_is_422_cnpj_invalido(self, db, bad):
        with pytest.raises(CommerceError) as exc:
            profile.put_profile(db, ORG_A, USER_ID, _data(cnpj=bad), expected_version=0, is_platform_admin=False)
        assert exc.value.code == "cnpj_invalido" and exc.value.status_code == 422
        assert db.table("commerce_store_profiles").select("*").execute().data == []

    def test_alphanumeric_cnpj_is_accepted(self, db):
        # 12.ABC.345/01DE-35 is the RFB's published alphanumeric example.
        saved = profile.put_profile(
            db, ORG_A, USER_ID, _data(cnpj="12.ABC.345/01DE-35"), expected_version=0, is_platform_admin=False
        )
        assert saved["cnpj"] == "12ABC34501DE35"


class TestVersionedLedger:
    def test_first_save_needs_expected_version_zero(self, db):
        with pytest.raises(CommerceError) as exc:
            profile.put_profile(db, ORG_A, USER_ID, _data(), expected_version=3, is_platform_admin=False)
        assert exc.value.code == "versao_conflitante" and exc.value.status_code == 409

    def test_each_save_appends_a_version_with_a_snapshot(self, db):
        seed_profile(db)
        profile.put_profile(db, ORG_A, USER_ID, _data(trade_name="Nova"), expected_version=1, is_platform_admin=False)
        versions = profile.list_versions(db, ORG_A)
        assert [v["version"] for v in versions] == [2, 1] or {v["version"] for v in versions} == {1, 2}
        latest = next(v for v in versions if v["version"] == 2)
        assert latest["snapshot"]["trade_name"] == "Nova" and latest["changed_by"] == USER_ID
        assert profile.get_profile(db, ORG_A)["version"] == 2

    def test_stale_expected_version_is_409_and_writes_nothing(self, db):
        seed_profile(db)
        profile.put_profile(db, ORG_A, USER_ID, _data(trade_name="Dois"), expected_version=1, is_platform_admin=False)
        with pytest.raises(CommerceError) as exc:
            profile.put_profile(db, ORG_A, USER_ID, _data(trade_name="Stale"), expected_version=1, is_platform_admin=False)
        assert exc.value.code == "versao_conflitante" and exc.value.details == {"current_version": 2}
        assert profile.get_profile(db, ORG_A)["trade_name"] == "Dois"
        assert len(profile.list_versions(db, ORG_A)) == 2

    def test_a_concurrent_winner_surfaces_as_409_via_the_pk_conflict(self, db):
        """Two saves read version 1; the loser's ledger INSERT hits the PK."""
        seed_profile(db)

        class RacyDb:
            """A PostgREST stub whose ledger INSERT loses the race (23505), delegating the rest."""

            def __init__(self, inner):
                self._inner = inner

            def table(self, name):
                if name == "commerce_store_profile_versions":
                    raise_ = _UniqueViolation
                    return _Raising(raise_)
                return self._inner.table(name)

        with pytest.raises(CommerceError) as exc:
            profile.put_profile(RacyDb(db), ORG_A, USER_ID, _data(), expected_version=1, is_platform_admin=False)
        assert exc.value.code == "versao_conflitante"

    def test_a_failed_profile_write_compensates_the_ledger_row(self, db):
        seed_profile(db)

        class BrokenProfileDb:
            def __init__(self, inner):
                self._inner = inner

            def table(self, name):
                if name == "commerce_store_profiles":
                    return _BrokenUpdate(self._inner.table(name))
                return self._inner.table(name)

        with pytest.raises(RuntimeError):
            profile.put_profile(BrokenProfileDb(db), ORG_A, USER_ID, _data(), expected_version=1, is_platform_admin=False)
        # v2 must not linger, or every later save would 409 forever.
        assert [v["version"] for v in profile.list_versions(db, ORG_A)] == [1]


class _UniqueViolation(Exception):
    code = "23505"


class _Raising:
    def __init__(self, exc_type):
        self._exc = exc_type

    def select(self, *a, **k):
        return self

    def insert(self, *a, **k):
        return self

    def execute(self):
        raise self._exc("duplicate key value violates unique constraint")


class _BrokenUpdate:
    def __init__(self, inner):
        self._inner = inner

    def select(self, *a, **k):
        return self._inner.select(*a, **k)

    def update(self, *a, **k):
        raise RuntimeError("boom")

    def insert(self, *a, **k):
        return self._inner.insert(*a, **k)


class TestPlatformFee:
    def test_only_a_platform_admin_can_set_the_fee(self, db):
        seed_profile(db)
        saved = profile.put_profile(
            db, ORG_A, USER_ID, _data(platform_fee_bps=250), expected_version=1, is_platform_admin=False
        )
        assert saved["platform_fee_bps"] == 0  # silently ignored (CONTRACT §3)

    def test_admin_sets_it_and_a_later_non_admin_save_keeps_it(self, db):
        seed_profile(db)
        profile.put_profile(db, ORG_A, USER_ID, _data(platform_fee_bps=250), expected_version=1, is_platform_admin=True)
        kept = profile.put_profile(
            db, ORG_A, USER_ID, _data(platform_fee_bps=9999, trade_name="X"), expected_version=2, is_platform_admin=False
        )
        assert kept["platform_fee_bps"] == 250 and kept["trade_name"] == "X"


class TestCnpjLookup:
    def test_prefill_from_the_registry(self):
        out = run(profile.cnpj_prefill(FakeCnpjRegistryLookup(), "11.222.333/0001-81"))
        assert out["cnpj"] == VALID_CNPJ and out["source"] == "fake" and out["legal_name"]

    def test_invalid_digits_never_cost_a_network_call(self):
        lookup = FakeCnpjRegistryLookup()
        with pytest.raises(CommerceError) as exc:
            run(profile.cnpj_prefill(lookup, "11222333000182"))
        assert exc.value.code == "cnpj_invalido" and lookup.chamadas == []

    def test_not_found_is_404(self):
        with pytest.raises(CommerceError) as exc:
            run(profile.cnpj_prefill(FakeCnpjRegistryLookup(erro=CnpjNotFoundError(VALID_CNPJ, source="fake")), VALID_CNPJ))
        assert exc.value.status_code == 404

    def test_upstream_failure_is_502_not_a_guess(self):
        with pytest.raises(CommerceError) as exc:
            run(profile.cnpj_prefill(FakeCnpjRegistryLookup(erro=CnpjRegistryUpstreamError("down")), VALID_CNPJ))
        assert exc.value.status_code == 502


def test_profiles_are_org_scoped(db):
    seed_profile(db, ORG_A)
    assert profile.get_profile(db, ORG_B) is None
    assert profile.current_version(db, ORG_B) == 0

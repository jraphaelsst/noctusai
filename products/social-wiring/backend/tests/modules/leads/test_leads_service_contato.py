"""`contato_norm` / `contato_tipo` derivation on the CRUD write path.

These exist because `MockSupabaseClient` has no triggers: without the
service-layer derivation the suite would assert a row shape production never
produces, and the mirrored trigger (migration 037) would be unverified here.
Every case below must match `social_wiring.canonicalize_lead_contato()`.
"""
from __future__ import annotations

from app.modules.leads.services.leads_service import _derive_contato_fields


class TestDeriveContatoFields:
    def test_a_phone_is_canonicalized(self):
        out = _derive_contato_fields({"contato": "11 99457.3387"})
        assert out["contato_norm"] == "+5511994573387"
        assert out["contato_tipo"] == "telefone"

    def test_an_email_is_lowercased(self):
        out = _derive_contato_fields({"contato": "Maria@Example.COM"})
        assert out["contato_norm"] == "maria@example.com"
        assert out["contato_tipo"] == "email"

    def test_an_unparseable_phone_keeps_its_type_with_no_norm(self):
        # Nothing may key on a value we had to guess, but it IS a phone —
        # typing it `desconhecido` would hide it from the filter a human
        # would use to find and fix it.
        out = _derive_contato_fields({"contato": "11 9999-9999"})
        assert out["contato_norm"] is None
        assert out["contato_tipo"] == "telefone"

    def test_a_short_string_is_desconhecido(self):
        out = _derive_contato_fields({"contato": "1234"})
        assert out["contato_norm"] is None
        assert out["contato_tipo"] == "desconhecido"

    def test_blank_clears_both(self):
        out = _derive_contato_fields({"contato": "   "})
        assert out["contato_norm"] is None
        assert out["contato_tipo"] == "desconhecido"

    def test_an_update_that_does_not_touch_contato_derives_nothing(self):
        # The trigger is `UPDATE OF contato`, so it would not fire either.
        # Re-deriving here would disagree with the DB.
        payload = {"status": "Em atendimento"}
        assert _derive_contato_fields(payload) == payload

    def test_an_insert_without_contato_still_gets_the_defaults(self):
        # The trigger runs on EVERY insert and stamps 'desconhecido' for a row
        # with no contact. Without `require_defaults` the mock's row shape
        # would differ from the real one — the exact drift this function
        # exists to prevent.
        out = _derive_contato_fields({"cliente_nome": "Ana"}, require_defaults=True)
        assert out["contato_norm"] is None
        assert out["contato_tipo"] == "desconhecido"

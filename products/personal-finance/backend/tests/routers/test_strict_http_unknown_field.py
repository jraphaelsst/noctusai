"""Regression test — StrictHttpModel rejects unknown request keys with 422.

Closes the silent-drop bug-class (memory `feedback_pydantic_silent_drop_kills_writes`):
pre-migration, an unknown field on `ContaCreate` was silently dropped by Pydantic's
`extra="ignore"` default — the POST returned 200 with the unknown field gone, mimicking
a successful write of misrouted data. Post-migration, `noctusai_lib.api.StrictHttpModel`
inherits `extra="forbid"`, so the request returns **422 Unprocessable Entity**.
"""
from __future__ import annotations


class TestStrictHttpUnknownFieldRejected:
    def test_create_conta_rejects_unknown_field_with_422(self, client):
        # Representative HTTP-boundary schema: ContaCreate inherits StrictHttpModel.
        # An unknown key on the JSON body must produce 422, not 200.
        response = client.post(
            "/api/contas",
            json={
                "nome": "Conta Corrente",
                "tipo": "corrente",
                "instituicao": "Banco do Brasil",
                "saldo": 5000.00,
                "definitely_not_a_field": "trojan",
            },
        )
        assert response.status_code == 422
        body = response.json()
        # FastAPI's 422 body names the offending location somewhere in the detail.
        detail_str = str(body.get("detail", body))
        assert "definitely_not_a_field" in detail_str

"""D1 write policy for `imovel_dados` (migration 154) — `campos_extraidos_
service.aplicar`, the conflict queue and its admin decision, and the human
PATCH's `manual` stamping the policy depends on.

WHAT THESE PIN
--------------
- an EMPTY field is filled with provenance and left machine-pending;
- the same value again writes nothing;
- a HUMAN value that disagrees opens a conflict (never overwrites), and a
  second reading does not open a second one;
- a MACHINE value that disagrees is a conflict too (never machine-over-machine);
- a conflict a human REJECTED is not re-opened by the same reading;
- accept lands the proposed value CONFIRMED by the decider; reject leaves
  the field; deciding is admin-only (strict 403) and first-decision-wins (400);
- groups (título pointer / ônus acts) compare by act identity, not offsets;
- `PATCH .../dados` stamps `manual` on the three new quintets (and clears
  them with the value).
"""
from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from noctusai_lib.testing import TEST_USER_ID

from app.modules.imovel_hub import campos_extraidos_service as campos_svc
from tests.modules.imovel_hub.conftest import CODIGO, ORG_ID, auth, dados_row, seed

ORG = UUID(ORG_ID)


def _dados(scoped) -> dict:
    return [r for r in scoped.table("imovel_dados").select("*").execute().data
            if r["codigo"] == CODIGO][0]


def _conflitos(scoped) -> list[dict]:
    return scoped.table("imovel_campo_conflitos").select("*").execute().data


def _make_admin(client) -> None:
    client.mock_supabase.set_table_data(
        "noctus_users", [{"id": TEST_USER_ID, "org_id": ORG_ID, "org_role": "owner"}]
    )


class TestAplicar:
    def test_an_empty_field_is_filled_machine_pending(self, client, scoped):
        seed(scoped)
        doc = str(uuid4())
        r = campos_svc.aplicar(
            scoped, ORG, CODIGO, "numero_registro_imoveis",
            "1º Oficial de Registro de Imóveis de Cotia",
            origem="matricula", documento_id=doc,
        )
        assert r.status == campos_svc.PREENCHIDO
        row = _dados(scoped)
        assert row["numero_registro_imoveis"] == "1º Oficial de Registro de Imóveis de Cotia"
        assert row["numero_registro_imoveis_origem"] == "matricula"
        assert row["numero_registro_imoveis_documento_id"] == doc
        assert row["numero_registro_imoveis_em"]
        assert row["numero_registro_imoveis_confirmado_em"] is None

        body = client.get(f"/api/imoveis/{CODIGO}/dados", headers=auth()).json()
        assert body["proveniencia"]["numero_registro_imoveis"]["pendente"] is True

    def test_the_same_value_again_writes_nothing(self, scoped):
        seed(scoped, dados=[dados_row(
            prefeitura_cadastro_imobiliario="123.456.7-8",
            prefeitura_cadastro_imobiliario_origem="manual",
        )])
        r = campos_svc.aplicar(
            scoped, ORG, CODIGO, "prefeitura_cadastro_imobiliario", "12345678",
            origem="guia_iptu",
        )
        assert r.status == campos_svc.IGUAL
        assert _conflitos(scoped) == []

    def test_a_human_value_is_never_overwritten_a_conflict_opens(self, scoped):
        seed(scoped, dados=[dados_row(
            numero_registro_imoveis="2º RI de Barueri",
            numero_registro_imoveis_origem="manual",
        )])
        r = campos_svc.aplicar(
            scoped, ORG, CODIGO, "numero_registro_imoveis", "1º RI de Barueri",
            origem="matricula", confianca="alta",
        )
        assert r.status == campos_svc.CONFLITO
        assert _dados(scoped)["numero_registro_imoveis"] == "2º RI de Barueri"
        [c] = _conflitos(scoped)
        assert c["valor_anterior"] == "2º RI de Barueri"
        assert c["origem_anterior"] == "manual"
        assert c["valor_proposto"] == "1º RI de Barueri"
        assert c["status"] == "pendente"

        # A second reading while one is pending does not pile up.
        r2 = campos_svc.aplicar(
            scoped, ORG, CODIGO, "numero_registro_imoveis", "3º RI de Barueri",
            origem="matricula",
        )
        assert r2.status == campos_svc.CONFLITO_EXISTENTE
        assert len(_conflitos(scoped)) == 1

    def test_machine_versus_machine_is_a_conflict_too(self, scoped):
        seed(scoped, dados=[dados_row(
            numero_matricula="45.678", numero_matricula_origem="matricula",
        )])
        r = campos_svc.aplicar(
            scoped, ORG, CODIGO, "numero_matricula", "45.679", origem="matricula",
        )
        assert r.status == campos_svc.CONFLITO
        assert _dados(scoped)["numero_matricula"] == "45.678"

    def test_a_rejected_reading_is_not_reopened(self, scoped):
        seed(
            scoped,
            dados=[dados_row(situacao_onus="livre", situacao_onus_origem="manual")],
            conflitos=[{
                "id": str(uuid4()), "org_id": ORG_ID, "codigo": CODIGO,
                "campo": "situacao_onus", "valor_anterior": "livre",
                "origem_anterior": "manual", "valor_proposto": "hipoteca",
                "origem_proposto": "matricula", "status": "rejeitado",
                "created_at": "2026-09-01T00:00:00+00:00",
            }],
        )
        r = campos_svc.aplicar(
            scoped, ORG, CODIGO, "situacao_onus", "hipoteca", origem="matricula",
        )
        assert r.status == campos_svc.REJEITADO_ANTES
        assert len(_conflitos(scoped)) == 1

    def test_a_group_compares_by_act_identity_not_offsets(self, scoped):
        eid, ato = str(uuid4()), str(uuid4())
        seed(scoped, dados=[dados_row(
            titulo_aquisitivo_extracao_id=eid, titulo_aquisitivo_ato_id=ato,
            titulo_aquisitivo_char_inicio=10, titulo_aquisitivo_char_fim=90,
            titulo_aquisitivo_origem="manual",
        )])
        r = campos_svc.aplicar(
            scoped, ORG, CODIGO, "titulo_aquisitivo",
            {
                "titulo_aquisitivo_extracao_id": eid,
                "titulo_aquisitivo_ato_id": ato,
                "titulo_aquisitivo_char_inicio": 8,
                "titulo_aquisitivo_char_fim": 88,
            },
            origem="sugerido",
        )
        assert r.status == campos_svc.IGUAL

    def test_an_empty_reading_is_refused_loudly(self, scoped):
        seed(scoped)
        with pytest.raises(ValueError):
            campos_svc.aplicar(scoped, ORG, CODIGO, "situacao_onus", "", origem="matricula")


class TestPrefeituraPrecedence:
    """Owner rule (2026-09-24), `prefeitura_cadastro_imobiliario` only: a
    guia_iptu/cnd_iptu reading outranks a matrícula-sourced, unconfirmed
    value — the live repro (folder 883): the matrícula gave
    `23231.42.11.0377.00.000-1`, the Guia IPTU gave
    `23231.42.11.0377.00.000` (no DV), and a conflict opened."""

    def test_a_prefeitura_document_replaces_an_unconfirmed_matricula_value(self, scoped):
        seed(scoped, dados=[dados_row(
            prefeitura_cadastro_imobiliario="23231.42.11.0377.00.000-9",
            prefeitura_cadastro_imobiliario_origem="matricula",
        )])
        doc = str(uuid4())
        r = campos_svc.aplicar(
            scoped, ORG, CODIGO, "prefeitura_cadastro_imobiliario",
            "23231.42.11.9999.00.000", origem="guia_iptu", documento_id=doc,
        )
        assert r.status == campos_svc.SUBSTITUIDO
        assert r.preenchido is True
        row = _dados(scoped)
        assert row["prefeitura_cadastro_imobiliario"] == "23231.42.11.9999.00.000"
        assert row["prefeitura_cadastro_imobiliario_origem"] == "guia_iptu"
        assert row["prefeitura_cadastro_imobiliario_documento_id"] == doc
        assert row["prefeitura_cadastro_imobiliario_confirmado_por"] is None
        assert row["prefeitura_cadastro_imobiliario_confirmado_em"] is None
        assert _conflitos(scoped) == []

    def test_a_trailing_dv_alone_is_not_a_conflict(self, scoped):
        """The exact live shape: the matrícula's value carries no DV, the
        Guia IPTU's does (or vice-versa) — same cadastral number."""
        seed(scoped, dados=[dados_row(
            prefeitura_cadastro_imobiliario="23231.42.11.0377.00.000",
            prefeitura_cadastro_imobiliario_origem="matricula",
        )])
        r = campos_svc.aplicar(
            scoped, ORG, CODIGO, "prefeitura_cadastro_imobiliario",
            "23231.42.11.0377.00.000-1", origem="guia_iptu",
        )
        assert r.status == campos_svc.IGUAL
        assert _conflitos(scoped) == []
        # The DV-bearing reading is offered nowhere near this — the field
        # keeps whatever it already had, exactly like any other IGUAL.
        assert _dados(scoped)["prefeitura_cadastro_imobiliario"] == "23231.42.11.0377.00.000"

    def test_a_human_confirmed_value_still_opens_a_conflict(self, scoped):
        seed(scoped, dados=[dados_row(
            prefeitura_cadastro_imobiliario="23231.42.11.0377.00.000",
            prefeitura_cadastro_imobiliario_origem="matricula",
            prefeitura_cadastro_imobiliario_confirmado_por=TEST_USER_ID,
            prefeitura_cadastro_imobiliario_confirmado_em="2026-09-01T00:00:00+00:00",
        )])
        r = campos_svc.aplicar(
            scoped, ORG, CODIGO, "prefeitura_cadastro_imobiliario",
            "23231.42.11.9999.00.000", origem="guia_iptu",
        )
        assert r.status == campos_svc.CONFLITO
        assert _dados(scoped)["prefeitura_cadastro_imobiliario"] == "23231.42.11.0377.00.000"

    def test_a_human_typed_value_still_opens_a_conflict(self, scoped):
        seed(scoped, dados=[dados_row(
            prefeitura_cadastro_imobiliario="23231.42.11.0377.00.000",
            prefeitura_cadastro_imobiliario_origem="manual",
        )])
        r = campos_svc.aplicar(
            scoped, ORG, CODIGO, "prefeitura_cadastro_imobiliario",
            "23231.42.11.9999.00.000", origem="guia_iptu",
        )
        assert r.status == campos_svc.CONFLITO

    def test_the_precedence_never_applies_to_other_fields(self, scoped):
        """`numero_matricula`/`numero_registro_imoveis` keep the ordinary
        D1 rule — the exception is named to ONE field."""
        seed(scoped, dados=[dados_row(
            numero_matricula="3917", numero_matricula_origem="matricula",
        )])
        r = campos_svc.aplicar(
            scoped, ORG, CODIGO, "numero_matricula", "4000", origem="guia_iptu",
        )
        assert r.status == campos_svc.CONFLITO

    def test_a_matricula_reading_never_replaces_a_prefeitura_one(self, scoped):
        """Precedence is directional — `origem` must be a prefeitura
        source; the matrícula never wins this one back."""
        seed(scoped, dados=[dados_row(
            prefeitura_cadastro_imobiliario="23231.42.11.0377.00.000",
            prefeitura_cadastro_imobiliario_origem="guia_iptu",
        )])
        r = campos_svc.aplicar(
            scoped, ORG, CODIGO, "prefeitura_cadastro_imobiliario",
            "23231.42.11.9999.00.000", origem="matricula",
        )
        assert r.status == campos_svc.CONFLITO


class TestDecidir:
    def _com_conflito(self, scoped) -> dict:
        seed(scoped, dados=[dados_row(
            numero_registro_imoveis="2º RI", numero_registro_imoveis_origem="manual",
        )])
        return campos_svc.aplicar(
            scoped, ORG, CODIGO, "numero_registro_imoveis", "1º RI",
            origem="matricula", documento_id=str(uuid4()),
        ).conflito

    def test_listing_is_open_to_members(self, client, scoped):
        c = self._com_conflito(scoped)
        body = client.get(f"/api/imoveis/{CODIGO}/conflitos", headers=auth()).json()
        assert [i["id"] for i in body["items"]] == [c["id"]]

    def test_a_member_cannot_decide(self, client, scoped):
        c = self._com_conflito(scoped)
        r = client.put(
            f"/api/imoveis/{CODIGO}/conflitos/{c['id']}/decidir",
            json={"aceitar": True}, headers=auth(),
        )
        assert r.status_code == 403, r.text
        assert _dados(scoped)["numero_registro_imoveis"] == "2º RI"

    def test_accept_lands_the_value_confirmed_by_the_decider(self, client, scoped):
        _make_admin(client)
        c = self._com_conflito(scoped)
        r = client.put(
            f"/api/imoveis/{CODIGO}/conflitos/{c['id']}/decidir",
            json={"aceitar": True}, headers=auth(),
        )
        assert r.status_code == 200, r.text
        assert r.json()["valor_anterior"] == "2º RI"
        row = _dados(scoped)
        assert row["numero_registro_imoveis"] == "1º RI"
        assert row["numero_registro_imoveis_origem"] == "matricula"
        assert row["numero_registro_imoveis_confirmado_por"] == TEST_USER_ID
        assert row["numero_registro_imoveis_confirmado_em"]

        # First decision wins.
        again = client.put(
            f"/api/imoveis/{CODIGO}/conflitos/{c['id']}/decidir",
            json={"aceitar": False}, headers=auth(),
        )
        assert again.status_code == 400, again.text  # ValidationError_ → 400 (house)

    def test_reject_leaves_the_human_value(self, client, scoped):
        _make_admin(client)
        c = self._com_conflito(scoped)
        r = client.put(
            f"/api/imoveis/{CODIGO}/conflitos/{c['id']}/decidir",
            json={"aceitar": False}, headers=auth(),
        )
        assert r.status_code == 200, r.text
        assert _dados(scoped)["numero_registro_imoveis"] == "2º RI"
        assert _conflitos(scoped)[0]["status"] == "rejeitado"


class TestNotificar:
    @pytest.mark.asyncio
    async def test_each_conflict_is_announced_and_stamped(self, scoped):
        from tests.modules.imovel_hub.conftest import FakeImovelNotifier

        seed(scoped, dados=[dados_row(situacao_onus="livre", situacao_onus_origem="manual")])
        c = campos_svc.aplicar(
            scoped, ORG, CODIGO, "situacao_onus", "hipoteca", origem="matricula"
        ).conflito
        fake = FakeImovelNotifier()
        await campos_svc.notificar(scoped, ORG, CODIGO, [c], fake)
        assert [n["conflito"]["id"] for n in fake.conflitos] == [c["id"]]
        assert _conflitos(scoped)[0]["notificado_em"]

    @pytest.mark.asyncio
    async def test_no_notifier_is_logged_not_dropped(self, scoped, caplog):
        seed(scoped, dados=[dados_row(situacao_onus="livre", situacao_onus_origem="manual")])
        c = campos_svc.aplicar(
            scoped, ORG, CODIGO, "situacao_onus", "hipoteca", origem="matricula"
        ).conflito
        await campos_svc.notificar(scoped, ORG, CODIGO, [c], None)
        assert "no notifier wired" in caplog.text
        assert _conflitos(scoped)[0]["status"] == "pendente"


class TestHumanPatchStampsManual:
    def test_patch_stamps_the_new_quintets_manual(self, client, scoped):
        seed(scoped)
        r = client.patch(
            f"/api/imoveis/{CODIGO}/dados",
            json={
                "numero_registro_imoveis": "OFICIAL DE REGISTRO DE IMÓVEIS DA COMARCA DE SÃO PAULO/SP",
                "prefeitura_cadastro_imobiliario": "123.456.7-8",
                "situacao_onus": "livre",
            },
            headers=auth(),
        )
        assert r.status_code == 200, r.text
        row = _dados(scoped)
        for campo in ("numero_registro_imoveis", "prefeitura_cadastro_imobiliario", "situacao_onus"):
            assert row[f"{campo}_origem"] == "manual"
            assert row[f"{campo}_confirmado_em"]
        assert r.json()["proveniencia"]["situacao_onus"]["pendente"] is False

    def test_clearing_clears_the_provenance(self, client, scoped):
        seed(scoped, dados=[dados_row(
            situacao_onus="hipoteca", situacao_onus_origem="matricula",
            situacao_onus_documento_id=str(uuid4()),
        )])
        r = client.patch(
            f"/api/imoveis/{CODIGO}/dados", json={"situacao_onus": None}, headers=auth()
        )
        assert r.status_code == 200, r.text
        row = _dados(scoped)
        assert row["situacao_onus"] is None
        assert row["situacao_onus_origem"] is None
        assert row["situacao_onus_documento_id"] is None

    def test_re_saving_an_unchanged_machine_value_does_not_validate_it(self, client, scoped):
        """The ônus block always sends `situacao_onus`; saving the observações
        next to a machine-read value must not silently mark it human."""
        seed(scoped, dados=[dados_row(
            situacao_onus="hipoteca", situacao_onus_origem="matricula",
        )])
        r = client.patch(
            f"/api/imoveis/{CODIGO}/dados",
            json={"situacao_onus": "hipoteca", "onus_observacoes": "ver R-5"},
            headers=auth(),
        )
        assert r.status_code == 200, r.text
        row = _dados(scoped)
        assert row["situacao_onus_origem"] == "matricula"
        assert r.json()["proveniencia"]["situacao_onus"]["pendente"] is True

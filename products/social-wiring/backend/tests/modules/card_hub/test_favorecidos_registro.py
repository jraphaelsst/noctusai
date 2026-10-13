"""Org-level Favorecidos registry (migration 251): routes, role gate, masking,
cross-org isolation, card SELECTION (reference semantics), the backfill SQL,
and the readiness fix for a blank CPF/CNPJ.

Auth (strict 401) lives in `test_auth_boundary_favorecidos.py`.
"""
from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

from noctusai_lib.testing import TEST_USER_ID
from noctusai_lib.testing.migrations import migration_sql

from tests.modules.card_hub import contrato_gerador_fixtures_pagamentos as fp
from tests.modules.card_hub.conftest import ORG_ID
from tests.modules.card_hub.test_contrato_gerador_pagamentos import _avaliar
from tests.modules.card_hub.test_negociacao_estruturada import _auth, _seed

_OUTRA_ORG = str(uuid4())
CPF_OK = "529.982.247-25"      # valid check digits (public test CPF)
CNPJ_OK = "11.222.333/0001-81"  # valid check digits (public test CNPJ)


def _papel(client, org_role: str | None) -> None:
    rows = [] if org_role is None else [
        {"id": TEST_USER_ID, "org_id": ORG_ID, "org_role": org_role}
    ]
    client.mock_supabase.set_table_data("noctus_users", rows)


def _corpo(**over) -> dict:
    corpo = {
        "nome": "Maria Souza", "tipo_pessoa": "PF", "cpf_cnpj": CPF_OK,
        "banco": "Banco Exemplo", "agencia": "0001", "conta": "12345-67",
        "tipo_conta": "corrente",
    }
    corpo.update(over)
    return corpo


def _rows(scoped, tabela):
    return scoped.tables[tabela] if hasattr(scoped, "tables") else scoped.table(tabela).select("*").execute().data


def _criar(client, **over):
    return client.post("/api/card-hub/favorecidos", json=_corpo(**over), headers=_auth())


class TestRegistroRoutes:
    def test_create_then_list_is_masked_and_detail_is_full_for_a_writer(self, client, scoped):
        scoped.set_table_data("favorecidos", [])
        _papel(client, "member")
        r = _criar(client)
        assert r.status_code == 201, r.text
        fid = r.json()["id"]
        assert r.json()["cpf_cnpj"] == CPF_OK

        lista = client.get("/api/card-hub/favorecidos", headers=_auth()).json()["items"]
        assert len(lista) == 1
        item = lista[0]
        assert item["cpf_cnpj_mascarado"] == "***.982.247-**"
        assert "cpf_cnpj" not in item and "conta" not in item and "pix" not in item
        assert item["ativo"] is True

        full = client.get(f"/api/card-hub/favorecidos/{fid}", headers=_auth()).json()
        assert full["cpf_cnpj"] == CPF_OK and full["conta"] == "12345-67"
        assert full["mascarado"] is False

    def test_a_viewer_gets_a_masked_detail_and_cannot_write(self, client, scoped):
        scoped.set_table_data("favorecidos", [])
        _papel(client, "member")
        fid = _criar(client).json()["id"]
        _papel(client, "viewer")
        det = client.get(f"/api/card-hub/favorecidos/{fid}", headers=_auth()).json()
        assert det["mascarado"] is True
        assert det["cpf_cnpj"] == "***.982.247-**"
        assert det["conta"] == "*****67"
        assert client.post("/api/card-hub/favorecidos", json=_corpo(cpf_cnpj=CNPJ_OK, tipo_pessoa="PJ"),
                           headers=_auth()).status_code == 403
        assert client.patch(f"/api/card-hub/favorecidos/{fid}", json={"nome": "X"},
                            headers=_auth()).status_code == 403
        assert client.delete(f"/api/card-hub/favorecidos/{fid}", headers=_auth()).status_code == 403

    def test_an_unresolvable_role_fails_closed(self, client, scoped):
        scoped.set_table_data("favorecidos", [])
        _papel(client, None)
        assert _criar(client).status_code == 403

    def test_invalid_cpf_and_cnpj_are_refused_never_computed(self, client, scoped):
        scoped.set_table_data("favorecidos", [])
        _papel(client, "member")
        r = _criar(client, cpf_cnpj="529.982.247-26")
        assert r.status_code == 400 and "CPF inválido" in r.text
        r = _criar(client, tipo_pessoa="PJ", cpf_cnpj="11.222.333/0001-82")
        assert r.status_code == 400 and "CNPJ inválido" in r.text
        assert _rows(scoped, "favorecidos") == []

    def test_conta_or_pix_is_required_and_conta_needs_banco_agencia(self, client, scoped):
        scoped.set_table_data("favorecidos", [])
        _papel(client, "member")
        r = _criar(client, banco=None, agencia=None, conta=None)
        assert r.status_code == 400 and "conta bancária ou a chave PIX" in r.text
        r = _criar(client, agencia=None)
        assert r.status_code == 400 and "banco e agência" in r.text
        r = _criar(client, banco=None, agencia=None, conta=None, pix="a@b.com", pix_tipo="email")
        assert r.status_code == 201, r.text

    def test_pix_only_list_masks_the_key(self, client, scoped):
        scoped.set_table_data("favorecidos", [])
        _papel(client, "member")
        _criar(client, banco=None, agencia=None, conta=None, pix="maria@exemplo.com", pix_tipo="email")
        item = client.get("/api/card-hub/favorecidos", headers=_auth()).json()["items"][0]
        assert item["pix_mascarado"] == "m***@exemplo.com"
        assert item["pix_tipo"] == "email"

    def test_a_duplicate_active_document_is_a_409_and_delete_frees_it(self, client, scoped):
        scoped.set_table_data("favorecidos", [])
        _papel(client, "member")
        fid = _criar(client).json()["id"]
        assert _criar(client, nome="Outra").status_code == 409
        assert client.delete(f"/api/card-hub/favorecidos/{fid}", headers=_auth()).status_code == 204
        row = next(r for r in _rows(scoped, "favorecidos") if r["id"] == fid)
        assert row["ativo"] is False  # soft delete, row kept
        assert _criar(client, nome="Outra").status_code == 201

    def test_filters_q_and_ativo(self, client, scoped):
        scoped.set_table_data("favorecidos", [])
        _papel(client, "member")
        a = _criar(client).json()["id"]
        _criar(client, nome="Imob Exemplo", tipo_pessoa="PJ", cpf_cnpj=CNPJ_OK)
        client.delete(f"/api/card-hub/favorecidos/{a}", headers=_auth())
        nomes = lambda **q: [i["nome"] for i in client.get("/api/card-hub/favorecidos", params=q, headers=_auth()).json()["items"]]
        assert nomes(q="imob") == ["Imob Exemplo"]
        assert nomes(q="982247") == ["Maria Souza"]
        assert nomes(ativo="true") == ["Imob Exemplo"]
        assert nomes(ativo="false") == ["Maria Souza"]

    def test_patch_is_validated_as_a_whole(self, client, scoped):
        scoped.set_table_data("favorecidos", [])
        _papel(client, "member")
        fid = _criar(client).json()["id"]
        r = client.patch(f"/api/card-hub/favorecidos/{fid}", json={"conta": None}, headers=_auth())
        assert r.status_code == 400  # would leave neither conta nor pix
        r = client.patch(f"/api/card-hub/favorecidos/{fid}", json={"nome": "Maria S. Souza"}, headers=_auth())
        assert r.status_code == 200 and r.json()["nome"] == "Maria S. Souza"
        assert r.json()["updated_por"] is not None


class TestIsolamentoEntreOrgs:
    def test_another_orgs_entry_is_invisible_and_untouchable(self, client, scoped):
        alheio = str(uuid4())
        scoped.set_table_data("favorecidos", [{
            "id": alheio, "org_id": _OUTRA_ORG, "nome": "Alheio", "tipo_pessoa": "PF",
            "cpf_cnpj": CPF_OK, "banco": "B", "agencia": "1", "conta": "9", "ativo": True,
            "created_at": "2026-01-01T00:00:00+00:00",
        }])
        _papel(client, "owner")
        assert client.get("/api/card-hub/favorecidos", headers=_auth()).json()["items"] == []
        assert client.get(f"/api/card-hub/favorecidos/{alheio}", headers=_auth()).status_code == 404
        assert client.patch(f"/api/card-hub/favorecidos/{alheio}", json={"nome": "X"}, headers=_auth()).status_code == 404
        assert client.delete(f"/api/card-hub/favorecidos/{alheio}", headers=_auth()).status_code == 404
        # the same document in OUR org is not a duplicate of theirs
        assert _criar(client).status_code == 201

    def test_selecting_another_orgs_entry_is_a_404(self, client, scoped):
        alheio = str(uuid4())
        cid, aid = _seed(scoped)
        scoped.set_table_data("favorecidos", [{
            "id": alheio, "org_id": _OUTRA_ORG, "nome": "Alheio", "tipo_pessoa": "PF",
            "cpf_cnpj": CPF_OK, "banco": "B", "agencia": "1", "conta": "9", "ativo": True,
            "created_at": "2026-01-01T00:00:00+00:00",
        }])
        r = client.put(f"/api/card-hub/atendimentos/{aid}/favorecidos/selecao",
                       json={"favorecido_id": alheio}, headers=_auth())
        assert r.status_code == 404


class TestSelecaoNoCard:
    def _registro(self, client, scoped, **over):
        scoped.set_table_data("favorecidos", [])
        _papel(client, "member")
        return _criar(client, **over).json()["id"]

    def test_selection_links_the_card_row_idempotently(self, client, scoped):
        cid, aid = _seed(scoped)
        fid = self._registro(client, scoped)
        url = f"/api/card-hub/atendimentos/{aid}/favorecidos/selecao"
        r = client.put(url, json={"favorecido_id": fid}, headers=_auth())
        assert r.status_code == 200, r.text
        assert r.json()["favorecido_id"] == fid
        assert r.json()["cpf_cnpj"] == CPF_OK
        again = client.put(url, json={"favorecido_id": fid}, headers=_auth())
        assert again.json()["id"] == r.json()["id"]
        assert len(_rows(scoped, "atendimento_favorecidos")) == 1

    def test_the_card_reads_the_registrys_current_values(self, client, scoped):
        cid, aid = _seed(scoped)
        fid = self._registro(client, scoped)
        url = f"/api/card-hub/atendimentos/{aid}/favorecidos/selecao"
        client.put(url, json={"favorecido_id": fid}, headers=_auth())
        client.patch(f"/api/card-hub/favorecidos/{fid}", json={"conta": "99999-0", "agencia": "0042"}, headers=_auth())
        card = client.get(f"/api/clientes/{cid}/negociacao/estruturada", headers=_auth()).json()
        assert card["favorecidos"][0]["conta"] == "99999-0"
        assert card["favorecidos"][0]["agencia"] == "0042"

    def test_a_linked_card_row_cannot_be_edited_on_the_card(self, client, scoped):
        cid, aid = _seed(scoped)
        fid = self._registro(client, scoped)
        body = client.put(f"/api/card-hub/atendimentos/{aid}/favorecidos/selecao",
                          json={"favorecido_id": fid}, headers=_auth()).json()
        card_id = body["id"]
        r = client.patch(f"/api/clientes/{cid}/negociacao/favorecidos/{card_id}",
                         json={"conta": "1"}, headers=_auth())
        assert r.status_code == 409

    def test_selection_can_set_the_intermediarios_favorecido(self, client, scoped):
        cid, aid = _seed(scoped)
        inter_id = str(uuid4())
        scoped.set_table_data("atendimento_intermediarios", [{
            "id": inter_id, "org_id": ORG_ID, "atendimento_id": aid, "nome": "Corretor X",
            "tipo": "percentual", "valor": "1", "natureza": "intermediario",
            "created_at": "2026-01-01T00:00:00+00:00",
        }])
        fid = self._registro(client, scoped)
        r = client.put(f"/api/card-hub/atendimentos/{aid}/favorecidos/selecao",
                       json={"favorecido_id": fid, "intermediario_id": inter_id}, headers=_auth())
        assert r.status_code == 200, r.text
        card_id = r.json()["id"]
        agregado = client.get(f"/api/clientes/{cid}/negociacao/estruturada", headers=_auth()).json()
        assert agregado["intermediarios"][0]["favorecido_id"] == card_id
        r = client.put(f"/api/card-hub/atendimentos/{aid}/favorecidos/selecao",
                       json={"favorecido_id": fid, "intermediario_id": str(uuid4())}, headers=_auth())
        assert r.status_code == 404

    def test_an_inactive_entry_cannot_be_newly_selected(self, client, scoped):
        cid, aid = _seed(scoped)
        fid = self._registro(client, scoped)
        client.delete(f"/api/card-hub/favorecidos/{fid}", headers=_auth())
        r = client.put(f"/api/card-hub/atendimentos/{aid}/favorecidos/selecao",
                       json={"favorecido_id": fid}, headers=_auth())
        assert r.status_code == 409

    def test_existing_per_card_endpoints_still_work(self, client, scoped):
        cid, aid = _seed(scoped)
        r = client.post(f"/api/clientes/{cid}/negociacao/favorecidos",
                        json={"nome": "Digitado", "cpf_cnpj": CPF_OK, "pix": "x"}, headers=_auth())
        assert r.status_code == 201, r.text
        assert r.json()["favorecidos"][0]["favorecido_id"] is None


class TestBackfillSql:
    """The backfill is SQL; no Postgres in unit tests, so pin its CONTRACT by
    parsing the file (the chain-replay hook runs it for real on PGlite)."""

    SQL = migration_sql(Path(__file__).resolve().parents[3], "favorecidos_registry")

    def test_dedupes_by_org_then_document_alphanumerics_else_name(self):
        assert "SELECT DISTINCT ON (k.org_id, k.chave)" in self.SQL
        assert "regexp_replace(upper(af.cpf_cnpj), '[^0-9A-Z]', '', 'g')" in self.SQL
        assert "'N:' || lower(btrim(af.nome))" in self.SQL

    def test_only_unlinked_card_rows_are_touched_so_a_rerun_is_a_noop(self):
        assert self.SQL.count("WHERE af.favorecido_id IS NULL") >= 2

    def test_registry_is_org_scoped_with_rls_like_atendimento_favorecidos(self):
        assert "ENABLE ROW LEVEL SECURITY" in self.SQL
        assert re.search(r"favorecidos_select_own_org.*?current_org_id_for\('social_wiring'\)", self.SQL, re.S)
        assert "favorecidos_service_role" in self.SQL
        assert "ON DELETE SET NULL" in self.SQL  # card link survives a hard delete

    def test_never_invents_a_tipo_pessoa(self):
        assert "WHEN k.tem_doc AND length(k.chave) = 11 THEN 'PF'" in self.SQL
        assert "ELSE" not in self.SQL.split("tipo_pessoa,")[1].split("FROM (")[0]


class TestReadinessFlagsABlankCpfCnpj:
    def test_a_favorecido_without_cpf_cnpj_is_not_ready(self):
        d = fp.sinal_em_partes()
        assert _avaliar(d, 1).pronto, "baseline must be ready"
        favs = [replace(f, cpf_cnpj="  ") if f.id == "fav-v" else f for f in d.favorecidos]
        av = _avaliar(replace(d, favorecidos=favs), 1)
        assert not av.pronto
        assert any(f["campo"] == "negociacao.favorecido.fav-v.cpf_cnpj" for f in av.faltando)

    def test_none_is_also_flagged(self):
        d = fp.sinal_em_partes()
        favs = [replace(f, cpf_cnpj=None) if f.id == "fav-v" else f for f in d.favorecidos]
        av = _avaliar(replace(d, favorecidos=favs), 1)
        assert any(f["campo"].endswith(".cpf_cnpj") for f in av.faltando)

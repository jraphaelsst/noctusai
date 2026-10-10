"""`identificadores_backfill` — the zero-API sweep over stored data (owner rule
2026-10-01, `canonical-identifiers`).

PINS
----
- fits-but-raw values become canonical, the RAW reading is logged first;
  values that do not fit are COUNTED and never touched; cross-type values
  (a CPF in the RG field) are counted, never moved;
- `--dry-run` writes NOTHING by construction (a read-only client), and its
  report equals the real run's;
- pending conflicts decided by equivalence / DV / type routing close as
  `resolvido_automatico` with the rule in `motivo_resolucao`; a conflict only
  a human can decide stays `pendente`;
- idempotent; the report is counts only (no document number in it).
"""
from __future__ import annotations

import json
from copy import deepcopy
from uuid import UUID, uuid4

import pytest
from noctusai_lib.testing import MockSupabaseClient

from app.services import identificadores_backfill as bf
from tests.modules.card_hub.conftest import ORG_ID, cliente_row

ORG_UUID = UUID(ORG_ID)
ORG = ORG_ID

CPF_RAW, CPF_CANON = "52998224725", "529.982.247-25"


def _conflito(cid, campo, anterior, proposto, *, origem_anterior="cnh", origem_proposto="matricula"):
    return {
        "id": str(uuid4()), "org_id": ORG_ID, "cliente_id": cid, "campo": campo,
        "valor_anterior": anterior, "origem_anterior": origem_anterior,
        "valor_proposto": proposto, "origem_proposto": origem_proposto,
        "confianca_proposta": "alta", "fonte_tabela": None, "fonte_id": None,
        "status": "pendente", "notificado_em": None, "decidido_por": None,
        "decidido_em": None, "created_at": "2026-09-30T00:00:00+00:00",
    }


@pytest.fixture
def banco() -> MockSupabaseClient:
    scoped = MockSupabaseClient()
    ids = {k: str(uuid4()) for k in "abcde"}
    scoped.set_table_data("clientes", [
        cliente_row(ids["a"], "A", cpf=CPF_RAW, cpf_origem="manual", rg="30128742", rg_origem="cnh",
                    endereco_cep="13010110"),
        cliente_row(ids["b"], "B", cpf="412.954.238-98", cpf_origem="cnh"),
        cliente_row(ids["c"], "C", rg="15.668.564-3", rg_origem="matricula"),          # DV fails
        cliente_row(ids["d"], "D", cpf="111.444.777-35", rg="297.556.088-50"),         # CPF in RG, not own
        cliente_row(ids["e"], "E", rg="52.179.965-X", rg_orgao_expedidor="SSP/MG"),   # no MG mask evidenced
    ])
    scoped.set_table_data("imoveis", [
        {"org_id": ORG_ID, "codigo": "ONE4770", "cidade": "Cotia"},
    ])
    scoped.set_table_data("imovel_registry", [])
    scoped.set_table_data("imovel_dados", [
        {"org_id": ORG_ID, "codigo": "ONE4770", "numero_matricula": "79826",
         "prefeitura_cadastro_imobiliario": "232314211037700000", "endereco_manual_cep": "13010110"},
    ])
    scoped.set_table_data("certidao_consultas", [
        {"id": str(uuid4()), "org_id": ORG_ID, "tipo_documento": "cpf", "documento": "41295423898"},
        {"id": str(uuid4()), "org_id": ORG_ID, "tipo_documento": "cnpj", "documento": "11.222.333/0001-81"},
    ])
    scoped.set_table_data("empresas", [
        {"id": str(uuid4()), "org_id": ORG_ID, "cnpj": "11222333000181"},
        {"id": str(uuid4()), "org_id": ORG_ID, "cnpj": "11222333000182"},   # DV fails
    ])
    scoped.set_table_data("identificador_canonizacoes", [])
    scoped.set_table_data("cliente_documentos", [])
    scoped.set_table_data("cliente_campo_conflitos", [
        _conflito(ids["a"], "rg", "30128742", "30.128.742-9"),                       # equivalence
        _conflito(ids["c"], "rg", "15.668.564-3", "16.669.554-3"),                   # DV validator
        _conflito(ids["d"], "rg", "297.556.088-50", "30.128.742-9"),                 # type routing
        _conflito(ids["e"], "rg", "52.179.965-X", "99.999.999-0",
                  origem_anterior="rg", origem_proposto="rg"),                         # human needed
    ])
    scoped.set_table_data("imovel_campo_conflitos", [
        {"id": str(uuid4()), "org_id": ORG_ID, "codigo": "ONE4770", "campo": "numero_matricula",
         "valor_anterior": "79826", "origem_anterior": "matricula",
         "valor_proposto": "0079.826", "origem_proposto": "matricula", "status": "pendente",
         "documento_id_proposto": None, "created_at": "2026-09-30T00:00:00+00:00"},
        {"id": str(uuid4()), "org_id": ORG_ID, "codigo": "ONE4770", "campo": "numero_registro_imoveis",
         "valor_anterior": "SERVENTIA DO REGISTRO DE IMÓVEIS de Cotia - CNS: 11991-7",
         "origem_anterior": "matricula", "valor_proposto": "11991-7", "origem_proposto": "matricula",
         "status": "pendente", "documento_id_proposto": None, "created_at": "2026-09-30T00:00:00+00:00"},
        {"id": str(uuid4()), "org_id": ORG_ID, "codigo": "ONE4770", "campo": "numero_matricula",
         "valor_anterior": "79.826", "origem_anterior": "matricula",
         "valor_proposto": "80.100", "origem_proposto": "guia_iptu", "status": "pendente",
         "documento_id_proposto": None, "created_at": "2026-09-30T00:00:01+00:00"},
    ])
    scoped.set_table_data("empresa_campo_conflitos", [])
    scoped._ids = ids  # noqa: SLF001 - test convenience
    return scoped


def _cliente(scoped, id_) -> dict:
    return next(r for r in scoped.table("clientes").select("*").execute().data if r["id"] == id_)


def _rows(scoped, tabela) -> list[dict]:
    return scoped.table(tabela).select("*").execute().data


class TestCanonizar:
    def test_fitting_values_become_canonical_and_the_raw_is_logged_first(self, banco):
        out = bf.run_backfill(banco, ORG_UUID)
        a = _cliente(banco, banco._ids["a"])
        assert (a["cpf"], a["rg"], a["endereco_cep"]) == (CPF_CANON, "30.128.742", "13010-110")
        log = {(r["tabela"], r["campo"]): r for r in _rows(banco, "identificador_canonizacoes")}
        assert log[("clientes", "cpf")]["valor_bruto"] == CPF_RAW
        assert log[("clientes", "rg")]["valor_bruto"] == "30128742"
        assert log[("clientes", "rg")]["origem"] == "backfill"
        assert out["valores"]["clientes.cpf"]["canonizados"] == 1

    def test_imovel_and_certidao_values_are_canonicalised(self, banco):
        bf.run_backfill(banco, ORG_UUID)
        d = _rows(banco, "imovel_dados")[0]
        assert d["numero_matricula"] == "79.826"
        assert d["prefeitura_cadastro_imobiliario"] == "23231.42.11.0377.00.000"  # Cotia mask
        assert d["endereco_manual_cep"] == "13010-110"
        docs = sorted(r["documento"] for r in _rows(banco, "certidao_consultas"))
        assert docs == ["11.222.333/0001-81", "412.954.238-98"]

    def test_what_does_not_fit_is_counted_and_never_rewritten(self, banco):
        # The canonicalisation step alone (the conflict step may legitimately
        # replace a value through the resolver — see `TestConflitos`).
        contagem = bf._Contagem()
        bf.canonizar_clientes(banco, ORG_UUID, contagem, dry_run=False)
        assert _cliente(banco, banco._ids["c"])["rg"] == "15.668.564-3"           # DV fails: as read
        assert _cliente(banco, banco._ids["d"])["rg"] == "297.556.088-50"         # CPF in RG: not moved
        assert _cliente(banco, banco._ids["e"])["rg"] == "52.179.965-X"           # SSP/MG: no mask evidenced
        rg = contagem.como_dict()["clientes.rg"]
        assert rg["tipo_trocado"] == 1
        assert rg["nao_cabem"] == {"cpf_no_campo_rg": 1, "dv_invalido": 1, "rg_uf_sem_mascara": 1}

    def test_empresas_cnpj_is_the_identity_key_and_is_never_rewritten(self, banco):
        before = [r["cnpj"] for r in _rows(banco, "empresas")]
        out = bf.run_backfill(banco, ORG_UUID)
        assert [r["cnpj"] for r in _rows(banco, "empresas")] == before
        assert out["valores"]["empresas.cnpj"]["nao_cabem"] == {"dv_invalido": 1}

    def test_the_report_carries_no_document_number(self, banco):
        blob = json.dumps(bf.run_backfill(banco, ORG_UUID, dry_run=True))
        for secret in (CPF_RAW, CPF_CANON, "30128742", "412.954.238-98", "79826", "11.222.333"):
            assert secret not in blob


class TestChavesDeBusca:
    def test_rows_stored_before_the_trigger_get_their_search_key(self, banco):
        """A row whose value is ALREADY canonical is never written by the
        canonicalisation step — without this its `documentos_chave` stays NULL
        and the rendered number would not find it."""
        out = bf.run_backfill(banco, ORG_UUID)
        assert _cliente(banco, banco._ids["b"])["documentos_chave"] == "41295423898"
        assert _cliente(banco, banco._ids["a"])["documentos_chave"] == "52998224725 30128742"
        assert _rows(banco, "imovel_dados")[0]["documentos_chave"] == "79826 232314211037700000"
        docs = {r["documento"]: r["documentos_chave"] for r in _rows(banco, "certidao_consultas")}
        assert docs["412.954.238-98"] == "41295423898"
        assert out["valores"]["clientes.documentos_chave"]["canonizados"] == 5

    def test_the_search_round_trip_works_on_a_backfilled_row(self, banco):
        from app.services import clientes_service as svc

        bf.run_backfill(banco, ORG_UUID)
        ids = [c["id"] for c in svc.list_clientes(banco, ORG, q="412.954.238-98")["items"]]
        assert ids == [banco._ids["b"]]

    def test_dry_run_derives_nothing(self, banco):
        bf.run_backfill(banco, ORG_UUID, dry_run=True)
        assert _cliente(banco, banco._ids["b"]).get("documentos_chave") is None


class TestConflitos:
    def test_pending_identifier_conflicts_close_with_their_rule(self, banco):
        out = bf.run_backfill(banco, ORG_UUID)
        por_campo = {(r["cliente_id"], r["campo"]): r for r in _rows(banco, "cliente_campo_conflitos")}
        a = por_campo[(banco._ids["a"], "rg")]
        assert a["status"] == "resolvido_automatico" and "[equivalencia]" in a["motivo_resolucao"]
        c = por_campo[(banco._ids["c"], "rg")]
        assert c["status"] == "resolvido_automatico" and "[validador]" in c["motivo_resolucao"]
        d = por_campo[(banco._ids["d"], "rg")]
        assert d["status"] == "resolvido_automatico" and "[tipo_detectado]" in d["motivo_resolucao"]
        assert out["conflitos"]["cliente_campo_conflitos"]["por_regra"] == {
            "rg:equivalencia": 1, "rg:tipo_detectado": 1, "rg:validador": 1,
        }

    def test_two_valid_different_rgs_still_need_a_human(self, banco):
        bf.run_backfill(banco, ORG_UUID)
        e = next(r for r in _rows(banco, "cliente_campo_conflitos") if r["cliente_id"] == banco._ids["e"])
        assert e["status"] == "pendente"

    def test_the_winning_reading_lands_on_the_cliente(self, banco):
        bf.run_backfill(banco, ORG_UUID)
        # DV-valid proposal won over the DV-invalid RG on file…
        assert _cliente(banco, banco._ids["c"])["rg"] == "16.669.554-3"
        # …and the CPF-in-RG on file lost to the real RG proposed.
        assert _cliente(banco, banco._ids["d"])["rg"] == "30.128.742-9"

    def test_imovel_equivalence_closes_and_a_real_disagreement_stays(self, banco):
        out = bf.run_backfill(banco, ORG_UUID)
        rows = _rows(banco, "imovel_campo_conflitos")
        status = {(r["campo"], r["valor_proposto"]): r["status"] for r in rows}
        assert status[("numero_matricula", "0079.826")] == "resolvido_automatico"
        assert status[("numero_registro_imoveis", "11991-7")] == "resolvido_automatico"
        assert status[("numero_matricula", "80.100")] == "pendente"
        assert out["conflitos"]["imovel_campo_conflitos"]["resolvidos"] == 2
        assert out["conflitos"]["empresa_campo_conflitos"]["resolvidos"] == 0


class TestDryRunAndIdempotence:
    def test_dry_run_writes_nothing_and_reports_what_a_real_run_does(self, banco):
        snapshot = {
            t: deepcopy(_rows(banco, t))
            for t in ("clientes", "imovel_dados", "certidao_consultas", "identificador_canonizacoes",
                      "cliente_campo_conflitos", "imovel_campo_conflitos")
        }
        dry = bf.run_backfill(banco, ORG_UUID, dry_run=True)
        for tabela, antes in snapshot.items():
            assert _rows(banco, tabela) == antes, tabela
        real = bf.run_backfill(banco, ORG_UUID)
        assert dry["dry_run"] is True and real["dry_run"] is False
        assert dry["valores"] == real["valores"]
        assert dry["conflitos"] == real["conflitos"]

    def test_a_second_run_finds_nothing_left_to_do(self, banco):
        bf.run_backfill(banco, ORG_UUID)
        out = bf.run_backfill(banco, ORG_UUID)
        for slot in out["valores"].values():
            assert slot["canonizados"] == 0
        assert out["conflitos"]["cliente_campo_conflitos"]["resolvidos"] == 0
        assert out["conflitos"]["imovel_campo_conflitos"]["resolvidos"] == 0

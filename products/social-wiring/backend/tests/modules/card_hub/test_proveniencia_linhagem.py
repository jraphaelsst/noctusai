"""SW data -> file -> source catalog, slice S2 —
`card_hub/proveniencia/linhagem.py`.

WHAT THESE PIN
--------------
- `linhagem_do_registro()` — the static `GET /api/proveniencia/registro`
  answer — has no DB reads and reshapes `fontes.FONTES`/`MANUAL_APENAS`
  faithfully (every `manual_apenas` category present, `entidade="contrato"`
  since those categories are not entity-scoped);
- `linhagem_do_card()` — `GET /api/clientes/{id}/contratos/{cid}/
  proveniencia` — reports a `REGISTRO` field's state (`vazio` / `maquina_
  pendente` / `confirmado` / `manual` / `conflito`), its source document
  (joined off `cliente_documentos`), and which `tipo_documento`(s) could
  still fill it in when empty;
- `CAMPO_CERTIDAO`/`CAMPO_ATO_DETALHE` never appear (scope, see the module
  docstring);
- an open `cliente_campo_conflitos` row overrides the state to `conflito`
  regardless of what the row itself says.

All data is synthetic (mock Supabase, `tests/modules/card_hub/conftest.py`).
"""
from __future__ import annotations

from uuid import uuid4

from app.modules.card_hub.contrato_gerador import validacao_extracao as vx
from app.modules.card_hub.proveniencia import fontes as fontes_mod
from app.modules.card_hub.proveniencia import linhagem
from tests.modules.card_hub.conftest import ORG_ID
from tests.modules.card_hub.test_contrato_gerador_endpoints import (
    _T0,
    _auth,
    _rows,
    _seed_base,
    _seed_completo,
    _url,
)

_ITEM_KEYS = {"entidade", "campo", "rotulo", "valor", "estado", "origem", "documento", "em", "fontes_possiveis"}


# ─── linhagem_do_registro — pure, no DB ─────────────────────────────────────


class TestLinhagemDoRegistro:
    def test_shape(self):
        body = linhagem.linhagem_do_registro()
        assert set(body) == {"fontes", "manual_apenas"}

    def test_every_fontes_entry_names_a_registro_field_with_candidates(self):
        body = linhagem.linhagem_do_registro()
        for entrada in body["fontes"]:
            assert set(entrada) == {"entidade", "campo", "fontes"}
            assert entrada["fontes"]
            for f in entrada["fontes"]:
                assert set(f) == {"tipo_documento", "entradas"}
                assert f["entradas"]

    def test_nome_oficial_lists_every_identity_document(self):
        body = linhagem.linhagem_do_registro()
        entrada = next(
            e for e in body["fontes"] if e["entidade"] == "cliente" and e["campo"] == "nome_oficial"
        )
        assert {f["tipo_documento"] for f in entrada["fontes"]} == {
            "rg", "cpf", "cnh", "certidao_casamento", "certidao_nascimento",
            # P0c contract §C1: Serasa Crednet also claims `nome` (`nome_oficial`).
            "serasa_crednet",
        }

    def test_profissao_lists_matricula_alongside_the_identity_documents(self):
        """The gap the REGINA case surfaced: `profissao` (and the other six
        matrícula-qualification fields) used to resolve `documento_ausente`
        with candidates rg/cnh/certidões only — the matrícula was never
        considered even though `matriculas.qualificacao_service` had
        already read it. `matricula`'s `Fonte.campos` now claims these
        seven (`fontes.py`, migration 137's write path), so the harness's
        gap trace (`tests/e2e_contrato/harness.py::classificar_gap`, driven
        by this exact function) can finally name it."""
        body = linhagem.linhagem_do_registro()
        for campo in (
            "profissao", "estado_civil", "nacionalidade", "rg",
            "rg_orgao_expedidor", "endereco", "genero",
        ):
            entrada = next(
                e for e in body["fontes"] if e["entidade"] == "cliente" and e["campo"] == campo
            )
            tipos = {f["tipo_documento"] for f in entrada["fontes"]}
            assert "matricula" in tipos, f"{campo} does not list matricula as a candidate: {tipos}"

    def test_certidao_do_imovel_lists_the_four_estrutura_extraivel_tipos(self):
        body = linhagem.linhagem_do_registro()
        entrada = next(
            e for e in body["fontes"]
            if e["entidade"] == vx.ENTIDADE_IMOVEL_DOCUMENTO and e["campo"] == "certidao"
        )
        assert {f["tipo_documento"] for f in entrada["fontes"]} == {
            "matricula", "guia_iptu", "cnd_iptu", "cnd_condominio",
        }

    def test_fora_do_escopo_fields_are_absent(self):
        body = linhagem.linhagem_do_registro()
        chaves = {(e["entidade"], e["campo"]) for e in body["fontes"]}
        assert chaves.isdisjoint(fontes_mod.FORA_DO_ESCOPO_S1)

    def test_manual_apenas_covers_every_category_under_a_fixed_entidade(self):
        body = linhagem.linhagem_do_registro()
        assert {m["campo"] for m in body["manual_apenas"]} == set(fontes_mod.MANUAL_APENAS)
        assert all(m["entidade"] == "contrato" and m["destino"] is None for m in body["manual_apenas"])


# ─── linhagem_do_card — over the mock DB ────────────────────────────────────


def _com_provenance(scoped, cliente_id: str, **colunas) -> None:
    """Adds the quinteto columns named by `colunas` (`{coluna: valor}`) to
    `cliente_id`'s row, leaving every other column untouched — mirrors
    `test_contrato_gerador_validacao_extracao.py::_cpf_extraido`'s shape."""
    linhas = []
    for r in _rows(scoped, "clientes"):
        linhas.append({**r, **colunas} if r["id"] == cliente_id else r)
    scoped.set_table_data("clientes", linhas)


def _item(items: list[dict], entidade: str, campo: str) -> dict:
    return next(i for i in items if i["entidade"] == entidade and i["campo"] == campo)


class TestLinhagemDoCard:
    def test_every_item_has_exactly_the_frozen_shape(self, client, scoped):
        ids = _seed_base(scoped)
        doc_id = str(uuid4())
        scoped.set_table_data("cliente_documentos", [{
            "id": doc_id, "org_id": ORG_ID, "cliente_id": ids["cliente"], "tipo_documento": "rg",
            "nome_original": "rg-beltrana.pdf", "deleted_at": None, "created_at": _T0,
        }])
        _com_provenance(
            scoped, ids["cliente"],
            cpf_origem="rg", cpf_documento_id=doc_id, cpf_em=_T0,
            cpf_confirmado_por=None, cpf_confirmado_em=None,
        )
        r = client.get(_url(ids, "proveniencia"), headers=_auth())
        assert r.status_code == 200, r.text
        body = r.json()
        assert set(body) == {"items"}
        assert body["items"]
        for item in body["items"]:
            assert set(item) == _ITEM_KEYS
            assert item["estado"] in {"vazio", "maquina_pendente", "confirmado", "manual", "conflito"}

    def test_certidao_and_ato_detalhe_never_appear(self, client, scoped):
        ids = _seed_base(scoped)
        body = client.get(_url(ids, "proveniencia"), headers=_auth()).json()
        entidades = {i["entidade"] for i in body["items"]}
        assert vx.ENTIDADE_CERTIDAO not in entidades
        assert vx.ENTIDADE_ATO_DETALHE not in entidades

    def test_a_machine_extracted_value_is_maquina_pendente_with_its_source(self, client, scoped):
        ids = _seed_base(scoped)
        doc_id = str(uuid4())
        scoped.set_table_data("cliente_documentos", [{
            "id": doc_id, "org_id": ORG_ID, "cliente_id": ids["cliente"], "tipo_documento": "rg",
            "nome_original": "rg-beltrana.pdf", "deleted_at": None, "created_at": _T0,
        }])
        _com_provenance(
            scoped, ids["cliente"],
            cpf_origem="rg", cpf_documento_id=doc_id, cpf_em=_T0,
            cpf_confirmado_por=None, cpf_confirmado_em=None,
        )
        body = client.get(_url(ids, "proveniencia"), headers=_auth()).json()
        item = _item(body["items"], vx.ENTIDADE_CLIENTE, "cpf")
        assert item["estado"] == "maquina_pendente"
        assert item["origem"] == "rg"
        assert item["documento"] == {
            "id": doc_id, "tipo": "rg", "nome": "rg-beltrana.pdf", "entrada": "cliente_card_upload",
        }
        tipos = {f["tipo_documento"] for f in item["fontes_possiveis"]}
        assert tipos == {
            "rg", "cpf", "cnh", "certidao_casamento", "certidao_nascimento",
            # P0c contract §C1: Serasa Crednet also claims `nome` (`nome_oficial`).
            "serasa_crednet",
        }
        assert all(f["destino"] == f"/clientes/{ids['cliente']}" for f in item["fontes_possiveis"])

    def test_a_confirmed_value_is_confirmado(self, client, scoped):
        ids = _seed_base(scoped)
        _com_provenance(
            scoped, ids["cliente"],
            cpf_origem="rg", cpf_documento_id=str(uuid4()), cpf_em=_T0,
            cpf_confirmado_por=None, cpf_confirmado_em=_T0,
        )
        body = client.get(_url(ids, "proveniencia"), headers=_auth()).json()
        assert _item(body["items"], vx.ENTIDADE_CLIENTE, "cpf")["estado"] == "confirmado"

    def test_a_manual_value_is_manual(self, client, scoped):
        ids = _seed_base(scoped)
        _com_provenance(
            scoped, ids["cliente"],
            cpf_origem="manual", cpf_documento_id=None, cpf_em=None,
            cpf_confirmado_por=None, cpf_confirmado_em=None,
        )
        body = client.get(_url(ids, "proveniencia"), headers=_auth()).json()
        assert _item(body["items"], vx.ENTIDADE_CLIENTE, "cpf")["estado"] == "manual"

    def test_an_open_conflict_wins_over_the_rows_own_state(self, client, scoped):
        ids = _seed_base(scoped)
        _com_provenance(
            scoped, ids["cliente"],
            cpf_origem="manual", cpf_documento_id=None, cpf_em=None,
            cpf_confirmado_por=None, cpf_confirmado_em=None,
        )
        scoped.set_table_data("cliente_campo_conflitos", [{
            "id": str(uuid4()), "org_id": ORG_ID, "cliente_id": ids["cliente"], "campo": "cpf",
            "valor_anterior": "111.111.111-11", "origem_anterior": "manual",
            "valor_proposto": "222.222.222-22", "origem_proposto": "rg", "confianca_proposta": "alta",
            "fonte_tabela": None, "fonte_id": None, "status": "pendente",
            "notificado_em": None, "decidido_por": None, "decidido_em": None, "created_at": _T0,
        }])
        body = client.get(_url(ids, "proveniencia"), headers=_auth()).json()
        assert _item(body["items"], vx.ENTIDADE_CLIENTE, "cpf")["estado"] == "conflito"

    def test_numero_matricula_lists_the_matricula_fonte(self, client, scoped):
        ids = _seed_completo(scoped)
        linhas = _rows(scoped, "imovel_dados")
        assert linhas, "expected _seed_completo to seed one imovel_dados row"
        atualizadas = [
            {**r, "numero_matricula_origem": "matricula", "numero_matricula_documento_id": None,
             "numero_matricula_em": _T0, "numero_matricula_confirmado_por": None,
             "numero_matricula_confirmado_em": None}
            for r in linhas
        ]
        scoped.set_table_data("imovel_dados", atualizadas)
        body = client.get(_url(ids, "proveniencia"), headers=_auth()).json()
        item = next(
            (i for i in body["items"] if i["entidade"] == vx.ENTIDADE_IMOVEL and i["campo"] == "numero_matricula"),
            None,
        )
        assert item is not None
        assert {f["tipo_documento"] for f in item["fontes_possiveis"]} == {"matricula"}

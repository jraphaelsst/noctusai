"""Owner decision D2 — the human validation gate over machine-extracted
contract data (`contrato_gerador.validacao_extracao`, migration 156).

WHAT THESE PIN
--------------
- the registry is DERIVED from what `carregador` reads: every value column it
  names is one the loader reads, and every column the loader reads that has
  a provenance quintet in the migrated schema is covered (drift guard both
  ways);
- a provenance column that does not exist yet (parallel migrations 153/154)
  makes its entry inert, never a crash — and writes only touch columns that
  exist on the row;
- GET .../validacao-extracao lists exactly the machine-pending values of THIS
  contract's partes / imóvel / certidões / última transferência, with source
  document, confidence, required flag and the manual-edit route;
- POST .../gerar refuses with 409 EXTRACAO_PENDENTE_VALIDACAO while anything
  is pending — the FE cannot bypass it;
- accept stamps `confirmado_por/_em` (value kept); reject NULLs the value and
  its provenance (the field becomes `faltando`, and the existing manual PATCH
  then fills it with `origem='manual'`); both append one ledger row;
- a stale `chave` is a 409 with NOTHING written.

All data is synthetic (see `contrato_gerador_fixtures`).
"""
from __future__ import annotations

import ast
import inspect
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from noctusai_lib.testing.migration_parser import parse_files

from app.modules.card_hub import documento_checklist_service as checklist_svc
from app.modules.card_hub import identidade_extracao_service as identidade_svc
from app.modules.card_hub.contrato_gerador import carregador
from app.modules.card_hub.contrato_gerador import validacao_extracao as vx
from app.modules.card_hub.contrato_gerador.service import hoje
from app.services import clientes_service as clientes_svc
from tests.modules.card_hub.conftest import ORG_ID
from tests.modules.card_hub.test_contrato_gerador_endpoints import (
    _T0,
    _auth,
    _rows,
    _seed_base,
    _seed_completo,
    _url,
)

_MIGRATIONS = Path(__file__).resolve().parents[3] / "migrations"


def _schema() -> dict[str, set[str]]:
    return parse_files(sorted(_MIGRATIONS.glob("[0-9]*.sql")))


def _chaves_lidas_pelo_carregador() -> set[str]:
    """Every literal key `carregador` reads off a row (`x.get("k")`), plus the
    `_endereco(row)` expansion and the columns `completude_contratual`
    selects (where `estado_civil` is read)."""
    arvore = ast.parse(inspect.getsource(carregador))
    chaves = {
        no.args[0].value
        for no in ast.walk(arvore)
        if isinstance(no, ast.Call)
        and isinstance(no.func, ast.Attribute)
        and no.func.attr == "get"
        and no.args
        and isinstance(no.args[0], ast.Constant)
        and isinstance(no.args[0].value, str)
    }
    chaves |= {f"endereco_{c}" for c in carregador._CAMPOS_ENDERECO}
    chaves |= set(checklist_svc._COLUNAS_QUALIFICACAO_CONTRATO)
    # `Pessoa.certidao_estado_civil_emitida_em` — read through completude's
    # `certidao_estado_civil_mais_recente`, which `select`s the 148 column.
    fonte_ec = ast.parse(inspect.getsource(identidade_svc.certidao_estado_civil_mais_recente).strip())
    chaves |= {
        no.args[0].value
        for no in ast.walk(fonte_ec)
        if isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute)
        and no.func.attr == "select" and no.args and isinstance(no.args[0], ast.Constant)
    }
    return chaves


# ─── The registry, structurally ─────────────────────────────────────────────


class TestRegistroDerivadoDoCarregador:
    def test_every_registry_value_column_is_one_the_loader_reads(self):
        lidas = _chaves_lidas_pelo_carregador()
        for campo in (*vx.CAMPOS_CLIENTE, *vx.CAMPOS_IMOVEL):
            for coluna in campo.valores:
                # The two act pointers are read as the dicts `dados_service
                # .obter` builds from these columns.
                fonte = {"onus_fonte": "onus_fonte", "titulo_aquisitivo": "titulo_aquisitivo_fonte"}
                if campo.campo in fonte:
                    assert fonte[campo.campo] in lidas
                    continue
                assert coluna in lidas, f"{campo.entidade}.{coluna} is not read by carregador"

    def test_every_loaded_column_with_provenance_is_in_the_registry(self):
        """The converse drift guard: a column the contract reads that ALREADY
        has a `<campo>_origem` column must be gated — otherwise a machine
        value reaches the instrument unvalidated."""
        schema = _schema()
        lidas = _chaves_lidas_pelo_carregador()
        cobertas = {
            ("clientes", c) for campo in vx.CAMPOS_CLIENTE for c in campo.valores
        } | {("imovel_dados", c) for campo in vx.CAMPOS_IMOVEL for c in campo.valores}
        for tabela in ("clientes", "imovel_dados"):
            colunas = schema[f"social_wiring.{tabela}"]
            for coluna in lidas & colunas:
                if f"{coluna}_origem" in colunas and f"{coluna}_confirmado_em" in colunas:
                    assert (tabela, coluna) in cobertas, (
                        f"{tabela}.{coluna} feeds the contract and has provenance, "
                        "but validacao_extracao.REGISTRO does not gate it"
                    )

    def test_the_ledger_table_matches_the_shared_contract(self):
        colunas = _schema()["social_wiring.extracao_validacoes"]
        assert {
            "id", "org_id", "contrato_id", "entidade", "entidade_id", "campo", "valor_extraido",
            "origem", "fonte_documento_id", "confianca", "decisao", "decidido_por", "decidido_em",
            "created_at",
        } <= colunas


class TestColunaAindaInexistente:
    """Parallel slices (153/154) add provenance columns; until they land an
    entry is inert, and writes never name a column the row lacks."""

    endereco = next(c for c in vx.CAMPOS_CLIENTE if c.campo == "endereco")

    def test_a_row_without_the_provenance_columns_is_not_pending(self):
        assert not self.endereco.pendente({"endereco_logradouro": "Rua X"})

    def test_the_same_row_with_153s_columns_is_pending(self):
        row = {
            "endereco_logradouro": "Rua X", "endereco_origem": "comprovante_endereco",
            "endereco_documento_id": str(uuid4()), "endereco_em": _T0,
            "endereco_confirmado_por": None, "endereco_confirmado_em": None,
        }
        assert self.endereco.pendente(row)
        assert not self.endereco.pendente({**row, "endereco_origem": "manual"})
        assert not self.endereco.pendente({**row, "endereco_confirmado_em": _T0})
        assert not self.endereco.pendente({**row, "endereco_logradouro": None})

    def test_reject_only_names_columns_present_on_the_row(self):
        row = {"endereco_logradouro": "Rua X", "endereco_cidade": "C", "endereco_origem": "x",
               "endereco_confirmado_em": None}
        patch = vx._patch_rejeite(self.endereco, row)
        assert set(patch) == set(row)
        assert all(v is None for v in patch.values())

    def test_the_ato_detalhe_reject_keeps_its_not_null_origem(self):
        row = {"data_registro": "2020-01-10", "transmitentes": [{"nome": "A"}],
               "origem": "sugestao", "confirmado_por": None, "confirmado_em": None}
        patch = vx._patch_rejeite(vx.CAMPO_ATO_DETALHE, row)
        assert "origem" not in patch
        assert patch["transmitentes"] == [] and patch["data_registro"] is None
        assert not vx.CAMPO_ATO_DETALHE.pendente({**row, **patch})


# ─── Over the mock DB, real loader ───────────────────────────────────────────


def _vendedor(scoped, ids) -> dict:
    return next(r for r in _rows(scoped, "clientes") if r["id"] == ids["vendedor"])


def _cpf_extraido(scoped, ids, *, confianca="alta") -> str:
    """The vendedor's CPF, as a machine read it off an RG upload."""
    doc_id = str(uuid4())
    scoped.set_table_data("cliente_documentos", _rows(scoped, "cliente_documentos") + [{
        "id": doc_id, "org_id": ORG_ID, "cliente_id": ids["vendedor"], "tipo_documento": "rg",
        "nome_original": "rg-fulano.pdf", "deleted_at": None, "extracao_descartada_em": None,
        "extracao_cpf_confianca": confianca, "created_at": _T0,
    }])
    linhas = []
    for r in _rows(scoped, "clientes"):
        if r["id"] == ids["vendedor"]:
            r = {**r, "cpf_origem": "rg", "cpf_documento_id": doc_id, "cpf_em": _T0,
                 "cpf_confirmado_por": None, "cpf_confirmado_em": None}
        linhas.append(r)
    scoped.set_table_data("clientes", linhas)
    return doc_id


def _pendentes(client, ids) -> list[dict]:
    r = client.get(_url(ids, "validacao-extracao"), headers=_auth())
    assert r.status_code == 200, r.text
    return r.json()["pendentes"]


def _decidir(client, ids, *decisoes):
    return client.post(
        _url(ids, "validacao-extracao/decisoes"),
        json={"decisoes": [{"chave": c, "decisao": d} for c, d in decisoes]},
        headers=_auth(),
    )


def _gerar(client, ids):
    return client.post(_url(ids, "gerar"), json={"assinatura_data": hoje().isoformat()}, headers=_auth())


class TestListagem:
    def test_a_fully_human_card_has_nothing_pending(self, client, scoped):
        ids = _seed_completo(scoped)
        assert _pendentes(client, ids) == []

    def test_a_machine_read_value_is_listed_with_its_source(self, client, scoped):
        ids = _seed_completo(scoped)
        doc_id = _cpf_extraido(scoped, ids)
        [item] = _pendentes(client, ids)
        vendedor = _vendedor(scoped, ids)
        assert item == {
            "chave": f"cliente:{ids['vendedor']}:cpf",
            "entidade": "cliente",
            "entidade_id": ids["vendedor"],
            "campo": "cpf",
            "grupo": "Fulano de Tal (proprietario)",
            "rotulo": "CPF",
            "valor": vendedor["cpf"],
            "origem": "rg",
            "fonte_documento_id": doc_id,
            "fonte_nome": "rg-fulano.pdf",
            "confianca": "alta",
            "obrigatorio": True,
            "edicao": {"rota": f"/api/clientes/{ids['vendedor']}", "campo": "cpf", "tipo": "texto"},
        }

    def test_a_confirmed_or_manual_value_is_not_pending(self, client, scoped):
        ids = _seed_completo(scoped)
        _cpf_extraido(scoped, ids)
        linhas = [
            {**r, "cpf_confirmado_em": _T0} if r["id"] == ids["vendedor"] else r
            for r in _rows(scoped, "clientes")
        ]
        scoped.set_table_data("clientes", linhas)
        assert _pendentes(client, ids) == []

    def test_an_api_certidao_and_a_suggested_last_transfer_are_listed(self, client, scoped):
        ids = _seed_completo(scoped)
        resultados = _rows(scoped, "certidao_resultados")
        resultados[0] = {**resultados[0], "resultado_origem": "api",
                         "confirmado_por": None, "confirmado_em": None}
        scoped.set_table_data("certidao_resultados", resultados)
        detalhes = [
            {**d, "origem": "sugestao", "confirmado_em": None, "data_registro_confianca": "baixa"}
            for d in _rows(scoped, "matricula_ato_detalhes")
        ]
        scoped.set_table_data("matricula_ato_detalhes", detalhes)

        por_entidade = {i["entidade"]: i for i in _pendentes(client, ids)}
        assert set(por_entidade) == {"certidao", "ato_detalhe"}
        cert = por_entidade["certidao"]
        assert cert["entidade_id"] == resultados[0]["id"]
        assert cert["origem"] == "api" and cert["obrigatorio"] is True and cert["edicao"] is None
        ato = por_entidade["ato_detalhe"]
        assert ato["confianca"] == "baixa"
        assert "Antiga Dona Exemplo" in ato["valor"]

    def test_a_machine_matricula_number_on_the_imovel_is_listed(self, client, scoped):
        ids = _seed_completo(scoped)
        dados = [
            {**d, "numero_matricula_origem": "matricula", "numero_matricula_confirmado_em": None}
            for d in _rows(scoped, "imovel_dados") if d["codigo"] == "EX001"
        ]
        scoped.set_table_data("imovel_dados", dados)
        [item] = _pendentes(client, ids)
        assert item["chave"] == "imovel:EX001:numero_matricula"
        assert item["edicao"]["rota"] == "/api/imoveis/EX001/dados"

    @pytest.mark.parametrize("sufixo, metodo", [
        ("validacao-extracao", "get"), ("validacao-extracao/decisoes", "post"),
    ])
    def test_a_deleted_contract_is_404(self, client, scoped, sufixo, metodo):
        ids = _seed_base(scoped, contrato_over={"deleted_at": _T0})
        kwargs = {"json": {"decisoes": [{"chave": "x", "decisao": "aceito"}]}} if metodo == "post" else {}
        r = getattr(client, metodo)(_url(ids, sufixo), headers=_auth(), **kwargs)
        assert r.status_code == 404, r.text


class TestGerarRecusaEnquantoPendente:
    def test_generation_is_refused_with_the_pending_list(self, client, scoped, fake_storage):
        ids = _seed_completo(scoped)
        _cpf_extraido(scoped, ids)
        pendentes = _pendentes(client, ids)
        r = _gerar(client, ids)
        assert r.status_code == 409, r.text
        corpo = r.json()
        assert corpo["error"]["code"] == "EXTRACAO_PENDENTE_VALIDACAO"
        assert corpo["error"]["details"]["pendentes"] == pendentes
        assert corpo["error"]["details"]["conflitos"] == []
        assert _rows(scoped, "atendimento_contrato_versoes") == []


class TestDecisoes:
    def test_accept_stamps_the_confirmation_logs_it_and_unblocks_generation(
        self, client, scoped, fake_storage
    ):
        ids = _seed_completo(scoped)
        doc_id = _cpf_extraido(scoped, ids)
        cpf = _vendedor(scoped, ids)["cpf"]
        chave = f"cliente:{ids['vendedor']}:cpf"

        r = _decidir(client, ids, (chave, "aceito"))
        assert r.status_code == 200, r.text
        assert r.json() == {"aplicadas": 1, "pendentes": [], "conflitos": []}

        vendedor = _vendedor(scoped, ids)
        assert vendedor["cpf"] == cpf and vendedor["cpf_origem"] == "rg"
        assert vendedor["cpf_confirmado_em"] is not None
        [linha] = _rows(scoped, vx.LEDGER)
        assert linha["decisao"] == "aceito"
        assert (linha["entidade"], linha["entidade_id"], linha["campo"]) == ("cliente", ids["vendedor"], "cpf")
        assert linha["valor_extraido"] == cpf and linha["origem"] == "rg"
        assert linha["fonte_documento_id"] == doc_id and linha["confianca"] == "alta"
        assert linha["contrato_id"] == ids["contrato"] and linha["org_id"] == ORG_ID

        assert _gerar(client, ids).status_code == 201

    def test_reject_nulls_value_and_provenance_then_the_manual_patch_fills_it(
        self, client, scoped, fake_storage
    ):
        ids = _seed_completo(scoped)
        _cpf_extraido(scoped, ids)
        cpf = _vendedor(scoped, ids)["cpf"]

        r = _decidir(client, ids, (f"cliente:{ids['vendedor']}:cpf", "rejeitado"))
        assert r.status_code == 200, r.text
        vendedor = _vendedor(scoped, ids)
        for coluna in ("cpf", "cpf_origem", "cpf_documento_id", "cpf_em", "cpf_confirmado_em"):
            assert vendedor[coluna] is None, coluna
        [linha] = _rows(scoped, vx.LEDGER)
        assert linha["decisao"] == "rejeitado" and linha["valor_extraido"] == cpf

        # Now a `faltando` in the EXISTING gate — no longer a pending validation.
        assert _pendentes(client, ids) == []
        geracao = client.get(_url(ids, "geracao"), headers=_auth()).json()
        assert any(f["campo"].endswith("cpf") for f in geracao["faltando"])

        # The modal's inline input is `PATCH /api/clientes/{id}` (the route's
        # own client seam is not the card_hub one this mock seeds), which
        # delegates to this service — the write that stamps origem='manual'.
        clientes_svc.update_cliente(scoped, UUID(ORG_ID), UUID(ids["vendedor"]), cpf=cpf)
        assert _vendedor(scoped, ids)["cpf_origem"] == "manual"
        assert _pendentes(client, ids) == []
        assert _gerar(client, ids).status_code == 201

    def test_accept_all_and_reject_all_in_one_request(self, client, scoped):
        ids = _seed_completo(scoped)
        _cpf_extraido(scoped, ids)
        resultados = _rows(scoped, "certidao_resultados")
        resultados[0] = {**resultados[0], "resultado_origem": "ia",
                         "confirmado_por": None, "confirmado_em": None}
        scoped.set_table_data("certidao_resultados", resultados)
        pendentes = _pendentes(client, ids)
        assert len(pendentes) == 2

        r = _decidir(client, ids, *[(p["chave"], "rejeitado") for p in pendentes])
        assert r.status_code == 200, r.text
        assert r.json()["aplicadas"] == 2 and r.json()["pendentes"] == []
        cert = next(x for x in _rows(scoped, "certidao_resultados") if x["id"] == resultados[0]["id"])
        for coluna in ("numero", "emitida_em", "validade_ate", "resultado", "resultado_origem"):
            assert cert[coluna] is None, coluna
        assert {l["decisao"] for l in _rows(scoped, vx.LEDGER)} == {"rejeitado"}

    def test_accepting_a_suggested_act_detail_confirms_it(self, client, scoped):
        ids = _seed_completo(scoped)
        detalhes = [{**d, "origem": "sugestao", "confirmado_em": None}
                    for d in _rows(scoped, "matricula_ato_detalhes")]
        scoped.set_table_data("matricula_ato_detalhes", detalhes)
        [item] = _pendentes(client, ids)
        assert _decidir(client, ids, (item["chave"], "aceito")).status_code == 200
        [det] = [d for d in _rows(scoped, "matricula_ato_detalhes") if d["id"] == item["entidade_id"]]
        assert det["origem"] == "confirmado" and det["confirmado_em"] is not None

    def test_a_stale_key_is_409_and_nothing_is_written(self, client, scoped):
        ids = _seed_completo(scoped)
        _cpf_extraido(scoped, ids)
        [item] = _pendentes(client, ids)
        r = _decidir(client, ids, (item["chave"], "aceito"), ("cliente:nao-existe:cpf", "aceito"))
        assert r.status_code == 409, r.text
        assert r.json()["error"]["code"] == "EXTRACAO_VALIDACAO_DESATUALIZADA"
        assert r.json()["error"]["details"]["chaves"] == ["cliente:nao-existe:cpf"]
        assert _rows(scoped, vx.LEDGER) == []
        assert _vendedor(scoped, ids)["cpf_confirmado_em"] is None

    def test_a_repeated_key_is_refused(self, client, scoped):
        ids = _seed_completo(scoped)
        _cpf_extraido(scoped, ids)
        [item] = _pendentes(client, ids)
        r = _decidir(client, ids, (item["chave"], "aceito"), (item["chave"], "rejeitado"))
        # The seed `ValidationError_` — this app's 400 VALIDATION_ERROR.
        assert r.status_code == 400, r.text
        assert r.json()["error"]["code"] == "VALIDATION_ERROR"
        assert _rows(scoped, vx.LEDGER) == []

    @pytest.mark.parametrize("corpo", [
        {"decisoes": []},
        {"decisoes": [{"chave": "x", "decisao": "talvez"}]},
    ])
    def test_a_malformed_body_is_422(self, client, scoped, corpo):
        ids = _seed_completo(scoped)
        r = client.post(_url(ids, "validacao-extracao/decisoes"), json=corpo, headers=_auth())
        assert r.status_code == 422, r.text


class TestTituloAquisitivoSugerido:
    """Migration 154 machine-fills the título pointer (`origem='sugerido'`,
    unconfirmed); accepting it here IS the confirmation the gate reads."""

    def _sugerido(self, scoped):
        dados = [
            {**d, "titulo_aquisitivo_origem": "sugerido", "titulo_aquisitivo_confirmado_em": None}
            if d["codigo"] == "EX001" else d
            for d in _rows(scoped, "imovel_dados")
        ]
        scoped.set_table_data("imovel_dados", dados)

    def test_it_is_pending_labelled_by_its_act(self, client, scoped):
        ids = _seed_completo(scoped)
        self._sugerido(scoped)
        [item] = _pendentes(client, ids)
        assert item["chave"] == "imovel:EX001:titulo_aquisitivo"
        assert item["valor"] == "R.1" and item["obrigatorio"] is True

    def test_accepting_it_satisfies_the_existing_gate(self, client, scoped, fake_storage):
        ids = _seed_completo(scoped)
        self._sugerido(scoped)
        geracao = client.get(_url(ids, "geracao"), headers=_auth()).json()
        assert any(f["campo"] == "matricula.titulo_aquisitivo" for f in geracao["faltando"])
        assert _decidir(client, ids, ("imovel:EX001:titulo_aquisitivo", "aceito")).status_code == 200
        geracao = client.get(_url(ids, "geracao"), headers=_auth()).json()
        assert geracao["pronto"] is True, geracao["faltando"]
        assert _gerar(client, ids).status_code == 201


class TestConflitosAbertos:
    def _conflito_cliente(self, scoped, ids, campo="cpf") -> str:
        cid = str(uuid4())
        scoped.set_table_data("cliente_campo_conflitos", [{
            "id": cid, "org_id": ORG_ID, "cliente_id": ids["vendedor"], "campo": campo,
            "valor_anterior": "111", "origem_anterior": "manual", "valor_proposto": "222",
            "origem_proposto": "rg", "confianca_proposta": "alta", "fonte_tabela": None,
            "fonte_id": None, "status": "pendente", "notificado_em": None, "decidido_por": None,
            "decidido_em": None, "created_at": _T0,
        }])
        return cid

    def test_an_open_party_conflict_is_listed_and_blocks_generation(self, client, scoped, fake_storage):
        ids = _seed_completo(scoped)
        cid = self._conflito_cliente(scoped, ids)
        corpo = client.get(_url(ids, "validacao-extracao"), headers=_auth()).json()
        assert corpo["pendentes"] == []
        [conflito] = corpo["conflitos"]
        assert conflito["id"] == cid and conflito["campo"] == "cpf"
        assert (conflito["valor_atual"], conflito["valor_proposto"]) == ("111", "222")
        assert conflito["link"]["rota"] == "/configuracoes"
        r = _gerar(client, ids)
        assert r.status_code == 409, r.text
        assert r.json()["error"]["details"]["conflitos"] == corpo["conflitos"]

    def test_a_conflict_on_a_non_contract_field_does_not_block(self, client, scoped, fake_storage):
        ids = _seed_completo(scoped)
        self._conflito_cliente(scoped, ids, campo="data_nascimento")
        assert client.get(_url(ids, "validacao-extracao"), headers=_auth()).json()["conflitos"] == []
        assert _gerar(client, ids).status_code == 201

    def test_the_identity_slices_conjuge_conflict_maps_to_the_registry_field(self, client, scoped):
        """153 files the cônjuge link conflict under its column name."""
        ids = _seed_completo(scoped)
        self._conflito_cliente(scoped, ids, campo="conjuge_cliente_id")
        [conflito] = client.get(_url(ids, "validacao-extracao"), headers=_auth()).json()["conflitos"]
        assert conflito["campo"] == "conjuge" and conflito["rotulo"] == "Cônjuge vinculado"

    def test_a_decided_conflict_does_not_block(self, client, scoped):
        ids = _seed_completo(scoped)
        self._conflito_cliente(scoped, ids)
        linhas = [{**r, "status": "aceito"} for r in _rows(scoped, "cliente_campo_conflitos")]
        scoped.set_table_data("cliente_campo_conflitos", linhas)
        assert client.get(_url(ids, "validacao-extracao"), headers=_auth()).json()["conflitos"] == []

    def test_an_open_imovel_conflict_links_to_the_imovel(self, client, scoped):
        ids = _seed_completo(scoped)
        cid = str(uuid4())
        scoped.set_table_data("imovel_campo_conflitos", [{
            "id": cid, "org_id": ORG_ID, "codigo": "EX001", "campo": "numero_matricula",
            "valor_anterior": "12345", "origem_anterior": "manual", "valor_proposto": "12346",
            "origem_proposto": "matricula", "status": "pendente", "created_at": _T0,
        }])
        [conflito] = client.get(_url(ids, "validacao-extracao"), headers=_auth()).json()["conflitos"]
        assert conflito["entidade"] == "imovel" and conflito["rotulo"] == "Número da matrícula"
        assert conflito["link"]["rota"] == f"/imoveis/EX001?conflito={cid}"

    def _empresa_com_conflito(self, scoped, ids, campo="situacao_cadastral") -> tuple[str, str]:
        """P0c contract §H6/item 4 — `empresa_campo_conflitos` (migration
        167), the SAME shared-writer table `app.services.campo_conflitos.
        EMPRESA` opens onto. The vendedor holds the participação (E1's
        `_empresas_de_certificandos`), so this empresa reaches
        `dados.empresas`/`listar_conflitos` the same way `_conflito_cliente`
        reaches `clientes` — through the real loader, not an injected
        fixture."""
        empresa_id = str(uuid4())
        scoped.set_table_data("empresas", [{
            "id": empresa_id, "org_id": ORG_ID, "cnpj": "11222333000181",
            "razao_social": "Empresa Conflito LTDA", "nome_fantasia": None,
            "natureza_juridica": None, "data_abertura": None,
            "situacao_cadastral": "ativa", "data_situacao_cadastral": None,
            "motivo_situacao": None, "dados_origem": "cartao_cnpj",
            "dados_documento_id": None, "dados_em": _T0,
            # Group provenance already CONFIRMED — isolates this test to
            # the per-field CONFLICT alone, never the group's own
            # machine-pending state (a separate, already-covered case:
            # `TestListagem`/`CAMPO_EMPRESA_DADOS`).
            "dados_confirmado_por": str(uuid4()), "dados_confirmado_em": _T0,
            "created_at": _T0, "updated_at": None,
        }])
        scoped.set_table_data("cliente_empresa_participacoes", [{
            "id": str(uuid4()), "org_id": ORG_ID, "cliente_id": ids["vendedor"],
            "empresa_id": empresa_id, "participacao_pct": "100.00", "desde": None,
            "fonte_documento_id": None, "origem": "manual",
            "confirmado_por": None, "confirmado_em": None, "created_at": _T0,
        }])
        conflito_id = str(uuid4())
        scoped.set_table_data("empresa_campo_conflitos", [{
            "id": conflito_id, "org_id": ORG_ID, "empresa_id": empresa_id, "campo": campo,
            "valor_anterior": "ativa", "origem_anterior": "cartao_cnpj",
            "valor_proposto": "baixada", "origem_proposto": "cartao_cnpj",
            "confianca_proposta": "alta", "fonte_tabela": "empresa_documentos", "fonte_id": None,
            "status": "pendente", "notificado_em": None, "decidido_por": None,
            "decidido_em": None, "created_at": _T0,
        }])
        return empresa_id, conflito_id

    def test_an_open_empresa_conflict_is_listed_and_blocks_generation(
        self, client, scoped, fake_storage
    ):
        ids = _seed_completo(scoped)
        empresa_id, conflito_id = self._empresa_com_conflito(scoped, ids)
        corpo = client.get(_url(ids, "validacao-extracao"), headers=_auth()).json()
        assert corpo["pendentes"] == []
        [conflito] = corpo["conflitos"]
        assert conflito["id"] == conflito_id
        assert conflito["entidade"] == "empresa" and conflito["entidade_id"] == empresa_id
        assert conflito["campo"] == "situacao_cadastral"
        assert conflito["rotulo"] == "Situação cadastral"
        assert conflito["grupo"] == "Empresa Empresa Conflito LTDA"
        assert (conflito["valor_atual"], conflito["valor_proposto"]) == ("ativa", "baixada")
        assert conflito["link"]["rota"] == "/configuracoes"
        r = _gerar(client, ids)
        assert r.status_code == 409, r.text
        assert r.json()["error"]["details"]["conflitos"] == corpo["conflitos"]

    def test_a_decided_empresa_conflict_does_not_block(self, client, scoped):
        ids = _seed_completo(scoped)
        self._empresa_com_conflito(scoped, ids)
        linhas = [{**r, "status": "aceito"} for r in _rows(scoped, "empresa_campo_conflitos")]
        scoped.set_table_data("empresa_campo_conflitos", linhas)
        assert client.get(_url(ids, "validacao-extracao"), headers=_auth()).json()["conflitos"] == []


# ─── S2b: negociação/financiamento extraction contract §E4/§G ──────────────


def _patch_row(scoped, tabela: str, chave_coluna: str, chave_valor, patch: dict) -> None:
    linhas = [
        {**r, **patch} if r.get(chave_coluna) == chave_valor else r
        for r in _rows(scoped, tabela)
    ]
    scoped.set_table_data(tabela, linhas)


class TestNegociacaoFinanciamentoD2:
    """[S2b contract §E4 item 4/§G] The D2 gate extended over migration
    171's four new provenance-tracked surfaces — `atendimento_negociacao.
    valor_negociado` (a house quintet), each `atendimento_negociacao_
    parcelas` row's `valor` (flat row provenance, [H4]'s derived
    intermediária suggestion is the same field with `origem='derivado'`),
    `atendimento_financiamento`'s fgts/numero_proposta/agente_financeiro/
    situacao ([H6]) quintets, and each `atendimento_favorecidos` row's bank
    data ([H5], flat row provenance) — plus `atendimento_campo_conflitos`.
    The migration itself is S2's (built in parallel); these columns are
    seeded directly onto the in-memory mock rows, which needs no schema."""

    def _doc(self, scoped, ids, tipo: str = "contrato_financiamento") -> str:
        """A row on the EXISTING `atendimento_documentos` store (0. — the
        deal document store `financiamento_service.obter` also reads
        unfiltered by tipo), so it needs that store's full 7-field shape
        (`documento_base`), not just the columns the D2 gate itself reads."""
        doc_id = str(uuid4())
        scoped.set_table_data("atendimento_documentos", _rows(scoped, "atendimento_documentos") + [{
            "id": doc_id, "org_id": ORG_ID, "atendimento_id": ids["atendimento"],
            "tipo_documento": tipo, "nome_original": f"{tipo}.pdf",
            "mime_type": "application/pdf", "tamanho_bytes": 1024, "enviado_por": None,
            "extracao_dados": None, "deleted_at": None, "created_at": _T0,
        }])
        return doc_id

    def _negociacao_extraida(self, scoped, ids, doc_id, *, origem="contrato_financiamento"):
        _patch_row(scoped, "atendimento_negociacao", "atendimento_id", ids["atendimento"], {
            "valor_negociado_origem": origem, "valor_negociado_documento_id": doc_id,
            "valor_negociado_em": _T0, "valor_negociado_confirmado_por": None,
            "valor_negociado_confirmado_em": None,
        })

    def _financiamento_patch(self, scoped, ids, patch: dict) -> None:
        _patch_row(scoped, "atendimento_financiamento", "atendimento_id", ids["atendimento"], patch)

    def _parcela_extraida(self, scoped, pid, doc_id, *, origem="contrato_financiamento"):
        _patch_row(scoped, "atendimento_negociacao_parcelas", "id", pid, {
            "origem": origem, "documento_id": doc_id, "extraido_em": _T0,
            "confirmado_por": None, "confirmado_em": None,
        })

    def _favorecido_extraido(self, scoped, fid, doc_id, *, origem="contrato_financiamento"):
        _patch_row(scoped, "atendimento_favorecidos", "id", fid, {
            "origem": origem, "documento_id": doc_id, "extraido_em": _T0,
            "confirmado_por": None, "confirmado_em": None,
        })

    # ── valor_negociado (§C item 3, §H2) ──

    def test_a_pending_valor_negociado_is_listed_and_blocks_generation(self, client, scoped, fake_storage):
        ids = _seed_completo(scoped)
        doc_id = self._doc(scoped, ids, "guia_itbi")
        self._negociacao_extraida(scoped, ids, doc_id, origem="guia_itbi")
        [item] = _pendentes(client, ids)
        assert item["chave"] == f"negociacao:{ids['atendimento']}:valor_negociado"
        assert item["entidade"] == "negociacao" and item["entidade_id"] == ids["atendimento"]
        assert item["grupo"] == "Negociação"
        assert item["origem"] == "guia_itbi" and item["fonte_documento_id"] == doc_id
        assert item["fonte_nome"] == "guia_itbi.pdf"
        r = _gerar(client, ids)
        assert r.status_code == 409, r.text
        assert r.json()["error"]["details"]["pendentes"] == [item]

    # 🔴 Accept/reject over the LIVE mock DB (`_decidir` -> `_gravar` ->
    # `.update(patch)`) is schema-VALIDATED against the migrations that are
    # actually in this worktree — `atendimento_negociacao`/`atendimento_
    # negociacao_parcelas`/`atendimento_financiamento` predate 171 (S2's
    # parallel PR), so a live write naming a quintet column 409s the mock
    # with `MockSchemaError`, not a finding about this code. Same posture
    # `TestColunaAindaInexistente` already takes for 153/154's columns:
    # exercise `_patch_aceite`/`_patch_rejeite`/`.pendente()` directly.
    def test_accepting_valor_negociado_stamps_confirmation(self):
        row = {
            "valor_negociado": "500000.00", "valor_negociado_origem": "contrato_financiamento",
            "valor_negociado_documento_id": str(uuid4()), "valor_negociado_em": _T0,
            "valor_negociado_confirmado_por": None, "valor_negociado_confirmado_em": None,
        }
        assert vx.CAMPO_NEGOCIACAO_VALOR.pendente(row)
        patch = vx._patch_aceite(vx.CAMPO_NEGOCIACAO_VALOR, row, uuid4(), _T0)
        assert patch["valor_negociado_confirmado_em"] == _T0
        assert not vx.CAMPO_NEGOCIACAO_VALOR.pendente({**row, **patch})

    # ── parcela valor (§C item 4, migration 171 nullable) ──

    def test_a_pending_parcela_valor_blocks_generation(self, client, scoped, fake_storage):
        ids = _seed_completo(scoped)
        doc_id = self._doc(scoped, ids)
        self._parcela_extraida(scoped, "p3", doc_id)
        [item] = _pendentes(client, ids)
        assert item["chave"] == "parcela:p3:valor"
        assert item["entidade"] == "parcela" and item["entidade_id"] == "p3"
        assert item["grupo"] == "Parcelas" and item["rotulo"] == "Valor da parcela — financiamento"
        r = _gerar(client, ids)
        assert r.status_code == 409, r.text
        assert r.json()["error"]["details"]["pendentes"] == [item]

    def test_rejecting_a_parcela_valor_nulls_it_into_the_existing_falta(self):
        """[§C item 4] `valor` is nullable (171) precisely so reject can NULL
        it without deleting the row — `derivacao` already treats a NULL
        parcela `valor` as `negociacao.parcela.<id>.valor` falta (§0)."""
        row = {
            "valor": "400000.00", "origem": "contrato_financiamento",
            "documento_id": str(uuid4()), "extraido_em": _T0,
            "confirmado_por": None, "confirmado_em": None,
        }
        patch = vx._patch_rejeite(vx.CAMPO_PARCELA_VALOR, row)
        assert set(patch) == set(row)
        assert all(v is None for v in patch.values())
        assert not vx.CAMPO_PARCELA_VALOR.pendente({**row, **patch})

    # ── financiamento quintets (§C item 5, §H6) ──

    def test_pending_fgts_is_listed_and_blocks(self, client, scoped, fake_storage):
        ids = _seed_completo(scoped, n=2)  # n=2 seeds the base row with fgts=True
        doc_id = self._doc(scoped, ids)
        self._financiamento_patch(scoped, ids, {
            "fgts_origem": "contrato_financiamento", "fgts_documento_id": doc_id,
            "fgts_em": _T0, "fgts_confirmado_por": None, "fgts_confirmado_em": None,
        })
        [item] = _pendentes(client, ids)
        assert item["chave"] == f"financiamento:{ids['atendimento']}:fgts"
        assert item["grupo"] == "Financiamento"
        assert _gerar(client, ids).status_code == 409

    def test_fgts_reject_resets_to_false_never_null(self):
        """[§E4 item 4] A NOT NULL boolean's `False` is indistinguishable
        from "unset" — reject must reset it, never leave a disallowed NULL."""
        campo_fgts = next(c for c in vx.CAMPOS_FINANCIAMENTO if c.campo == "fgts")
        row = {
            "fgts": True, "fgts_origem": "contrato_financiamento",
            "fgts_documento_id": str(uuid4()), "fgts_em": _T0,
            "fgts_confirmado_por": None, "fgts_confirmado_em": None,
        }
        patch = vx._patch_rejeite(campo_fgts, row)
        assert patch["fgts"] is False
        assert patch["fgts_origem"] is None
        assert not campo_fgts.pendente({**row, **patch})

    def test_numero_proposta_and_agente_financeiro_and_situacao_are_pending(self, client, scoped, fake_storage):
        ids = _seed_completo(scoped)
        doc_id = self._doc(scoped, ids, "proposta_financiamento")
        self._financiamento_patch(scoped, ids, {
            "numero_proposta": "12345", "numero_proposta_origem": "proposta_financiamento",
            "numero_proposta_documento_id": doc_id, "numero_proposta_em": _T0,
            "numero_proposta_confirmado_por": None, "numero_proposta_confirmado_em": None,
            "agente_financeiro_id": str(uuid4()), "agente_financeiro_origem": "proposta_financiamento",
            "agente_financeiro_documento_id": doc_id, "agente_financeiro_em": _T0,
            "agente_financeiro_confirmado_por": None, "agente_financeiro_confirmado_em": None,
            # [H6] A signed contrato de financiamento sets `situacao='aprovado'`.
            "situacao_origem": "contrato_financiamento", "situacao_documento_id": doc_id,
            "situacao_em": _T0, "situacao_confirmado_por": None, "situacao_confirmado_em": None,
        })
        chaves = {p["chave"] for p in _pendentes(client, ids)}
        assert chaves == {
            f"financiamento:{ids['atendimento']}:numero_proposta",
            f"financiamento:{ids['atendimento']}:agente_financeiro",
            f"financiamento:{ids['atendimento']}:situacao",
        }
        r = _gerar(client, ids)
        assert r.status_code == 409, r.text

    # ── favorecido bank data (§H5) ──

    def test_favorecido_bank_data_is_pending_and_blocks(self, client, scoped, fake_storage):
        ids = _seed_completo(scoped)
        doc_id = self._doc(scoped, ids)
        self._favorecido_extraido(scoped, ids["fav_vendedor"], doc_id)
        [item] = _pendentes(client, ids)
        assert item["chave"] == f"favorecido:{ids['fav_vendedor']}:dados"
        assert item["entidade"] == "favorecido" and item["entidade_id"] == ids["fav_vendedor"]
        assert item["grupo"] == "Favorecidos" and item["rotulo"].startswith("Dados bancários do favorecido")
        assert _gerar(client, ids).status_code == 409

    # ── atendimento_campo_conflitos (§E4 item 4) ──

    def test_an_open_valor_negociado_conflict_blocks_generation(self, client, scoped, fake_storage):
        ids = _seed_completo(scoped)
        cid = str(uuid4())
        scoped.set_table_data("atendimento_campo_conflitos", [{
            "id": cid, "org_id": ORG_ID, "atendimento_id": ids["atendimento"],
            "campo": "valor_negociado", "valor_anterior": "500000.00", "origem_anterior": "manual",
            "valor_proposto": "510000.00", "origem_proposto": "guia_itbi",
            "confianca_proposta": "media", "fonte_tabela": "atendimento_documentos",
            "fonte_id": None, "documento_id_proposto": None, "status": "pendente",
            "notificado_em": None, "decidido_por": None, "decidido_em": None, "created_at": _T0,
        }])
        corpo = client.get(_url(ids, "validacao-extracao"), headers=_auth()).json()
        assert corpo["pendentes"] == []
        [conflito] = corpo["conflitos"]
        assert conflito["id"] == cid and conflito["entidade"] == "negociacao"
        assert conflito["entidade_id"] == ids["atendimento"] and conflito["campo"] == "valor_negociado"
        assert (conflito["valor_atual"], conflito["valor_proposto"]) == ("500000.00", "510000.00")
        r = _gerar(client, ids)
        assert r.status_code == 409, r.text
        assert r.json()["error"]["details"]["conflitos"] == corpo["conflitos"]

    def test_a_parcela_conflict_resolves_to_its_own_parcela_row(self, client, scoped, fake_storage):
        ids = _seed_completo(scoped)
        cid = str(uuid4())
        scoped.set_table_data("atendimento_campo_conflitos", [{
            "id": cid, "org_id": ORG_ID, "atendimento_id": ids["atendimento"],
            "campo": "parcela.p3.valor", "valor_anterior": "400000.00", "origem_anterior": "manual",
            "valor_proposto": "410000.00", "origem_proposto": "contrato_financiamento",
            "confianca_proposta": "baixa", "fonte_tabela": "atendimento_documentos",
            "fonte_id": None, "documento_id_proposto": None, "status": "pendente",
            "notificado_em": None, "decidido_por": None, "decidido_em": None, "created_at": _T0,
        }])
        [conflito] = client.get(_url(ids, "validacao-extracao"), headers=_auth()).json()["conflitos"]
        assert conflito["entidade"] == "parcela" and conflito["entidade_id"] == "p3"
        assert conflito["campo"] == "valor" and conflito["rotulo"] == "Valor da parcela"

    def test_a_financiamento_conflict_resolves_by_the_dotted_vocabulary(self, client, scoped, fake_storage):
        ids = _seed_completo(scoped)
        scoped.set_table_data("atendimento_campo_conflitos", [{
            "id": str(uuid4()), "org_id": ORG_ID, "atendimento_id": ids["atendimento"],
            "campo": "financiamento.agente_financeiro_id", "valor_anterior": None,
            "origem_anterior": None, "valor_proposto": str(uuid4()),
            "origem_proposto": "proposta_financiamento", "confianca_proposta": "baixa",
            "fonte_tabela": "atendimento_documentos", "fonte_id": None,
            "documento_id_proposto": None, "status": "pendente", "notificado_em": None,
            "decidido_por": None, "decidido_em": None, "created_at": _T0,
        }])
        [conflito] = client.get(_url(ids, "validacao-extracao"), headers=_auth()).json()["conflitos"]
        assert conflito["entidade"] == "financiamento" and conflito["entidade_id"] == ids["atendimento"]
        assert conflito["campo"] == "agente_financeiro" and conflito["rotulo"] == "Agente financeiro"

    def test_an_unrecognized_atendimento_conflito_campo_is_skipped_not_crashed(
        self, client, scoped, fake_storage
    ):
        ids = _seed_completo(scoped)
        scoped.set_table_data("atendimento_campo_conflitos", [{
            "id": str(uuid4()), "org_id": ORG_ID, "atendimento_id": ids["atendimento"],
            "campo": "algo_desconhecido", "valor_anterior": None, "origem_anterior": None,
            "valor_proposto": None, "origem_proposto": None, "confianca_proposta": None,
            "fonte_tabela": None, "fonte_id": None, "documento_id_proposto": None,
            "status": "pendente", "notificado_em": None, "decidido_por": None,
            "decidido_em": None, "created_at": _T0,
        }])
        assert client.get(_url(ids, "validacao-extracao"), headers=_auth()).json()["conflitos"] == []
        assert _gerar(client, ids).status_code == 201

    def test_a_decided_atendimento_conflict_does_not_block(self, client, scoped, fake_storage):
        ids = _seed_completo(scoped)
        scoped.set_table_data("atendimento_campo_conflitos", [{
            "id": str(uuid4()), "org_id": ORG_ID, "atendimento_id": ids["atendimento"],
            "campo": "valor_negociado", "valor_anterior": "500000.00", "origem_anterior": "manual",
            "valor_proposto": "510000.00", "origem_proposto": "guia_itbi",
            "confianca_proposta": "media", "fonte_tabela": "atendimento_documentos",
            "fonte_id": None, "documento_id_proposto": None, "status": "aceito",
            "notificado_em": None, "decidido_por": str(uuid4()), "decidido_em": _T0, "created_at": _T0,
        }])
        assert client.get(_url(ids, "validacao-extracao"), headers=_auth()).json()["conflitos"] == []
        assert _gerar(client, ids).status_code == 201

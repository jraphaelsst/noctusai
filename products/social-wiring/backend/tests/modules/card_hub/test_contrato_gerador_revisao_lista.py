"""The "Aguardando revisão jurídica" list, shaped like the real case the owner
called trash (2026-10-13): 43 rows, no values, the same fact once per spouse,
derived/copied values counted as "extracted", ~15 certidão rows with one
Serasa file three times, and an unrelated company that only reached the
contract through an UNCONFIRMED Crednet participação.

WHAT THESE PIN (`validacao_extracao.pendentes_para_revisao`, through the real
loader over the mock DB):
- every item carries its VALUE, rendered for display (dates dd/mm/aaaa,
  CPF/RG masked in `valor_mascarado`);
- ONE row per fact: a couple fact (same certidão, same value) appears once,
  labelled with both names; no (campo, valor, documento) repeats;
- `conjuge_domicilio`, a gênero inferred from a certidão and the cônjuge link
  are `derivado` — listed apart, never counted as extracted;
- a value two independent documents agree on is `corroborado`, not pending;
- the confidence shown is the MEASURED precision for (campo, origem), never a
  document's own confidence (which, on a spouse's row, was the titular's);
- certidões: the latest result per tipo only, and an `api`/`texto` verdict is
  the issuer's, not a review item — one Serasa (`ia`) row survives;
- an empresa reached only through an unconfirmed Crednet participação never
  enters the contract, so never its review list.

All data is synthetic.
"""
from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.modules.card_hub import contratos_service as contratos_svc
from app.modules.card_hub.contrato_gerador import carregador
from app.modules.card_hub.contrato_gerador import validacao_extracao as vx
from tests.modules.card_hub.conftest import ORG_ID
from tests.modules.card_hub.test_contrato_gerador_endpoints import (
    _T0,
    _auth,
    _qualificado,
    _rows,
    _seed_completo,
)
from tests.modules.card_hub.test_contrato_gerador_revisao_juridica import _gerado_com_cpf_extraido
from tests.modules.card_hub.test_contrato_gerador_validacao_extracao import _vendedor

#: The regression cap for `_caso_real` — the owner's panel showed 43 rows for
#: the real deal; this synthetic one listed 25 before the rework. Every
#: row now is one fact a human must actually look at, plus the two collapsed
#: groups (derivados, corroborados).
MAX_ITENS_CASO_REAL = 9


def _sem_confirmacao(**campos_origem: tuple[str, str | None]) -> dict:
    """`{campo: (origem, documento_id)}` -> the provenance columns of a
    machine-filled, unconfirmed value."""
    out: dict = {}
    for campo, (origem, doc) in campos_origem.items():
        out.update({
            f"{campo}_origem": origem, f"{campo}_documento_id": doc, f"{campo}_em": _T0,
            f"{campo}_confirmado_por": None, f"{campo}_confirmado_em": None,
        })
    return out


def _doc(cid: str, tipo: str, nome: str, **extra) -> dict:
    return {
        "id": str(uuid4()), "org_id": ORG_ID, "cliente_id": cid, "tipo_documento": tipo,
        "nome_original": nome, "deleted_at": None, "extracao_descartada_em": None,
        "created_at": _T0, **extra,
    }


def _caso_real(scoped) -> dict:
    ids = _seed_completo(scoped)
    vend, conj, parte_conj = ids["vendedor"], str(uuid4()), str(uuid4())

    cert = _doc(vend, "certidao_casamento", "certidao-casamento.pdf",
                extracao_genero="Feminino", extracao_genero_confianca="baixa",
                extracao_nome_confianca="alta")
    cnh = _doc(vend, "cnh", "cnh-fulano.pdf", extracao_nome="Fulano de Tal",
               extracao_nome_confianca="alta", extracao_rg="11.111.111-1",
               extracao_rg_confianca="alta")
    rg = _doc(vend, "rg", "rg-fulano.pdf", extracao_nome="Fulano de Tal",
              extracao_nome_confianca="alta")
    comprovante = _doc(vend, "comprovante_endereco", "conta-de-luz.pdf")
    crednet = _doc(vend, "serasa_crednet", "serasa-crednet.pdf")
    scoped.set_table_data(
        "cliente_documentos",
        _rows(scoped, "cliente_documentos") + [cert, cnh, rg, comprovante, crednet],
    )

    casamento = {"estado_civil": "casado", "regime_bens": "comunhao_parcial",
                 "data_casamento": "2015-06-20"}
    da_certidao = {c: ("certidao_casamento", cert["id"])
                   for c in ("estado_civil", "regime_bens", "data_casamento", "conjuge")}
    clientes = []
    for r in _rows(scoped, "clientes"):
        if r["id"] == vend:
            r = {**r, **casamento, "conjuge_cliente_id": conj, **_sem_confirmacao(
                **da_certidao,
                nome_oficial=("matricula", None),
                cpf=("cnh", cnh["id"]),
                rg=("cnh", cnh["id"]),
                endereco=("comprovante_endereco", comprovante["id"]),
            )}
        clientes.append(r)
    conjuge = {
        **_qualificado(conj, "Ciclana de Tal", "Feminino", "111222333", "55.555.555-5"),
        **casamento, "conjuge_cliente_id": vend,
        **_sem_confirmacao(
            **da_certidao,
            nome_oficial=("certidao_casamento", cert["id"]),
            genero=("certidao_casamento", cert["id"]),
            # R3 — the household address copied from the husband's own
            # comprovante: not a reading of any document of hers.
            endereco=("conjuge_domicilio", comprovante["id"]),
        ),
    }
    scoped.set_table_data("clientes", clientes + [conjuge])
    scoped.set_table_data("atendimento_partes", _rows(scoped, "atendimento_partes") + [{
        "id": parte_conj, "org_id": ORG_ID, "atendimento_id": ids["atendimento"],
        "cliente_id": conj, "lado": "vendedor", "papel": "conjuge", "ordem": 1,
        "observacao": None, "created_at": _T0, "created_by": None, "updated_at": None,
    }])

    # Certidões: the issuer's own verdicts (`api`), plus ONE Crednet reading
    # fanned into every consulta of the vendedor — 3 Serasa copies.
    serasa_ia = {"resultado_origem": "ia", "fonte_cliente_documento_id": crednet["id"],
                 "arquivo_nome": "serasa_crednet.pdf", "numero": "PROT-0001"}
    resultados = []
    for r in _rows(scoped, "certidao_resultados"):
        r = {**r, "resultado_origem": "api", "confirmado_por": None, "confirmado_em": None}
        if r["tipo"] == "serasa":
            r.update(serasa_ia)
        resultados.append(r)
    consultas = _rows(scoped, "certidao_consultas")
    base = consultas[0]
    for n in (2, 3):
        cid = str(uuid4())
        consultas.append({**base, "id": cid, "created_at": f"2026-0{n}-01T00:00:00+00:00"})
        serasa = next(r for r in resultados if r["tipo"] == "serasa" and r["consulta_id"] == base["id"])
        resultados.append({**serasa, "id": str(uuid4()), "consulta_id": cid,
                           "created_at": f"2026-0{n}-01T00:00:00+00:00"})
    scoped.set_table_data("certidao_consultas", consultas)
    scoped.set_table_data("certidao_resultados", resultados)

    # An unrelated company the Crednet lists as a participação — unconfirmed.
    empresa_id = str(uuid4())
    scoped.set_table_data("empresas", [{
        "id": empresa_id, "org_id": ORG_ID, "cnpj": "11444777000161",
        "razao_social": "SPEDIREXPRESS TRANSPORTES LTDA", "nome_fantasia": None,
        "situacao_cadastral": None, "data_situacao_cadastral": None,
        "dados_origem": "serasa_crednet", "dados_documento_id": crednet["id"], "dados_em": _T0,
        "dados_confirmado_por": None, "dados_confirmado_em": None, "created_at": _T0,
    }])
    scoped.set_table_data("cliente_empresa_participacoes", [{
        "id": str(uuid4()), "org_id": ORG_ID, "cliente_id": vend, "empresa_id": empresa_id,
        "participacao_pct": None, "desde": None, "fonte_documento_id": crednet["id"],
        "origem": "serasa_crednet", "confirmado_por": None, "confirmado_em": None,
        "created_at": _T0,
    }])
    ids.update(conjuge=conj, empresa=empresa_id, doc_certidao=cert["id"], doc_crednet=crednet["id"])
    return ids


def _lista(scoped, ids) -> list[dict]:
    dados, _ = carregador.carregar(
        scoped, UUID(ORG_ID), UUID(ids["cliente"]), UUID(ids["contrato"]), usuario_id=None
    )
    return vx.pendentes_para_revisao(scoped, UUID(ORG_ID), dados, usuario_id=None)


def _extraidos(itens: list[dict]) -> list[dict]:
    return [i for i in itens if i["secao"] == vx.SECAO_EXTRAIDO]


class TestCasoReal:
    def test_the_item_count_is_capped(self, client, scoped):
        itens = _lista(scoped, _caso_real(scoped))
        assert len(itens) <= MAX_ITENS_CASO_REAL, [(i["grupo"], i["rotulo"]) for i in itens]

    def test_no_fact_repeats(self, client, scoped):
        itens = _lista(scoped, _caso_real(scoped))
        # The spouse's COPY of an address shares (campo, valor, documento)
        # with the reading it was copied from, but is listed apart (derivado).
        chaves = [(i["campo"], i["valor_sha256"], i["fonte_documento_id"], i["secao"]) for i in itens]
        assert len(chaves) == len(set(chaves))
        assert len({i["chave"] for i in itens}) == len(itens)

    def test_every_item_carries_its_value(self, client, scoped):
        for item in _lista(scoped, _caso_real(scoped)):
            assert item["valor"], item

    def test_a_couple_fact_is_one_row_named_for_both(self, client, scoped):
        ids = _caso_real(scoped)
        [casamento] = [i for i in _lista(scoped, ids) if i["campo"] == "data_casamento"]
        assert casamento["valor"] == "20/06/2015"
        assert "Fulano de Tal" in casamento["grupo"] and "Ciclana de Tal" in casamento["grupo"]
        assert {a["chave"] for a in casamento["agrupadas"]} == {
            f"cliente:{ids['conjuge']}:data_casamento"
        }

    def test_derived_and_copied_values_are_not_extracted(self, client, scoped):
        ids = _caso_real(scoped)
        itens = _lista(scoped, ids)
        derivados = {(i["entidade_id"], i["campo"]) for i in itens if i["secao"] == vx.SECAO_DERIVADO}
        assert (ids["conjuge"], "endereco") in derivados
        assert (ids["conjuge"], "genero") in derivados
        assert "conjuge" in {c for _, c in derivados}
        assert not {(i["entidade_id"], i["campo"]) for i in _extraidos(itens)} & derivados
        assert len([i for i in itens if i["campo"] == "conjuge"]) == 1

    def test_two_agreeing_documents_corroborate(self, client, scoped):
        ids = _caso_real(scoped)
        [nome] = [i for i in _lista(scoped, ids)
                  if i["campo"] == "nome_oficial" and i["entidade_id"] == ids["vendedor"]]
        assert nome["secao"] == vx.SECAO_CORROBORADO
        assert nome["n_documentos"] == 2

    def test_confidence_is_the_measured_precision(self, client, scoped):
        ids = _caso_real(scoped)
        itens = {(i["entidade_id"], i["campo"]): i for i in _lista(scoped, ids)}
        rg = itens[(ids["vendedor"], "rg")]
        assert rg["precisao"] == "precisão medida 39% (18 contratos)"
        assert rg["valor_mascarado"] != rg["valor"] and rg["valor_mascarado"].endswith("1-1")
        # The spouse's nome comes off the couple's certidão — its measured
        # cell, never the document's own (the husband's) confidence column.
        assert itens[(ids["conjuge"], "nome_oficial")]["precisao"] == "precisão medida 60% (5 contratos)"
        assert itens[(ids["vendedor"], "endereco")]["fonte_tipo"] == "Comprovante de endereço"

    def test_one_serasa_and_no_issuer_verdicts(self, client, scoped):
        itens = _lista(scoped, _caso_real(scoped))
        certidoes = [i for i in itens if i["entidade"] == vx.ENTIDADE_CERTIDAO]
        assert len(certidoes) == 1
        assert certidoes[0]["origem"] == "ia"
        assert "PROT-0001" in certidoes[0]["valor"]

    def test_an_unconfirmed_crednet_empresa_is_not_in_the_contract(self, client, scoped):
        ids = _caso_real(scoped)
        dados, _ = carregador.carregar(
            scoped, UUID(ORG_ID), UUID(ids["cliente"]), UUID(ids["contrato"]), usuario_id=None
        )
        assert dados.empresas == []
        assert not [i for i in _lista(scoped, ids) if i["entidade"] == vx.ENTIDADE_EMPRESA]

    def test_order_is_identity_then_civil_then_address(self, client, scoped):
        ids = _caso_real(scoped)
        do_vendedor = [i["campo"] for i in _extraidos(_lista(scoped, ids))
                       if i["entidade_id"] == ids["vendedor"]]
        assert do_vendedor.index("rg") < do_vendedor.index("endereco")


class TestEmpresaConfirmada:
    @pytest.mark.parametrize("over", [
        {"confirmado_em": _T0, "confirmado_por": None},
        {"origem": "manual"},
    ])
    def test_a_confirmed_or_manual_participacao_enters_the_contract(self, client, scoped, over):
        ids = _caso_real(scoped)
        scoped.set_table_data("cliente_empresa_participacoes", [
            {**r, **over} for r in _rows(scoped, "cliente_empresa_participacoes")
        ])
        dados, _ = carregador.carregar(
            scoped, UUID(ORG_ID), UUID(ids["cliente"]), UUID(ids["contrato"]), usuario_id=None
        )
        assert [e.id for e in dados.empresas] == [ids["empresa"]]
        [item] = [i for i in _lista(scoped, ids) if i["entidade"] == vx.ENTIDADE_EMPRESA]
        assert item["fonte_tipo"] == "Serasa Crednet"
        assert "Cartão CNPJ" not in item["rotulo"]

    def test_a_pj_party_company_enters_even_unconfirmed(self, client, scoped):
        ids = _caso_real(scoped)
        scoped.set_table_data("atendimento_partes", _rows(scoped, "atendimento_partes") + [{
            "id": str(uuid4()), "org_id": ORG_ID, "atendimento_id": ids["atendimento"],
            "cliente_id": None, "empresa_id": ids["empresa"], "lado": "vendedor",
            "papel": "proprietario", "ordem": 2, "observacao": None, "created_at": _T0,
            "created_by": None, "updated_at": None,
        }])
        dados, _ = carregador.carregar(
            scoped, UUID(ORG_ID), UUID(ids["cliente"]), UUID(ids["contrato"]), usuario_id=None
        )
        assert ids["empresa"] in [e.id for e in dados.empresas]


class TestValorNaLista:
    """The version never stores the value (LGPD: no second copy of a CPF) —
    the contract list reads it LIVE off its row and says whether it is still
    the value the version printed."""

    def _listado(self, client, ids) -> dict:
        r = client.get(f"/api/clientes/{ids['cliente']}/contratos", headers=_auth())
        assert r.status_code == 200, r.text
        [contrato] = [c for c in r.json()["contratos"] if c["id"] == ids["contrato"]]
        [campo] = contrato["versao_atual"]["revisao_juridica"]["campos"]
        return campo

    def test_the_listed_item_carries_the_live_value_masked(self, client, scoped, fake_storage):
        ids, _versao = _gerado_com_cpf_extraido(client, scoped)
        cpf = _vendedor(scoped, ids)["cpf"]
        campo = self._listado(client, ids)
        assert campo["valor"] == cpf
        assert campo["valor_mascarado"].startswith("***.") and campo["valor_mascarado"] != cpf
        assert campo["valor_confere"] is True
        assert "valor_sha256" not in campo

    def test_a_value_changed_after_generation_no_longer_confere(self, client, scoped, fake_storage):
        ids, _versao = _gerado_com_cpf_extraido(client, scoped)
        scoped.set_table_data("clientes", [
            {**r, "cpf": "529.982.247-25"} if r["id"] == ids["vendedor"] else r
            for r in _rows(scoped, "clientes")
        ])
        campo = self._listado(client, ids)
        assert campo["valor"] == "529.982.247-25"
        assert campo["valor_confere"] is False


class TestAprovacaoConfirmaOFatoInteiro:
    def test_approving_a_couple_fact_confirms_both_spouses(self, client, scoped):
        ids = _caso_real(scoped)
        itens = _lista(scoped, ids)
        dados, _ = carregador.carregar(
            scoped, UUID(ORG_ID), UUID(ids["cliente"]), UUID(ids["contrato"]), usuario_id=None
        )
        registrados = [{k: i[k] for k in contratos_svc.CAMPOS_REVISAO_CHAVES} for i in itens]
        vx.confirmar_por_revisao(
            scoped, UUID(ORG_ID), dados, UUID(ids["contrato"]), str(uuid4()), registrados,
            usuario_id=None,
        )
        por_id = {r["id"]: r for r in _rows(scoped, "clientes")}
        assert por_id[ids["vendedor"]]["data_casamento_confirmado_em"] is not None
        assert por_id[ids["conjuge"]]["data_casamento_confirmado_em"] is not None
        # Corroborated = not pending: the approval leaves it as it was.
        assert por_id[ids["vendedor"]]["nome_oficial_confirmado_em"] is None


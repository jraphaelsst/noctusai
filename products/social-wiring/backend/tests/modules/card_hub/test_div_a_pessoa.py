"""Divergence-email study (2026-10-05) — the PERSON apply path.

Shapes are anonymized from the evidence dataset (invented names / numbers):
a two-person document's facts landing on the wrong card, a bill whose holder
is not the person, address comparison gap-fill, and rejected / ping-ponging
proposals being e-mailed again and again.
"""
from __future__ import annotations

from uuid import UUID, uuid4

from app.modules.card_hub import identidade_extracao_service as svc
from app.services import campo_conflitos
from tests.modules.card_hub.conftest import ORG_ID, cliente_row
from tests.modules.card_hub.test_identidade_d1_contrato import ORG_UUID, _cliente, _conflitos

RG_A = "30.128.742-9"
RG_B = "41.555.123-0"


def _lido(valor, conf="alta"):
    return (valor, conf, "ROTULO", True)


def _lidos(**campos):
    base = svc._lidos_vazios()
    base.update({k: _lido(v) for k, v in campos.items()})
    return base


def _aplicar(db, cid, lidos, origem="certidao_casamento", **kw):
    return svc.aplicar_campos_ao_cliente(
        db, ORG_UUID, UUID(cid), origem, lidos, documento_id=uuid4(), **kw
    )


class TestPersonBinding:
    def test_a_foreign_persons_rg_does_not_open_a_conflict_on_the_card_owner(self, client, scoped):
        cid = str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(
            cid, nome="Carlos Eduardo Lima", nome_oficial="CARLOS EDUARDO LIMA",
            rg=RG_A, rg_origem="rg",
        )])
        avisos: list[str] = []
        aplicados, conflitos = _aplicar(
            scoped, cid,
            _lidos(nome_oficial="ANA PAULA SOUZA", rg=RG_B, genero="feminino"),
            origem="cnh", avisos_outra_pessoa=avisos, ligar_pessoa=True,
        )
        assert conflitos == [] and _conflitos(scoped) == []
        assert not any(aplicados.values())
        assert _cliente(scoped, cid)["rg"] == RG_A
        assert "rg" in avisos

    def test_routed_to_the_linked_spouse_when_the_document_names_them(self, client, scoped):
        cid, esposa = str(uuid4()), str(uuid4())
        scoped.set_table_data("clientes", [
            cliente_row(cid, nome="Carlos Eduardo Lima", nome_oficial="CARLOS EDUARDO LIMA",
                        conjuge_cliente_id=esposa),
            cliente_row(esposa, nome="Ana Paula Souza", nome_oficial="ANA PAULA SOUZA",
                        conjuge_cliente_id=cid),
        ])
        _aplicar(scoped, cid, _lidos(nome_oficial="ANA PAULA SOUZA", rg=RG_B),
                 origem="cnh", ligar_pessoa=True)
        assert _cliente(scoped, esposa)["rg"] == RG_B
        assert _cliente(scoped, cid).get("rg") is None

    def test_one_letter_name_variant_still_binds(self, client, scoped):
        cid = str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(
            cid, nome="Carlos Eduardo Lima", nome_oficial="CARLOS EDUARDO LIMA",
            rg=RG_A, rg_origem="rg",
        )])
        _aplicar(
            scoped, cid, _lidos(nome_oficial="CARLOS EDUARDA LIMA", rg=RG_B),
            origem="cnh", ligar_pessoa=True,
        )
        # same person: the rg divergence is ADJUDICATED (conflict row or an
        # auditable automatic resolution) instead of being dropped as foreign
        assert "rg" in [c["campo"] for c in _conflitos(scoped)]

    def test_the_name_the_certidao_says_was_left_behind_binds(self, client, scoped):
        cid = str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(
            cid, nome="Ana Paula Souza", nome_oficial="ANA PAULA SOUZA",
        )])
        aplicados, _ = _aplicar(
            scoped, cid, _lidos(nome_oficial="ANA PAULA SOUZA RANGEL", rg=RG_B),
            ligar_pessoa=True, nomes_anteriores={"nome_oficial": "ANA PAULA SOUZA"},
        )
        assert aplicados["rg"] is True

    def test_binding_is_opt_in_so_cpf_anchored_sources_keep_real_name_conflicts(self, client, scoped):
        cid = str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(
            cid, nome="Carlos Eduardo Lima", nome_oficial="CARLOS EDUARDO LIMA",
            nome_oficial_origem="rg",
        )])
        _, conflitos = _aplicar(scoped, cid, _lidos(nome_oficial="CARLOS E LIMA SANTOS"), origem="crednet")
        assert [c["campo"] for c in conflitos] == ["nome_oficial"]


class TestMesmoEndereco:
    def _atual(self, **over):
        base = {
            "endereco_logradouro": "RUA DAS FLORES", "endereco_numero": "0123",
            "endereco_complemento": "CS 02", "endereco_bairro": "CENTRO",
            "endereco_cidade": "SAO PAULO", "endereco_uf": "SP", "endereco_cep": "01454-011",
        }
        base.update(over)
        return base

    def test_a_null_cidade_uf_bairro_on_the_record_is_a_gap_not_a_difference(self):
        atual = self._atual(endereco_cidade=None, endereco_uf=None, endereco_bairro=None)
        proposto = {"logradouro": "RUA DAS FLORES", "numero": "123", "cidade": "SAO PAULO",
                    "uf": "SP", "bairro": "CENTRO", "cep": "01454011"}
        assert svc._mesmo_endereco(atual, proposto) is True

    def test_leading_zeros_and_complemento_synonyms(self):
        proposto = {"logradouro": "RUA DAS FLORES", "numero": "123", "complemento": "CASA 2"}
        assert svc._mesmo_endereco(self._atual(), proposto) is True
        assert svc._mesmo_endereco(
            self._atual(endereco_complemento="AP 12"), {"complemento": "APTO 12"}
        ) is True

    def test_a_missing_logradouro_on_the_record_is_still_a_difference(self):
        assert svc._mesmo_endereco(
            self._atual(endereco_logradouro=None), {"logradouro": "RUA DAS FLORES"}
        ) is False

    def test_the_titular_key_of_a_conflict_json_is_ignored(self):
        a = '{"logradouro": "RUA DAS FLORES", "numero": "123", "titular": "ANA"}'
        b = '{"logradouro": "RUA DAS FLORES", "numero": "0123", "titular": "OUTRA"}'
        assert svc._mesmo_valor_conflito("endereco", a, b) is True


class TestRejectionsAndDedupe:
    def _conflito(self, scoped, cid, status, valor, **over):
        row = {
            "id": str(uuid4()), "org_id": ORG_ID, "cliente_id": cid, "campo": "rg",
            "valor_anterior": RG_A, "valor_proposto": valor, "origem_proposto": "cnh",
            "status": status, "decidido_por": None, "notificado_em": None,
            "created_at": "2026-10-01T00:00:00+00:00",
        }
        row.update(over)
        scoped.table("cliente_campo_conflitos").insert(row).execute()
        return row

    def _cliente_com_rg(self, scoped):
        cid = str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(
            cid, nome="Carlos Eduardo Lima", rg=RG_A, rg_origem="rg",
        )])
        scoped.set_table_data("cliente_campo_conflitos", [])
        return cid

    def test_a_reading_a_human_already_rejected_is_not_reopened(self, client, scoped):
        cid = self._cliente_com_rg(scoped)
        self._conflito(scoped, cid, "rejeitado", "415551230", decidido_por=str(uuid4()))
        _, conflitos = _aplicar(scoped, cid, _lidos(rg=RG_B), origem="cnh")
        assert conflitos == []
        assert len(_conflitos(scoped)) == 1  # no pending, no automatic-resolution row

    def test_a_pending_conflict_is_deduped_by_fact_not_by_string(self, client, scoped):
        cid = self._cliente_com_rg(scoped)
        self._conflito(scoped, cid, "pendente", RG_B)
        novo = svc._registrar_conflito(
            scoped, ORG_UUID, UUID(cid), "rg",
            valor_anterior=RG_A, origem_anterior="rg", valor_proposto="415551230",
            origem_proposto="ficha_cadastral", confianca_proposta="media",
            fonte_tabela=None, fonte_id=None,
        )
        assert novo is None
        assert len(_conflitos(scoped)) == 1

    def test_ping_pong_between_two_sources_emails_each_value_once(self, client, scoped):
        cid = self._cliente_com_rg(scoped)
        x, y = "41.555.123-0", "52.666.234-1"

        def propor(valor, origem):
            return svc._registrar_conflito(
                scoped, ORG_UUID, UUID(cid), "rg",
                valor_anterior=RG_A, origem_anterior="rg", valor_proposto=valor,
                origem_proposto=origem, confianca_proposta="media",
                fonte_tabela=None, fonte_id=None,
            )

        primeiro = propor(x, "ficha_cadastral")
        assert primeiro is not None
        scoped.table("cliente_campo_conflitos").update({"notificado_em": "2026-10-02T00:00:00+00:00"}).eq("id", primeiro["id"]).execute()
        segundo = propor(y, "comprovante")
        assert segundo is not None
        scoped.table("cliente_campo_conflitos").update({"notificado_em": "2026-10-03T00:00:00+00:00"}).eq("id", segundo["id"]).execute()
        # the ficha reading comes back: already shown + superseded -> silent
        assert propor(x, "ficha_cadastral") is None
        assert propor(y, "comprovante") is None
        pend = [c for c in _conflitos(scoped) if c["status"] == "pendente"]
        assert [c["valor_proposto"] for c in pend] == [y]

    def test_other_tables_keep_the_legacy_supersede_behaviour(self, client, scoped):
        scoped.set_table_data("imovel_campo_conflitos", [])
        t = campo_conflitos.IMOVEL
        kw = dict(valor_anterior="a", origem_anterior="o", origem_proposto="p")
        r1 = campo_conflitos.registrar_conflito(scoped, t, ORG_UUID, "C1", "campo", valor_proposto="x", **kw)
        scoped.table(t.table).update({"notificado_em": "2026-10-02T00:00:00+00:00"}).eq("id", r1["id"]).execute()
        assert campo_conflitos.registrar_conflito(scoped, t, ORG_UUID, "C1", "campo", valor_proposto="y", **kw)
        assert campo_conflitos.registrar_conflito(scoped, t, ORG_UUID, "C1", "campo", valor_proposto="x", **kw)


class TestEnderecoSugestaoEWiring:
    def _cliente_com_endereco(self, scoped, nome="Ana Paula Souza"):
        cid, did = str(uuid4()), str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(
            cid, nome=nome, endereco_cep="04000-000", endereco_logradouro="RUA B",
            endereco_origem="comprovante_endereco",
        )])
        scoped.set_table_data("cliente_documentos", [{
            "id": did, "org_id": ORG_ID, "cliente_id": cid, "tipo_documento": "comprovante_endereco",
            "nome_original": "luz.pdf", "deleted_at": None, "extracao_status": "ok",
            "extracao_em": "2026-10-01T00:00:00+00:00",
            "extracao_aviso": svc.AVISO_TITULAR_NAO_CONFERE,
            "extracao_endereco_cep": "01454-011", "extracao_endereco_logradouro": "R PROF ARTUR RAMOS",
            "extracao_endereco_titular": "ENERGIA DISTRIBUIDORA S A",
        }])
        return cid, did

    def test_a_mismatched_bill_against_a_set_address_is_offered_and_acceptable(self, client, scoped):
        cid, did = self._cliente_com_endereco(scoped)
        sug = svc.sugestoes_pendentes(scoped, ORG_UUID, UUID(cid))["endereco"]
        assert sug["substitui"] is True and sug["valor"]["cep"] == "01454-011"
        assert sug["valor_atual"]["cep"] == "04000-000"
        out = svc.confirmar_sugestao(
            scoped, ORG_UUID, UUID(cid), UUID(did), item_key="endereco", user_id=uuid4()
        )
        assert out["substituiu"]["cep"] == "04000-000"
        assert _cliente(scoped, cid)["endereco_cep"] == "01454-011"
        assert "endereco" not in svc.sugestoes_pendentes(scoped, ORG_UUID, UUID(cid))

    def test_a_mismatched_bill_can_be_refused(self, client, scoped):
        cid, did = self._cliente_com_endereco(scoped)
        svc.descartar_sugestao(scoped, ORG_UUID, UUID(cid), UUID(did), item_key="endereco", user_id=uuid4())
        assert "endereco" not in svc.sugestoes_pendentes(scoped, ORG_UUID, UUID(cid))
        assert _cliente(scoped, cid)["endereco_cep"] == "04000-000"

    def test_a_company_holder_is_never_the_person_even_when_it_shares_words(self, client, scoped):
        cid = str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(cid, nome="Energia Souza")])
        avisos: list[str] = []
        aplicado, conflito = svc.aplicar_endereco_ao_cliente(
            scoped, ORG_UUID, UUID(cid), "comprovante_endereco",
            {"logradouro": "RUA B", "cep": "04000-000"},
            titular_documento="ENERGIA SOUZA DISTRIBUIDORA DE ENERGIA S A", avisos=avisos,
        )
        assert (aplicado, conflito) == (False, None)
        assert avisos == [svc.AVISO_TITULAR_NAO_CONFERE]

    def test_complemento_bled_into_bairro_is_moved_before_writing(self, client, scoped):
        cid = str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(cid, nome="Ana Paula Souza")])
        svc.aplicar_endereco_ao_cliente(
            scoped, ORG_UUID, UUID(cid), "comprovante_endereco",
            {"logradouro": "RUA B", "cep": "04000-000", "bairro": "TP A AP 157"},
            titular_documento="ANA PAULA SOUZA",
        )
        row = _cliente(scoped, cid)
        assert row.get("endereco_bairro") is None
        assert "157" in (row.get("endereco_complemento") or "")

    def test_street_type_swap_is_the_same_street(self):
        assert svc._mesmo_endereco(
            {"endereco_logradouro": "ESTRADA DAS FLORES"}, {"logradouro": "RUA DAS FLORES"}
        ) is True

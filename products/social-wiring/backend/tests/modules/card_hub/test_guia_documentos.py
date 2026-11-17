"""`GET /api/guia-documentos` — the contract (bare `GuiaDocumentos`), derived
from the catalogs that own each fact. Synthetic data only."""
from __future__ import annotations

from app.modules.card_hub import documento_checklist_service as checklist
from app.modules.card_hub import guia_documentos_service as svc
from app.modules.card_hub.contrato_gerador import derivacao
from app.modules.card_hub.proveniencia import fontes as fontes_mod
from app.modules.certidoes import registry
from app.modules.pipeline import stage_gate

from tests.modules.card_hub.conftest import ORG_ID, _auth

CHAVES = {"versao", "documentos", "campos", "certidoes", "etapas", "dados_obrigatorios"}


def _guia():
    return svc.montar_guia()


class TestContrato:
    def test_chaves_de_topo_e_de_cada_item(self):
        g = _guia()
        assert set(g) == CHAVES
        assert isinstance(g["versao"], str) and g["versao"]
        for d in g["documentos"]:
            assert set(d) == {"tipo_documento", "rotulo", "campos", "observacao", "usos"}
            for c in d["campos"]:
                assert set(c) == {"campo", "rotulo"}
        for c in g["campos"]:
            assert set(c) == {"campo", "rotulo", "documentos"}
        for c in g["certidoes"]:
            assert set(c) == {"tipo", "linha", "rotulo", "fonte", "requisitos", "credencial", "observacao"}
            assert c["fonte"] in ("infosimples", "manual") and c["credencial"] in ("govbr", None)
            for r in c["requisitos"]:
                assert r["documento"] in ("cpf", "cnpj")
        for e in g["etapas"]:
            assert set(e) == {"chave", "rotulo", "bloco", "exige", "observacao"}
            for x in e["exige"]:
                assert set(x) == {"rotulo", "tipo", "ref"} and x["tipo"] in ("campo", "documento", "certidao")
        for o in g["dados_obrigatorios"]:
            assert set(o) == {"chave", "rotulo", "documentos", "escopo", "dica"}

    def test_versao_estavel_e_sensivel_ao_conteudo(self):
        assert _guia()["versao"] == _guia()["versao"]
        assert svc.montar_guia(rotulos_etapa={"visitas": "Visitas X"})["versao"] != _guia()["versao"]


class TestDerivacao:
    def test_todo_documento_do_catalogo_aparece(self):
        tipos = [d["tipo_documento"] for d in _guia()["documentos"]]
        assert tipos == [f.tipo_documento for f in fontes_mod.FONTES_REGISTRO]

    def test_campos_do_documento_cobrem_o_catalogo(self):
        por_tipo = {d["tipo_documento"]: {c["campo"] for c in d["campos"]} for d in _guia()["documentos"]}
        for f in fontes_mod.FONTES_REGISTRO:
            assert set(f.campos) | set(f.campos_sem_capacidade) <= por_tipo[f.tipo_documento]

    def test_indice_reverso_igual_as_sugestoes_da_prontidao(self):
        for c in _guia()["campos"]:
            esperado = [s["tipo_documento"] for s in derivacao._sugestoes_para_campo(c["campo"])]
            assert c["documentos"] == esperado and esperado, c["campo"]

    def test_nenhum_campo_fica_sem_rotulo(self):
        g = _guia()
        campos = [c for d in g["documentos"] for c in d["campos"]] + g["campos"]
        assert [c["campo"] for c in campos if c["rotulo"] == c["campo"]] == []

    def test_toda_certidao_tem_requisitos(self):
        g = _guia()
        assert {c["tipo"] for c in g["certidoes"]} == {
            c["tipo"] for c in registry.CERTIDOES_CONFIG + registry.MANUAL_TIPOS_CONFIG
        }
        for c in g["certidoes"]:
            assert c["requisitos"], c["tipo"]

    def test_dados_obrigatorios_chave_e_a_key_do_checklist(self):
        assert [o["chave"] for o in _guia()["dados_obrigatorios"]] == list(checklist.ITEM_KEYS)

    def test_usos_nomeiam_a_certidao_que_exige_o_campo(self):
        rg = next(d for d in _guia()["documentos"] if d["tipo_documento"] == "rg")
        assert "Qualificação no contrato" in rg["usos"]
        assert "Certidão Receita Federal (data de nascimento)" in rg["usos"]
        assert "Certidão TJSP (RG)" in rg["usos"]


class TestEtapas:
    def test_sem_org_usa_os_blocos_padrao(self):
        etapas = _guia()["etapas"]
        assert etapas[0]["chave"] == "sdr" and etapas[0]["exige"] == []
        por = {e["chave"]: e for e in etapas}
        assert por["qualificacao"]["bloco"] == "atendimento"
        assert [x["ref"] for x in por["qualificacao"]["exige"]] == [e["key"] for e in stage_gate.EXIGENCIAS]
        # processos_venda moves are never gated; jurídico lists the contract readiness.
        assert por["financiamento_escritura"]["exige"] == []
        refs = {x["ref"] for x in por["elaboracao_contrato"]["exige"]}
        assert "identidade" in refs and "cnd_federal" in refs
        assert "não trava" in por["elaboracao_contrato"]["observacao"]

    def test_rotulos_e_ordem_da_org(self):
        rotulos, ordem = svc.etapas_da_org([
            {"pipeline": "funil", "slug": "visitas", "label": "Visitas"},
            {"pipeline": "funil", "slug": "qualificacao", "label": "Qualificação"},
        ])
        g = svc.montar_guia(rotulos_etapa=rotulos, etapas_org=ordem)
        funil = [e for e in g["etapas"] if e["chave"] in ("visitas", "qualificacao")]
        assert [(e["chave"], e["rotulo"]) for e in funil] == [("visitas", "Visitas"), ("qualificacao", "Qualificação")]


class TestRota:
    def test_exige_autenticacao(self, anon_client):
        assert anon_client.get("/api/guia-documentos").status_code == 401

    def test_payload_cru_com_as_etapas_da_org(self, client, scoped):
        scoped.set_table_data("pipeline_stages", [
            {"id": "s1", "org_id": ORG_ID, "pipeline": "funil", "slug": "qualificacao",
             "label": "Qualificação Org", "posicao": 0, "ativo": True},
            {"id": "s2", "org_id": "outra-org", "pipeline": "funil", "slug": "qualificacao",
             "label": "De outra org", "posicao": 0, "ativo": True},
        ])
        r = client.get("/api/guia-documentos", headers=_auth())
        assert r.status_code == 200
        body = r.json()
        assert set(body) == CHAVES
        qual = next(e for e in body["etapas"] if e["chave"] == "qualificacao")
        assert qual["rotulo"] == "Qualificação Org"

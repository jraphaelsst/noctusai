"""`ficha_cadastral.py` — pure, fitz-free: field-name classification, the
text-based estado-civil/regime-de-bens vocabulary, and person assembly off
already-classified widget values.

Fixtures mimic the FIELD-NAME shapes measured on the real corpus (masked —
no real name/CPF/address ever appears here, per this package's own privacy
discipline), never the real bytes.
"""
from datetime import date, timedelta

import pytest

from noctusai_lib.integrations.documents.ficha_cadastral import (
    CampoWidget,
    classificar_campo,
    estado_civil_de_texto,
    montar_pessoas,
    regime_bens_de_texto,
)
from noctusai_lib.integrations.documents.types import ExtractionConfidence

ALTA = ExtractionConfidence.ALTA
BAIXA = ExtractionConfidence.BAIXA
NENHUMA = ExtractionConfidence.NENHUMA

#: A synthetic, obviously-fake CPF whose check digits verify — `cpf.
#: is_valid` computed off `123.456.789-09`.
CPF_VALIDO = "123.456.789-09"
NASCIMENTO_PLAUSIVEL = (date.today() - timedelta(days=365 * 40)).strftime("%d/%m/%Y")


class TestClassificarCampo:
    """One widget field name → the semantic slot, across every naming
    convention the real templates use (full word, abbreviated, `#`-suffixed)."""

    @pytest.mark.parametrize(
        "nome_campo,campo_esperado",
        [
            ("Nome completo (sem abreviações) 1", "nome"),
            ("Nome Vendedor#V1", "nome"),
            ("nomev2", "nome"),
            ("CPF 1", "cpf"),
            ("CPF#V1", "cpf"),
            ("cpf#v2", "cpf"),
            ("Data de Nascimento 1", "data_nascimento"),
            ("nascv2", "data_nascimento"),
            ("Nacionalidade#V1", "nacionalidade"),
            ("naciov2", "nacionalidade"),
            ("Profissão, principal ocupação ou atividade 1", "profissao"),
            ("profiss#v2", "profissao"),
            ("Número de documento 1", "rg_numero"),
            ("numdocv2", "rg_numero"),
            ("Documento vendedor#V1", "rg_numero"),
            ("Órgão expedidor 1", "rg_orgao"),
            ("órgaov2", "rg_orgao"),
            ("EstadoCivil1#0", "estado_civil"),
            ("estadocivilv2", "estado_civil"),
            ("Regime Casamento1#0", "regime_bens"),
            ("regimedecasamento1#V1", "regime_bens"),
            ("CEP 1", "endereco_cep"),
            ("cep1", "endereco_cep"),
            ("Bairro 1", "endereco_bairro"),
            ("bairro#v1", "endereco_bairro"),
            ("Endereço Residencial 1", "endereco_logradouro"),
            ("End#V1", "endereco_logradouro"),
            ("Número 1", "endereco_numero"),
            ("Num#v1", "endereco_numero"),
            ("Complemento1", "endereco_complemento"),
            ("complem#v1", "endereco_complemento"),
            ("Cidade 1", "endereco_cidade"),
            ("Estado 1", "endereco_uf"),
            ("ENDEREÇO", "endereco_bruto"),
            ("ENDEREÇOCONT", "endereco_bruto_cont"),
            ("telefone celular 1", "telefone"),
            ("Telcel#V1", "telefone"),
            ("e-mail 1", "email"),
            ("email#v2", "email"),
        ],
    )
    def test_reconhece_toda_a_variedade_de_templates(self, nome_campo, campo_esperado):
        assert classificar_campo(nome_campo) == campo_esperado

    @pytest.mark.parametrize(
        "nome_campo",
        [
            "Nome procurador 1",
            "CPF procurador 1",
            "Nome da mãe ou do pai 1",
            "Filiação 1",
            "CPF ou CNPJ",
            "Banco nº",
            "Agência nº",
            "Nome cartorio",
            "Numero matricula",
            "numero IPU",
            "Cidade do cartório",
            "Tipo de Documento1#0",
            "Anexo/Garagem",
        ],
    )
    def test_exclui_o_que_nao_e_a_pessoa_deste_bloco(self, nome_campo):
        assert classificar_campo(nome_campo) is None

    def test_endereco_de_correspondencia_e_excluido(self):
        for nome_campo in ("Endcorresp1#v1", "endcorrespv2", "bairrocorrespv2", "cepcorresp1"):
            assert classificar_campo(nome_campo) is None

    def test_nome_vendedor_nunca_vira_endereco(self):
        """`"end"` is a substring of `"vendedor"` — regression for the exact
        P3 bug this module's own docstring names: a bare containment check
        on that short abbreviation misclassified the person's OWN NAME
        field as an address line, on a real template."""
        assert classificar_campo("Nome Vendedor#V1") == "nome"
        assert classificar_campo("Nome completo ou Razão social") is None  # procurador/bank row

    def test_cidade_de_nascimento_nao_e_data_nascimento_nem_endereco(self):
        assert classificar_campo("Cidade de Nascimento 1") is None
        assert classificar_campo("UF Nascimento 1") is None
        assert classificar_campo("cidnascv2") is None

    def test_campo_vazio_ou_irreconhecivel(self):
        assert classificar_campo("") is None
        assert classificar_campo("Texto Livre 42") is None


class TestVocabularioTexto:
    def test_estado_civil_de_texto(self):
        assert estado_civil_de_texto("Solteiro(a)") == "solteiro"
        assert estado_civil_de_texto("CASADO") == "casado"
        assert estado_civil_de_texto("Divorciado(a)") == "divorciado"
        assert estado_civil_de_texto("Desquitado(a)") is None
        assert estado_civil_de_texto("") is None

    def test_regime_bens_de_texto(self):
        assert regime_bens_de_texto("Comunhão Parcial") == "comunhao_parcial"
        assert regime_bens_de_texto("Separação Total") == "separacao_total"
        assert regime_bens_de_texto("algo desconhecido") is None


def _campo(campo, valor, tipo="Text"):
    return CampoWidget(campo=campo, valor=valor, tipo=tipo)


class TestMontarPessoas:
    def test_pessoa_completa_uma_pagina(self):
        campos = [
            _campo("nome", "FULANO DE TAL"),
            _campo("cpf", CPF_VALIDO),
            _campo("data_nascimento", NASCIMENTO_PLAUSIVEL),
            _campo("nacionalidade", "BRASILEIRO"),
            _campo("profissao", "ENGENHEIRO"),
            _campo("rg_numero", "12.345.678-9"),
            _campo("rg_orgao", "SSP/SP"),
            _campo("estado_civil_geo", "CASADO", tipo="RadioButton"),
            _campo("regime_bens_geo", "COMUNHAO PARCIAL", tipo="RadioButton"),
            _campo("endereco_cep", "01234-567"),
            _campo("endereco_logradouro", "RUA DAS FLORES"),
            _campo("endereco_numero", "123"),
            _campo("endereco_bairro", "CENTRO"),
            _campo("endereco_cidade", "SAO PAULO"),
            _campo("endereco_uf", "SP"),
            _campo("telefone", "(11) 91234-5678"),
            _campo("email", "fulano@example.com"),
        ]
        (pessoa,) = montar_pessoas({0: campos}, papel_por_pagina={0: "proponente"})
        assert pessoa.papel == "proponente"
        assert pessoa.nome == "FULANO DE TAL"
        assert pessoa.nome_confianca is ALTA
        assert pessoa.cpf == CPF_VALIDO
        assert pessoa.cpf_confianca is ALTA
        assert pessoa.data_nascimento is not None
        assert pessoa.data_nascimento_confianca is ALTA
        assert pessoa.nacionalidade == "brasileiro"
        assert pessoa.profissao == "engenheiro"
        assert pessoa.rg == "12.345.678-9"
        assert pessoa.rg_orgao == "SSP/SP"
        # RadioButton-geometric decode — BAIXA, never ALTA (see the module
        # docstring's P3-corpus note on why the export VALUE is never
        # trusted by position).
        assert pessoa.estado_civil == "casado"
        assert pessoa.estado_civil_confianca is BAIXA
        assert pessoa.regime_bens == "comunhao_parcial"
        assert pessoa.regime_bens_confianca is BAIXA
        assert pessoa.endereco is not None
        assert pessoa.endereco.cep == "01234-567"
        assert pessoa.endereco.logradouro == "RUA DAS FLORES"
        assert pessoa.telefone == "(11) 91234-5678"
        assert pessoa.email == "fulano@example.com"

    def test_estado_civil_texto_e_alta_nao_baixa(self):
        """FGTS's own `ComboBox` prints the option's text directly — the
        document's own labelled word, not a geometric inference."""
        campos = [
            _campo("nome", "FULANA DE TAL"),
            _campo("cpf", CPF_VALIDO),
            _campo("estado_civil_texto", "Solteiro(a)", tipo="ComboBox"),
            _campo("profissao", "MEDICA"),
        ]
        (pessoa,) = montar_pessoas({0: campos})
        assert pessoa.estado_civil == "solteiro"
        assert pessoa.estado_civil_confianca is ALTA

    def test_duas_pessoas_duas_paginas(self):
        pagina0 = [
            _campo("nome", "PROPONENTE UM"),
            _campo("cpf", CPF_VALIDO),
            _campo("profissao", "COMERCIANTE"),
        ]
        pagina1 = [
            _campo("nome", "CONJUGE DOIS"),
            _campo("cpf", "987.654.321-00"),
            _campo("profissao", "PROFESSORA"),
        ]
        pessoas = montar_pessoas(
            {0: pagina0, 1: pagina1},
            papel_por_pagina={0: "proponente", 1: "conjuge"},
        )
        assert len(pessoas) == 2
        assert pessoas[0].papel == "proponente"
        assert pessoas[0].nome == "PROPONENTE UM"
        assert pessoas[1].papel == "conjuge"
        assert pessoas[1].nome == "CONJUGE DOIS"

    def test_pagina_sem_cpf_ou_nome_e_ignorada(self):
        pagina_vazia = [_campo("profissao", "ALGO")]
        assert montar_pessoas({0: pagina_vazia}) == ()

    def test_pagina_rica_mas_incompleta_repetindo_titular_e_ignorada(self):
        """A bank-account row repeats this person's own name/CPF for
        payment purposes, with nothing else beside it — not a person's own
        block (`_pessoa_valida`'s richness bar)."""
        pagina_conta_bancaria = [
            _campo("nome", "PROPONENTE UM"),
            _campo("cpf", CPF_VALIDO),
        ]
        assert montar_pessoas({0: pagina_conta_bancaria}) == ()

    def test_cpf_invalido_ainda_e_lido_mas_baixa(self):
        campos = [
            _campo("nome", "FULANO"),
            _campo("cpf", "111.111.111-11"),  # repdigit — fails the check digit
            _campo("profissao", "ALGO"),
        ]
        (pessoa,) = montar_pessoas({0: campos})
        assert pessoa.cpf_confianca is BAIXA

    def test_endereco_raw_fgts_via_find_endereco(self):
        campos = [
            _campo("nome", "TRABALHADOR FGTS"),
            _campo("cpf", CPF_VALIDO),
            _campo("endereco_bruto", "RUA DAS ACACIAS Nº 45 - CASA 2"),
            _campo("endereco_bruto_cont", "JARDIM PAULISTA - SAO PAULO - SP - CEP: 01234-567"),
        ]
        (pessoa,) = montar_pessoas({0: campos})
        assert pessoa.endereco is not None
        assert pessoa.endereco.cep == "01234-567"

    def test_endereco_estruturado_sem_logradouro_nao_produz_resultado_incompleto(self):
        """A `bairro` alone (no `logradouro`, no `cep`) is not a usable
        address — matches `EnderecoLido.presente`'s own bar, and matters
        because every downstream consumer refuses a group missing either."""
        campos = [
            _campo("nome", "FULANO"),
            _campo("cpf", CPF_VALIDO),
            _campo("profissao", "ALGO"),
            _campo("endereco_bairro", "CENTRO"),
        ]
        (pessoa,) = montar_pessoas({0: campos})
        assert pessoa.endereco is None

    def test_data_nascimento_implausivel_e_descartada(self):
        campos = [
            _campo("nome", "FULANO"),
            _campo("cpf", CPF_VALIDO),
            _campo("data_nascimento", "01/01/1830"),
            _campo("profissao", "ALGO"),
        ]
        (pessoa,) = montar_pessoas({0: campos})
        assert pessoa.data_nascimento is None
        assert pessoa.data_nascimento_confianca is NENHUMA

    def test_ordem_das_paginas_e_preservada(self):
        pagina5 = [_campo("nome", "B"), _campo("cpf", "987.654.321-00"), _campo("profissao", "X")]
        pagina1 = [_campo("nome", "A"), _campo("cpf", CPF_VALIDO), _campo("profissao", "Y")]
        pessoas = montar_pessoas({5: pagina5, 1: pagina1})
        assert [p.nome for p in pessoas] == ["A", "B"]

"""Filiação (nome_mae / nome_pai) and naturalidade — owner decision 2026-10-21.

Printed on an RG/CIN (`FILIAÇÃO`, `NATURALIDADE`), a CNH (`FILIAÇÃO` only), a
certidão de nascimento, and — per spouse — a certidão de casamento's
qualification clause. Invented names throughout.
"""
from __future__ import annotations

import asyncio

from noctusai_lib.integrations.documents.conjuges import find_conjuges
from noctusai_lib.integrations.documents.filiacao import (
    find_filiacao,
    find_naturalidade,
    ler_trecho,
)
from noctusai_lib.integrations.documents.ladder import LeituraTexto
from noctusai_lib.integrations.documents.real import LadderIdentityExtractor
from noctusai_lib.integrations.documents.types import TextSource, TitularEsperado

from tests.integrations.documents.test_certidao_casamento_sp_nomes_repetidos import CERTIDAO_SP


class _Ladder:
    def __init__(self, texto: str) -> None:
        self.texto = texto

    async def ler(self, content, mimetype, filename, **kw):
        return LeituraTexto(self.texto, TextSource.TEXT_LAYER, None)


def _ler(texto: str, tipo: str | None, titular: TitularEsperado | None = None):
    return asyncio.run(
        LadderIdentityExtractor(ladder=_Ladder(texto)).extract(
            b"%PDF", mimetype="application/pdf", tipo_documento=tipo, titular=titular
        )
    )


class TestFiliacao:
    def test_explicit_role_labels_are_alta(self):
        pai, cp, mae, cm, rotulo = find_filiacao("PAI: Aurelio Prado\nMÃE: Marta Menezes\n")
        assert (pai, cp, mae, cm) == ("Aurelio Prado", "alta", "Marta Menezes", "alta")

    def test_nome_do_pai_nome_da_mae_labels(self):
        pai, _, mae, _, _ = find_filiacao("NOME DO PAI: Aurelio Prado\nNOME DA MÃE: Marta Menezes\n")
        assert (pai, mae) == ("Aurelio Prado", "Marta Menezes")

    def test_unlabelled_filiacao_block_is_positional_and_never_above_baixa(self):
        pai, cp, mae, cm, rotulo = find_filiacao(
            "NOME: JOAO X\nFILIAÇÃO\nAURELIO PRADO\nMARTA MENEZES\nDATA DE NASCIMENTO 10/03/1985\n"
        )
        assert (pai, mae) == ("AURELIO PRADO", "MARTA MENEZES")
        assert cp == cm == "baixa" and rotulo == "FILIAÇÃO"

    def test_filiacao_on_one_line_joined_by_e(self):
        pai, _, mae, _, _ = find_filiacao("FILIAÇÃO: AURELIO PRADO E MARTA MENEZES\n")
        assert (pai, mae) == ("AURELIO PRADO", "MARTA MENEZES")

    def test_a_block_stops_at_the_next_label(self):
        pai, _, mae, _, _ = find_filiacao("FILIAÇÃO\nAURELIO PRADO\nDATA DE NASCIMENTO 10/03/1985\n")
        assert pai is None and mae is None  # one name + a label: no pair

    def test_narrative_filho_de_is_media_in_pai_then_mae_order(self):
        pai, cp, mae, cm, _ = find_filiacao("nascido ..., filho de Aurelio Prado e de Marta Menezes.")
        assert (pai, cp, mae, cm) == ("Aurelio Prado", "media", "Marta Menezes", "media")

    def test_two_different_clauses_are_two_holders_not_attributable(self):
        assert find_filiacao(
            "filho de Aurelio Prado e de Marta Menezes. filha de Hugo Quintana e de Lia Alencar."
        )[0] is None

    def test_two_different_labelled_fathers_are_not_attributable(self):
        assert find_filiacao("PAI: Aurelio Prado\nPAI: Hugo Quintana\n")[0] is None

    def test_a_non_name_is_not_a_parent(self):
        assert find_filiacao("PAI: NAO CONSTA\nMÃE: 12345\n")[0] is None

    def test_nothing_to_read(self):
        assert find_filiacao("") == (None, "nenhuma", None, "nenhuma", None)


class TestNaturalidade:
    def test_label_with_city_and_uf(self):
        assert find_naturalidade("NATURALIDADE: SÃO PAULO - SP\n") == (
            "SÃO PAULO/SP", "alta", "NATURALIDADE",
        )

    def test_local_de_nascimento_label(self):
        assert find_naturalidade("LOCAL DE NASCIMENTO: Campinas/SP\n")[0] == "Campinas/SP"

    def test_narrative_natural_de_with_estado(self):
        v, c, _ = find_naturalidade("brasileiro, natural de Campinas, Estado de São Paulo, nascido")
        assert (v, c) == ("Campinas/SP", "media")

    def test_a_city_without_uf_is_kept_as_printed(self):
        assert find_naturalidade("NATURALIDADE: Campinas\n")[0] == "Campinas"

    def test_two_different_readings_are_absent(self):
        assert find_naturalidade("natural de Campinas/SP e natural de Santos/SP")[0] is None

    def test_the_certidao_column_header_is_not_a_value(self):
        assert find_naturalidade("DATAS DE NASCIMENTO, NATURALIDADE, NACIONALIDADE E FILIAÇÃO DOS CÔNJUGES: X")[0] is None

    def test_not_stated(self):
        assert find_naturalidade("NATURALIDADE: NAO CONSTA\n")[0] is None


class TestPerSpouseClause:
    def test_ler_trecho_reads_one_persons_clause(self):
        out = ler_trecho(
            "Rafael, brasileiro, natural de Campinas, Estado de São Paulo, nascido no dia 10/03/1985, "
            "filho de Aurelio Prado e de Marta Menezes."
        )
        assert out == {
            "nome_pai": ("Aurelio Prado", "media"),
            "nome_mae": ("Marta Menezes", "media"),
            "naturalidade": ("Campinas/SP", "media"),
        }

    def test_each_spouse_gets_their_own_parents_and_birthplace(self):
        a, b = find_conjuges(CERTIDAO_SP)
        assert (a.nome_pai, a.nome_mae, a.naturalidade) == (
            "Aurelio Prado", "Marta Menezes", "Campinas/SP",
        )
        assert (b.nome_pai, b.nome_mae, b.naturalidade) == (
            "Hugo Quintana", "Lia Alencar", "Santos/SP",
        )
        assert a.nome_mae_confianca == "media"  # attributed by name anchor, never alta

    def test_a_certidao_without_the_clauses_leaves_them_empty(self):
        sem = CERTIDAO_SP.replace("filho de", "fi").replace("filha de", "fi").replace("natural de", "n")
        a, b = find_conjuges(sem)
        assert a.nome_mae is None and b.nome_pai is None and a.naturalidade is None


class TestExtractor:
    RG = (
        "REGISTRO GERAL\nNOME: JOAO CARLOS EXEMPLO\nRG 12.345.678-9\nCPF 529.982.247-25\n"
        "FILIAÇÃO\nPEDRO EXEMPLO\nANA EXEMPLO\nDATA DE NASCIMENTO 01/02/1950\n"
        "NATURALIDADE: SÃO PAULO - SP\n"
    )

    def test_rg_reads_filiacao_and_naturalidade(self):
        r = _ler(self.RG, "rg")
        assert (r.nome_pai, r.nome_mae) == ("PEDRO EXEMPLO", "ANA EXEMPLO")
        assert r.nome_mae_confianca.value == "baixa" and r.naturalidade == "SÃO PAULO/SP"
        assert r.persistable("naturalidade") and r.sugestao("nome_mae")

    def test_cnh_reads_filiacao_but_never_a_naturalidade(self):
        r = _ler(self.RG, "cnh")
        assert r.nome_mae == "ANA EXEMPLO" and r.naturalidade is None

    def test_certidao_nascimento_reads_them(self):
        r = _ler(
            "CERTIDÃO DE NASCIMENTO\nNOME: JOAO CARLOS EXEMPLO\nFILIAÇÃO: PEDRO EXEMPLO E ANA EXEMPLO\n"
            "LOCAL DE NASCIMENTO: Campinas/SP\nDATA DE NASCIMENTO 01/02/1950\n",
            "certidao_nascimento",
        )
        assert (r.nome_pai, r.nome_mae, r.naturalidade) == ("PEDRO EXEMPLO", "ANA EXEMPLO", "Campinas/SP")

    def test_certidao_casamento_gives_the_titular_only_their_own(self):
        r = _ler(CERTIDAO_SP, "certidao_casamento", TitularEsperado(nome="Rafael Menezes do Prado"))
        assert (r.nome_pai, r.nome_mae, r.naturalidade) == ("Aurelio Prado", "Marta Menezes", "Campinas/SP")
        assert r.cpf == "529.982.247-25" and (r.rg, r.rg_orgao) == ("11.222.333-4", "SSP/SP")

    def test_certidao_casamento_without_a_titular_reads_nothing_per_person(self):
        r = _ler(CERTIDAO_SP, "certidao_casamento")
        assert r.nome_mae is None and r.nome_pai is None and r.naturalidade is None
        assert r.cpf is None and r.rg is None  # never the first spouse's by accident
        assert len(r.conjuges) == 2

    def test_an_undeclared_type_never_attributes_two_holders_to_one(self):
        r = _ler(CERTIDAO_SP, None)
        assert r.nome_mae is None and r.nome_pai is None and r.naturalidade is None

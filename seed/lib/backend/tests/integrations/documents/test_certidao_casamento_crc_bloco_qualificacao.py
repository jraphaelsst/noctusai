"""CRC national-model certidão de casamento: the "Nomes completos ... dos
cônjuges" prose block + the identity-based spouse agreement (F96, prod,
2026-10-24).

A perfectly legible office photo came back with estado civil / regime / data
right but NO spouses: the primary read named "A + LUCIANA" (a name cut at a
line break), the re-read only "A", and the agreement gate dropped the whole
list because the two name sets were not equal. Fixtures are synthetic,
OCR-shaped transcriptions of that layout (invented names, dates, CPFs).
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest

from noctusai_lib.integrations.documents import ExtractionConfidence
from noctusai_lib.integrations.documents.conjuges import ConjugeLido, find_conjuges
from noctusai_lib.integrations.documents.real import LadderIdentityExtractor
from noctusai_lib.integrations.documents.releitura import (
    AVISO_DIVERGENCIA,
    conciliar,
    conjuges_concordam,
    mesclar,
)
from noctusai_lib.integrations.documents.types import IdentityFields, TextSource

# The F96 shape: header current names, a "--"-separated prose block whose
# second name WRAPS mid-name, "permanecerá a usar" / "passará a adotar".
CRC_F96 = (
    "REPÚBLICA FEDERATIVA DO BRASIL\n"
    "REGISTRO CIVIL DAS PESSOAS NATURAIS\n"
    "CERTIDÃO DE CASAMENTO\n"
    "Nomes:\n"
    "RODRIGO ALVES PEREIRA\n"
    "LUCIANA MARTINS PEREIRA\n"
    "Matrícula:\n"
    "123456 01 55 2010 2 00045 123 0012345 67\n"
    "Nomes completos, datas e locais de nascimento, nacionalidade e\n"
    "filiações dos cônjuges:\n"
    "RODRIGO ALVES PEREIRA, nacionalidade brasileira, nascido em Campinas,\n"
    "Estado de São Paulo, a quatro de março de mil novecentos e oitenta,\n"
    "filho de José Alves Pereira e de Maria Alves Pereira -- LUCIANA MARTINS\n"
    "SOUZA, nacionalidade brasileira, nascida em Santos, Estado de São Paulo,\n"
    "a dez de junho de mil novecentos e oitenta e dois, filha de Paulo Souza\n"
    "e de Ana Martins Souza --\n"
    "Data do registro do casamento: doze de maio de dois mil e dez (12/05/2010)\n"
    "Regime de bens do casamento: Comunhão parcial de bens\n"
    "Nome que cada um dos cônjuges passou a utilizar:\n"
    "O contraente permanecerá a usar o nome de RODRIGO ALVES PEREIRA. A\n"
    "contraente passará a adotar o nome de LUCIANA MARTINS\n"
    "PEREIRA.\n"
)

# The 799 shape on the same layout: "passará a USAR o nome de", the header
# printing each name with its CPF, and the header's second name wrapped.
CRC_799 = (
    "CERTIDÃO DE CASAMENTO\n"
    "NOMES:\n"
    "MARCOS VINICIUS TAVARES\n"
    "CPF: 529.982.247-25\n"
    "PATRICIA HELENA\n"
    "BARROS TAVARES\n"
    "CPF: 111.444.777-35\n"
    "MATRÍCULA: 654321 01 55 2015 2 00100 200 0054321 10\n"
    "NOMES COMPLETOS, DATAS E LOCAIS DE NASCIMENTO, NACIONALIDADE E FILIAÇÕES DOS CÔNJUGES:\n"
    "MARCOS VINICIUS TAVARES, nacionalidade brasileira, nascido em Curitiba, Estado do\n"
    "Paraná, a vinte e um de janeiro de mil novecentos e setenta e oito, filho de Jorge\n"
    "Tavares e de Celia Tavares -- PATRICIA HELENA BARROS, nacionalidade brasileira,\n"
    "nascida em Londrina, Estado do Paraná, a três de setembro de mil novecentos e\n"
    "oitenta e um, filha de Otavio Barros e de Rosa Barros --\n"
    "REGIME DE BENS DO CASAMENTO: Comunhão universal de bens\n"
    "NOME QUE CADA UM DOS CÔNJUGES PASSOU A UTILIZAR:\n"
    "O contraente continuará a usar o nome de MARCOS VINICIUS TAVARES. A contraente\n"
    "passará a usar o nome de PATRICIA HELENA BARROS TAVARES.\n"
)


class TestCrcBlockParser:
    def test_f96_both_spouses_with_their_own_facts(self):
        a, b = find_conjuges(CRC_F96)
        assert a.nome == "RODRIGO ALVES PEREIRA" and a.nome_anterior is None
        assert a.data_nascimento == date(1980, 3, 4)
        assert a.naturalidade == "Campinas/SP"
        assert (a.nome_pai, a.nome_mae) == ("José Alves Pereira", "Maria Alves Pereira")
        assert a.genero == "Masculino" and a.genero_derivado
        # The bride: maiden name from the block (re-joined across the line
        # wrap), married name from "passará a adotar o nome de" (also wrapped).
        assert b.nome == "LUCIANA MARTINS PEREIRA"
        assert b.nome_anterior == "LUCIANA MARTINS SOUZA"
        assert b.data_nascimento == date(1982, 6, 10)
        assert b.naturalidade == "Santos/SP"
        assert (b.nome_pai, b.nome_mae) == ("Paulo Souza", "Ana Martins Souza")
        # Neither spouse got the couple's celebration date as a birth date.
        assert date(2010, 5, 12) not in (a.data_nascimento, b.data_nascimento)
        # Both printed in the header "Nomes:" list too.
        assert a.confirmado_cabecalho and b.confirmado_cabecalho

    def test_799_passara_a_usar_and_header_cpfs(self):
        a, b = find_conjuges(CRC_799)
        assert (a.nome, a.cpf) == ("MARCOS VINICIUS TAVARES", "529.982.247-25")
        assert (b.nome, b.nome_anterior) == ("PATRICIA HELENA BARROS TAVARES", "PATRICIA HELENA BARROS")
        assert b.cpf == "111.444.777-35"
        assert a.data_nascimento == date(1978, 1, 21)
        assert b.data_nascimento == date(1981, 9, 3)
        # The header name wrapped onto two lines is re-joined, so it confirms.
        assert a.confirmado_cabecalho and b.confirmado_cabecalho

    def test_no_adoption_clause_the_header_gives_the_current_name(self):
        texto = CRC_F96.split("Nome que cada um")[0]
        _, b = find_conjuges(texto)
        assert (b.nome, b.nome_anterior) == ("LUCIANA MARTINS PEREIRA", "LUCIANA MARTINS SOUZA")

    def test_a_lost_separator_is_recovered_from_the_header_prenome(self):
        texto = CRC_F96.replace(" -- LUCIANA", " LUCIANA")
        a, b = find_conjuges(texto)
        assert a.nome == "RODRIGO ALVES PEREIRA"
        assert b.nome_anterior == "LUCIANA MARTINS SOUZA"

    def test_a_single_clause_is_not_a_couple(self):
        texto = CRC_F96.split(" -- LUCIANA")[0] + "\nRegime de bens: Comunhão parcial\n"
        assert all(c.nome != "LUCIANA" for c in find_conjuges(texto))

    @pytest.mark.asyncio
    async def test_end_to_end_through_the_extractor(self):
        class _Resolved:
            text, error, error_message = CRC_F96, None, None

        class _Resolver:
            async def resolve(self, media):
                return _Resolved()

        out = await LadderIdentityExtractor(resolver=_Resolver()).extract(b"x", mimetype="image/jpeg")
        assert [c.nome for c in out.conjuges] == ["RODRIGO ALVES PEREIRA", "LUCIANA MARTINS PEREIRA"]
        assert out.estado_civil == "casado"
        assert out.data_casamento == date(2010, 5, 12)


def _leitura(*conjuges: ConjugeLido) -> IdentityFields:
    return IdentityFields(
        estado_civil="casado", estado_civil_confianca=ExtractionConfidence.MEDIA,
        conjuges=tuple(conjuges), source=TextSource.OCR,
    )


_A = ConjugeLido(nome="RODRIGO ALVES PEREIRA", data_nascimento=date(1980, 3, 4), confirmado_cabecalho=True)
_B = ConjugeLido(
    nome="LUCIANA MARTINS PEREIRA", nome_anterior="LUCIANA MARTINS SOUZA",
    data_nascimento=date(1982, 6, 10), confirmado_cabecalho=True,
)


class TestSpouseAgreementByIdentity:
    def test_f96_partial_reread_keeps_the_header_confirmed_superset(self):
        primaria = _leitura(*find_conjuges(CRC_F96))
        releitura = _leitura(ConjugeLido(nome="RODRIGO ALVES PEREIRA"))
        out = mesclar(primaria, releitura, escalation_model="m")
        assert [c.nome for c in out.conjuges] == ["RODRIGO ALVES PEREIRA", "LUCIANA MARTINS PEREIRA"]
        assert "conjuges" not in [c for c, _ in out.divergencias]

    def test_an_uncorroborated_extra_spouse_goes_to_review_the_common_one_stays(self):
        """The literal F96 pair: 'A + LUCIANA' (truncated, not in any header)
        vs 'A'. A is corroborated; the fragment is withheld, never the list."""
        out = mesclar(
            _leitura(ConjugeLido(nome="RODRIGO ALVES PEREIRA"), ConjugeLido(nome="LUCIANA")),
            _leitura(ConjugeLido(nome="RODRIGO ALVES PEREIRA")),
            escalation_model="m",
        )
        assert [c.nome for c in out.conjuges] == ["RODRIGO ALVES PEREIRA"]
        assert out.divergencias == (("conjuges", ("LUCIANA",)),)
        assert AVISO_DIVERGENCIA in out.aviso.split("+")

    def test_maiden_vs_married_form_is_the_same_person(self):
        so_solteira = ConjugeLido(nome="LUCIANA MARTINS SOUZA", data_nascimento=date(1982, 6, 10))
        out = mesclar(_leitura(_A, _B), _leitura(_A, so_solteira), escalation_model="m")
        assert [c.nome for c in out.conjuges] == ["RODRIGO ALVES PEREIRA", "LUCIANA MARTINS PEREIRA"]
        assert out.conjuges[1].nome_anterior == "LUCIANA MARTINS SOUZA"
        assert out.divergencias == ()
        assert conjuges_concordam(_leitura(_A, _B), _leitura(_A, so_solteira))

    def test_order_does_not_matter(self):
        assert conjuges_concordam(_leitura(_A, _B), _leitura(_B, _A))

    def test_a_conflicting_birth_date_goes_to_review_the_spouse_stays(self):
        outra_data = replace(_B, data_nascimento=date(1982, 6, 1), confirmado_cabecalho=False)
        out = mesclar(_leitura(_A, _B), _leitura(_A, outra_data), escalation_model="m")
        assert len(out.conjuges) == 2
        assert out.conjuges[1].data_nascimento is None
        ((campo, valores),) = out.divergencias
        assert campo == "conjuges"
        assert "data_nascimento 1982-06-10 ≠ 1982-06-01" in valores[0]

    def test_a_gap_is_filled_from_the_other_read(self):
        sem_data = replace(_B, data_nascimento=None)
        out = mesclar(_leitura(_A, sem_data), _leitura(_A, _B), escalation_model="m")
        assert out.conjuges[1].data_nascimento == date(1982, 6, 10)

    def test_no_spouse_in_common_still_withholds_everything(self):
        out = mesclar(
            _leitura(ConjugeLido(nome="ANA EXEMPLO SILVA")),
            _leitura(ConjugeLido(nome="BRUNO EXEMPLO COSTA")),
            escalation_model="m",
        )
        assert out.conjuges == ()
        assert [c for c, _ in out.divergencias] == ["conjuges"]

    def test_production_conciliation_f96(self):
        """`conciliar` (one fallback read for the doubtful `conjuges`)."""
        primaria = _leitura(*find_conjuges(CRC_F96))
        fallback = _leitura(ConjugeLido(nome="RODRIGO ALVES PEREIRA"))
        out = conciliar(primaria, fallback, duvidosos=("conjuges",), modelo_fallback="m")
        assert [c.nome for c in out.conjuges] == ["RODRIGO ALVES PEREIRA", "LUCIANA MARTINS PEREIRA"]

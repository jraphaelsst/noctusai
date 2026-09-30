"""The vision/OCR fallback parser — single-person, deliberately scoped (see
the module's own docstring for why a multi-person text-only read is out of
scope)."""
from datetime import date, timedelta

from noctusai_lib.integrations.documents.ficha_cadastral_texto import parse_texto
from noctusai_lib.integrations.documents.types import ExtractionConfidence

NASCIMENTO = (date.today() - timedelta(days=365 * 35)).strftime("%d/%m/%Y")


class TestParseTexto:
    def test_reads_a_single_person_off_narrative_text(self):
        texto = (
            "FORMULARIO FGTS\n"
            "Nome: FULANO DE TAL\n"
            f"Data de Nascimento: {NASCIMENTO}\n"
            "CPF: 123.456.789-09\n"
            "Nacionalidade: brasileiro\n"
            "Profissão: pedreiro\n"
            "Estado civil: casado\n"
        )
        lida = parse_texto(texto)
        assert len(lida.pessoas) == 1
        pessoa = lida.pessoas[0]
        assert pessoa.nome == "FULANO DE TAL"
        assert pessoa.cpf == "123.456.789-09"
        # Every field is tempered off a vision pass — never ALTA.
        assert pessoa.nome_confianca is not ExtractionConfidence.ALTA
        assert pessoa.cpf_confianca is not ExtractionConfidence.ALTA

    def test_empty_text_yields_no_people_not_an_error(self):
        lida = parse_texto("nada de util aqui")
        assert lida.pessoas == ()
        assert lida.error is None

    def test_blank_text(self):
        lida = parse_texto("")
        assert lida.pessoas == ()

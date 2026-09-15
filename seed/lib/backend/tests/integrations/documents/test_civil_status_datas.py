"""`find_data_casamento` / `find_data_emissao` — contract F6 (social-wiring
migration 117).

🔴 SCOPE NOTE — pure-parser tests only, deliberately
------------------------------------------------------
This slice's dispatch scope is `types.py` + `civil_status.py` (+ additive
`__init__.py` lines) only. `real.LadderIdentityExtractor` — which wires
`find_estado_civil`/`find_regime_bens` into the full `extract()` call — is
NOT in scope, so it does not yet call these two new finders either. These
tests therefore exercise the bare parsers directly, the same ground-truth
layer `test_civil_status.py`'s `TestEstadoCivilLabelled` etc. classes do,
without the end-to-end `TestCivilStatusWiring` section that file also has —
that wiring is a follow-up slice's job, not this one's. Synthetic text only,
never a real CPF/RG/certidão.
"""
from __future__ import annotations

from datetime import date

from noctusai_lib.integrations.documents import (
    ExtractionConfidence,
    IdentityFields,
    find_data_casamento,
    find_data_emissao,
)
from noctusai_lib.integrations.documents.types import CAMPOS


class TestDataCasamentoCelebrationLabel:
    def test_hyphenated_casaram_se_em_numeric(self):
        valor, conf, rotulo = find_data_casamento(
            "CERTIDAO DE CASAMENTO\nOS CONTRAENTES CASARAM-SE EM 12/03/2010\n"
        )
        assert (valor, conf) == (date(2010, 3, 12), "alta")
        assert rotulo == "CASARAM-SE EM"

    def test_data_do_casamento_semi_extenso(self):
        valor, conf, rotulo = find_data_casamento(
            "DATA DO CASAMENTO: 12 DE MARCO DE 2010"
        )
        assert (valor, conf) == (date(2010, 3, 12), "alta")
        assert rotulo == "DATA DO CASAMENTO"

    def test_fully_extenso_date(self):
        """The office's own example: 'doze de março de dois mil e dez'."""
        valor, conf, _ = find_data_casamento(
            "CASARAM-SE EM DOZE DE MARCO DE DOIS MIL E DEZ"
        )
        assert (valor, conf) == (date(2010, 3, 12), "alta")

    def test_fully_extenso_pre_1977_date_for_the_lei_6515_boundary(self):
        """29/12/1980 sits on the POST-26/12/1977 side; the office's citation
        branch itself is the product's job, not this parser's — this only
        proves the date comes out right on either side of that line."""
        valor, conf, _ = find_data_casamento(
            "DATA DO CASAMENTO: VINTE E NOVE DE DEZEMBRO DE MIL NOVECENTOS E "
            "OITENTA"
        )
        assert (valor, conf) == (date(1980, 12, 29), "alta")

    def test_fully_extenso_date_before_the_lei_boundary(self):
        valor, conf, _ = find_data_casamento(
            "CASARAM-SE EM DEZ DE JANEIRO DE MIL NOVECENTOS E SETENTA"
        )
        assert (valor, conf) == (date(1970, 1, 10), "alta")

    def test_accents_and_casing_do_not_matter(self):
        valor, conf, _ = find_data_casamento("Casaram-se em 05/06/1999")
        assert (valor, conf) == (date(1999, 6, 5), "alta")


class TestDataCasamentoRegistroFallback:
    def test_registro_used_only_when_no_celebration_label_exists(self):
        valor, conf, rotulo = find_data_casamento("DATA DE REGISTRO: 01/02/1975")
        assert (valor, conf) == (date(1975, 2, 1), "alta")
        assert rotulo == "DATA DE REGISTRO"

    def test_celebration_label_wins_over_a_registro_date(self):
        texto = "CASARAM-SE EM 12/03/2010\nDATA DE REGISTRO: 20/03/2010\n"
        valor, conf, rotulo = find_data_casamento(texto)
        assert (valor, conf) == (date(2010, 3, 12), "alta")
        assert rotulo == "CASARAM-SE EM"

    def test_an_unlabelled_registro_style_date_is_never_guessed(self):
        """'registro date fallback only if clearly labelled' — a bare date
        near the word REGISTRO with no explicit label is not accepted."""
        valor, conf, _ = find_data_casamento("REGISTRO NUMERO 12345, 01/02/1975")
        assert valor is None
        assert conf == "nenhuma"


class TestDataCasamentoNeverGuesses:
    def test_empty_text(self):
        assert find_data_casamento("") == (None, "nenhuma", None)

    def test_a_document_without_the_field_is_not_an_error(self):
        assert find_data_casamento("CPF 123.456.789-00\nNOME FULANO") == (
            None,
            "nenhuma",
            None,
        )

    def test_two_disagreeing_celebration_labels_report_nothing(self):
        texto = "CASARAM-SE EM 12/03/2010 ... DATA DO CASAMENTO: 01/01/2011"
        valor, conf, _ = find_data_casamento(texto)
        assert valor is None
        assert conf == "nenhuma"

    def test_two_agreeing_celebration_labels_are_still_high(self):
        texto = "CASARAM-SE EM 12/03/2010 ... DATA DO CASAMENTO: 12/03/2010"
        valor, conf, _ = find_data_casamento(texto)
        assert (valor, conf) == (date(2010, 3, 12), "alta")

    def test_a_future_date_is_implausible(self):
        valor, conf, _ = find_data_casamento("CASARAM-SE EM 12/03/2099")
        assert valor is None
        assert conf == "nenhuma"

    def test_a_pre_1900_date_is_implausible(self):
        valor, conf, _ = find_data_casamento("CASARAM-SE EM 12/03/1850")
        assert valor is None
        assert conf == "nenhuma"

    def test_a_nearer_nascimento_label_is_not_read_as_casamento(self):
        """A decoy: DATA DE NASCIMENTO sits closer to the date than our own
        label would, so the date is not ours."""
        valor, conf, _ = find_data_casamento("DATA DE NASCIMENTO: 12/03/2010")
        assert valor is None
        assert conf == "nenhuma"


class TestDataEmissaoExplicitLabel:
    def test_emitida_em_numeric(self):
        valor, conf, rotulo = find_data_emissao("EMITIDA EM 15/03/2024")
        assert (valor, conf) == (date(2024, 3, 15), "alta")
        assert rotulo == "EMITIDA EM"

    def test_data_de_emissao_semi_extenso(self):
        valor, conf, _ = find_data_emissao("DATA DE EMISSAO: 15 DE MARCO DE 2024")
        assert (valor, conf) == (date(2024, 3, 15), "alta")

    def test_emitido_em_fully_extenso(self):
        valor, conf, _ = find_data_emissao(
            "EMITIDO EM DOZE DE MARCO DE DOIS MIL E VINTE E QUATRO"
        )
        assert (valor, conf) == (date(2024, 3, 12), "alta")

    def test_two_agreeing_labels_are_still_high(self):
        texto = "EMITIDA EM 15/03/2024 ... DATA DE EMISSAO: 15/03/2024"
        valor, conf, _ = find_data_emissao(texto)
        assert (valor, conf) == (date(2024, 3, 15), "alta")

    def test_two_disagreeing_labels_report_nothing(self):
        texto = "EMITIDA EM 15/03/2024 ... DATA DE EMISSAO: 01/01/2024"
        valor, conf, _ = find_data_emissao(texto)
        assert valor is None
        assert conf == "nenhuma"


class TestDataEmissaoClosingLineFallback:
    def test_falls_back_to_the_last_dated_line_when_unlabelled(self):
        texto = (
            "CERTIDAO DE CASAMENTO\n"
            "CASARAM-SE EM 12/03/2010\n"
            "SAO PAULO, DOZE DE MARCO DE DOIS MIL E VINTE E QUATRO.\n"
        )
        valor, conf, rotulo = find_data_emissao(texto)
        assert (valor, conf) == (date(2024, 3, 12), "baixa")
        assert rotulo == "FECHAMENTO_CARTORIO"

    def test_an_explicit_label_far_from_the_closing_line_wins(self):
        """The closing date sits well outside `EMITIDA EM`'s 48-char label
        window (unlike the two adjacent dates in the fallback test above),
        so the two are genuinely distinguishable readings, not an ambiguous
        pair — `EMITIDA EM` wins outright."""
        texto = (
            "CERTIDAO DE CASAMENTO\n"
            "EMITIDA EM 20/03/2024\n"
            "OS CONTRAENTES CASARAM-SE SOB O REGIME DA COMUNHAO PARCIAL DE "
            "BENS, CONFORME CONSTA DO LIVRO COMPETENTE DESTE CARTORIO DE "
            "REGISTRO CIVIL DAS PESSOAS NATURAIS\n"
            "SAO PAULO, DOZE DE MARCO DE DOIS MIL E VINTE E QUATRO.\n"
        )
        valor, conf, rotulo = find_data_emissao(texto)
        assert (valor, conf) == (date(2024, 3, 20), "alta")
        assert rotulo == "EMITIDA EM"


class TestDataEmissaoAmbiguousLabelWindow:
    def test_two_dates_sharing_one_nearby_label_disagree_and_report_nothing(self):
        """Same 'disagreement is absence' rule every other function in this
        module applies: a label found near TWO distinct dates (both inside
        its 48-char window) is ambiguous, not resolved by picking one."""
        texto = "EMITIDA EM 20/03/2024 SAO PAULO, 12/03/2024\n"
        valor, conf, _ = find_data_emissao(texto)
        assert valor is None
        assert conf == "nenhuma"


class TestDataEmissaoNeverGuessesBeyondTheFallback:
    def test_empty_text(self):
        assert find_data_emissao("") == (None, "nenhuma", None)

    def test_a_document_with_no_dates_at_all(self):
        assert find_data_emissao("NOME FULANO DE TAL") == (None, "nenhuma", None)

    def test_a_future_date_is_implausible_even_for_the_fallback(self):
        valor, conf, _ = find_data_emissao("SAO PAULO, 12/03/2099")
        assert valor is None
        assert conf == "nenhuma"


class TestDataCasamentoIsACampoDataEmissaoIsNot:
    """The `types.IdentityFields` contract: `data_casamento` gets the full
    persistable/sugestao machinery via `CAMPOS`; `data_emissao` rides on the
    document alone, exactly as `rg_orgao` does."""

    def test_data_casamento_is_in_campos(self):
        assert "data_casamento" in CAMPOS

    def test_data_emissao_is_not_in_campos(self):
        assert "data_emissao" not in CAMPOS

    def test_persistable_data_casamento_requires_alta(self):
        alta = IdentityFields(
            data_casamento=date(2010, 3, 12),
            data_casamento_confianca=ExtractionConfidence.ALTA,
        )
        assert alta.persistable_data_casamento is True
        assert alta.sugestao_data_casamento is False

    def test_data_emissao_has_no_persistable_property(self):
        assert not hasattr(IdentityFields(), "persistable_data_emissao")

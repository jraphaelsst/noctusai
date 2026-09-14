"""`find_estado_civil` / `find_regime_bens` — marital status, and the one
field family where "averbação later wins" replaces "disagreement is
absence".

🔴 WHAT THESE TESTS ARE REALLY FOR
------------------------------------
Every sibling parser treats two conflicting readings as a misread. Here that
rule would silently DROP the whole reason `certidao_casamento` became
extractable at all: a registro reading "casado" and a later AVERBAÇÃO
reading "divorciado" are not noise, they are the document doing its job. So
most of what follows verifies the boundary between the two cases — a real
disagreement (still absence) vs. an averbação-mediated update (the later
reading wins) — using SYNTHETIC text only, never a real CPF/RG/certidão.
"""
from __future__ import annotations

import pytest

from noctusai_lib.integrations.documents import (
    ExtractionConfidence,
    FakeIdentityExtractor,
    find_estado_civil,
    find_regime_bens,
)
from noctusai_lib.integrations.documents.civil_status import (
    ESTADO_CIVIL_VALORES,
    REGIME_BENS_VALORES,
)
from noctusai_lib.integrations.documents.real import LadderIdentityExtractor

REGISTRO_CASADOS = (
    "CERTIDAO DE CASAMENTO\n"
    "OS CONTRAENTES CASARAM-SE SOB O REGIME DA COMUNHAO PARCIAL DE BENS\n"
)


class TestVocabulary:
    def test_the_closed_vocabularies_are_snake_case(self):
        for token in ESTADO_CIVIL_VALORES:
            assert token == token.lower()
            assert " " not in token
        for token in REGIME_BENS_VALORES:
            assert token == token.lower()
            assert " " not in token


class TestEstadoCivilLabelled:
    def test_estado_civil_label_reads_high(self):
        valor, conf, rotulo = find_estado_civil("NOME FULANO\nESTADO CIVIL: CASADO")
        assert (valor, conf) == ("casado", "alta")
        assert rotulo == "ESTADO CIVIL"

    def test_feminine_spelling_normalises_to_the_same_token(self):
        valor, conf, _ = find_estado_civil("ESTADO CIVIL: DIVORCIADA")
        assert (valor, conf) == ("divorciado", "alta")

    def test_uniao_estavel_is_a_two_word_phrase(self):
        valor, conf, _ = find_estado_civil("ESTADO CIVIL: UNIAO ESTAVEL")
        assert (valor, conf) == ("uniao_estavel", "alta")

    def test_accents_and_casing_do_not_matter(self):
        valor, conf, _ = find_estado_civil("Estado Cívil: Viúva")
        assert (valor, conf) == ("viuvo", "alta")


class TestEstadoCivilNeverGuesses:
    def test_a_bare_word_with_no_label_is_never_accepted(self):
        """The whole point of this module, unlike `gender.py`'s whole-word
        fallback: "casado" is an ordinary Portuguese word with far more
        reasons to appear loose in prose than a sex word does."""
        valor, conf, _ = find_estado_civil("O CLIENTE E CASADO COM DUAS FILHAS")
        assert valor is None
        assert conf == "nenhuma"

    def test_a_document_without_the_field_is_not_an_error(self):
        assert find_estado_civil("CPF 123.456.789-00\nNOME FULANO") == (
            None,
            "nenhuma",
            None,
        )

    def test_empty_text(self):
        assert find_estado_civil("") == (None, "nenhuma", None)

    def test_a_filiacao_block_does_not_supply_the_holders_estado_civil(self):
        """Attributing a parent's anything to the holder is the error this
        whole label-anchored family exists to avoid — same discipline
        `gender.py` applies."""
        valor, conf, _ = find_estado_civil("FILIACAO: MAE ESTADO CIVIL: CASADA")
        assert valor is None
        assert conf == "nenhuma"


class TestEstadoCivilDisagreementWithNoAverbacaoIsAbsence:
    def test_two_labelled_readings_that_disagree_report_nothing(self):
        """Same family rule `gender.py` applies: two conflicting labelled
        readings with no averbação between them is a misread, not an
        update."""
        valor, conf, _ = find_estado_civil(
            "ESTADO CIVIL: CASADO ... ESTADO CIVIL: SOLTEIRO"
        )
        assert valor is None
        assert conf == "nenhuma"

    def test_two_agreeing_labelled_readings_are_still_high(self):
        valor, conf, _ = find_estado_civil("ESTADO CIVIL: CASADO ... ESTADO CIVIL: CASADO")
        assert (valor, conf) == ("casado", "alta")


class TestEstadoCivilAverbacaoOverridesTheRegistro:
    """🔴 The reason this module exists: `certidao_casamento` (migration 103)
    is only safe to extract because the averbação, not the registro, is
    read as the truth when both are present."""

    def test_divorcio_averbacao_overrides_a_casado_registro(self):
        texto = (
            REGISTRO_CASADOS
            + "AVERBACAO: DIVORCIO AVERBADO EM 10/03/2020, CONFORME SENTENCA\n"
        )
        valor, conf, rotulo = find_estado_civil(texto)
        assert (valor, conf) == ("divorciado", "alta")
        assert rotulo is not None and "AVERBACAO" in rotulo

    def test_obito_averbacao_reads_as_viuvo(self):
        texto = REGISTRO_CASADOS + "AVERBACAO: OBITO DO CONJUGE EM 01/01/2021\n"
        valor, conf, _ = find_estado_civil(texto)
        assert (valor, conf) == ("viuvo", "alta")

    def test_separacao_judicial_averbacao(self):
        texto = REGISTRO_CASADOS + "AVERBACAO DE SEPARACAO JUDICIAL EM 05/05/2019\n"
        valor, conf, _ = find_estado_civil(texto)
        assert (valor, conf) == ("separado_judicialmente", "alta")

    def test_conversao_de_uniao_estavel_averbacao_reads_as_casado(self):
        texto = (
            "ESTADO CIVIL: SOLTEIRO\n"
            "AVERBACAO: CONVERSAO DE UNIAO ESTAVEL EM CASAMENTO, 12/12/2018\n"
        )
        valor, conf, _ = find_estado_civil(texto)
        assert (valor, conf) == ("casado", "alta")

    def test_conflicting_events_inside_one_averbacao_zone_report_nothing(self):
        """Two different life events in the same amendment zone means the
        text was misread, not that both happened."""
        texto = (
            REGISTRO_CASADOS
            + "AVERBACAO: DIVORCIO EM 2019. AVERBACAO: OBITO EM 2021.\n"
        )
        valor, conf, _ = find_estado_civil(texto)
        assert valor is None
        assert conf == "nenhuma"

    def test_an_averbacao_zone_with_no_recognised_event_falls_back_to_the_registro(self):
        """An averbação exists (a name-spelling correction, say) but carries
        none of the five recognised life events — the registro still
        stands."""
        texto = REGISTRO_CASADOS + "AVERBACAO: RETIFICACAO DE GRAFIA DO NOME\n"
        valor, conf, _ = find_estado_civil(texto)
        assert (valor, conf) == ("casado", "alta")


class TestEstadoCivilInferredFromRegimeDeBens:
    def test_a_bare_regime_phrase_infers_casado(self):
        """The one structural inference this module makes — see the module
        docstring."""
        valor, conf, rotulo = find_estado_civil(
            "CASARAM-SE SOB O REGIME DA COMUNHAO UNIVERSAL DE BENS"
        )
        assert (valor, conf) == ("casado", "alta")
        assert rotulo is not None and "COMUNHAO UNIVERSAL" in rotulo

    def test_an_explicit_label_wins_over_the_regime_inference(self):
        texto = "ESTADO CIVIL: SOLTEIRO\n" + REGISTRO_CASADOS
        valor, conf, rotulo = find_estado_civil(texto)
        assert (valor, conf) == ("solteiro", "alta")
        assert rotulo == "ESTADO CIVIL"


class TestRegimeBensUnlabelled:
    def test_comunhao_parcial_is_read_without_any_label(self):
        valor, conf, rotulo = find_regime_bens(REGISTRO_CASADOS)
        assert (valor, conf) == ("comunhao_parcial", "alta")
        assert "COMUNHAO PARCIAL" in (rotulo or "")

    def test_participacao_final_de_aquestos(self):
        valor, conf, _ = find_regime_bens(
            "REGIME DE PARTICIPACAO FINAL NOS AQUESTOS"
        )
        assert (valor, conf) == ("participacao_final_aquestos", "alta")

    def test_separacao_obrigatoria(self):
        valor, conf, _ = find_regime_bens("SEPARACAO OBRIGATORIA DE BENS")
        assert (valor, conf) == ("separacao_obrigatoria", "alta")

    def test_empty_text(self):
        assert find_regime_bens("") == (None, "nenhuma", None)

    def test_a_document_without_the_field_is_not_an_error(self):
        assert find_regime_bens("CPF 123.456.789-00") == (None, "nenhuma", None)


class TestRegimeBensAverbacaoOverride:
    def test_a_later_regime_after_an_averbacao_wins(self):
        texto = (
            REGISTRO_CASADOS
            + "AVERBACAO: ALTERACAO DE REGIME DE BENS PARA SEPARACAO TOTAL DE BENS\n"
        )
        valor, conf, rotulo = find_regime_bens(texto)
        assert (valor, conf) == ("separacao_total", "alta")
        assert rotulo is not None and rotulo.startswith("AVERBACAO:")

    def test_two_conflicting_readings_with_no_averbacao_between_them_is_absence(self):
        texto = "COMUNHAO PARCIAL DE BENS ... COMUNHAO UNIVERSAL DE BENS"
        valor, conf, _ = find_regime_bens(texto)
        assert valor is None
        assert conf == "nenhuma"

    def test_repeating_the_same_regime_is_still_high(self):
        texto = REGISTRO_CASADOS + "AVERBACAO: NADA CONSTA\n" + "COMUNHAO PARCIAL DE BENS"
        valor, conf, _ = find_regime_bens(texto)
        assert (valor, conf) == ("comunhao_parcial", "alta")


# ─── End-to-end through the ladder ───────────────────────────────────────
#
# The bare-parser tests above are the ground truth; these confirm the same
# behaviour survives the full `extract()` call. Image mimetype is used
# throughout so the text-layer rung is skipped entirely (no PDF text-layer
# classification involved), which means an injected resolver is the only
# seam needed — no patching of our own code.

CERTIDAO_COM_AVERBACAO = (
    "CERTIDAO DE CASAMENTO\n"
    "OS CONTRAENTES CASARAM-SE SOB O REGIME DA COMUNHAO PARCIAL DE BENS\n"
    "AVERBACAO: DIVORCIO AVERBADO EM 10/03/2020, CONFORME SENTENCA\n"
)


class _StubResolved:
    def __init__(self, text="", error=None, error_message=None):
        self.text, self.error, self.error_message = text, error, error_message


class _StubResolver:
    """Stands in for the media resolver's vision rung — dependency
    injection, not a patch of our own code."""

    def __init__(self, resolved=None):
        self._resolved = resolved or _StubResolved(text="")
        self.calls = 0

    async def resolve(self, media):
        self.calls += 1
        return self._resolved


class TestCivilStatusWiring:
    """`estado_civil` / `regime_bens` end-to-end — the Fake adapter scripts
    a married reading, the Real adapter parses one, and the
    averbação-precedence rule holds through the full `extract()` call, not
    just at the bare parser level."""

    @pytest.mark.asyncio
    async def test_fake_adapter_scripts_a_married_reading(self):
        out = await FakeIdentityExtractor().extract(b"x", filename="rg.jpg")
        assert out.estado_civil == "casado"
        assert out.estado_civil_confianca is ExtractionConfidence.ALTA
        assert out.persistable_estado_civil is True
        assert out.regime_bens == "comunhao_parcial"
        assert out.persistable_regime_bens is True

    @pytest.mark.asyncio
    async def test_real_adapter_reads_a_bare_registro(self):
        resolver = _StubResolver(_StubResolved(text="COMUNHAO PARCIAL DE BENS"))
        out = await LadderIdentityExtractor(resolver=resolver).extract(
            b"x", mimetype="image/png"
        )
        assert out.estado_civil == "casado"
        assert out.regime_bens == "comunhao_parcial"
        # Not tempered by source, unlike `nome`/`rg` — see `real.py`.
        assert out.estado_civil_confianca is ExtractionConfidence.ALTA

    @pytest.mark.asyncio
    async def test_real_adapter_honours_averbacao_precedence_through_the_ladder(self):
        """🔴 The reason `certidao_casamento` is safe to extract at all
        (social-wiring migration 103): reading the whole document through
        the ladder must still land on the AVERBAÇÃO, not the registro."""
        resolver = _StubResolver(_StubResolved(text=CERTIDAO_COM_AVERBACAO))
        out = await LadderIdentityExtractor(resolver=resolver).extract(
            b"x", mimetype="image/png"
        )
        assert out.estado_civil == "divorciado"
        assert out.estado_civil_rotulo is not None
        assert "AVERBACAO" in out.estado_civil_rotulo
        # regime_bens is unaffected by an estado_civil-only averbação.
        assert out.regime_bens == "comunhao_parcial"

    @pytest.mark.asyncio
    async def test_a_document_with_neither_field_yields_no_guess(self):
        resolver = _StubResolver(_StubResolved(text="NOME FULANO DE TAL"))
        out = await LadderIdentityExtractor(resolver=resolver).extract(
            b"x", mimetype="image/png"
        )
        assert out.estado_civil is None
        assert out.estado_civil_confianca is ExtractionConfidence.NENHUMA
        assert out.regime_bens is None
        assert out.persistable_estado_civil is False

"""`derivar_nacionalidade_civil` — deriving `"brasileiro"` off a state civil
RG issuer, never off document prose.

Separate suite from `test_nacionalidade.py` on purpose: that one exercises
`find_nacionalidade`'s "never guess" label-anchored read; this one exercises
a deliberately DIFFERENT, lower-confidence, explicitly-labelled DERIVED
value that never touches that module or its vocabulary.
"""
from __future__ import annotations

from noctusai_lib.integrations.documents.nacionalidade_civil import (
    derivar_nacionalidade_civil,
)


class TestStateCivilIssuerInfers:
    def test_cnh_ssp_sp_with_no_printed_nationality(self):
        """The brief's own example: "12345678 SSP SP" — a CNH's issuer box,
        no `NACIONALIDADE` label anywhere on the document."""
        valor, conf, rotulo = derivar_nacionalidade_civil("SSP/SP")
        assert (valor, conf) == ("brasileiro", "baixa")
        assert rotulo == "inferida: RG civil estadual (SSP)"

    def test_slash_or_space_separated_issuer_both_normalise(self):
        assert derivar_nacionalidade_civil("SSP SP")[:2] == ("brasileiro", "baixa")
        assert derivar_nacionalidade_civil("SSP-SP")[:2] == ("brasileiro", "baixa")

    def test_other_state_issuers_on_the_whitelist(self):
        assert derivar_nacionalidade_civil("IFP/RJ")[0] == "brasileiro"
        assert derivar_nacionalidade_civil("DETRAN/MG")[0] == "brasileiro"
        assert derivar_nacionalidade_civil("PC/AC")[0] == "brasileiro"

    def test_a_cin_issuer_gets_its_own_provenance_label(self):
        valor, conf, rotulo = derivar_nacionalidade_civil("IIGDR/SP")
        assert (valor, conf) == ("brasileiro", "baixa")
        assert rotulo == "inferida: CIN"

    def test_the_institutes_own_correct_initialism_also_resolves(self):
        assert derivar_nacionalidade_civil("IIRGD/SP")[2] == "inferida: CIN"


class TestForeignIssuerNeverInfers:
    def test_rne(self):
        assert derivar_nacionalidade_civil("RNE") == (None, "nenhuma", None)

    def test_rnm(self):
        assert derivar_nacionalidade_civil("RNM/DF") == (None, "nenhuma", None)

    def test_crnm(self):
        assert derivar_nacionalidade_civil("CRNM") == (None, "nenhuma", None)

    def test_policia_federal_bare_acronym(self):
        assert derivar_nacionalidade_civil("PF/DF") == (None, "nenhuma", None)

    def test_policia_federal_spelled_out(self):
        assert derivar_nacionalidade_civil("POLICIA FEDERAL") == (None, "nenhuma", None)

    def test_mre(self):
        assert derivar_nacionalidade_civil("MRE") == (None, "nenhuma", None)


class TestClosedWhitelistRefusesTheUnknown:
    def test_an_unrecognised_issuer_infers_nothing(self):
        """Not on either list: the whitelist is closed, not "everything not
        on the foreign blocklist"."""
        assert derivar_nacionalidade_civil("XYZ/SP") == (None, "nenhuma", None)

    def test_no_issuer_at_all(self):
        assert derivar_nacionalidade_civil(None) == (None, "nenhuma", None)
        assert derivar_nacionalidade_civil("") == (None, "nenhuma", None)


class TestPrintedNationalityAlwaysWins:
    def test_a_printed_reading_on_the_same_document_refuses_the_guess(self):
        """Even a textbook state-issuer document infers nothing once the
        document (or a certidão for the same person) already printed a
        nationality — the printed reading always wins."""
        assert derivar_nacionalidade_civil(
            "SSP/SP", nacionalidade_lida="italiano"
        ) == (None, "nenhuma", None)

    def test_a_matching_printed_reading_also_refuses(self):
        assert derivar_nacionalidade_civil(
            "SSP/SP", nacionalidade_lida="brasileiro"
        ) == (None, "nenhuma", None)


class TestHumanConfirmedIsUntouched:
    def test_an_already_confirmed_record_is_never_contested(self):
        valor, conf, rotulo = derivar_nacionalidade_civil(
            "SSP/SP", nacionalidade_atual_confirmada=True,
        )
        assert (valor, conf, rotulo) == (None, "nenhuma", None)

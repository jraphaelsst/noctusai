"""`find_endereco` — a postal address off a comprovante de endereço.

🔴 P1/883 (2026-09-25), real, measured against two live utility bills
(names/addresses below are invented; the real documents are private —
see `KB § PATTERNS/backend/backend.md`'s LGPD posture)
----------------------------------------------------------------------
Both comprovantes carried a full, legible address — printed as real text,
not needing a vision call at all — and the parser still returned an
incomplete or empty result:

1. **An Enel-style bill**: `CEP`, `logradouro` and `número` came back, but
   `cidade`/`uf` did not, even though the SAME line prints
   `CEP: 09876-543 - CAMPINAS/SP` — an unlabelled trailing city/UF right
   after the CEP, which `_ROTULOS`'s per-field scan never looks for (it only
   opens a field on its OWN label). The bill's second, more fully labelled
   address block ALSO carries the city, as `CEP: 09876-543  - Município:
   CAMPINAS` — a real label, but separated from the CEP by exactly one
   space, one character short of `_ROTULOS`'s 2-space-or-pipe boundary.

2. **A Vivo-style bill**: the address came back EMPTY (`confianca="nenhuma"`)
   — `sem_dados` in the product. The bill prints its own mailing-window
   address AND its issuer's own address (with the issuer's `CNPJ Emissor:`
   marker two lines below THAT address line, not one). With
   `_EMISSOR_JANELA_LINHAS=1`, the issuer's CEP survived as an unrejected
   candidate, disagreed with the holder's genuine one, and `_envelope()`
   correctly refused to guess between two DISTINCT candidates — reporting
   nothing for a document whose real address was sitting in the text.

Both are fixed here: `_completar_cidade_uf_da_linha_do_cep` backfills
cidade/uf from a CEP line's own tail (labelled or not), and
`_EMISSOR_JANELA_LINHAS` widened from 1 to 2 lines.
"""
from __future__ import annotations

from noctusai_lib.integrations.documents import find_endereco


class TestCepInlineCidadeUfNoSeparateLabel:
    """`CEP: NNNNN-NNN - CIDADE/UF` on one line, no `CIDADE:`/`MUNICIPIO:`
    label anywhere — the Enel envelope-block shape. No `Endereço:` label
    exists in THIS block alone, so `_rotulado()` on its own returns `None`
    and `_envelope()` (pre-existing, positional) answers at `baixa` — same
    posture the real document's own unlabelled mailing block gets."""

    def test_cidade_and_uf_come_off_the_ceps_own_tail(self):
        texto = (
            "JOAO DA SILVA SAUER\n"
            "AL DAS ACACIAS 45 - CASA 2\n"
            "CEP: 09876-543 - CAMPINAS/SP\n"
            "CPF: 123.456.789-00 Cod. Barras: 123456\n"
        )
        r = find_endereco(texto)
        assert r.cep == "09876-543"
        assert r.cidade == "CAMPINAS"
        assert r.uf == "SP"

    def test_dash_form_without_a_slash_also_works(self):
        texto = (
            "JOAO DA SILVA SAUER\n"
            "AL DAS ACACIAS 45 - CASA 2\n"
            "CEP: 09876-543 - CAMPINAS - SP\n"
        )
        r = find_endereco(texto)
        assert (r.cidade, r.uf) == ("CAMPINAS", "SP")

    def test_the_same_backfill_feeds_a_labelled_result_at_alta(self):
        """The real Enel bill carries BOTH an unlabelled mailing block (this
        fix's target) AND a separate `Endereço:` block further down —
        `_rotulado()` picks the CEP's own tail up from the FIRST, unlabelled
        occurrence, backfilling `achados` before the labelled block is even
        reached, so the FINAL result is `alta` (a real `Endereço:` label was
        found) with cidade/uf filled in from the earlier, unlabelled line."""
        texto = (
            "JOAO DA SILVA SAUER\n"
            "AL DAS ACACIAS 45 - CASA 2\n"
            "CEP: 09876-543 - CAMPINAS/SP\n"
            "Titular: JOAO DA SILVA SAUER\n"
            "Endereco: AL DAS ACACIAS 45\n"
        )
        r = find_endereco(texto)
        assert r.confianca == "alta"
        assert r.cep == "09876-543"
        assert r.cidade == "CAMPINAS"
        assert r.uf == "SP"


class TestCepLineWithASeparatelyLabelledMunicipio:
    """`CEP: NNNNN-NNN  - Município: CIDADE` — a real label, but only ONE
    space separates it from the CEP token, short of `_ROTULOS`'s own
    2-space/pipe/line-start field-opening boundary."""

    def test_municipio_label_one_space_after_the_cep_is_still_read(self):
        texto = (
            "Titular: JOAO DA SILVA SAUER\n"
            "Endereco: AL DAS ACACIAS 45\n"
            "CEP: 09876-543  - Municipio: CAMPINAS\n"
        )
        r = find_endereco(texto)
        assert r.cep == "09876-543"
        assert r.cidade == "CAMPINAS"
        assert r.confianca == "alta"

    def test_only_consulted_when_the_ceps_own_tail_has_no_uf(self):
        """`_completar_cidade_uf_da_linha_do_cep` tries the trailing
        `CIDADE/UF` shape FIRST and returns as soon as it finds a `uf` —
        the `Município:` label is a fallback for when that shape is not
        there at all, not a second opinion to race against it."""
        texto = "CEP: 09876-543 - CAMPINAS/SP\n"
        r = find_endereco("Endereco: AL DAS ACACIAS 45\n" + texto)
        assert (r.cidade, r.uf) == ("CAMPINAS", "SP")


class TestIssuerCepTwoLinesFromItsOwnCnpjMarker:
    """P1/883: the issuer's own CNPJ marker sat TWO lines below the
    issuer's own address line, not one — `_EMISSOR_JANELA_LINHAS=1` missed
    it, the issuer's CEP survived as a false holder candidate, and two
    DISTINCT (cep, logradouro) pairs made `_envelope()` report nothing."""

    TEXTO = (
        "MARIA DE SOUZA PEREIRA\n"
        "AV BRIGADEIRO FARIA LIMA 900\n"
        "CENTRO EMPRESARIAL\n"
        "09876-543 GUARULHOS - SP\n"
        "Central de Atendimento\n"
        "AV. ENGENHEIRO LUIS CARLOS BERRINI, 1500 - CEP: 04571-010 - SAO PAULO - SP\n"
        "Inscricao Estadual: 123.456.789.111\n"
        "I.E.: 111222333 CNPJ Emissor: 12.345.678/0001-99\n"
    )

    def test_the_holders_own_envelope_address_is_read_not_nothing(self):
        r = find_endereco(self.TEXTO)
        assert r.presente, "expected a real address, not `_NADA`"
        assert r.cep == "09876-543"
        assert "FARIA LIMA" in (r.logradouro or "")
        assert r.cidade == "GUARULHOS"
        assert r.uf == "SP"

    def test_the_issuers_own_cep_never_wins_alone_either(self):
        """Sanity check on the fixture itself: the issuer's CEP is a
        DIFFERENT number from the holder's, so a regression that stops
        excluding the issuer would surface as `_NADA` (two distinct
        candidates), not as a silently wrong single answer."""
        r = find_endereco(self.TEXTO)
        assert r.cep != "04571-010"

    def test_a_genuinely_adjacent_cnpj_marker_still_excludes_the_line(self):
        """The ORIGINAL 1-line case must keep working — widening the window
        to 2 must not have been a blind delete of the guard. Keeps the same
        spacer line between the holder's own block and the issuer's as the
        fixture above: a CNPJ marker one line below the issuer's address
        also sits within 2 lines of the holder's own CEP unless the two
        blocks are far enough apart — exactly the shape a real bill has
        (the issuer's footer is nowhere near the holder's mailing window)."""
        texto = (
            "MARIA DE SOUZA PEREIRA\n"
            "AV BRIGADEIRO FARIA LIMA 900\n"
            "CENTRO EMPRESARIAL\n"
            "09876-543 GUARULHOS - SP\n"
            "Central de Atendimento\n"
            "AV. ENGENHEIRO LUIS CARLOS BERRINI, 1500 - CEP: 04571-010 - SAO PAULO - SP\n"
            "CNPJ Emissor: 12.345.678/0001-99\n"
        )
        r = find_endereco(texto)
        assert r.presente
        assert r.cep == "09876-543"

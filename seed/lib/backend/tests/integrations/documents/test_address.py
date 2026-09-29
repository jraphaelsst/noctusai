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
from noctusai_lib.integrations.documents.address import normalizar_tipo_logradouro


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


class TestLogradouroTypeAbbreviationExpansion:
    """G18: bills print `AL`, `R`, `AV`, `ESTR`, etc.; the contract wants the
    full DNE type ("Alameda ..."). Only the LEADING type token is touched —
    the rest of the string, whatever case a bill printed it in, survives
    untouched, and an unrecognised leading token is left exactly as-is."""

    def test_al_expands_to_alameda(self):
        r = find_endereco("AL DAS ACACIAS 45\nCEP: 09876-543 - CAMPINAS/SP\n")
        assert r.logradouro == "Alameda DAS ACACIAS"

    def test_av_expands_to_avenida(self):
        r = find_endereco(
            "AV BRIGADEIRO FARIA LIMA 900\nCEP: 09876-543 - GUARULHOS/SP\n"
        )
        assert r.logradouro == "Avenida BRIGADEIRO FARIA LIMA"

    def test_bare_r_expands_to_rua(self):
        r = find_endereco("R PROF ARTUR RAMOS 123\nCEP: 01454-011 - SAO PAULO/SP\n")
        assert r.logradouro == "Rua PROF ARTUR RAMOS"

    def test_a_leading_full_word_is_never_double_expanded(self):
        r = find_endereco("RUA DAS FLORES 123\nCEP: 01234-567 - SAO PAULO/SP\n")
        assert r.logradouro == "RUA DAS FLORES"

    def test_a_trailing_period_on_the_abbreviation_is_consumed(self):
        r = find_endereco("AV. ENGENHEIRO BERRINI 1500\nCEP: 04571-010 - SAO PAULO/SP\n")
        assert r.logradouro == "Avenida ENGENHEIRO BERRINI"

    def test_an_unknown_leading_token_is_left_exactly_as_printed(self):
        # `normalizar_tipo_logradouro` is pure and total — call it directly
        # so an unrecognised type can be checked without needing a whole
        # comprovante shaped around it.
        assert normalizar_tipo_logradouro("XYZ DAS ACACIAS 45") == "XYZ DAS ACACIAS 45"

    def test_none_and_empty_pass_through(self):
        assert normalizar_tipo_logradouro(None) is None
        assert normalizar_tipo_logradouro("") == ""

    def test_a_brasilia_quadra_code_is_not_touched(self):
        """SQN/SQS/SHIS/SHIN are Brasília's OWN addressing scheme, not an
        abbreviation of anything — deliberately absent from the expansion
        table (see its own comment)."""
        assert normalizar_tipo_logradouro("SQN 408 BLOCO A") == "SQN 408 BLOCO A"


class TestTitularBankSlipLabels:
    """P2 (2026-09-28), measured against 9 real comprovantes: none carried
    `Titular`/`Cliente`/`Nome`/`Destinatário` — the bills that were bank/boleto
    slips instead print `Sacado`/`Pagador`, and every one of the 9 came back
    with `titular=None`. `SACADO`/`PAGADOR` joining `_TITULAR_ROTULO_RE` is
    the label-anchored fix; both read at `alta` exactly like `Titular`/
    `Cliente` do, and neither is confused with the issuer's own
    `Cedente`/`Beneficiário` line (deliberately absent from the whitelist)."""

    def test_sacado_label_is_read_as_titular(self):
        texto = (
            "Sacado: JOAO DA SILVA SAUER\n"
            "Endereco: R PROF ARTUR RAMOS, 123\n"
            "Bairro: JARDIM PAULISTANO   CEP: 01454-011\n"
            "Cidade: SAO PAULO - SP\n"
        )
        r = find_endereco(texto)
        assert r.titular == "JOAO DA SILVA SAUER"
        assert r.confianca == "alta"

    def test_pagador_label_is_read_as_titular(self):
        texto = (
            "Cedente: BANCO XYZ S.A.\n"
            "Pagador: MARIA APARECIDA DE SOUZA\n"
            "Endereco: RUA DAS FLORES, 123 - AP 45\n"
            "Bairro: JARDIM PAULISTA   CEP: 01234-567\n"
            "Cidade: SAO PAULO - SP\n"
        )
        r = find_endereco(texto)
        # The issuer's own "Cedente" line is never mistaken for the holder.
        assert r.titular == "MARIA APARECIDA DE SOUZA"
        assert r.confianca == "alta"

    def test_sacado_label_also_works_in_the_positional_envelope_block(self):
        texto = (
            "Sacado: ANA BEATRIZ LIMA\n"
            "Alameda Santos, 1000, Conj 52 - Cerqueira Cesar - Sao Paulo - SP - CEP 01418-100\n"
        )
        r = find_endereco(texto)
        assert r.titular == "ANA BEATRIZ LIMA"


class TestTitularWeakPositionalHeuristics:
    """P2, round 2 (2026-09-28): re-measured against the same 9 real
    comprovantes after `SACADO`/`PAGADOR` shipped — titular now reads on
    4/9. The 3 remaining misses (party's name genuinely in the text, digits
    masked to `9`/names replaced below) each carry the name in a shape
    neither a same-line label match nor `_ler_bloco`'s own local scan
    covers. Every fixture also carries the issuer's own company name near
    (or, for `test_a_...` below, far from) the street line it would
    otherwise be mistaken for the holder of."""

    def test_889_label_alone_on_its_line_value_on_the_next_with_a_customer_code(self):
        """Text-layer telecom bill: `DESTINATARIO:` carries nothing on its
        own line; the value sits on the line right after, prefixed by a
        customer code (`54321 - `). The issuer's own name/CNPJ two lines up
        must never be mistaken for it."""
        texto = (
            "OPTELECOM TELECOMUNICACOES LTDA\n"
            "CNPJ 12.345.678/0001-90\n"
            "DESTINATARIO:\n"
            "54321 - MARCOS ANTONIO FERREIRA\n"
            "CPF: 123.456.789-00\n"
            "RUA DAS ACACIAS, 45, CASA 2 - CEP: 04571-010 - SAO PAULO - SP\n"
        )
        r = find_endereco(texto)
        assert r.titular == "MARCOS ANTONIO FERREIRA"
        assert r.presente

    def test_888_bare_name_line_immediately_before_cod_cliente(self):
        """Text-layer water bill, column layout: every label is stacked
        first (`CLIENTE:`, `PDE/RGI:`, ...), every value stacked after — the
        holder's name is the bare line directly before `COD.CLIENTE:`."""
        texto = (
            "COMPANHIA DE SANEAMENTO XYZ\n"
            "CNPJ 98.765.432/0001-11\n"
            "CLIENTE:\n"
            "PDE/RGI:\n"
            "HIDROMETRO:\n"
            "LACRE:\n"
            "11223344556677\n"
            "SOR998877665544\n"
            "MARIA HELENA COSTA\n"
            "COD.CLIENTE: 5566778899\n"
            "RUA DOS IPES, 88 - CEP: 12345-678 - CAMPINAS - SP\n"
        )
        r = find_endereco(texto)
        assert r.titular == "MARIA HELENA COSTA"

    def test_882_bare_name_line_immediately_before_a_street_line_no_label_anywhere(self):
        """Vision-read energy bill: the document's LABELLED block (further
        down, with its own `Endereço:`/`CEP:` labels) is what makes the
        address `alta` — but it carries no titular label at all. The
        holder's name only ever appears, unlabelled, directly above a
        SEPARATE positional mailing-window line earlier in the same text —
        the weakest of the three heuristics, so it must not fire on the
        issuer's own name (`ENEL DISTRIBUICAO SAO PAULO`, several lines
        above, structurally shaped exactly like a person's name)."""
        texto = (
            "ENEL DISTRIBUICAO SAO PAULO\n"
            "TIPO DE FORNECIMENTO: RESIDENCIAL\n"
            "\n"
            "PAULO HENRIQUE ARAUJO\n"
            "ALAMEDA CAJA MIRIM, 100 - RES PALM HILLS - COTIA - SP\n"
            "Endereco: ALAMEDA CAJA MIRIM, 100\n"
            "Bairro: RES PALM HILLS   CEP: 06709-050\n"
            "Cidade: COTIA - SP\n"
        )
        r = find_endereco(texto)
        assert r.titular == "PAULO HENRIQUE ARAUJO"
        assert r.confianca == "alta"  # the labelled block still drives the address's own confidence

    def test_893_enel_envelope_block_non_party_is_still_read_correctly(self):
        """P2/893: the holder is a non-party — reading the name at all (so
        social-wiring can flag "comprovante em nome de terceiro") is the
        goal, not filtering it out. Same envelope shape the existing ENEL
        fixture already covers (bare name directly above the street line,
        no blank between them) — re-measured here with fresh masked data."""
        texto = (
            "ENEL DISTRIBUICAO SAO PAULO\n"
            "Rua Atica, 673 - Jardim Brasil - Sao Paulo - SP - CEP 04634-042\n"
            "CNPJ 61.695.227/0001-93 Inscricao Estadual 108.042.323.117\n"
            "CONTA DE ENERGIA ELETRICA\n"
            "REGINA APARECIDA DOS SANTOS\n"
            "RUA DOS CRAVOS 99 CASA 9\n"
            "JARDIM DAS FLORES\n"
            "09999-999 SAO PAULO SP\n"
        )
        r = find_endereco(texto)
        assert r.titular == "REGINA APARECIDA DOS SANTOS"

    def test_a_company_name_far_from_its_own_cnpj_is_never_read_as_titular(self):
        """The weakest heuristic (name directly above a street line, no
        label) is the one most exposed to an issuer's own name passing
        `looks_like_a_name`'s structural check — `_emissor_proximo`'s 2-line
        CNPJ window is the primary guard, but a CNPJ can sit further away
        than that. `_EMISSOR_TOKEN_RE` (LTDA/EIRELI/S.A./...) is the
        defense-in-depth that must still catch it."""
        texto = (
            "OPTELECOM TELECOMUNICACOES LTDA\n"
            "AVENIDA PAULISTA, 1000 - CEP: 01310-100 - SAO PAULO - SP\n"
            "Fatura referente ao mes de servicos prestados\n"
            "Detalhamento de consumo e tarifas aplicadas\n"
            "CNPJ 11.222.333/0001-44\n"
        )
        r = find_endereco(texto)
        assert r.presente
        assert r.titular is None

    def test_beneficiario_and_cedente_labels_are_never_read_as_titular(self):
        """`BENEFICIARIO:`/`CEDENTE:` (the issuer, on a boleto) are
        deliberately absent from every titular label — the SAME-line
        `SACADO:` label a few lines down is what the reader actually uses."""
        texto = (
            "CEDENTE: BANCO XYZ LTDA\n"
            "BENEFICIARIO: BANCO XYZ LTDA\n"
            "SACADO: FERNANDA LIMA COSTA\n"
            "RUA DAS PALMEIRAS, 10 - CEP: 01000-000 - SAO PAULO - SP\n"
        )
        r = find_endereco(texto)
        assert r.titular == "FERNANDA LIMA COSTA"


class TestAddressPresenceRound3:
    """P2, round 3 (2026-09-28): re-measured after round 2 shipped — titular
    now reads on 5/9 (889 joined the 4 already reading), but the remaining 3
    (888, 882, 893) fail ONE STEP EARLIER than titular: `find_endereco`
    returns nothing `presente` at all, so the titular fallback (gated on
    `presente`) never gets a chance to run. Two independent gaps, both
    fixed here: an unlabelled "END:" street label (888, never in the
    `logradouro` whitelist before) paired with an unhyphenated 8-digit CEP
    (already matched by `_CEP_ROTULO_RE` — the hyphen was already optional),
    and a CEP-LESS document (882, 893 — no CEP anywhere at all) whose only
    usable signal is a street line with a número and a trailing city/UF."""

    def test_888_end_label_with_an_unhyphenated_cep_on_the_same_line(self):
        texto = (
            "TIPO DE FORNECIMENTO:\n"
            "CEP:  99999999        END:  AVENIDA MONTE CASTELO, 456 - BAIRRO NOVO\n"
        )
        r = find_endereco(texto)
        assert r.presente
        assert r.cep == "99999-999"
        assert r.logradouro == "AVENIDA MONTE CASTELO"
        assert r.numero == "456"
        assert r.confianca == "alta"

    def test_888_full_shape_combines_the_end_label_fix_with_round_2s_titular_fix(self):
        """The SAME real document (888): a column-stacked block names the
        holder right before `COD.CLIENTE:` (round 2's fix), and a SEPARATE
        block carries the address behind an unhyphenated `CEP:`/`END:` pair
        (this round's fix). Neither alone made the real document read
        end-to-end; both must land together."""
        texto = (
            "CLIENTE:\n"
            "PDE/RGI:\n"
            "HIDROMETRO:\n"
            "LACRE:\n"
            "11223344556677\n"
            "SOR998877665544\n"
            "MARIA HELENA COSTA\n"
            "COD.CLIENTE: 5566778899\n"
            "TIPO DE FORNECIMENTO:\n"
            "CEP:  99999999        END:  AVENIDA MONTE CASTELO, 456 - BAIRRO NOVO\n"
        )
        r = find_endereco(texto)
        assert r.presente
        assert r.cep == "99999-999"
        assert r.titular == "MARIA HELENA COSTA"
        assert r.confianca == "alta"

    def test_882_cep_less_street_line_with_number_and_trailing_city_uf(self):
        """Vision-read, no CEP anywhere in the document at all. The street
        line carries a número and a trailing "- CIDADE - UF", with a stray
        trailing date token ("12/25") that must never leak into `uf`."""
        texto = (
            "ENEL DISTRIBUICAO SAO PAULO\n"
            "TIPO DE FORNECIMENTO: RESIDENCIAL\n"
            "\n"
            "PAULO HENRIQUE ARAUJO\n"
            "ALAMEDA CAJA MIRIM, 100 - RES PALM HILLS - COTIA - SP 12/25\n"
        )
        r = find_endereco(texto)
        assert r.presente
        assert r.cep is None
        assert r.logradouro == "ALAMEDA CAJA MIRIM"
        assert r.numero == "100"
        assert (r.cidade, r.uf) == ("COTIA", "SP")
        assert r.confianca == "baixa"
        assert r.titular == "PAULO HENRIQUE ARAUJO"

    def test_882_real_trailing_reference_longer_than_month_year(self):
        """The real 882 vision read ends the street line in a 2/5-digit
        reference ("SP 99/99999"), followed by a blank line and "Cod. Cliente"."""
        texto = (
            "Tipo de fornecimento: RESIDENCIAL\n"
            "\n"
            "PAULO HENRIQUE ARAUJO\n"
            "ALAMEDA CAJA MIRIM, 100 - RES PALM HILLS - COTIA - SP 06/71234\n"
            "\n"
            "Cod. Cliente: 1234567890\n"
        )
        r = find_endereco(texto)
        assert r.presente
        assert r.cep is None
        assert (r.logradouro, r.numero) == ("ALAMEDA CAJA MIRIM", "100")
        assert (r.cidade, r.uf) == ("COTIA", "SP")
        assert r.titular == "PAULO HENRIQUE ARAUJO"

    def test_893_cep_less_envelope_non_party_still_reads(self):
        """P2/893: no CEP anywhere either; same no-CEP shape as 882. The
        holder is a non-party — reading the name at all (so social-wiring
        can flag "comprovante em nome de terceiro") is the goal."""
        texto = (
            "ENEL DISTRIBUICAO SAO PAULO\n"
            "TIPO DE FORNECIMENTO: RESIDENCIAL\n"
            "\n"
            "REGINA APARECIDA DOS SANTOS\n"
            "RUA DOS CRAVOS, 99 - JARDIM DAS FLORES - SAO PAULO - SP 03/26\n"
        )
        r = find_endereco(texto)
        assert r.presente
        assert r.cep is None
        assert (r.cidade, r.uf) == ("SAO PAULO", "SP")
        assert r.titular == "REGINA APARECIDA DOS SANTOS"

    def test_a_street_line_with_no_city_uf_trailer_still_yields_nothing(self):
        """The multi-line CEP-less shape (street, bairro, city/UF each on
        their OWN line, no CEP anywhere) is deliberately NOT read — the
        city/UF trailer must be on the SAME line as the street. Pins the
        pre-existing `test_no_cep_no_address` contract unchanged."""
        texto = "RUA DAS FLORES 123\nJARDIM PAULISTA\nSAO PAULO SP\n"
        assert not find_endereco(texto).presente

    def test_a_cep_less_issuer_address_is_never_read_as_the_holders(self):
        """No CEP anywhere, AND the only street line is the issuer's own —
        `_emissor_proximo` (CNPJ within 2 lines) excludes it exactly like it
        already does for the CEP-anchored paths."""
        texto = (
            "OPTELECOM TELECOMUNICACOES LTDA\n"
            "AVENIDA PAULISTA, 1000 - SAO PAULO - SP\n"
            "CNPJ 11.222.333/0001-44\n"
        )
        r = find_endereco(texto)
        assert not r.presente
        assert r.titular is None

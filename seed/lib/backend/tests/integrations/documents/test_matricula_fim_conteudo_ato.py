"""`fim_conteudo_ato` — registry boilerplate trailing an act is not the act.

All names and numbers are invented.
"""
from __future__ import annotations

from noctusai_lib.integrations.documents import fim_conteudo_ato, segment_matricula_atos

ASSIN = (
    "O Oficial Substituto, ____________ Beltrano Ficticio\n"
    "Oficial, __________________ Ciclano Inventado\n"
)
RODAPE = (
    "M. 99999 - Página 3/3 - PROT. 11.222\n"
    "CERTIDÃO DIGITAL\n"
    "CERTIFICO E DOU FÉ, (Protocolo nº 11.222) que a presente é cópia.\n"
    "Mat.99999 - PROTOCOLO: 11.222\n"
    "Emolumentos: R$: 45,88\nEstado: R$: 13,04\nTotal: R$: 76,98\n"
    "Cidadefiticia-SP, - 12 de março de 2026\n"
    "O PRAZO DE VALIDADE DESTA CERTIDÃO É DE 30 (TRINTA) DIAS.\n"
)
ATO1 = "AV-1/99.999 - Em 01 de abril de 2014. CONSTRUCAO de casa. (Protocolo n° 30.513 de 31/03/2014).\n"
ATO2 = "AV-2/99.999 - Em 02 de maio de 2015. CASAMENTO dos proprietarios. (Protocolo n° 40.000 de 01/05/2015).\n"


def _quotes(texto):
    return [
        texto[a.start : fim_conteudo_ato(texto, a.start, a.end)]
        for a in segment_matricula_atos(texto)
        if a.kind != "abertura"
    ]


def test_signature_lines_after_midpage_act_are_trimmed():
    t = "IMOVEL: lote 1.\n" + ATO1 + ASSIN + ATO2 + ASSIN
    q1, q2 = _quotes(t)
    assert q1.rstrip().endswith("31/03/2014).")
    assert q2.rstrip().endswith("01/05/2015).")


def test_last_act_certidao_footer_is_trimmed():
    t = "IMOVEL: lote 1.\n" + ATO1 + ASSIN + "\n" + RODAPE
    (q,) = _quotes(t)
    assert q.rstrip().endswith("(Protocolo n° 30.513 de 31/03/2014).")
    assert "CERTIFICO" not in q and "Emolumentos" not in q


def test_footer_without_page_header_or_signature():
    t = ATO1 + "CERTIDÃO DIGITAL\nCERTIFICO E DOU FÉ, x\n"
    (q,) = _quotes(t)
    assert q.rstrip().endswith("31/03/2014).")


def test_mid_act_page_header_keeps_real_continuation():
    t = (
        "AV-1/99.999 - Em 01 de abril de 2014. CONSTRUCAO de casa com\n"
        "M. 99999 - Página 2/3 - PROT. 11.222\n"
        "area de 100m2. (Protocolo n° 30.513 de 31/03/2014).\n" + ASSIN
    )
    (q,) = _quotes(t)
    assert "Página 2/3" in q  # page furniture is the ruido layer's job
    assert q.rstrip().endswith("31/03/2014).")


def test_no_trailing_boilerplate_is_noop():
    t = ATO1.rstrip("\n")
    assert fim_conteudo_ato(t, 0, len(t)) == len(t)

"""Document-level numbers: the CNH Nº REGISTRO and the certidão RCPN matrícula.

Sibling of `rg.py`/`cpf.py`: pure, label-anchored, and validated by the ONE
identifier module (`primitives.identificador`). A value that fails its HARD
rule is not emitted; a SOFT finding (an unverified DV) rides as an aviso
code, never as a refusal (owner rule 2026-10-13: validation only accepts or
flags — nothing is computed and appended).
"""
from __future__ import annotations

import re
from datetime import date
from typing import Optional

from noctusai_lib.integrations.documents.text import fold_upper_collapsed
from noctusai_lib.primitives import identificador as _idf

#: The CNH field 5 label: "Nº REGISTRO", "N° REGISTRO", "5 NO REGISTRO",
#: "REGISTRO". The espelho number (vertical, on the card edge) and the
#: RENACH (`SP123456789`) are different numbers and are refused by label.
_REGISTRO_CNH_RE = re.compile(
    r"(?<![A-Z])(?P<rotulo>(?:N[O°º]?\.?\s*)?REGISTRO)(?!\s+(?:GERAL|NACIONAL|CIVIL|DE\s+IMOVEIS))"
    r"\s*[:.\-]?\s*(?P<valor>(?:\d\s?){11})(?!\d)"
)
_NAO_REGISTRO_CNH = re.compile(r"(?:RENACH|ESPELHO|N[O°º]?\s*DO\s+ESPELHO)\W*$")


def find_registro_cnh(text: str) -> tuple[Optional[str], str, Optional[str]]:
    """The CNH Nº REGISTRO: `(valor, confianca, rotulo)`.

    `alta` only when labelled AND the check digits verify
    (`identificador.validar_cnh_registro`); a DV failure is `nenhuma` (a
    misread, never stored). Two different valid labelled readings are
    absence, never a vote.
    """
    norm = fold_upper_collapsed(text or "")
    achados: list[tuple[str, str]] = []
    for m in _REGISTRO_CNH_RE.finditer(norm):
        if _NAO_REGISTRO_CNH.search(norm[max(0, m.start() - 24) : m.start()]):
            continue
        digitos = re.sub(r"\s", "", m.group("valor"))
        if _idf.validar_cnh_registro(digitos).valido:
            achados.append((digitos, " ".join(m.group("rotulo").split())))
    if not achados or len({v for v, _ in achados}) != 1:
        return (None, "nenhuma", None)
    return (achados[0][0], "alta", achados[0][1])


_MATRICULA_RE = re.compile(
    r"\bMATRICULA\b\s*(?:N[O°º]?\.?)?\s*[:\-]?\s*(?P<valor>(?:\d[\s.\-]{0,2}){32})(?!\d)"
)

#: `tipo_documento` -> `identificador.TIPO_LIVRO_RCPN` key.
_TIPO_CERTIDAO = {
    "CERTIDAO_CASAMENTO": "casamento",
    "CERTIDAO_NASCIMENTO": "nascimento",
}


def find_matricula_certidao(
    text: str,
    *,
    tipo_documento: Optional[str] = None,
    data_emissao: Optional[date] = None,
) -> tuple[Optional[str], str, tuple[str, ...]]:
    """The certidão's 32-digit RCPN matrícula: `(valor, confianca, avisos)`.

    `valor` is the printed digit run (spaces/dots dropped — the matrícula has
    no punctuation of its own). Emitted only when the structure validates
    (positions 9-10 = "55", tipoLivro matches the declared certidão type,
    ano ≤ emission year). A failed structure is `(None, "nenhuma",
    ("matricula_<motivo>",))` so the reason is visible; the DV is SOFT
    (`matricula_dv_nao_confere`).
    """
    norm = fold_upper_collapsed(text or "")
    tipo = _TIPO_CERTIDAO.get((tipo_documento or "").upper())
    for m in _MATRICULA_RE.finditer(norm):
        digitos = re.sub(r"\D", "", m.group("valor"))
        if len(digitos) != 32:
            continue
        r = _idf.validar_matricula_rcpn(digitos, tipo_certidao=tipo, data_emissao=data_emissao)
        if not r.valido:
            return (None, "nenhuma", (f"matricula_{r.motivo}",))
        return (digitos, "alta", tuple(f"matricula_{a}" for a in r.avisos))
    return (None, "nenhuma", ())


__all__ = ["find_matricula_certidao", "find_registro_cnh"]

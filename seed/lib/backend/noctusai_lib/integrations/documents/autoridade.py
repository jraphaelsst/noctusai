"""Field authority per document type: which fields a document may EMIT.

The owner's definition of done (2026-10-13): "extract the correct data from
the correct document file and store it as the corresponding data field".
The identity extractor used to be type-agnostic — every finder ran on every
document — so a document "extracted" fields it is not the authoritative
source for (an RNE landed in `rg`, a certidão de casamento's grammar became a
seller's `genero`, a profissão was lifted off a decades-old certidão).

This table is THE declaration. `real.LadderIdentityExtractor._ler` consults
it BEFORE running each finder: a field outside the declared type's set is
never read, and so never emitted.

🔴 CAPACIDADES IS NOT THIS TABLE. `capacidades.CAPACIDADES` is the product-
facing UPPER BOUND a product's `Fonte.campos` may claim (still the broad
`_IDENTIDADE_COMPLETA` for the identity family). Narrowing it is a product-
side change (social-wiring `proveniencia.fontes` claims those fields) —
NOC-REMEDIATE[autoridade-capacidades-sync]: narrow `CAPACIDADES` rg/cnh/
cin/certidão entries + `fontes.FONTES_REGISTRO` campos to this table, owner:
card_hub proveniencia.

A type ABSENT from the table (cpf card, comprovante, ficha, an undeclared
`tipo_documento`) keeps the historical type-agnostic read: `None` from
`campos_autorizados` means "no authority rule", never "nothing allowed".

Field vocabulary is `IdentityFields`' attribute names (`rg` carries
`rg_orgao`; `rne` carries `rne_orgao`), plus the group fields `endereco` /
`conjuges`.

NOT MODELLED AS FIELDS (yet): filiação (nome_mae/nome_pai) and
naturalidade — `IdentityFields` carries neither; the printed filiação is
read by `legibilidade` only as a cross-check.
"""
from __future__ import annotations

from typing import Optional

from noctusai_lib.integrations.documents.text import strip_accents_upper

#: Normalised `tipo_documento` -> the fields that type is authoritative for.
AUTORIDADE: dict[str, frozenset[str]] = {
    # RG (SSP) — the state cédula. Prints no sexo, no nacionalidade (the
    # consumer derives a suggestion from the issuer), no estado civil.
    # `rne`: an RNE card uploaded under "rg" is still emitted as what it IS
    # (never into `rg`).
    "RG": frozenset({"nome", "rg", "rne", "data_nascimento", "data_emissao", "cpf"}),
    # CIN — the number IS the CPF (so no separate `rg`); prints SEXO and
    # NACIONALIDADE.
    "CIN": frozenset({"nome", "cpf", "data_nascimento", "genero", "nacionalidade", "data_emissao"}),
    # CNH — RG + órgão + UF read together off the 4c box; a foreigner's box
    # holds an RNE (-> `rne`). Nº REGISTRO (11 digits, DV) — never the
    # espelho nor the RENACH. Prints no SEXO.
    "CNH": frozenset({
        "nome", "cpf", "data_nascimento", "rg", "rne", "registro_cnh",
        "nacionalidade", "data_emissao",
    }),
    # RNE / RNM / CRNM — the foreign national's own card. Prints SEXO.
    "RNE": frozenset({"nome", "rne", "nacionalidade", "data_nascimento", "genero", "data_emissao"}),
    # Certidão de casamento — both spouses (names before/after), the couple's
    # facts, each spouse's nacionalidade/data de nascimento, the matrícula.
    # 🔴 `genero` is NOT printed: only a DERIVED value (grammatical agreement,
    # `IdentityFields.genero_derivado=True`) may ride, never as a reading.
    # No CPF/RG (not the authoritative source), no profissão, no endereço
    # (the cartório's address is nobody's home).
    "CERTIDAO_CASAMENTO": frozenset({
        "conjuges", "nome", "data_casamento", "regime_bens", "estado_civil",
        "nacionalidade", "data_nascimento", "genero", "matricula_certidao",
        "data_emissao",
    }),
    # Certidão de nascimento — prints SEXO; the averbação margin carries a
    # later estado civil.
    "CERTIDAO_NASCIMENTO": frozenset({
        "nome", "data_nascimento", "genero", "estado_civil", "matricula_certidao",
        "data_emissao",
    }),
}

#: Synonyms a caller may declare for the same document.
_SINONIMOS = {
    "CRNM": "RNE",
    "RNM": "RNE",
    "CEDULA_IDENTIDADE": "RG",
}

#: Types whose gender is never printed — a gender here is DERIVED or absent.
GENERO_SO_DERIVADO: frozenset[str] = frozenset({"CERTIDAO_CASAMENTO"})


def tipo_normalizado(tipo_documento: Optional[str]) -> Optional[str]:
    """`"certidao_casamento"` -> `"CERTIDAO_CASAMENTO"`, synonyms folded."""
    if not tipo_documento:
        return None
    t = strip_accents_upper(tipo_documento.strip()).replace(" ", "_").replace("-", "_")
    return _SINONIMOS.get(t, t)


def campos_autorizados(tipo_documento: Optional[str]) -> Optional[frozenset[str]]:
    """The fields `tipo_documento` may emit, or `None` (no rule: read all)."""
    t = tipo_normalizado(tipo_documento)
    return AUTORIDADE.get(t) if t else None


def autorizado(tipo_documento: Optional[str], campo: str) -> bool:
    """May a document of this type emit `campo`?"""
    campos = campos_autorizados(tipo_documento)
    return campos is None or campo in campos


__all__ = [
    "AUTORIDADE",
    "GENERO_SO_DERIVADO",
    "autorizado",
    "campos_autorizados",
    "tipo_normalizado",
]

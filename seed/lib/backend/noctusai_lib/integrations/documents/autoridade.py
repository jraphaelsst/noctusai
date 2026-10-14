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

`PRECEDENCIA` (owner rule 2026-10-14) is the companion table: among the
types that may emit a field, their ORDER of authority — which document the
stored value should be sourced from (`posto` / `mais_autoritativo`).

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


#: 🔴 SOURCE PRECEDENCE (owner rule 2026-10-14, prod deal 876) — per FIELD,
#: the document types in order of authority, as TIERS (types within one tier
#: tie). `AUTORIDADE` says which fields a type may EMIT at all; this says,
#: among the types that do, WHICH ONE the stored value should be sourced
#: from. The owner's definition of done is "the correct value, extracted from
#: the correct document": a ficha cadastral read before the certidão de
#: casamento must hand `estado_civil` over to the certidão when the certidão
#: reads the same fact — and conflict (never overwrite) when it reads a
#: different one.
#:
#: Field vocabulary: `IdentityFields`' names (`nome`, `rg`, `rg_orgao`, ...),
#: plus the group `endereco` and the ficha-only `profissao`/`email`. A type
#: absent from a field's tiers is UNRANKED for it (a bureau feed, a
#: matrícula, an undeclared type): `posto()` returns `None` and no precedence
#: decision is ever made against or for it.
PRECEDENCIA: dict[str, tuple[frozenset[str], ...]] = {
    "estado_civil": (
        frozenset({"CERTIDAO_CASAMENTO"}),
        frozenset({"CERTIDAO_NASCIMENTO"}),
        frozenset({"FICHA_CADASTRAL"}),
    ),
    "regime_bens": (
        frozenset({"CERTIDAO_CASAMENTO", "PACTO_ANTENUPCIAL"}),
        frozenset({"FICHA_CADASTRAL"}),
    ),
    "data_casamento": (
        frozenset({"CERTIDAO_CASAMENTO"}),
        frozenset({"FICHA_CADASTRAL"}),
    ),
    # A CNH "estrangeiro" is never read as a nationality (the seed's CNH
    # rung); a CNH that does print one ranks with the CIN. The owner's
    # ladder also names the certidão de nascimento and the RG, but neither
    # may EMIT `nacionalidade` (`AUTORIDADE` above: the RG prints none — its
    # issuer-derived value is a suggestion never written to the record — and
    # the birth certificate's is not read), so they hold no tier here: a
    # tier never names a type that cannot supply the field
    # (`test_autoridade_por_tipo.TestPrecedencia`). Add them back the day
    # `AUTORIDADE` lets them read it.
    "nacionalidade": (
        frozenset({"RNE"}),
        frozenset({"CERTIDAO_CASAMENTO"}),
        frozenset({"CIN", "CNH"}),
        frozenset({"FICHA_CADASTRAL"}),
    ),
    "nome": (
        frozenset({"RG", "CIN", "CNH", "RNE"}),
        frozenset({"CERTIDAO_CASAMENTO", "CERTIDAO_NASCIMENTO"}),
        frozenset({"FICHA_CADASTRAL"}),
    ),
    "cpf": (
        frozenset({"CIN", "CNH", "CPF", "RG"}),
        frozenset({"FICHA_CADASTRAL"}),
    ),
    "rg": (
        frozenset({"RG"}),
        frozenset({"CNH"}),
        frozenset({"FICHA_CADASTRAL"}),
    ),
    "rg_orgao": (
        frozenset({"RG"}),
        frozenset({"CNH"}),
        frozenset({"FICHA_CADASTRAL"}),
    ),
    # Owner decision 2026-10-13 ("ficha prevalece"): the party's own
    # declaration outranks a utility bill, which only CONFIRMS it.
    "endereco": (
        frozenset({"FICHA_CADASTRAL"}),
        frozenset({"COMPROVANTE_ENDERECO"}),
    ),
    "profissao": (frozenset({"FICHA_CADASTRAL"}),),
    "email": (frozenset({"FICHA_CADASTRAL"}),),
}


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


def posto(campo: str, tipo_documento: Optional[str]) -> Optional[int]:
    """`tipo_documento`'s authority tier for `campo` (0 = most authoritative),
    or `None` when the type is unranked for that field (see `PRECEDENCIA`)."""
    t = tipo_normalizado(tipo_documento)
    if not t:
        return None
    for i, tier in enumerate(PRECEDENCIA.get(campo, ())):
        if t in tier:
            return i
    return None


def mais_autoritativo(
    campo: str, tipo_proposto: Optional[str], tipo_atual: Optional[str]
) -> bool:
    """Does a `tipo_proposto` reading of `campo` STRICTLY outrank the
    `tipo_atual` source behind the stored value? `False` whenever either side
    is unranked (no rule ≠ "outranks") or both share a tier."""
    novo = posto(campo, tipo_proposto)
    atual = posto(campo, tipo_atual)
    return novo is not None and atual is not None and novo < atual


__all__ = [
    "AUTORIDADE",
    "GENERO_SO_DERIVADO",
    "PRECEDENCIA",
    "autorizado",
    "campos_autorizados",
    "mais_autoritativo",
    "posto",
    "tipo_normalizado",
]

"""Social-wiring's one door to the canonical identifier registry.

OWNER RULE (2026-10-01): the canonical reference for every document number /
id / protocol is its PUNCTUATED form (`KB § PATTERNS/common/canonical-
identifiers.md`). The registry itself is the seed's
(`noctusai_lib.primitives.identificador`); this module is the PRODUCT-side
policy on top of it, so the ~15 write paths and the search surfaces make the
same call the same way instead of each hand-rolling one:

- `para_gravar` — what a write path may store for a value claiming to be an
  identifier of type X: the canonical punctuated form when it fits; the
  value AS READ (never rewritten) when it does not fit but claims nothing
  else; NOTHING when it is a valid instance of ANOTHER type (a CPF sitting
  in an RG field) — with the reason, so a human sees it.
- `iguais` — "same identifier?" for the conflict machinery. True only when
  the registry proves it (format-only differences, an RG with and without
  its check digit); `None`/`False` stay conflicts.
- `chave` / `needle_busca` — the search key, for BOTH needle and haystack
  (`feedback_canonicalizing_a_value_breaks_search`), floored at
  `CHAVE_BUSCA_MIN`.
- `cns_do_cartorio` — the cartório CNS inside free text, for the
  `numero_registro_imoveis` equivalence (text vs `11991-7`).

NEVER invents data (the registry's rule) and never raises on a bad value:
a value that does not fit is data to show, not an error to throw.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from noctusai_lib.primitives import identificador as ident
from noctusai_lib.primitives.identificador import CHAVE_BUSCA_MIN

# ─── campo → registry type ──────────────────────────────────────────────────

#: `clientes` columns → registry type. `cpf` is the CPF number; `rg` is read
#: with the UF of its own órgão expedidor (see `uf_do_orgao`).
TIPO_POR_CAMPO_CLIENTE: dict[str, str] = {
    "cpf": "cpf",
    "rg": "rg",
    "rg_orgao_expedidor": "orgao_expedidor",
    "endereco_cep": "cep",
}

#: `imovel_dados` columns → registry type. `numero_registro_imoveis` holds the
#: cartório (a name, a CNS, or both in one string): it is compared through
#: `cns_do_cartorio`, never rewritten.
TIPO_POR_CAMPO_IMOVEL: dict[str, str] = {
    "numero_matricula": "matricula_imovel",
    "prefeitura_cadastro_imobiliario": "inscricao_municipal",
}

#: `<entidade>_campo_conflitos.campo` → registry type, for the conflict /
#: display surfaces that only know the campo name.
TIPO_POR_CAMPO: dict[str, str] = {
    **TIPO_POR_CAMPO_CLIENTE,
    **TIPO_POR_CAMPO_IMOVEL,
    "cnpj": "cnpj",
}


def uf_do_orgao(orgao: Any) -> Optional[str]:
    """The UF of an órgão expedidor reading (`SSP/SP`, `IIRGD` → `SP`), or
    None when the text carries none. Feeds `ler('rg', ..., uf=...)` so an RG
    issued outside SP is never forced into the SP mask."""
    if orgao is None or not str(orgao).strip():
        return None
    canon = ident.canonico("orgao_expedidor", orgao)
    if canon and "/" in canon:
        return canon.rsplit("/", 1)[1]
    return None


# ─── write side ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Gravacao:
    """What a write path may do with one identifier reading.

    `valor` — the text to store, or None when nothing should be written.
    `canonico` — `valor` is the punctuated canonical form (it FITS the type).
    `aceito` — False only when the value is rejected outright (another
    type's identifier); a value that merely does not fit is still accepted,
    as read, and flagged by `motivo`.
    `motivo` — the registry's stable code, or `<outro_tipo>_no_campo_<tipo>`.
    """

    valor: Optional[str]
    aceito: bool
    canonico: bool
    motivo: str
    tipo_detectado: Optional[str] = None

    @property
    def rejeitado_por_tipo(self) -> bool:
        return self.tipo_detectado is not None and not self.aceito


def _texto(valor: Any) -> str:
    return "" if valor is None else str(valor).strip()


def para_gravar(
    tipo: str,
    valor: Any,
    *,
    uf: Optional[str] = None,
    municipio: Optional[str] = None,
    ibge: Optional[str] = None,
    cpf_proprio: Any = None,
) -> Gravacao:
    """Decide what to store for `valor` read as identifier `tipo`.

    `cpf_proprio` is the CPF of the SAME person: a CIN prints the CPF number
    AS the identity number (contract 08 — `RG 448.864.938-66`), so an `rg`
    reading equal to its holder's own CPF is a legitimate RG, stored in the
    CPF's canonical form — the one case where a valid CPF belongs in the RG
    field.
    """
    texto = _texto(valor)
    if not texto:
        return Gravacao(None, False, False, "vazio")
    leitura = ident.ler(tipo, texto, uf=uf, municipio=municipio, ibge=ibge)
    # `desconhecido_mantido` (an órgão expedidor the registry does not know)
    # comes back upper-cased and accent-stripped — a comparison form, not a
    # shape the text FITS — so it is never written over what was read.
    if leitura.canonico and leitura.motivo != "desconhecido_mantido":
        return Gravacao(leitura.canonico, True, True, leitura.motivo)
    if leitura.tipo_detectado:
        if (
            tipo == "rg"
            and leitura.tipo_detectado in ("cpf", "cin")
            and cpf_proprio
            and ident.equivalentes("cpf", texto, cpf_proprio) is True
        ):
            return Gravacao(ident.canonico("cpf", texto), True, True, "cin_igual_ao_cpf")
        return Gravacao(
            None, False, False,
            f"{leitura.tipo_detectado}_no_campo_{tipo}", leitura.tipo_detectado,
        )
    return Gravacao(texto, True, False, leitura.motivo)


def cabe(tipo: str, valor: Any, **ctx: Optional[str]) -> bool:
    """Does `valor` FIT identifier `tipo` (shape and, where it exists, the
    check digit)?"""
    return bool(_texto(valor)) and ident.ler(tipo, valor, **ctx).cabe


def canonico_ou_bruto(tipo: str, valor: Any, **ctx: Optional[str]) -> Optional[str]:
    """`valor` in canonical form when it fits, else as read (trimmed), else
    None for empty — the display / compare form (never a destructive rewrite
    of what a human typed)."""
    texto = _texto(valor)
    if not texto:
        return None
    return ident.canonico(tipo, texto, **ctx) or texto


# ─── compare side ───────────────────────────────────────────────────────────


def iguais(tipo: str, a: Any, b: Any, **ctx: Optional[str]) -> bool:
    """True iff the registry PROVES `a` and `b` are the same identifier.
    Undecidable (`None`) and different (`False`) are both "not proven" — the
    conflict machinery keeps treating them as a disagreement."""
    if not _texto(a) or not _texto(b):
        return False
    return ident.equivalentes(tipo, a, b, **ctx) is True


def cns_do_cartorio(valor: Any) -> Optional[str]:
    """The cartório CNS (`11991-7`) of a `numero_registro_imoveis` reading:
    the CNS printed inside a free-text name, or the value itself when it IS a
    bare CNS."""
    texto = _texto(valor)
    if not texto:
        return None
    return ident.extrair_cns(texto) or ident.canonico("cns_cartorio", texto)


def cartorios_iguais(a: Any, b: Any) -> Optional[bool]:
    """Same cartório? Decided by CNS when BOTH readings carry one (the name
    text varies wildly: `SERVENTIA DO REGISTRO DE IMÓVEIS de Cotia - CNS:
    11991-7` vs `11991-7`). One CNS missing → None (text alone cannot prove
    a difference)."""
    ca, cb = cns_do_cartorio(a), cns_do_cartorio(b)
    if ca is None or cb is None:
        return None
    return ca == cb


# ─── search side ────────────────────────────────────────────────────────────


def chave(tipo: str, valor: Any, **ctx: Optional[str]) -> Optional[str]:
    """Search key: canonical alnum when the value parses, RAW alnum
    otherwise — apply to the needle AND the haystack."""
    return ident.chave_busca(tipo, valor, **ctx)


def documentos_chave(pares: list[tuple[str, Any, dict]]) -> Optional[str]:
    """Python twin of the `documentos_chave` TRIGGER column (migration 187):
    the space-joined `chave` of each `(tipo, valor, ctx)` — what the database
    stores beside the row so a search can match the number a screen RENDERS.
    Fixtures derive the column through this (mocks have no triggers —
    `feedback_canonicalizing_a_value_breaks_search`, leg 4)."""
    chaves = [k for tipo, valor, ctx in pares if (k := chave(tipo, valor, **ctx))]
    return " ".join(chaves) or None


def documentos_chave_cliente(row: dict) -> Optional[str]:
    """`clientes.documentos_chave` for a row (cpf + rg, RG read with its
    órgão's UF)."""
    uf = uf_do_orgao(row.get("rg_orgao_expedidor"))
    return documentos_chave([
        ("cpf", row.get("cpf"), {}),
        ("rg", row.get("rg"), {"uf": uf} if uf else {}),
    ])


def documentos_chave_imovel(row: dict, municipio: Optional[str] = None) -> Optional[str]:
    """`imovel_dados.documentos_chave` for a row (matrícula + inscrição
    municipal read in its município's mask)."""
    return documentos_chave([
        ("matricula_imovel", row.get("numero_matricula"), {}),
        (
            "inscricao_municipal", row.get("prefeitura_cadastro_imobiliario"),
            {"municipio": municipio} if municipio else {},
        ),
    ])


def needle_chave(termo: Any) -> Optional[str]:
    """The key a typed search term is matched by against `*_chave` columns:
    alphanumerics of the term, uppercased, accent-folded — `None` when the
    term is too short (`CHAVE_BUSCA_MIN`) or has no digit (a name fragment
    is never a document number, and `joao` must not scan the key columns).

    The columns hold `chave(...)` values (alnum, upper), so a RAW needle
    keyed the same way finds a rendered value (`412.954.238-98`), a bare
    one (`41295423898`) and a fragment (`412954`) alike. A needle that is a
    complete identifier of some type is keyed through its canonical form
    first — `30128742` (an RG without DV) then matches the stored
    `30.128.742-9` row (`301287429`)."""
    texto = _texto(termo)
    if not texto:
        return None
    candidato: Optional[str] = None
    for tipo in ("cpf", "cnpj", "rg", "matricula_imovel"):
        c = ident.canonico(tipo, texto)
        if c:
            candidato = ident.chave_busca(tipo, texto)
            break
    k = candidato or ident.chave_busca("cpf", texto)  # non-fitting → RAW alnum
    if not k or len(k) < CHAVE_BUSCA_MIN or not any(ch.isdigit() for ch in k):
        return None
    return k


def chaves_do_needle(termo: Any) -> list[str]:
    """Every key worth searching for `termo`: its RAW alnum run (a fragment
    the user typed, or a value stored raw) AND, when it parses as a complete
    identifier, the canonical key — so searches stay STRICTLY ADDITIVE to a
    raw substring pass."""
    texto = _texto(termo)
    if not texto:
        return []
    cru = ident.chave_busca("cpf", texto)  # not a valid CPF ⇒ RAW alnum
    canon = needle_chave(texto)
    out: list[str] = []
    for k in (cru, canon):
        if k and len(k) >= CHAVE_BUSCA_MIN and any(ch.isdigit() for ch in k) and k not in out:
            out.append(k)
    return out


__all__ = [
    "CHAVE_BUSCA_MIN",
    "Gravacao",
    "TIPO_POR_CAMPO",
    "TIPO_POR_CAMPO_CLIENTE",
    "TIPO_POR_CAMPO_IMOVEL",
    "cabe",
    "canonico_ou_bruto",
    "cartorios_iguais",
    "chave",
    "chaves_do_needle",
    "documentos_chave",
    "documentos_chave_cliente",
    "documentos_chave_imovel",
    "cns_do_cartorio",
    "iguais",
    "needle_chave",
    "para_gravar",
    "uf_do_orgao",
]

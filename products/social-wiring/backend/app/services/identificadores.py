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

import re
import unicodedata
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

#: Every `imovel_dados` column a write path stores canonical: the identifiers
#: above plus the hand-typed address CEP (`endereco_manual_cep`, migration 159).
TIPO_POR_CAMPO_ESCRITA_IMOVEL: dict[str, str] = {
    **TIPO_POR_CAMPO_IMOVEL,
    "endereco_manual_cep": "cep",
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
    #: `ident.rg_anomalia` code when an AUTOMATIC write was refused for a
    #: value of the wrong kind that no other type's check digit proves
    #: (`forma_de_cpf`, `truncado`).
    anomalia: Optional[str] = None

    @property
    def rejeitado_por_tipo(self) -> bool:
        return self.tipo_detectado is not None and not self.aceito

    @property
    def recusado_por_anomalia(self) -> bool:
        return self.anomalia is not None and not self.aceito

    @property
    def recusado(self) -> bool:
        """Refused outright — by another type's identifier OR by an anomaly."""
        return self.rejeitado_por_tipo or self.recusado_por_anomalia


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
    extracao: bool = False,
) -> Gravacao:
    """Decide what to store for `valor` read as identifier `tipo`.

    `cpf_proprio` is the CPF of the SAME person: a CIN prints the CPF number
    AS the identity number (contract 08 — `RG 448.864.938-66`), so an `rg`
    reading equal to its holder's own CPF is a legitimate RG, stored in the
    CPF's canonical form — the one case where a valid CPF belongs in the RG
    field.

    `extracao=True` marks a MACHINE reading (OCR / vision / text parser): there
    an RG that is CPF-shaped or truncated (`ident.rg_anomalia`) is refused —
    to be flagged for a human, never stored as read. A human-typed value
    (`extracao=False`) is authoritative and keeps the lenient "as read" path.
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
    if tipo == "rg" and extracao:
        anomalia = ident.rg_anomalia(texto, uf=uf)
        if anomalia:
            return Gravacao(None, False, False, f"rg_{anomalia}", None, anomalia)
    return Gravacao(texto, True, False, leitura.motivo)


def cabe(tipo: str, valor: Any, **ctx: Optional[str]) -> bool:
    """Does `valor` FIT identifier `tipo` (shape and, where it exists, the
    check digit)?"""
    return bool(_texto(valor)) and ident.ler(tipo, valor, **ctx).cabe


def tipo_do_documento_pessoa(valor: Any) -> Optional[str]:
    """`'cpf'` / `'cnpj'` for a free-text CPF-or-CNPJ field (a favorecido's
    `cpf_cnpj`), told by the number's own length (11 / 14 alphanumerics) —
    None when it is neither (shown and kept as typed)."""
    tamanho = len("".join(ch for ch in _texto(valor) if ch.isalnum()))
    return {11: "cpf", 14: "cnpj"}.get(tamanho)


def canonico_cpf_cnpj(valor: Any) -> Optional[str]:
    """A free-text CPF-or-CNPJ in its canonical punctuated form when it FITS;
    as typed (trimmed) when it does not; None when empty."""
    texto = _texto(valor)
    if not texto:
        return None
    tipo = tipo_do_documento_pessoa(texto)
    return canonico_ou_bruto(tipo, texto) if tipo else texto


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


# ─── refinement (one reading = the other + the detail it lacked) ───────────
#
# Owner directive (2026-10-03, P3/P4 live test loop): a correct fresh read must
# not stay blocked behind an older reading that says LESS about the same fact.
# These answer "is one reading the other one plus a detail it was missing?" —
# a deterministic, document-free relation (no tier, no vote), so the resolver
# can keep the more complete reading without a human. Anything else (a
# different órgão, a different cartório, two CNSs that disagree) stays None:
# not proven, still a conflict.

#: `refinamento_*` verdicts: which side carries the extra detail.
MAIS_COMPLETO_A = "a"
MAIS_COMPLETO_B = "b"
EQUIVALENTE = "equivalente"


def orgao_refinamento(a: Any, b: Any) -> Optional[str]:
    """`MAIS_COMPLETO_A` / `MAIS_COMPLETO_B` when both órgão expedidor
    readings name the SAME órgão and exactly one carries its UF (`SSP` vs
    `SSP/SP` — a bank form that printed the issuer without the state); None
    otherwise (empty, a different órgão, both or neither with a UF).

    The registry alone answers `equivalentes('orgao_expedidor', 'SSP/SP',
    'SSP')` with None (undecidable — it cannot invent the missing UF); this
    is the product's rule on top: the reading WITH the UF is the same órgão,
    stated completely, so it is kept — never a new value invented."""
    if not _texto(a) or not _texto(b):
        return None
    ca = ident.ler("orgao_expedidor", a).canonico
    cb = ident.ler("orgao_expedidor", b).canonico
    if not ca or not cb:
        return None
    base_a, _, uf_a = ca.partition("/")
    base_b, _, uf_b = cb.partition("/")
    if base_a != base_b:
        return None
    if uf_a and not uf_b:
        return MAIS_COMPLETO_A
    if uf_b and not uf_a:
        return MAIS_COMPLETO_B
    return None


#: The matrícula's book header ("LIVRO Nº 2 - REGISTRO GERAL") that an older
#: cartório reader glued onto the serventia's name — page furniture, not part
#: of the cartório's identity.
_LIVRO_CABECALHO = re.compile(
    r"\bLIVRO\s+N\S{0,2}\s*\d+\s*[-–—]?\s*REGISTRO\s+GERAL\b", re.IGNORECASE
)
#: A CNS fragment ("- CNS: 11991-7") — compared separately via
#: `cns_do_cartorio`, so it is removed from the name text.
_CNS_FRAGMENTO = re.compile(r"[-–—,]?\s*\bCNS\b\s*[:Nº°.]*\s*[\d.\-/]+", re.IGNORECASE)
#: What may follow " DE " in a locality suffix: a city name (letters, spaces,
#: apostrophes, hyphens), at most five words — never more structure.
_LOCALIDADE = re.compile(r"^[A-Z' \-]+$")


def cartorio_normalizado(valor: Any) -> str:
    """The serventia's NAME as comparison text: accents/case/whitespace
    folded, the book header and the CNS fragment removed, separators (`|`,
    stray dashes) collapsed. `""` for an empty value."""
    texto = _texto(valor)
    if not texto:
        return ""
    texto = _LIVRO_CABECALHO.sub(" ", texto)
    texto = _CNS_FRAGMENTO.sub(" ", texto)
    decomposto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in decomposto if not unicodedata.combining(c)).upper()
    texto = texto.replace("|", " ")
    texto = re.sub(r"\s+", " ", texto).strip(" -–—,.")
    return texto


def cartorio_refinamento(a: Any, b: Any) -> Optional[str]:
    """Relation between two `numero_registro_imoveis` readings:

    - `EQUIVALENTE` — same serventia name once the book header, the CNS
      fragment and formatting are set aside (and no CNS disagreement);
    - `MAIS_COMPLETO_A` / `MAIS_COMPLETO_B` — one is the other plus a
      locality (`SERVENTIA DO REGISTRO DE IMÓVEIS` vs `SERVENTIA DO
      REGISTRO DE IMÓVEIS de Cotia`): same serventia, the longer one names
      its city;
    - None — not proven (different names, or two CNSs that disagree)."""
    if cartorios_iguais(a, b) is False:
        return None
    na, nb = cartorio_normalizado(a), cartorio_normalizado(b)
    if not na or not nb:
        return None
    if na == nb:
        return EQUIVALENTE
    for curto, longo, veredito in ((na, nb, MAIS_COMPLETO_B), (nb, na, MAIS_COMPLETO_A)):
        prefixo = f"{curto} DE "
        if longo.startswith(prefixo):
            resto = longo[len(prefixo):].strip()
            if resto and len(resto.split()) <= 5 and _LOCALIDADE.match(resto):
                return veredito
    return None


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
    "TIPO_POR_CAMPO_ESCRITA_IMOVEL",
    "TIPO_POR_CAMPO_IMOVEL",
    "cabe",
    "canonico_cpf_cnpj",
    "canonico_ou_bruto",
    "EQUIVALENTE",
    "MAIS_COMPLETO_A",
    "MAIS_COMPLETO_B",
    "cartorio_normalizado",
    "cartorio_refinamento",
    "cartorios_iguais",
    "chave",
    "chaves_do_needle",
    "documentos_chave",
    "documentos_chave_cliente",
    "documentos_chave_imovel",
    "cns_do_cartorio",
    "iguais",
    "needle_chave",
    "orgao_refinamento",
    "para_gravar",
    "tipo_do_documento_pessoa",
    "uf_do_orgao",
]

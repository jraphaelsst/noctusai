"""Read a holder's filiação (mother's / father's name) and naturalidade
(place of birth) off a Brazilian document.

Sibling of `profession.py` / `nacionalidade.py`: pure, anchored, returning
`(value, confidence, matched_label)` triples with confidence as a plain string.

WHERE EACH IS PRINTED
---------------------
- RG, CIN, CNH, certidão de nascimento: a `FILIAÇÃO` block (father first, then
  mother, one name per line or joined by "e"), or explicit `PAI:` / `MÃE:` /
  `NOME DO PAI:` / `NOME DA MÃE:` fields. The RG and the certidão de
  nascimento also print `NATURALIDADE:` / `LOCAL DE NASCIMENTO:`; a CNH prints
  no place of birth.
- certidão de casamento: per spouse, inside the qualification clause —
  "..., brasileiro, natural de Campinas, Estado de São Paulo, nascido ...,
  filho de FULANO e de FULANA." Whole-document reads would mix the two
  spouses, so the extractor takes this only per spouse
  (`conjuges._com_filiacao`, via `ler_trecho`).

CONFIDENCE
----------
- An explicit `PAI:` / `MÃE:` label names the ROLE: `alta`.
- "filho(a) de X e de Y" is the registrars' fixed order (pai, mãe): `media`.
- An unlabelled `FILIAÇÃO` block names no role, only an ORDER: `baixa` — a
  swapped pair would land a father's name in `nome_mae`, which is worse than
  asking a human.
- `naturalidade` printed under its label: `alta`; read from "natural de ...":
  `media`.

🔴 NEVER GUESSED. Anything that is not a plausible personal name
(`name.looks_like_a_name`) is not a parent; a value with digits, a
"não consta/ignorado" marker or another label is not a naturalidade. A
single unattributable name (no role) is not emitted.
"""
from __future__ import annotations

import re
from typing import Optional

from noctusai_lib.integrations.documents.matricula_atos import normalized_with_offsets
from noctusai_lib.integrations.documents.name import looks_like_a_name

#: State name (accent-stripped, upper) -> UF.
_UF_POR_ESTADO: dict[str, str] = {
    "ACRE": "AC", "ALAGOAS": "AL", "AMAPA": "AP", "AMAZONAS": "AM", "BAHIA": "BA",
    "CEARA": "CE", "DISTRITO FEDERAL": "DF", "ESPIRITO SANTO": "ES", "GOIAS": "GO",
    "MARANHAO": "MA", "MATO GROSSO": "MT", "MATO GROSSO DO SUL": "MS",
    "MINAS GERAIS": "MG", "PARA": "PA", "PARAIBA": "PB", "PARANA": "PR",
    "PERNAMBUCO": "PE", "PIAUI": "PI", "RIO DE JANEIRO": "RJ",
    "RIO GRANDE DO NORTE": "RN", "RIO GRANDE DO SUL": "RS", "RONDONIA": "RO",
    "RORAIMA": "RR", "SANTA CATARINA": "SC", "SAO PAULO": "SP", "SERGIPE": "SE",
    "TOCANTINS": "TO",
}
_UFS: frozenset[str] = frozenset(_UF_POR_ESTADO.values())

#: A person-name span in normalised text: letters, spaces, apostrophes, dots.
_NOME = r"[A-Z][A-Z' .]{3,80}?"
#: What ends a name inside prose.
_FIM_NOME = (
    r"(?=\s*(?:[,;.\n]|$)|\s+(?:NASCID[OA]|CASAD[OA]|NATURAL|DOMICILIAD[OA]|RESIDENT[EA]|"
    r"PROFISSAO|BRASILEIR[OA]|PORTADOR|INSCRIT[OA]|E\s+DE\s+PROFISSAO)\b)"
)

#: "FILHO(A) DE <pai> E DE <mãe>" — registrars' fixed order.
_FILHO_DE_RE = re.compile(
    r"\bFILH[OA]S?\s+(?:LEGITIM[OA]\s+)?DE\s+(?P<resto>[A-Z][A-Z' .]{3,160}?)" + _FIM_NOME
)
#: The SP RCPN typed layout (old livro): "filho de: <PAI>, e de: <MÃE>, avós
#: ..." — a colon after each "de" and a comma before the connector, which the
#: prose pattern above (name ends at the first comma) cannot span. The colons
#: ARE the anchor, so this stays as strict as the prose form.
_FILHO_DE_DOIS_PONTOS_RE = re.compile(
    r"\bFILH[OA]S?\s+DE\s*:\s*(?P<pai>" + _NOME + r")\s*[,;]?\s+E\s+DE\s*:\s*"
    r"(?P<mae>" + _NOME + r")(?=\s*(?:[,;.\n]|$)|\s+(?:AVOS?|AVO|NASCID|OBSERV))"
)
#: Explicit role labels. `PAI` / `MAE` alone only count at a line start or
#: after a separator, so "COMPANHIA", "CAMPAI" are never matched.
_PAPEL_RE = re.compile(
    r"(?:(?<=\n)|(?<=^)|(?<=[|;]))[ \t]*(?:NOME\s+D[OA]\s+)?(?P<papel>PAI|MAE|GENITOR|GENITORA)"
    r"[ \t]*[:\-][ \t]*(?P<nome>" + _NOME + r")(?=\s*(?:[,;.|\n]|$))",
    re.MULTILINE,
)
_FILIACAO_ROTULO_RE = re.compile(r"\bFILIACAO\b[ \t]*[:\-]?[ \t]*")
#: Lines a FILIAÇÃO block stops at.
_ROTULO_SEGUINTE_RE = re.compile(
    r"^(?:DATA|DOC|REGISTRO|NATURALIDADE|NACIONALIDADE|CPF|RG|VALIDADE|ASSINATURA|"
    r"LOCAL|OBSERV|ESTADO\s+CIVIL|CATEGORIA|NOME|SEXO|SEXO)\b"
)

_NATURALIDADE_ROTULO_RE = re.compile(
    r"\b(?P<rotulo>NATURALIDADE|LOCAL\s+DE\s+NASCIMENTO|MUNICIPIO\s+DE\s+NASCIMENTO)\b"
    r"[ \t]*[:\-]?[ \t]*\n?[ \t]*"
)
_NATURAL_DE_RE = re.compile(r"\bNATURAL\s+(?:DE|DO|DA)\s+(?=(?P<resto>[A-Z][^\n]{1,120}))")
_NAO_VALOR_RE = re.compile(
    r"^(?:NAO\s+(?:CONSTA|DECLARAD[OA]|INFORMAD[OA])|IGNORAD[OA]|DATA|DOC|CPF|RG|"
    r"NACIONALIDADE|SEXO|FILIACAO|NOME|---+|\*+)"
)
_CIDADE_RE = re.compile(r"[A-Z][A-Z' ]{1,50}")


def _colapsa(s: str) -> str:
    return " ".join(s.split()).strip(" .,;-–")


def _literal(text: str, origem: list[int], norm: str, a: int, b: int) -> str:
    """The ORIGINAL-text slice behind `norm[a:b]` (accents kept)."""
    if a >= b or b > len(origem):
        return _colapsa(norm[a:b])
    return _colapsa(text[origem[a] : origem[b - 1] + 1])


def _par_de_nomes(resto: str) -> Optional[tuple[int, int, int, int]]:
    """Split `resto` ("PAI E DE MAE" / "PAI E MAE") into the two name spans
    `(a1, b1, a2, b2)`, each validated as a personal name. Tries the
    unambiguous " E DE " connector first, then a bare " E "."""
    for padrao in (r"\s+E\s+DE\s+", r"\s+E\s+"):
        for m in re.finditer(padrao, resto):
            a, b = resto[: m.start()], resto[m.end() :]
            if looks_like_a_name(a) and looks_like_a_name(b):
                return (0, m.start(), m.end(), len(resto))
    return None


def _nome_valido(n: str) -> bool:
    return looks_like_a_name(n) and not _NAO_VALOR_RE.match(n)


def _filiacao_de(norm: str, text: str, origem: list[int], *, bloco: bool = True):
    """`(nome_pai, nome_mae, conf_pai, conf_mae, rotulo)` or all-None."""
    # 1. Explicit role labels.
    papeis: dict[str, tuple[str, str]] = {}
    for m in _PAPEL_RE.finditer(norm):
        papel = "mae" if m.group("papel") in ("MAE", "GENITORA") else "pai"
        nome = _colapsa(m.group("nome"))
        if not _nome_valido(nome):
            continue
        lido = (
            _literal(text, origem, norm, m.start("nome"), m.end("nome")),
            " ".join(m.group("papel").split()),
        )
        if papel in papeis and papeis[papel][0].upper() != lido[0].upper():
            # Two DIFFERENT labelled parents of the same role (a document that
            # names two holders) — not attributable to one person.
            return (None, None, "nenhuma", "nenhuma", None)
        papeis.setdefault(papel, lido)
    if papeis:
        return (
            papeis.get("pai", (None, None))[0], papeis.get("mae", (None, None))[0],
            "alta" if "pai" in papeis else "nenhuma",
            "alta" if "mae" in papeis else "nenhuma",
            (papeis.get("mae") or papeis.get("pai"))[1],
        )
    # 2. "filho(a) de X e de Y".
    pares_narrativos: list[tuple[str, str]] = []
    for m in _FILHO_DE_RE.finditer(norm):
        par = _par_de_nomes(m.group("resto"))
        if par is None:
            continue
        a1, b1, a2, b2 = par
        ini = m.start("resto")
        pares_narrativos.append((
            _literal(text, origem, norm, ini + a1, ini + b1),
            _literal(text, origem, norm, ini + a2, ini + b2),
        ))
    for m in _FILHO_DE_DOIS_PONTOS_RE.finditer(norm):
        pai_t, mae_t = _colapsa(m.group("pai")), _colapsa(m.group("mae"))
        if _nome_valido(pai_t) and _nome_valido(mae_t):
            pares_narrativos.append((
                _literal(text, origem, norm, m.start("pai"), m.end("pai")),
                _literal(text, origem, norm, m.start("mae"), m.end("mae")),
            ))
    if pares_narrativos:
        # Two different "filho de" clauses = two holders (a certidão de
        # casamento read whole): not attributable, never the first one's.
        if len({(p.upper(), m.upper()) for p, m in pares_narrativos}) > 1:
            return (None, None, "nenhuma", "nenhuma", None)
        return (*pares_narrativos[0], "media", "media", "filho(a) de")
    # 3. FILIAÇÃO block: positional (pai, mãe). Never inside a narrative clause
    # (a certidão's column header also says "... E FILIAÇÃO DOS CÔNJUGES").
    for m in (_FILIACAO_ROTULO_RE.finditer(norm) if bloco else ()):
        fim_linha = norm.find("\n", m.end())
        fim_linha = len(norm) if fim_linha < 0 else fim_linha
        mesma = norm[m.end() : fim_linha]
        nomes: list[tuple[int, int]] = []
        if mesma.strip():
            par = _par_de_nomes(mesma)
            if par is not None:
                a1, b1, a2, b2 = par
                nomes = [(m.end() + a1, m.end() + b1), (m.end() + a2, m.end() + b2)]
            elif _nome_valido(_colapsa(mesma)):
                nomes = [(m.end(), fim_linha)]
        pos = fim_linha + 1
        while len(nomes) < 2 and pos < len(norm):
            f = norm.find("\n", pos)
            f = len(norm) if f < 0 else f
            linha = norm[pos:f]
            if linha.strip():
                if _ROTULO_SEGUINTE_RE.match(linha.strip()) or not _nome_valido(_colapsa(linha)):
                    break
                nomes.append((pos, f))
            pos = f + 1
        if len(nomes) == 2:
            return (
                _literal(text, origem, norm, *nomes[0]),
                _literal(text, origem, norm, *nomes[1]),
                "baixa", "baixa", "FILIAÇÃO",
            )
    return (None, None, "nenhuma", "nenhuma", None)


def _uf_do_resto(resto: str) -> tuple[str, Optional[str], int]:
    """From the text after the city: `(city_end_text, uf, consumed)`. Accepts
    "/SP", "- SP", ", SP", ", ESTADO DE SAO PAULO", ", ESTADO DO PARA"."""
    m = re.match(r"\s*[/\-,]\s*([A-Z]{2})\b", resto)
    if m and m.group(1) in _UFS:
        return ("", m.group(1), m.end())
    m = re.match(r"\s*,?\s*ESTADO\s+D[OEA]S?\s+([A-Z ]{3,24}?)(?=\s*[,.;\n]|\s+NASCID|\s+FILH|$)", resto)
    if m:
        uf = _UF_POR_ESTADO.get(" ".join(m.group(1).split()))
        if uf:
            return ("", uf, m.end())
    return ("", None, 0)


def _naturalidade_do_valor(
    norm: str, text: str, origem: list[int], ini: int
) -> Optional[str]:
    """`"Cidade/UF"` (or just the city) from the value starting at `ini`."""
    m = _CIDADE_RE.match(norm, ini)
    if not m:
        return None
    cidade_txt = m.group(0)
    # City ends at the first separator / stop word.
    corte = re.search(
        r"\s*(?:[,/;.\n\-]|$)|\s+(?=(?:NASCID|ESTADO\b|FILH|BRASILEIR|CASAD|DOMICILIAD|RESIDENT))",
        cidade_txt,
    )
    cidade_fim = ini + (corte.start() if corte else len(cidade_txt))
    cidade = _colapsa(norm[ini:cidade_fim])
    if (
        len(cidade) < 2 or any(c.isdigit() for c in cidade) or _NAO_VALOR_RE.match(cidade)
        or cidade in ("ESTADO", "CAPITAL")
    ):
        return None
    _, uf, _ = _uf_do_resto(norm[cidade_fim : cidade_fim + 60])
    literal = _literal(text, origem, norm, ini, cidade_fim)
    return f"{literal}/{uf}" if uf else literal


def _naturalidade_de(norm: str, text: str, origem: list[int]):
    """`(valor, confianca, rotulo)` — labelled first, else "natural de"."""
    leituras: list[tuple[str, str, str]] = []
    for m in _NATURALIDADE_ROTULO_RE.finditer(norm):
        valor = _naturalidade_do_valor(norm, text, origem, m.end())
        if valor:
            leituras.append((valor, "alta", " ".join(m.group("rotulo").split())))
    if not leituras:
        for m in _NATURAL_DE_RE.finditer(norm):
            valor = _naturalidade_do_valor(norm, text, origem, m.start("resto"))
            if valor:
                leituras.append((valor, "media", "natural de"))
    if not leituras:
        return (None, "nenhuma", None)
    primeiro = leituras[0]
    # Two DIFFERENT labelled readings = a layout this parser cannot attribute
    # (same rule as every sibling finder).
    if any(l[0].upper() != primeiro[0].upper() for l in leituras[1:]):
        return (None, "nenhuma", None)
    return primeiro


def find_filiacao(
    text: str,
) -> tuple[Optional[str], str, Optional[str], str, Optional[str]]:
    """`(nome_pai, conf_pai, nome_mae, conf_mae, rotulo)` for a single-holder
    document. `(None, "nenhuma", None, "nenhuma", None)` when nothing is
    attributable."""
    if not text:
        return (None, "nenhuma", None, "nenhuma", None)
    norm, origem = normalized_with_offsets(text)
    pai, mae, cp, cm, rotulo = _filiacao_de(norm, text, origem)
    return (pai, cp if pai else "nenhuma", mae, cm if mae else "nenhuma", rotulo)


def find_naturalidade(text: str) -> tuple[Optional[str], str, Optional[str]]:
    """`(valor, confianca, rotulo)` — `"Cidade/UF"` as printed."""
    if not text:
        return (None, "nenhuma", None)
    norm, origem = normalized_with_offsets(text)
    return _naturalidade_de(norm, text, origem)


def ler_trecho(trecho: str) -> dict[str, tuple[Optional[str], str]]:
    """Both facts off ONE person's qualification clause (a spouse's segment of
    a certidão de casamento): `{"nome_pai"|"nome_mae"|"naturalidade":
    (valor, confianca)}`, only the keys that were read. The caller attributes
    the segment to a person, so these are at most `media`."""
    if not trecho:
        return {}
    norm, origem = normalized_with_offsets(trecho)
    pai, mae, _, _, _ = _filiacao_de(norm, trecho, origem, bloco=False)
    nat, _, _ = _naturalidade_de(norm, trecho, origem)
    out: dict[str, tuple[Optional[str], str]] = {}
    if pai:
        out["nome_pai"] = (pai, "media")
    if mae:
        out["nome_mae"] = (mae, "media")
    if nat:
        out["naturalidade"] = (nat, "media")
    return out


__all__ = ["find_filiacao", "find_naturalidade", "ler_trecho"]

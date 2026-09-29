"""Read a Brazilian postal address off a comprovante de endereço.

Utility bills (luz, água, gás, telefone), bank statements and fichas
cadastrais all print the holder's address, but in two very different shapes:

- **labelled** — `Endereço: R PROF ARTUR RAMOS, 123 - APTO 12` /
  `Bairro: JARDIM PAULISTANO` / `CEP: 01454-011` / `Cidade: SAO PAULO - SP`;
- **envelope block** — the mailing block a bill prints for the window
  envelope, no labels at all:

      MARIA DE SOUZA
      RUA DAS FLORES 123 AP 45
      JARDIM PAULISTA
      01234-567 SAO PAULO SP

🔴 THE CEP IS THE ANCHOR
------------------------
A CEP (`NNNNN-NNN`) is the one part of an address with a checkable SHAPE, and
the parts around it follow a stable order (street, bairro, city/UF). So the
envelope reader finds a CEP first and reads outward from it; a document with
no CEP yields nothing rather than a guess assembled from loose lines.

🔴 THE ISSUER PRINTS ITS OWN ADDRESS TOO
-----------------------------------------
Every bill carries the utility's own address — usually beside its CNPJ
("Enel Distribuição São Paulo, Rua Ática, 673 ... CEP 04634-042 CNPJ ...").
A CEP whose neighbourhood mentions a CNPJ / inscrição estadual is the
ISSUER's and is never a candidate. Several remaining CEPs that disagree mean
this parser cannot tell which is the holder's: the result is `nenhuma`.

🔴 THE HOLDER IS OFTEN SOMEONE ELSE
------------------------------------
A comprovante is routinely in a spouse's or a parent's name. The printed
holder (`titular`) is returned alongside the address so the CONSUMER can
check it against the person the document was uploaded for — this module does
not decide whose address it is, it reports whose name the bill carries.

Values are literal slices of the caller's text (accents and casing as
printed), via the same offset map `matricula_atos` uses; the CEP alone is
canonicalised to `NNNNN-NNN`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Optional

from noctusai_lib.integrations.documents.matricula_atos import normalized_with_offsets
from noctusai_lib.integrations.documents.name import looks_like_a_name

UFS = frozenset(
    "AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split()
)

#: Street-type prefixes, normalised. `R`/`AV`/`AL`... are the abbreviations
#: utilities print; the long forms are what fichas print.
_TIPOS_LOGRADOURO = (
    "RUA", "R", "AVENIDA", "AV", "AVDA", "ALAMEDA", "AL", "TRAVESSA", "TV", "TRAV",
    "ESTRADA", "EST", "ESTR", "RODOVIA", "ROD", "PRACA", "PC", "PCA", "LARGO", "LGO",
    "VIELA", "VLA", "PASSAGEM", "PSG", "VIA", "VIADUTO", "PARQUE", "PQ", "QUADRA",
    "SQN", "SQS", "SHIS", "SHIN", "CONDOMINIO", "COND", "BECO", "LADEIRA", "LD",
    "TRAVESSA", "SERVIDAO", "VILA", "VL", "CAMINHO", "RUELA", "PRAIA", "ACESSO",
)
_TIPO_RE = re.compile(
    r"^(?:" + "|".join(sorted(set(_TIPOS_LOGRADOURO), key=len, reverse=True)) + r")\.?\s+\S"
)

#: G18 — Correios' own street-type abbreviations, expanded to the DNE
#: (Diretório Nacional de Endereços) full type name a contract prints
#: ("Alameda ..." never "AL ..."). Deliberately CLOSED and narrow: only the
#: genuinely ABBREVIATED forms of `_TIPOS_LOGRADOURO` above are keys here —
#: an entry already spelled out ("RUA", "AVENIDA", "CONDOMINIO", ...) or a
#: Brasília quadra code (`SQN`/`SQS`/`SHIS`/`SHIN`, themselves the canonical
#: addressing scheme, not an abbreviation OF anything) is deliberately
#: absent, so looking it up is a no-op rather than a guessed expansion.
_TIPO_LOGRADOURO_EXTENSO: dict[str, str] = {
    "R": "Rua",
    "AV": "Avenida",
    "AVDA": "Avenida",
    "AL": "Alameda",
    "TV": "Travessa",
    "TRAV": "Travessa",
    "EST": "Estrada",
    "ESTR": "Estrada",
    "ROD": "Rodovia",
    "PC": "Praça",
    "PCA": "Praça",
    "LGO": "Largo",
    "VLA": "Viela",
    "PSG": "Passagem",
    "PQ": "Parque",
    "COND": "Condomínio",
    "LD": "Ladeira",
    "VL": "Vila",
}

#: The leading type token only — an optional trailing period (a bill prints
#: both "AL" and "AL."), then whatever separates it from the rest.
_TIPO_LOGRADOURO_LIDER_RE = re.compile(r"^([A-Za-zÀ-ÖØ-öø-ÿ]+)\.?(\s+)")


def normalizar_tipo_logradouro(logradouro: Optional[str]) -> Optional[str]:
    """Expand ONLY the leading street-type abbreviation to its full DNE
    form — `AL DAS ACACIAS` -> `Alameda DAS ACACIAS`.

    Applied to a leading token alone: nothing else in the string is
    touched, so the rest of a bill's own capitalisation (`DAS ACACIAS`)
    survives untouched. A leading token this closed table does not carry —
    an already-spelled-out type, a genuinely different abbreviation, or a
    logradouro this parser could not type-anchor at all — is returned
    exactly as printed; this function only ever EXPANDS a known token, it
    never guesses at one it does not recognise.
    """
    if not logradouro:
        return logradouro
    m = _TIPO_LOGRADOURO_LIDER_RE.match(logradouro)
    if not m:
        return logradouro
    extenso = _TIPO_LOGRADOURO_EXTENSO.get(m.group(1).upper())
    if extenso is None:
        return logradouro
    return extenso + " " + logradouro[m.end():]

#: Tokens that open a complemento.
_COMPLEMENTO_RE = re.compile(
    r"^(?:AP|APT|APTO|APARTAMENTO|BL|BLOCO|CASA|CS|SALA|SL|CJ|CONJ|CONJUNTO|LOJA|LJ|"
    r"FUNDOS|FDS|FRENTE|LOTE|LT|QD|QUADRA|TORRE|TR|ANDAR|UNIDADE|UN|BOX|KM|SOBRADO|"
    r"SOB|TERREO|GALPAO|PAVIMENTO|PAV)\b"
)

_CEP_HIFEN_RE = re.compile(r"(?<![\d.])(\d{2})\.?(\d{3})\s?-\s?(\d{3})(?![\d-])")
_CEP_ROTULO_RE = re.compile(r"\bCEP\b\s*[:.\-]?\s*(\d{2})\.?(\d{3})\s?-?\s?(\d{3})(?!\d)")

#: Markers that a CEP belongs to the ISSUER, not to the holder.
_EMISSOR_RE = re.compile(r"\bCNPJ\b|INSCRICAO\s+ESTADUAL|\bI\.?\s?E\.?\s*[:.]|RAZAO\s+SOCIAL")
#: 🔴 P1/883 (2026-09-25), real, measured: a Vivo bill prints its own
#: mailing-window address ("AV. ENGENHEIRO LUIS CARLOS BERRINI, 1.376 - CEP:
#: NNNNN-NNN - SAO PAULO - SP") on one line and its "Inscrição Estadual: ..."
#: / "CNPJ Emissor: ..." block TWO lines below it, not one — with
#: `_EMISSOR_JANELA_LINHAS=1`, `_emissor_proximo` missed the marker entirely,
#: the issuer's own CEP survived as an unrejected candidate, `_envelope`
#: then found it disagreeing with the holder's genuine envelope-block CEP a
#: few lines above, and — two DISTINCT (cep, logradouro) pairs, neither
#: provably the right one — returned nothing at all, for a document whose
#: real address was sitting in the text the whole time. Widened by one line;
#: still narrow enough that an unrelated CNPJ mention several lines away
#: (an unrelated attachment, a different section) does not reach back and
#: reject a genuine holder CEP.
_EMISSOR_JANELA_LINHAS = 2

#: Labelled-mode field labels (normalised). Each must start the value's line
#: or follow at least two spaces / a separator, so "RUA" inside a street name
#: never re-opens a field.
_ROTULOS = {
    "logradouro": r"(?:ENDERECO(?:\s+(?:DE\s+(?:ENTREGA|CORRESPONDENCIA|INSTALACAO|COBRANCA)|DA\s+UNIDADE(?:\s+CONSUMIDORA)?|DO\s+IMOVEL|RESIDENCIAL|DO\s+CLIENTE))?|LOGRADOURO|LOCAL\s+DE\s+(?:INSTALACAO|ENTREGA|CONSUMO))",
    "numero": r"(?:NUMERO|NUM|N[O°º])",
    "complemento": r"(?:COMPLEMENTO|COMPL)",
    "bairro": r"(?:BAIRRO|DISTRITO)",
    "cidade": r"(?:CIDADE|MUNICIPIO|LOCALIDADE)",
    "uf": r"(?:UF|ESTADO)",
}
#: P2 (2026-09-28), measured against 9 real comprovantes: none carried
#: `Titular`/`Cliente`/`Nome`/`Destinatário` and none was read — every one
#: was either a bank/boleto slip (`Sacado`/`Pagador` — the payer, printed
#: next to their own address block) or an envelope block with no label at
#: all (handled separately, positionally, by `_ler_bloco` below). Adding
#: `SACADO`/`PAGADOR` here is the label-anchored half of the fix.
_TITULAR_ROTULO_RE = re.compile(
    r"^\s*(?:NOME(?:\s+DO\s+(?:CLIENTE|TITULAR))?|CLIENTE|TITULAR|DESTINATARIO|"
    r"CONSUMIDOR|SACADO|PAGADOR)\s*[:\-]\s*(.+?)\s*$"
)

#: P2 round 2 (2026-09-28), measured against 4 of the 9 real comprovantes
#: `SACADO`/`PAGADOR` still missed — the SAME label whitelist, but the value
#: sits somewhere OTHER than "on this line": the label alone on its own line
#: (`_TITULAR_ROTULO_SOZINHO_RE`, value on the line right after — sometimes
#: behind a customer-code prefix, `_CODIGO_CLIENTE_PREFIXO_RE`), a bare name
#: line immediately BEFORE a "COD.CLIENTE" line (`_COD_CLIENTE_RE`, a
#: column-layout bill that stacks every label first and every value after),
#: or — the weakest signal, no label anywhere — a bare name line immediately
#: BEFORE a recognised street-type line. All three are wired as a
#: document-wide FALLBACK (`_titular_por_heuristicas_fracas`), consulted only
#: when neither a same-line label nor `_ler_bloco`'s own local scan already
#: found one — a labelled, same-line read always wins first.
_TITULAR_ROTULO_SOZINHO_RE = re.compile(
    r"^\s*(?:NOME(?:\s+DO\s+(?:CLIENTE|TITULAR))?|CLIENTE|TITULAR|DESTINATARIO|"
    r"CONSUMIDOR|SACADO|PAGADOR)\s*[:\-]?\s*$"
)
_CODIGO_CLIENTE_PREFIXO_RE = re.compile(r"^\s*\d+\s*-\s*(.+)$")
#: Narrow ON PURPOSE — "COD.CLIENTE" only, never a bare "COD." prefix that
#: would also swallow an unrelated "COD. BARRAS" or similar field.
_COD_CLIENTE_RE = re.compile(r"^\s*COD\.?\s*CLIENTE\b")
#: Legal-entity suffixes that pass `looks_like_a_name`'s own structural check
#: (letters-only, 2..8 words) because a company's own name is shaped exactly
#: like a person's — real, measured (P2): ENEL's and a telecom issuer's own
#: header would otherwise be read as the holder by the positional heuristics
#: above. `_emissor_proximo` (a CNPJ/IE marker within 2 lines) is the PRIMARY
#: guard already; this is defense in depth for when that marker sits
#: further away than its window.
_EMISSOR_TOKEN_RE = re.compile(
    r"\b(?:LTDA|EIRELI|CIA|COMPANHIA|S/?A|TELECOM|TELEFONICA|DISTRIBUICAO|"
    r"SANEAMENTO|ENERGIA|BANCO)\b"
)


def _e_nome_de_pessoa(candidato: Optional[str]) -> bool:
    """`looks_like_a_name`, plus never an issuer/company string."""
    return bool(candidato) and looks_like_a_name(candidato) and not _EMISSOR_TOKEN_RE.search(
        candidato
    )


#: Where a labelled value stops: two+ spaces, a pipe, or another label.
_PARADA = r"(?=\s{2,}|\s*\||\s+(?:CEP|BAIRRO|CIDADE|MUNICIPIO|UF|ESTADO|COMPLEMENTO|NUMERO)\b\s*[:\-]|$)"


@dataclass(frozen=True)
class EnderecoLido:
    """A postal address read off one document. Every part Optional.

    `titular` is the name the document prints as its holder, when one could
    be told apart — NOT a claim about whose address it is (see the module
    docstring). `confianca` is `alta` for a labelled read, `baixa` for an
    envelope-block read (positional), `nenhuma` when nothing usable was found.
    """

    cep: Optional[str] = None
    logradouro: Optional[str] = None
    numero: Optional[str] = None
    complemento: Optional[str] = None
    bairro: Optional[str] = None
    cidade: Optional[str] = None
    uf: Optional[str] = None
    titular: Optional[str] = None
    confianca: str = "nenhuma"
    rotulo: Optional[str] = None

    #: The seven address parts, in the order a contract prints them.
    PARTES = ("cep", "logradouro", "numero", "complemento", "bairro", "cidade", "uf")

    def partes(self) -> dict[str, Optional[str]]:
        return {p: getattr(self, p) for p in self.PARTES}

    @property
    def presente(self) -> bool:
        """A usable address: a CEP plus a street at least."""
        return bool(self.cep and self.logradouro)


_NADA = EnderecoLido()


def _cep(a: str, b: str, c: str) -> str:
    return f"{a}{b}-{c}"


class _Texto:
    """The caller's text, its normalised copy, and the map between them."""

    def __init__(self, text: str) -> None:
        self.orig = text
        self.norm, self._origem = normalized_with_offsets(text)
        self.linhas: list[tuple[int, str]] = []
        pos = 0
        for linha in self.norm.split("\n"):
            self.linhas.append((pos, linha))
            pos += len(linha) + 1

    def literal(self, a: int, b: int) -> Optional[str]:
        """Original-text slice for normalised span [a, b)."""
        while a < b and self.norm[a].isspace():
            a += 1
        while b > a and self.norm[b - 1].isspace():
            b -= 1
        if a >= b or b > len(self._origem):
            return None
        valor = self.orig[self._origem[a] : self._origem[b - 1] + 1]
        valor = " ".join(valor.split()).strip(" ,;-–")
        return valor or None


def _parse_logradouro(t: _Texto, base: int, linha: str) -> dict[str, Optional[str]]:
    """Split one street line into logradouro / número / complemento / bairro.

    `base` is the line's absolute offset in `t.norm`.
    """
    out: dict[str, Optional[str]] = {
        "logradouro": None, "numero": None, "complemento": None, "bairro": None,
    }
    m = re.match(
        r"^\s*(?P<log>[^\d,]*?[A-Z][^\d,]*?)\s*,?\s*(?:N[O°º]?\s*[.:]?\s*)?"
        r"(?P<num>\d+[A-Z]?\b|S\s*/\s*N[O°º]?\b|SN\b)\s*(?P<resto>.*)$",
        linha,
    )
    if not m:
        out["logradouro"] = t.literal(base, base + len(linha.rstrip()))
        return out
    out["logradouro"] = t.literal(base + m.start("log"), base + m.end("log"))
    num = m.group("num")
    out["numero"] = "S/N" if num.replace(" ", "").startswith("S") else t.literal(
        base + m.start("num"), base + m.end("num")
    )
    resto_ini = base + m.start("resto")
    resto = m.group("resto")
    # Segments separated by " - " or ","; a complemento opens with a
    # complemento token, anything else (the first such) is the bairro.
    pos = 0
    complemento: list[tuple[int, int]] = []
    for seg in re.split(r"(\s+-\s+|\s*,\s*|\s{2,})", resto):
        ini, fim = pos, pos + len(seg)
        pos = fim
        s = seg.strip(" -,")
        if not s or re.fullmatch(r"\s+-\s+|\s*,\s*|\s{2,}", seg):
            continue
        if _COMPLEMENTO_RE.match(s) or (complemento and re.fullmatch(r"[A-Z]?\d+[A-Z]?", s)):
            complemento.append((ini, fim))
        elif out["bairro"] is None and not _nao_e_bairro(s):
            out["bairro"] = t.literal(resto_ini + ini, resto_ini + fim)
    if complemento:
        out["complemento"] = t.literal(resto_ini + complemento[0][0], resto_ini + complemento[-1][1])
    return out


def _nao_e_bairro(s: str) -> bool:
    """A trailing segment that is really the city/UF/CEP, not a bairro."""
    return bool(
        _CEP_HIFEN_RE.search(s)
        or s in UFS
        or re.search(r"\bCEP\b", s)
    )


def _cidade_uf(t: _Texto, base: int, linha: str) -> tuple[Optional[str], Optional[str]]:
    """`SAO PAULO - SP` / `SAO PAULO/SP` / `SAO PAULO SP` -> (cidade, uf)."""
    m = re.search(r"(?P<cid>[A-Z][A-Z .'-]*?[A-Z])\s*(?:[-/,]\s*|\s+)(?P<uf>[A-Z]{2})\s*$", linha)
    if m and m.group("uf") in UFS:
        cidade = t.literal(base + m.start("cid"), base + m.end("cid"))
        if cidade:
            cidade = re.sub(r"^(?:CIDADE|MUNICIPIO)\s*[:\-]\s*", "", cidade, flags=re.I)
        return (cidade or None, m.group("uf"))
    return (None, None)


def _emissor_proximo(t: _Texto, idx: int) -> bool:
    ini = max(0, idx - _EMISSOR_JANELA_LINHAS)
    fim = min(len(t.linhas), idx + _EMISSOR_JANELA_LINHAS + 1)
    return any(_EMISSOR_RE.search(t.linhas[i][1]) for i in range(ini, fim))


#: A `CIDADE`/`MUNICIPIO`/`LOCALIDADE` label sitting on a CEP's OWN line —
#: `CEP: NNNNN-NNN - Município: SAO PAULO`. Scoped to the tail of that one
#: line, so the relaxed single-space-or-dash boundary below (unlike
#: `_ROTULOS`'s own 2-space/pipe/line-start rule, built to stop "RUA" INSIDE
#: a street name from re-opening a field) cannot mis-fire anywhere else in a
#: long document.
_CIDADE_ROTULO_NA_LINHA_DO_CEP_RE = re.compile(
    r"\b(?:CIDADE|MUNICIPIO|LOCALIDADE)\s*[:\-]\s*(?P<v>.+?)\s*$"
)


def _completar_cidade_uf_da_linha_do_cep(
    t: _Texto, base: int, linha: str, fim_cep: int, achados: dict[str, Optional[str]]
) -> None:
    """Backfill `cidade`/`uf` from the TAIL of a CEP's own line, when the
    main per-line label scan (`_rotulado`'s own loop) found neither.

    🔴 P1/883 (2026-09-25), real, measured: an Enel bill prints
    `CEP: NNNNN-NNN - SAO PAULO/SP` with no separate `CIDADE:`/`MUNICIPIO:`
    label at all — an unlabelled tail on the SAME line as the CEP, which
    `_ROTULOS`'s per-field scan never looks at (it only opens a field on ITS
    OWN label). The same bill's second, more fully labelled address block
    prints `CEP: NNNNN-NNN  - Município: SAO PAULO` — a real label, but
    separated from the CEP by exactly ONE space, one character short of
    `_ROTULOS`'s 2-space-or-pipe field-opening boundary, so it never
    matched either. Both shapes read off the SAME line the CEP itself
    matched on, so completing them right here — rather than loosening
    `_ROTULOS`'s boundary document-wide, which risks a label mid-sentence
    elsewhere re-opening a field — is the narrow fix.
    """
    if achados.get("cidade") and achados.get("uf"):
        return
    resto = linha[fim_cep:]
    cid, uf = _cidade_uf(t, base + fim_cep, resto)
    if uf and not achados.get("uf"):
        achados["uf"] = uf
        if cid and not achados.get("cidade"):
            achados["cidade"] = cid
        return
    m = _CIDADE_ROTULO_NA_LINHA_DO_CEP_RE.search(resto)
    if m and not achados.get("cidade"):
        cidade = t.literal(base + fim_cep + m.start("v"), base + fim_cep + m.end("v"))
        if cidade:
            achados["cidade"] = cidade


def _rotulado(t: _Texto) -> Optional[EnderecoLido]:
    """Labelled-mode read, or None when there is no labelled street."""
    achados: dict[str, Optional[str]] = {}
    titular: Optional[str] = None
    cep: Optional[str] = None
    for idx, (base, linha) in enumerate(t.linhas):
        if titular is None:
            mt = _TITULAR_ROTULO_RE.match(linha)
            if mt and _e_nome_de_pessoa(mt.group(1)):
                titular = t.literal(base + mt.start(1), base + mt.end(1))
        mc = _CEP_ROTULO_RE.search(linha)
        if mc and not _emissor_proximo(t, idx):
            if cep is None:
                cep = _cep(*mc.groups())
            _completar_cidade_uf_da_linha_do_cep(t, base, linha, mc.end(), achados)
        for campo, rotulo in _ROTULOS.items():
            if achados.get(campo):
                continue
            m = re.search(
                r"(?:^|\s{2,}|\|\s*|^\s*)" + rotulo + r"\s*[:\-]\s*(?P<v>.+?)" + _PARADA, linha
            )
            if not m:
                continue
            if campo == "logradouro":
                if _emissor_proximo(t, idx):
                    continue
                partes = _parse_logradouro(t, base + m.start("v"), m.group("v"))
                for k, v in partes.items():
                    if v and not achados.get(k):
                        achados[k] = v
                # Inline "..., CIDADE - UF" tail on the same labelled line.
                cid, uf = _cidade_uf(t, base, linha[: m.end("v")])
                if uf and not achados.get("uf"):
                    achados["uf"] = uf
                    if cid and not achados.get("cidade") and cid != achados.get("bairro"):
                        achados["cidade"] = cid
                if not cep:
                    mh = _CEP_HIFEN_RE.search(linha)
                    if mh:
                        cep = _cep(*mh.groups())
            elif campo == "cidade":
                cid, uf = _cidade_uf(t, base + m.start("v"), m.group("v"))
                if cid:
                    achados["cidade"] = cid
                    if uf and not achados.get("uf"):
                        achados["uf"] = uf
                else:
                    achados["cidade"] = t.literal(base + m.start("v"), base + m.end("v"))
            elif campo == "uf":
                uf = m.group("v").strip()[:2]
                if uf in UFS:
                    achados["uf"] = uf
            else:
                achados[campo] = t.literal(base + m.start("v"), base + m.end("v"))
    if not achados.get("logradouro"):
        return None
    return EnderecoLido(
        cep=cep,
        logradouro=achados.get("logradouro"),
        numero=achados.get("numero"),
        complemento=achados.get("complemento"),
        bairro=achados.get("bairro"),
        cidade=achados.get("cidade"),
        uf=achados.get("uf"),
        titular=titular,
        confianca="alta" if cep else "baixa",
        rotulo="ENDERECO",
    )


def _envelope(t: _Texto) -> EnderecoLido:
    """CEP-anchored read of an unlabelled mailing block."""
    candidatos: list[tuple[int, str]] = []
    for idx, (_base, linha) in enumerate(t.linhas):
        for m in list(_CEP_ROTULO_RE.finditer(linha)) or list(_CEP_HIFEN_RE.finditer(linha)):
            if _emissor_proximo(t, idx):
                continue
            candidatos.append((idx, _cep(*m.groups())))
    # Keep only candidates with a street line within the 4 lines above (or on
    # the same line) — a CEP with no street beside it is a stray number.
    lidos: list[EnderecoLido] = []
    for idx, cep in candidatos:
        lido = _ler_bloco(t, idx, cep)
        if lido is not None:
            lidos.append(lido)
    distintos = {(l.cep, (l.logradouro or "").upper()) for l in lidos}
    if len(distintos) != 1:
        return _NADA
    return lidos[0]


def _ler_bloco(t: _Texto, idx: int, cep: str) -> Optional[EnderecoLido]:
    base_cep, linha_cep = t.linhas[idx]
    # Blank the CEP out IN PLACE (same length) so offsets into the line stay
    # valid for the literal slices taken from it below.
    _branco = lambda m: " " * len(m.group(0))  # noqa: E731
    resto_cep = _CEP_ROTULO_RE.sub(_branco, linha_cep)
    resto_cep = _CEP_HIFEN_RE.sub(_branco, resto_cep)

    # Single-line form: "RUA X, 123 - BAIRRO - CIDADE - UF - CEP 01234-567".
    rua_idx: Optional[int] = None
    for j in range(idx, max(-1, idx - 5), -1):
        if _TIPO_RE.match(t.linhas[j][1].strip()):
            rua_idx = j
            break
    if rua_idx is None:
        return None

    base_rua, linha_rua = t.linhas[rua_idx]
    recuo = len(linha_rua) - len(linha_rua.lstrip())
    corpo_rua = linha_rua.strip()
    if rua_idx == idx:
        # Cut the street line at the CEP so the city/UF tail parses apart.
        mc = _CEP_ROTULO_RE.search(linha_rua) or _CEP_HIFEN_RE.search(linha_rua)
        corte = mc.start() if mc else len(linha_rua)
        corpo_rua = linha_rua[recuo:corte].rstrip(" -,")
    partes = _parse_logradouro(t, base_rua + recuo, corpo_rua)

    cidade: Optional[str] = None
    uf: Optional[str] = None
    if rua_idx == idx:
        # The tail segments after the street: "... - BAIRRO - CIDADE - UF".
        segs = [s.strip() for s in re.split(r"\s+-\s+|\s*/\s*|,", corpo_rua) if s.strip()]
        if len(segs) >= 2 and segs[-1] in UFS:
            uf = segs[-1]
            cid_txt = segs[-2]
            pos = corpo_rua.rfind(cid_txt)
            cidade = t.literal(base_rua + recuo + pos, base_rua + recuo + pos + len(cid_txt))
            if partes.get("bairro") and partes["bairro"].upper() == (cidade or "").upper():
                partes["bairro"] = None
    else:
        cidade, uf = _cidade_uf(t, base_cep, resto_cep.rstrip())
        if uf is None and idx + 1 < len(t.linhas):
            b1, l1 = t.linhas[idx + 1]
            cidade, uf = _cidade_uf(t, b1, l1.rstrip())
        # Lines between the street and the CEP line: the bairro.
        if not partes.get("bairro"):
            for j in range(rua_idx + 1, idx + 1):
                bj, lj = t.linhas[j]
                txt = lj.strip()
                if j == idx:
                    txt = resto_cep.strip()
                    # "JARDIM X  SAO PAULO SP" — nothing reliable to split on
                    # beyond the city/UF already read.
                    if cidade:
                        continue
                if not txt or _TIPO_RE.match(txt) or re.search(r"\d{3,}", txt):
                    continue
                recuo_j = len(lj) - len(lj.lstrip())
                partes["bairro"] = t.literal(bj + recuo_j, bj + recuo_j + len(txt))
                break

    titular: Optional[str] = None
    for j in range(rua_idx - 1, max(-1, rua_idx - 3), -1):
        bj, lj = t.linhas[j]
        txt = lj.strip()
        if not txt:
            continue
        mt = _TITULAR_ROTULO_RE.match(lj)
        if mt:
            txt = mt.group(1)
            recuo_j = mt.start(1)
        else:
            recuo_j = len(lj) - len(lj.lstrip())
        if _e_nome_de_pessoa(txt) and not re.search(r"\d", txt):
            titular = t.literal(bj + recuo_j, bj + recuo_j + len(txt))
        break

    return EnderecoLido(
        cep=cep,
        logradouro=partes.get("logradouro"),
        numero=partes.get("numero"),
        complemento=partes.get("complemento"),
        bairro=partes.get("bairro"),
        cidade=cidade,
        uf=uf,
        titular=titular,
        confianca="baixa",
        rotulo="CEP",
    )


def _titular_por_heuristicas_fracas(t: _Texto) -> Optional[str]:
    """Titular via the three WEAK, document-wide heuristics `_rotulado`'s
    same-line label match and `_ler_bloco`'s own local scan both miss —
    measured against the P2 corpus, round 2 (2026-09-28). Tried in document
    order, first match wins:

    1. a titular label alone on its own line, the value on the line right
       AFTER it (`_TITULAR_ROTULO_SOZINHO_RE`), sometimes behind a customer
       code (`_CODIGO_CLIENTE_PREFIXO_RE` — "54321 - JOAO DA SILVA");
    2. a bare name line immediately BEFORE a "COD.CLIENTE" line
       (`_COD_CLIENTE_RE`) — a column-layout bill that stacks its labels
       first, then its values, in two separate blocks;
    3. a bare name line immediately BEFORE a recognised street-type line
       (`_TIPO_RE`), no label anywhere — the weakest signal, so it is tried
       last and is guarded exactly like `_envelope`'s own CEP candidates:
       never the issuer's own address block (`_emissor_proximo`), never a
       legal-entity name (`_e_nome_de_pessoa`).

    Only ever consulted by `find_endereco` as a FALLBACK, when the address
    itself is already `presente` but no titular was found any other way —
    a same-line labelled read always wins first; this never overrides one.
    """
    for idx, (_base, linha) in enumerate(t.linhas):
        if _TITULAR_ROTULO_SOZINHO_RE.match(linha) and idx + 1 < len(t.linhas):
            prox_base, prox_linha = t.linhas[idx + 1]
            mc = _CODIGO_CLIENTE_PREFIXO_RE.match(prox_linha)
            ini, fim = (mc.start(1), mc.end(1)) if mc else (0, len(prox_linha.rstrip()))
            if _e_nome_de_pessoa(prox_linha[ini:fim]):
                candidato = t.literal(prox_base + ini, prox_base + fim)
                if candidato:
                    return candidato

        if _COD_CLIENTE_RE.match(linha) and idx > 0:
            ant_base, ant_linha = t.linhas[idx - 1]
            txt = ant_linha.strip()
            if _e_nome_de_pessoa(txt):
                recuo = len(ant_linha) - len(ant_linha.lstrip())
                candidato = t.literal(ant_base + recuo, ant_base + recuo + len(txt))
                if candidato:
                    return candidato

        if _TIPO_RE.match(linha.strip()) and idx > 0 and not _emissor_proximo(t, idx):
            ant_base, ant_linha = t.linhas[idx - 1]
            txt = ant_linha.strip()
            if _e_nome_de_pessoa(txt):
                recuo = len(ant_linha) - len(ant_linha.lstrip())
                candidato = t.literal(ant_base + recuo, ant_base + recuo + len(txt))
                if candidato:
                    return candidato
    return None


def find_endereco(text: str) -> EnderecoLido:
    """The holder's address off a comprovante, or an empty `EnderecoLido`.

    Labelled layout first (exact labels, `alta` when a CEP is present);
    otherwise the CEP-anchored envelope block (`baixa` — positional). When
    the address is `presente` but no titular was found by either primary
    path, `_titular_por_heuristicas_fracas` tries three weaker, document-wide
    heuristics before giving up — see that function's own docstring.
    `logradouro`'s leading street-type token is expanded to its full DNE
    form (G18 — `normalizar_tipo_logradouro`); every other part stays a
    literal slice of the caller's text, per the module docstring. Never
    raises.
    """
    if not text or not text.strip():
        return _NADA
    t = _Texto(text)
    lido = _rotulado(t)
    if lido is None:
        lido = _envelope(t)
    if not lido.presente:
        return _NADA
    if not lido.titular:
        titular_fraco = _titular_por_heuristicas_fracas(t)
        if titular_fraco:
            lido = replace(lido, titular=titular_fraco)
    return replace(lido, logradouro=normalizar_tipo_logradouro(lido.logradouro))


__all__ = ["EnderecoLido", "UFS", "find_endereco", "normalizar_tipo_logradouro"]


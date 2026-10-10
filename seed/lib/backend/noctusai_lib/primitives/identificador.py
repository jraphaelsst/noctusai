"""Canonical identifier formats for the whole platform (CPF, CNPJ, RG, ...).

OWNER RULE (2026-10-01): the canonical reference for every document number,
id and protocol is its PUNCTUATED form (`412.954.238-98`, `30.128.742-9`,
`79.826`). A value that claims to be a document number but carries no
punctuation is CHECKED AGAINST the punctuated shape of its type to measure
whether it fits — and, where the type has a check digit, the digit decides.

Same contract as `primitives.phone`, deliberately:

- ONE shared case table (`seed/lib/shared/identificador.cases.json`) is
  asserted by Python (`tests/test_identificador.py`), TypeScript
  (`@noctusai/lib/identificador`, vitest) and the plpgsql twin
  (`seed/lib/sql/identificador.sql`, a parity block RAISEs on drift).
  Add a case to all runtimes or to none.
- It NEVER invents data. A SP RG read without its check digit is COMPLETED
  (the digit is a pure function of the other eight — arithmetic, not a
  guess); everything else unparseable is `canonico=None, cabe=False` and the
  value stays VISIBLE so a human fixes what a machine must not guess.
- Pure and deterministic: zero LLM/API cost, usable over already-stored
  extractions.
- `formatar` is THE display seam; `chave_busca` is the search key (canonical
  alnum when the value parses, RAW alnum otherwise — a fragment the user
  typed is not a valid value and must still match; see memory
  `feedback_canonicalizing_a_value_breaks_search`). Callers must put a floor
  (`CHAVE_BUSCA_MIN`) on the needle length.

This module is the ONE implementation of the CPF / CNPJ / SP-RG check-digit
algorithms; `integrations/documents/{cpf,cnpj,rg}.py` delegate here.

Public API: `ler`, `canonico`, `equivalentes`, `detectar_tipo`, `chave_busca`,
`formatar`, `extrair_cns`, plus the low-level `cpf_dv_valido`,
`cnpj_dv_valido`, `rg_sp_dv`, `mascara_cpf`, `mascara_cnpj`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Callable, Optional
from noctusai_lib.primitives.accents import fold_accents

#: Floor callers should apply to a search needle: a 2-3 char needle matching
#: canonical keys returns every row.
CHAVE_BUSCA_MIN = 4

_SEP = re.compile(r"[.\-/\s]")
_UFS = frozenset(
    "AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split()
)


@dataclass(frozen=True)
class Leitura:
    """How a raw value reads as a given identifier type.

    `canonico` is the punctuated canonical form, or None when the value does
    not fit. `cabe` — it fits the type (shape and, where it exists, the
    check digit). `dv_ok` — True/False when a check digit was verified,
    None when the type has none or none was present. `dv_completado` — the
    check digit was absent and COMPUTED (SP RG only). `motivo` — a stable
    code (`ok`, `dv_completado`, `dv_invalido`, `tamanho`, ...), asserted
    by the shared case table. `tipo_detectado` — when it does not fit but is
    a valid value of ANOTHER type (a CPF sitting in an RG field).
    """

    canonico: Optional[str]
    cabe: bool
    dv_ok: Optional[bool]
    dv_completado: bool
    motivo: str
    tipo_detectado: Optional[str] = None


def _ok(canon: str, motivo: str = "ok", dv_ok: Optional[bool] = None, completado: bool = False) -> Leitura:
    return Leitura(canon, True, dv_ok, completado, motivo, None)


def _no(motivo: str, dv_ok: Optional[bool] = None) -> Leitura:
    return Leitura(None, False, dv_ok, False, motivo, None)


# ─── text helpers ────────────────────────────────────────────────────────────


def _texto(valor: object) -> str:
    if valor is None:
        return ""
    if isinstance(valor, float) and valor.is_integer():
        valor = int(valor)  # Excel number column stringified back
    return str(valor).strip()


def _deaccent_upper(s: str) -> str:
    return fold_accents(s).upper()


def _alnum(s: str) -> str:
    return re.sub(r"[^0-9A-Z]", "", _deaccent_upper(s))


def _numerico(s: str) -> Optional[str]:
    d = _SEP.sub("", s)
    return d if re.fullmatch(r"[0-9]+", d) else None


# ─── check-digit algorithms (the single implementation) ─────────────────────


def cpf_dv_valido(digits: str) -> bool:
    """Mod-11 CPF check digits; rejects the ten repdigit strings."""
    if not re.fullmatch(r"[0-9]{11}", digits or "") or digits == digits[0] * 11:
        return False
    for tamanho in (9, 10):
        soma = sum(int(digits[i]) * (tamanho + 1 - i) for i in range(tamanho))
        resto = (soma * 10) % 11
        if (0 if resto == 10 else resto) != int(digits[tamanho]):
            return False
    return True


_PESOS_CNPJ_1 = (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)
_PESOS_CNPJ_2 = (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)


def _cnpj_digito(base: str, pesos: tuple[int, ...]) -> int:
    resto = sum((ord(c) - 48) * p for c, p in zip(base, pesos)) % 11
    return 0 if resto < 2 else 11 - resto


def cnpj_dv_valido(alnum: str) -> bool:
    """CNPJ check digits (numeric AND alphanumeric CNPJ); rejects repdigits."""
    s = alnum or ""
    if not re.fullmatch(r"[0-9A-Z]{12}[0-9]{2}", s):
        return False
    if s.isdigit() and s == s[0] * 14:
        return False
    dv1 = _cnpj_digito(s[:12], _PESOS_CNPJ_1)
    dv2 = _cnpj_digito(s[:12] + str(dv1), _PESOS_CNPJ_2)
    return s[12:] == f"{dv1}{dv2}"


def mascara_cpf(digits: str) -> Optional[str]:
    if not re.fullmatch(r"[0-9]{11}", digits or ""):
        return None
    return f"{digits[0:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:11]}"


def mascara_cnpj(alnum: str) -> Optional[str]:
    if not re.fullmatch(r"[0-9A-Z]{12}[0-9]{2}", alnum or ""):
        return None
    return f"{alnum[:2]}.{alnum[2:5]}.{alnum[5:8]}/{alnum[8:12]}-{alnum[12:]}"


def rg_sp_dv(digits8: str) -> str:
    """SP RG check digit: weights 2..9 left to right, mod 11, `10 -> X`, `11 -> 0`."""
    soma = sum(int(c) * (i + 2) for i, c in enumerate(digits8))
    dv = 11 - soma % 11
    return "X" if dv == 10 else "0" if dv == 11 else str(dv)


def _cnh_dv_ok(d: str) -> bool:
    if d == d[0] * 11:
        return False
    v = sum(int(d[i]) * (9 - i) for i in range(9))
    dsc = 0
    dv1 = v % 11
    if dv1 >= 10:
        dv1, dsc = 0, 2
    v = sum(int(d[i]) * (1 + i) for i in range(9))
    dv2 = v % 11 - dsc
    if dv2 < 0:
        dv2 += 11
    if dv2 >= 10:
        dv2 = 0
    return d[9:] == f"{dv1}{dv2}"


def _titulo_dv(seq_ou_uf_dv: str, uf: int, pesos: tuple[int, ...]) -> int:
    resto = sum(int(c) * p for c, p in zip(seq_ou_uf_dv, pesos)) % 11
    if resto == 10:
        return 0
    if resto == 0 and uf in (1, 2):  # SP / MG special case
        return 1
    return resto


def _titulo_dv_ok(d: str) -> bool:
    uf = int(d[8:10])
    if not 1 <= uf <= 28:
        return False
    dv1 = _titulo_dv(d[:8], uf, (2, 3, 4, 5, 6, 7, 8, 9))
    dv2 = _titulo_dv(d[8:10] + str(dv1), uf, (7, 8, 9))
    return d[10:] == f"{dv1}{dv2}"


def _nis_dv_ok(d: str) -> bool:
    if d == d[0] * 11:
        return False
    soma = sum(int(c) * p for c, p in zip(d[:10], (3, 2, 9, 8, 7, 6, 5, 4, 3, 2)))
    dv = 11 - soma % 11
    return d[10] == str(0 if dv >= 10 else dv)


# ─── per-type readers ────────────────────────────────────────────────────────

#: Reader context: município / IBGE for inscrição municipal, UF hint for
#: RG and órgão expedidor.
@dataclass(frozen=True)
class _Ctx:
    municipio: Optional[str] = None
    ibge: Optional[str] = None
    uf: Optional[str] = None


def _ler_cpf(s: str, ctx: _Ctx) -> Leitura:
    d = _numerico(s)
    if d is None:
        return _no("caracteres_invalidos")
    if len(d) != 11:
        return _no("tamanho")
    if not cpf_dv_valido(d):
        return _no("dv_invalido", False)
    return _ok(mascara_cpf(d) or "", dv_ok=True)


def _ler_cnpj(s: str, ctx: _Ctx) -> Leitura:
    a = _SEP.sub("", _deaccent_upper(s))
    if not re.fullmatch(r"[0-9A-Z]+", a):
        return _no("caracteres_invalidos")
    if not re.fullmatch(r"[0-9A-Z]{12}[0-9]{2}", a):
        return _no("tamanho")
    if not cnpj_dv_valido(a):
        return _no("dv_invalido", False)
    return _ok(mascara_cnpj(a) or "", dv_ok=True)


#: UF -> RG masks known. Only SP is evidenced; extend with evidence only.
_RG_UFS_CONHECIDAS = frozenset({"SP"})


def _ler_rg(s: str, ctx: _Ctx) -> Leitura:
    a = _SEP.sub("", _deaccent_upper(s))
    if ctx.uf and ctx.uf.upper() not in _RG_UFS_CONHECIDAS:
        return _no("rg_uf_sem_mascara")
    if re.fullmatch(r"[0-9]{8}", a):
        dv = rg_sp_dv(a)
        return _ok(f"{a[:2]}.{a[2:5]}.{a[5:8]}-{dv}", "dv_completado", None, True)
    if re.fullmatch(r"[0-9]{8}[0-9X]", a):
        if rg_sp_dv(a[:8]) != a[8]:
            return _no("dv_invalido", False)
        return _ok(f"{a[:2]}.{a[2:5]}.{a[5:8]}-{a[8]}", dv_ok=True)
    return _no("rg_formato_desconhecido")


def _ler_cnh(s: str, ctx: _Ctx) -> Leitura:
    d = _numerico(s)
    if d is None:
        return _no("caracteres_invalidos")
    if len(d) != 11:
        return _no("tamanho")
    if not _cnh_dv_ok(d):
        return _no("dv_invalido", False)
    return _ok(d, dv_ok=True)


def _ler_titulo(s: str, ctx: _Ctx) -> Leitura:
    d = _numerico(s)
    if d is None:
        return _no("caracteres_invalidos")
    if len(d) != 12:
        return _no("tamanho")
    if not _titulo_dv_ok(d):
        return _no("dv_invalido", False)
    return _ok(f"{d[:4]} {d[4:8]} {d[8:]}", dv_ok=True)


def _ler_nis(s: str, ctx: _Ctx) -> Leitura:
    d = _numerico(s)
    if d is None:
        return _no("caracteres_invalidos")
    if len(d) != 11:
        return _no("tamanho")
    if not _nis_dv_ok(d):
        return _no("dv_invalido", False)
    return _ok(f"{d[:3]}.{d[3:8]}.{d[8:10]}-{d[10]}", dv_ok=True)


def _ler_cep(s: str, ctx: _Ctx) -> Leitura:
    d = _numerico(s)
    if d is None:
        return _no("caracteres_invalidos")
    if len(d) != 8:
        return _no("tamanho")  # a 7-digit CEP lost a leading zero: never guess it
    return _ok(f"{d[:5]}-{d[5:]}")


def _ler_cns(s: str, ctx: _Ctx) -> Leitura:
    d = _numerico(s)
    if d is None:
        return _no("caracteres_invalidos")
    if len(d) != 6:
        return _no("tamanho")
    return _ok(f"{d[:5]}-{d[5]}")  # DV algorithm not published: dv_ok stays None


def _ler_matricula(s: str, ctx: _Ctx) -> Leitura:
    d = re.sub(r"[.\s]", "", s)
    if not re.fullmatch(r"[0-9]+", d):
        return _no("caracteres_invalidos")
    if len(d) > 9:
        return _no("tamanho")
    n = int(d)
    if n == 0:
        return _no("zero")
    return _ok(f"{n:,}".replace(",", "."))


# Inscrição municipal — per-município profiles (group sizes; optional `-D`).
_IBGE_POR_MUNICIPIO = {"COTIA": "3513009"}
_PERFIS_IM: dict[str, tuple[int, ...]] = {"3513009": (5, 2, 2, 4, 2, 3)}


def _resolver_perfil_im(ctx: _Ctx) -> Optional[tuple[int, ...]]:
    ibge = ctx.ibge
    if not ibge and ctx.municipio:
        nome = _deaccent_upper(ctx.municipio).strip()
        nome = re.sub(r"\s*[-/,]\s*[A-Z]{2}$", "", nome).strip()
        ibge = _IBGE_POR_MUNICIPIO.get(nome)
    return _PERFIS_IM.get(ibge or "")


def _mascara_im(d: str, grupos: tuple[int, ...]) -> str:
    partes, i = [], 0
    for g in grupos:
        partes.append(d[i : i + g])
        i += g
    out = ".".join(partes)
    return f"{out}-{d[i:]}" if len(d) > i else out


def _ler_im(s: str, ctx: _Ctx) -> Leitura:
    d = _numerico(s)
    if d is None:
        return _no("caracteres_invalidos")
    grupos = _resolver_perfil_im(ctx)
    if grupos is None:
        return _no("municipio_sem_perfil")
    base = sum(grupos)
    if len(d) not in (base, base + 1):
        return _no("digitos_incompativeis")
    return _ok(_mascara_im(d, grupos))


# Órgão expedidor.
_ORGAOS_COM_UF = frozenset("SSP DETRAN IFP SJS SDS SESP SEJUSP PC PM CBM DIC".split())
_ORGAOS_SEM_UF = frozenset("DPF DPMAF MD MAER MEX MAR".split())


def _parse_orgao(s: str, ctx: _Ctx) -> tuple[str, Optional[str], str]:
    up = re.sub(r"\s+", " ", _deaccent_upper(s)).strip()
    tok = [t for t in re.split(r"[\s./\-,]+", up) if t]
    if not tok:
        return up, None, "vazio"
    if tok[0] == "IIRGD" and len(tok) <= 2:
        return "SSP", "SP", "ok"
    uf_hint = ctx.uf.upper() if ctx.uf and ctx.uf.upper() in _UFS else None
    if tok[0] in _ORGAOS_COM_UF and len(tok) <= 2:
        if len(tok) == 2 and tok[1] in _UFS:
            return tok[0], tok[1], "ok"
        if len(tok) == 1:
            if uf_hint:
                return tok[0], uf_hint, "ok"
            return tok[0], None, "sem_uf"
    if tok[0] in _ORGAOS_SEM_UF and len(tok) == 1:
        return tok[0], None, "ok"
    return up, None, "desconhecido_mantido"


def _ler_orgao(s: str, ctx: _Ctx) -> Leitura:
    org, uf, motivo = _parse_orgao(s, ctx)
    if motivo == "vazio":
        return _no("vazio")
    return _ok(f"{org}/{uf}" if uf else org, motivo)


def _ler_certidao_receita(s: str, ctx: _Ctx) -> Leitura:
    a = _SEP.sub("", _deaccent_upper(s))
    if not re.fullmatch(r"[0-9A-F]{16}", a):
        return _no("tamanho" if re.fullmatch(r"[0-9A-Z]+", a) else "caracteres_invalidos")
    return _ok(".".join(a[i : i + 4] for i in range(0, 16, 4)))


def _ler_cenprot(s: str, ctx: _Ctx) -> Leitura:
    # Protocol numbers have no punctuated shape: canonical IS the digit run.
    d = _numerico(s)
    if d is None:
        return _no("caracteres_invalidos")
    return _ok(d)


_REGISTRO: dict[str, Callable[[str, _Ctx], Leitura]] = {
    "cpf": _ler_cpf,
    "cin": _ler_cpf,  # the CIN number IS the CPF number
    "cnpj": _ler_cnpj,
    "rg": _ler_rg,
    "cnh": _ler_cnh,
    "titulo_eleitor": _ler_titulo,
    "nis_pis": _ler_nis,
    "cep": _ler_cep,
    "cns_cartorio": _ler_cns,
    "matricula_imovel": _ler_matricula,
    "inscricao_municipal": _ler_im,
    "orgao_expedidor": _ler_orgao,
    "certidao_controle_receita": _ler_certidao_receita,
    "protocolo_cenprot": _ler_cenprot,
}
_ALIASES = {"cin": ("cpf",), "cpf": ("cin",)}

#: Types whose check digit makes them detectable inside a foreign field.
_DETECTAVEIS_DV = ("cpf", "cnpj", "cnh", "nis_pis", "titulo_eleitor")


def tipos() -> tuple[str, ...]:
    return tuple(_REGISTRO)


def _detectar(s: str) -> list[str]:
    ctx = _Ctx()
    achados = []
    for t in _DETECTAVEIS_DV:
        r = _REGISTRO[t](s, ctx)
        if r.cabe and r.dv_ok:
            achados.append(t)
    if re.fullmatch(r"[0-9]{5}-[0-9]{3}", s):
        achados.append("cep")
    if re.fullmatch(r"[0-9]{1,2}\.[0-9]{3}\.[0-9]{3}-[0-9X]", s.upper()):
        r = _ler_rg(s, ctx)
        if r.cabe and r.dv_ok:
            achados.append("rg")
    return achados


#: Why an RG-claiming value is refused on an AUTOMATIC (extraction) write even
#: though no other type's check digit proves it is something else.
RG_ANOMALIA_FORMA_DE_CPF = "forma_de_cpf"
RG_ANOMALIA_TRUNCADO = "truncado"


def rg_anomalia(valor: object, *, uf: Optional[str] = None) -> Optional[str]:
    """`forma_de_cpf` / `truncado` when `valor` read as an RG is the WRONG KIND
    of value, else None. Complements `ler(...).tipo_detectado`, which only
    catches a value whose OTHER type's check digit verifies:

    - `forma_de_cpf`: eleven digits (or the `000.000.000-00` mask) that fail
      the CPF check digit — a misread CPF — or any CPF-shaped run in the RG
      field. A VALID CPF equal to the holder's own is the CIN convention and
      is decided by the caller (`cpf_proprio`), not here.
    - `truncado`: a bare 6-7 digit run (a 7-digit RG is one digit short of
      the SP body, a 6-digit one two) where the SP mask needs eight digits — only judged when the
      órgão's UF is SP or unknown, since other states' RG shapes are not
      evidenced (`_RG_UFS_CONHECIDAS`).
    Pure, never raises. Never rewrites the value.
    """
    s = _texto(valor)
    if not s:
        return None
    a = _SEP.sub("", _deaccent_upper(s))
    if re.fullmatch(r"[0-9]{11}", a) and not re.search(r"[A-Za-z]", s):
        return RG_ANOMALIA_FORMA_DE_CPF
    if uf and uf.upper() not in _RG_UFS_CONHECIDAS:
        return None
    if re.fullmatch(r"[0-9]{6,7}", a):
        return RG_ANOMALIA_TRUNCADO
    return None


def detectar_tipo(valor: object) -> list[str]:
    """Types this value is a VALID instance of (check-digit-backed, or an
    exact punctuated CEP / SP-RG shape). `297.556.088-50` -> `['cpf']`."""
    s = _texto(valor)
    return _detectar(s) if s else []


def _leitor(tipo: str) -> Callable[[str, _Ctx], Leitura]:
    try:
        return _REGISTRO[tipo]
    except KeyError:
        raise ValueError(f"tipo de identificador desconhecido: {tipo!r}") from None


def ler(
    tipo: str,
    valor: object,
    *,
    municipio: Optional[str] = None,
    ibge: Optional[str] = None,
    uf: Optional[str] = None,
) -> Leitura:
    """Read `valor` as identifier `tipo` — see `Leitura`."""
    leitor = _leitor(tipo)
    s = _texto(valor)
    if not s:
        return _no("vazio")
    r = leitor(s, _Ctx(municipio, ibge, uf))
    if not r.cabe and r.dv_ok is None:
        det = [t for t in _detectar(s) if t != tipo and t not in _ALIASES.get(tipo, ())]
        if det:
            r = replace(r, tipo_detectado=det[0])
    return r


def canonico(tipo: str, valor: object, **ctx: Optional[str]) -> Optional[str]:
    return ler(tipo, valor, **ctx).canonico


def formatar(tipo: str, valor: object, **ctx: Optional[str]) -> str:
    """THE display seam: canonical form when it fits, else the raw value as
    stored (so a human can see and fix it)."""
    c = ler(tipo, valor, **ctx).canonico
    return c if c is not None else _texto(valor)


def chave_busca(tipo: str, valor: object, **ctx: Optional[str]) -> Optional[str]:
    """Search key: canonical alnum when the value parses, RAW alnum otherwise."""
    c = ler(tipo, valor, **ctx).canonico
    k = _alnum(c if c is not None else _texto(valor))
    return k or None


def _im_partes(r: Leitura) -> tuple[str, Optional[str]]:
    c = r.canonico or ""
    return (c[:23], c[24:] or None) if len(c) > 23 else (c, None)


def equivalentes(tipo: str, a: object, b: object, **ctx: Optional[str]) -> Optional[bool]:
    """True: same identifier · False: different · None: undecidable."""
    la, lb = ler(tipo, a, **ctx), ler(tipo, b, **ctx)
    ra, rb = _alnum(_texto(a)), _alnum(_texto(b))
    if not ra or not rb:
        return None
    if tipo == "orgao_expedidor":
        oa, ua, _ = _parse_orgao(_texto(a), _Ctx(None, None, ctx.get("uf")))
        ob, ub, _ = _parse_orgao(_texto(b), _Ctx(None, None, ctx.get("uf")))
        if oa != ob:
            return False
        if ua is None or ub is None:
            return None if (oa in _ORGAOS_COM_UF) else True
        return ua == ub
    if tipo == "inscricao_municipal":
        if la.canonico and lb.canonico:
            ba, da = _im_partes(la)
            bb, db = _im_partes(lb)
            if ba != bb:
                return False
            return False if (da and db and da != db) else True
        if la.motivo == "municipio_sem_perfil" and lb.motivo == "municipio_sem_perfil":
            da, db = _numerico(_texto(a)) or "", _numerico(_texto(b)) or ""
            if da and da == db:
                return True
            if da and db and (da.startswith(db) or db.startswith(da)):
                return None
            return False if da and db else None
    if la.canonico and lb.canonico:
        return la.canonico == lb.canonico
    if ra == rb:
        return True
    if (la.canonico and lb.dv_ok is False) or (lb.canonico and la.dv_ok is False):
        return False
    return None


# ─── CNS (cartório) extraction ───────────────────────────────────────────────

_CNS_RE = re.compile(r"\bC\.?\s?N\.?\s?S\.?\s*[:\-.Nº°O]*\s*([0-9]{2}\.?[0-9]{3}\s?-?\s?[0-9])(?![0-9])")


def extrair_cns(texto: object) -> Optional[str]:
    """The cartório CNS (`11991-7`) found in free text such as `SERVENTIA DO
    REGISTRO DE IMÓVEIS de Cotia - CNS: 11991-7`. Two DIFFERENT CNS in one
    text is absence, not a vote: returns None."""
    achados = {
        c
        for m in _CNS_RE.finditer(_deaccent_upper(_texto(texto)))
        if (c := _ler_cns(m.group(1), _Ctx()).canonico)
    }
    return next(iter(achados)) if len(achados) == 1 else None


__all__ = [
    "CHAVE_BUSCA_MIN",
    "Leitura",
    "canonico",
    "chave_busca",
    "cnpj_dv_valido",
    "cpf_dv_valido",
    "detectar_tipo",
    "equivalentes",
    "extrair_cns",
    "formatar",
    "ler",
    "mascara_cnpj",
    "mascara_cpf",
    "RG_ANOMALIA_FORMA_DE_CPF",
    "RG_ANOMALIA_TRUNCADO",
    "rg_anomalia",
    "rg_sp_dv",
    "tipos",
]

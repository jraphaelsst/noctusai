"""Escrita humana: the deterministic "anti-AI-slop" checker (pt-BR). Pure: text in, failure codes out, no IO.

``checar_escrita(texto, perfil=..., registro=...)`` returns CODES (empty list == pass), never prose. The word lists and
every threshold are DATA in the sibling ``escrita_humana.json`` (house proposals, to be calibrated against real
creator transcripts; see its ``_nota``). Matching is accent-insensitive (``fold_accents``) and whole-word only
("vaga" never hits inside "devagar").

Perfis: ``chat`` (WhatsApp-style bubble), ``roteiro`` (spoken script/slide text), ``legenda`` (post caption),
``headline`` (one line). Registros: ``informal`` (default; "pra", "tá", "tô" allowed) and ``formal`` (also flags them).

Codes: ``travessao:N`` · ``contraste_nao_e:N`` · ``triade:N`` · ``lexico_ia:a,b`` · ``abertura_bajuladora`` ·
``fechamento_cliche`` · ``aspas_curvas`` · ``title_case`` · ``markdown_no_chat`` · ``emoji_excesso:N`` ·
``conectivos_densos:D`` · ``conectivos_consecutivos`` · ``giria:a,b`` · roteiro rhythm: ``frases_curtas:R`` (share of
spoken sentences under 8 words), ``abertura_repetida:xx`` (two consecutive blocks opening alike),
``ritmo_uniforme:CV`` and ``frases_muito_curtas:k/n``.

A roteiro's format-required markup (``**Slide 1 — nome**``, ``**Quadro 1 — nome**``, ``**Tela 1**``, ``###`` headers,
``(Gancho)`` labels) is stripped by ``texto_falado`` first, so only the spoken/slide TEXT is judged.

Evidence the design rests on:
- Wikipedia, "Signs of AI writing" https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing (em dash as a now
  "historical" indicator; negative parallelism; rule of three; AI-vocabulary clusters; collaborative-communication
  boilerplate; curly quotes; Title Case);
- Kobak et al., excess vocabulary https://arxiv.org/abs/2406.07016 ;
- Fast Company Brasil on the 2026 Economist study (only Claude still over-uses the em dash)
  https://fastcompanybrasil.com/ia/esqueca-o-travessao-esses-sinais-entregam-se-um-texto-foi-feito-por-ia/ ;
- pt.wikipedia, "Sinais de texto gerado por inteligência artificial".
"""
from __future__ import annotations

import json
import re
import statistics
from functools import lru_cache
from importlib import resources
from typing import Any, Iterable, Literal

from noctusai_lib.primitives.accents import fold_accents

Perfil = Literal["chat", "roteiro", "legenda", "headline"]
Registro = Literal["formal", "informal"]
PERFIS = ("chat", "roteiro", "legenda", "headline")
REGISTROS = ("formal", "informal")


def _f(t: str) -> str:
    return fold_accents(t).casefold()


@lru_cache(maxsize=1)
def config() -> dict[str, Any]:
    """The thresholds/word lists (``escrita_humana.json``), loaded once."""
    return json.loads(resources.files(__package__).joinpath("escrita_humana.json").read_text(encoding="utf-8"))


def _alternancia(termos: Iterable[str], sufixo_plural: bool = False) -> re.Pattern[str]:
    partes = sorted((re.escape(_f(t)).replace(r"\ ", r"\s+") for t in termos), key=len, reverse=True)
    fim = "s?" if sufixo_plural else ""
    return re.compile(r"(?<!\w)(" + "|".join(partes) + r")" + fim + r"(?!\w)")


@lru_cache(maxsize=1)
def _rx() -> dict[str, re.Pattern[str]]:
    c = config()
    return {
        "lexico": _alternancia(c["lexico_ia"]["termos"], True),
        "conectivo": _alternancia(c["conectivos"]["termos"]),
    }


_PALAVRA = re.compile(r"\w+(?:[-']\w+)*", re.UNICODE)
_TRAVESSAO_EM = re.compile("—")
_FAIXA_NUM = re.compile(r"(?<=\d)\s*–\s*(?=\d)")
_ASPAS_CURVAS = re.compile("[“”‘’]")
_EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF☀-➿⬀-⯿⌀-⏿←-⇿⤀-⥿\U0001F900-\U0001F9FF]"
)
_CONTRASTE = (
    re.compile(r"(?<!\w)n[ãa]o é(?!\w)[^.!?;\n]{1,80}?,\s*é(?!\w)"),
    re.compile(r"(?<!\w)n[ãa]o é(?!\w)[^.!?\n]{1,80}[.!?]\s+é(?!\w)"),
    re.compile(r"(?<!\w)n[ãa]o se trata\b[^.!?\n]{1,100}?(?<!\w)(?:mas|e sim)(?!\w)"),
    re.compile(r"(?<!\w)n[ãa]o (?:s[óo]|apenas|somente)(?!\w)[^.!?\n]{1,100}?(?<!\w)mas(?!\w)"),
)
_MD_NEGRITO = re.compile(r"\*\*|__")
_MD_LISTA = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+\S", re.MULTILINE)
_MD_CABECALHO = re.compile(r"^\s*#{1,6}\s", re.MULTILINE)

# structure the SW roteiro grammar REQUIRES (and may carry an em dash): never judged as writing
_EST_NEGRITO = re.compile(r"^\s*\*\*\s*(?:slide|quadro|tela)\s+\d+\s*(?:[—–-][^*\n]*)?\*\*[ \t]*(.*)$", re.IGNORECASE)
_EST_TRACO = re.compile(r"^\s*(?:slide|quadro|tela)\s+\d+\s*[—–-].*$", re.IGNORECASE)
_EST_NU = re.compile(r"^\s*(?:slide|quadro|tela)\s+\d+\s*:?\s*$", re.IGNORECASE)
_EST_CAB = re.compile(r"^\s*#{1,6}\s.*$")
_ROTULO = re.compile(r"\([^)\n]{1,40}\)|\[[^\]\n]*\]")


def texto_falado(texto: str) -> str:
    """A roteiro body without its format markup: the ``Slide/Quadro/Tela n`` label lines (text after a ``**Tela 1**``
    label is kept), ``###`` headers and ``(Gancho)``-style block labels. What is left is the spoken/slide text."""
    saida: list[str] = []
    for ln in (texto or "").split("\n"):
        m = _EST_NEGRITO.match(ln)
        if m:
            ln = m.group(1)
        elif _EST_TRACO.match(ln) or _EST_NU.match(ln) or _EST_CAB.match(ln):
            continue
        saida.append(_ROTULO.sub(" ", ln))
    return "\n".join(saida)


def palavras(texto: str) -> list[str]:
    return _PALAVRA.findall(texto or "")


def frases(corpo: str) -> list[str]:
    """Sentences of a spoken body (bullets, ``[..]`` and ``(..)`` labels dropped)."""
    limpo = re.sub(r"^\s*[-*•]\s+|\[[^\]]*\]|\([^)]*\)", " ", corpo or "", flags=re.MULTILINE)
    return [f.strip() for f in re.split(r"(?<=[.!?…])\s+|\n+", limpo) if len(f.split()) >= 1]


def blocos(corpo: str) -> list[str]:
    return [b.strip() for b in re.split(r"\n\s*\n", corpo or "") if b.strip()]


def _sem_marcas(f: str) -> str:
    return re.sub(r"[\*_#>]+", "", f).strip(" \t\"'“”‘’.,;:!?…-")


# ── the checks ────────────────────────────────────────────────────────────────────────────────────────────

def _travessao(texto: str) -> list[str]:
    n = len(_TRAVESSAO_EM.findall(texto))
    sem_faixas = _FAIXA_NUM.sub(" ", texto)
    n += sum(1 for c in sem_faixas if c == "–")
    return [f"travessao:{n}"] if n > config()["travessao"]["max"] else []


def _contraste(texto: str, perfil: str) -> list[str]:
    c = config()["contraste"]
    t = texto.casefold()
    n = sum(len(rx.findall(t)) for rx in _CONTRASTE)
    limite = c["max_headline"] if perfil == "headline" else c["max_outros"]
    return [f"contraste_nao_e:{n}"] if n > limite else []


def _triades(texto: str) -> int:
    c = config()["triade"]
    saud = {_f(s) for s in c["saudacoes"]}
    n = 0
    for fr in re.split(r"(?<=[.!?…])\s+|\n+", texto):
        if "?" in fr:
            continue
        corpo = fr.split(":")[-1].strip(" .!…")
        if "," not in corpo:
            continue
        m = re.match(r"^(.*)\s+(?:e|ou)\s+(.*)$", corpo)
        if not m:
            continue
        itens = [i.strip() for i in m.group(1).split(",")] + [m.group(2).strip()]
        itens = [i for i in itens if i]
        if len(itens) < 3 or _f(itens[0].strip(" ,")) in saud:
            continue
        if all(1 <= len(palavras(i)) <= c["max_palavras_item"] for i in itens):
            n += 1
    return n


def _triade(texto: str, perfil: str) -> list[str]:
    c = config()["triade"]
    n = _triades(texto)
    limite = c["max_headline"] if perfil == "headline" else c["max_outros"]
    return [f"triade:{n}"] if n > limite else []


def _lexico(texto: str, perfil: str) -> list[str]:
    c = config()["lexico_ia"]
    achados = [m.group(1) for m in _rx()["lexico"].finditer(_f(texto))]
    if not achados:
        return []
    n_pal = max(1, len(palavras(texto)))
    permitido = 0 if perfil == "headline" else n_pal / c["palavras_por_ocorrencia"]
    if len(achados) > permitido:
        return ["lexico_ia:" + ",".join(sorted({re.sub(r"\s+", " ", a) for a in achados}))]
    return []


def _abertura_fechamento(texto: str) -> list[str]:
    c = config()
    fr = [f for f in frases(texto) if _sem_marcas(f)]
    if not fr:
        return []
    out: list[str] = []
    primeira = _f(_sem_marcas(fr[0]))
    if any(primeira.startswith(_f(a)) for a in c["aberturas"]) or primeira in {_f(a) for a in c["aberturas_exatas"]}:
        out.append("abertura_bajuladora")
    ultima = _f(_sem_marcas(fr[-1]))
    if any(_f(x) in ultima for x in c["fechamentos"]):
        out.append("fechamento_cliche")
    return out


def _title_case(texto: str, nomes: set[str]) -> list[str]:
    c = config()["title_case"]
    stop = {_f(s) for s in c["stopwords"]}
    caps = total = 0
    for fr in re.split(r"(?<=[.!?…])\s+|\n+", _ROTULO.sub(" ", texto)):
        pals = palavras(fr)
        for p in pals[1:]:
            fp = _f(p)
            if fp in stop or fp in nomes:
                continue
            total += 1
            if p[0].isupper() and not (len(p) > 1 and p.isupper()):
                caps += 1
    if caps >= c["min_palavras"] and total and caps / total >= c["min_razao"]:
        return ["title_case"]
    return []


def _markdown(texto: str) -> list[str]:
    return ["markdown_no_chat"] if _MD_NEGRITO.search(texto) or _MD_LISTA.search(texto) or _MD_CABECALHO.search(texto) else []


def _emoji(texto: str, perfil: str) -> list[str]:
    n = len(_EMOJI.findall(texto))
    return [f"emoji_excesso:{n}"] if n > config()["emoji_max"][perfil] else []


def _conectivos(texto: str) -> list[str]:
    c = config()["conectivos"]
    t = _f(texto)
    n = len(_rx()["conectivo"].findall(t))
    n_pal = max(1, len(palavras(texto)))
    out: list[str] = []
    if n > max(1.0, n_pal * c["max_por_100_palavras"] / 100):
        out.append(f"conectivos_densos:{n / n_pal:.2f}")
    abre = [bool(_rx()["conectivo"].match(_f(_sem_marcas(f)))) for f in frases(texto)]
    if any(a and b for a, b in zip(abre, abre[1:])):
        out.append("conectivos_consecutivos")
    return out


def checar_ritmo(corpo: str) -> list[str]:
    """Rhythm of ONE spoken body (codes without a roteiro prefix): enough short sentences, varied lengths, no two
    consecutive blocks opening with the same words. (This is the former ``criacao.saida.checar_humanizacao`` core.)"""
    r = config()["ritmo"]
    out: list[str] = []
    fr = frases(corpo)
    if fr:
        tam = [len(f.split()) for f in fr]
        curtas = sum(1 for n in tam if n < r["frase_curta_palavras"]) / len(tam)
        if curtas < r["frases_curtas_share_min"]:
            out.append(f"frases_curtas:{curtas:.2f}")
        if len(tam) >= r["min_frases"]:
            media = statistics.fmean(tam)
            cv = statistics.pstdev(tam) / media if media else 0.0
            if cv < r["cv_min"]:
                out.append(f"ritmo_uniforme:{cv:.2f}")
            muito = sum(1 for n in tam if n <= r["curta_palavras"])
            if muito < len(tam) // r["curta_a_cada"]:
                out.append(f"frases_muito_curtas:{muito}/{len(tam)}")
    ab = [" ".join(_f(b).split()[: r["abertura_palavras"]]) for b in blocos(corpo)]
    for a, b in zip(ab, ab[1:]):
        if a and a == b:
            out.append(f"abertura_repetida:{a}")
    return out


def _giria(texto: str, registro: str) -> list[str]:
    g = config()["giria"]
    alvos = list(g["sempre"]) + (list(g["so_formal"]) if registro == "formal" else [])
    t = _f(texto)
    achados = {m.group(1) for m in _alternancia(alvos).finditer(t)}
    if re.search(r"(?<!\w)k{3,}(?!\w)", t):
        achados.add("kkk")
    return ["giria:" + ",".join(sorted(achados))] if achados else []


def checar_escrita(
    texto: str, *, perfil: Perfil, registro: Registro = "informal", nomes_proprios: Iterable[str] = (),
) -> list[str]:
    """Every deterministic anti-slop check of ``texto`` for ``perfil``. ``nomes_proprios`` (caller allowlist) are not
    counted as Title Case. Empty list == pass."""
    if perfil not in PERFIS:
        raise ValueError(f"perfil desconhecido: {perfil!r}")
    if registro not in REGISTROS:
        raise ValueError(f"registro desconhecido: {registro!r}")
    bruto = texto or ""
    if perfil == "roteiro":
        bruto = texto_falado(bruto)
    if not bruto.strip():
        return []
    out: list[str] = []
    out += _travessao(bruto)
    out += _contraste(bruto, perfil)
    out += _triade(bruto, perfil)
    out += _lexico(bruto, perfil)
    out += _abertura_fechamento(bruto)
    if _ASPAS_CURVAS.search(bruto):
        out.append("aspas_curvas")
    if perfil in config()["title_case"]["perfis"]:
        out += _title_case(bruto, {_f(n) for n in nomes_proprios})
    if perfil == "chat":
        out += _markdown(bruto)
    out += _emoji(bruto, perfil)
    out += _conectivos(bruto)
    if perfil == "roteiro":
        out += checar_ritmo(bruto)
    out += _giria(bruto, registro)
    return out


__all__ = ["PERFIS", "REGISTROS", "blocos", "checar_escrita", "checar_ritmo", "config", "frases", "palavras", "texto_falado"]

"""The note we leave in Vista with every edit (owner 2026-11-04: "we shall never edit vista data without a reason and without
leaving a note behind").

The team's internal log lives in the property field `ObsVenda` (sale) -- `ObsLocacao` is presumably the rental twin (no sample seen;
verify with `listarcampos`/`detalhes` before relying on it). Its shape: HEADER lines first (lote/quadra/address, partner code,
owner contact), then a dated log, NEWEST FIRST, one line each: `DD/MM/YY <fonte> informa <o que>. (<autor>)`. Variants exist
(`DD/MM/YYYY - texto (CY)`, `DD/MM/YY: texto`), so a dated line is detected by a leading `\\d{2}/\\d{2}/\\d{2,4}`.

OUR line (one line, no phone, no e-mail):
    DD/MM/YY <fonte> informa via <canal>: <campo> <antes> → <depois>. <motivo>. Conversa: <url> (<autor>)
is inserted just BEFORE the first dated line; with none, appended after the header with one blank line between; an empty field
becomes just the line. Header text is never modified. Pure functions, shared by `VistaClient` and `FakeVistaClient`.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any, Mapping, Optional

OBS_VENDA = "ObsVenda"
OBS_LOCACAO = "ObsLocacao"
_DATADA = re.compile(r"^\s*\d{2}/\d{2}/\d{2,4}")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_TEL = re.compile(r"\+?\d[\d\s().-]{8,}\d")


def campo_obs(finalidade: str) -> str:
    """The internal-observations field for a finalidade (`venda` | `locacao`)."""
    f = (finalidade or "venda").strip().lower()
    if f in ("locacao", "locação", "aluguel"):
        return OBS_LOCACAO
    if f in ("venda", "venda e aluguel"):
        return OBS_VENDA
    raise ValueError(f"finalidade {finalidade!r}: use venda ou locacao")


def _limpo(texto: Any) -> str:
    """One line, no phone, no e-mail."""
    return " ".join(_TEL.sub("[telefone]", _EMAIL.sub("[e-mail]", str(texto if texto is not None else ""))).split())


def exigir_motivo(motivo: Optional[str], autor: Optional[str]) -> tuple[str, str]:
    m, a = _limpo(motivo).rstrip(". "), _limpo(autor)
    if not m:
        raise ValueError("a Vista edit needs a non-empty `motivo` (the reason is written into the property's internal observations)")
    if not a:
        raise ValueError("a Vista edit needs an `autor` label (who/what makes the edit)")
    return m, a


def montar_linha(
    *, fonte: str, canal: str, campo: str, antes: Any, depois: Any, motivo: str, autor: str,
    conversa_url: Optional[str] = None, hoje: Optional[date] = None,
) -> str:
    """The one-line note for a single field change."""
    return _linha_multipla([f"{_limpo(campo)} {_limpo(antes) or '—'} → {_limpo(depois) or '—'}"], fonte, canal, motivo, autor, conversa_url, hoje)


def inserir_linha(atual: Optional[str], linha: str) -> str:
    """`atual` (the field as Vista holds it NOW) with `linha` placed before its first dated line; header untouched."""
    linhas = (atual or "").replace("\r\n", "\n").split("\n")
    if not any(l.strip() for l in linhas):
        return linha
    for i, l in enumerate(linhas):
        if _DATADA.match(l):
            return "\n".join([*linhas[:i], linha, *linhas[i:]])
    return "\n".join([*(linhas[:-1] if not linhas[-1].strip() else linhas), "", linha])


def compor_campos(
    campos: Mapping[str, Any], atual: Mapping[str, Any], *, finalidade: str, fonte: str, canal: str, motivo: str, autor: str,
    conversa_url: Optional[str] = None, rotulos: Optional[Mapping[str, str]] = None, hoje: Optional[date] = None,
) -> tuple[dict[str, Any], str]:
    """`(fields to PUT, the note line)`: `campos` plus the updated Obs field, built from `atual` (the CURRENT detalhes record)."""
    exigir_motivo(motivo, autor)
    obs = campo_obs(finalidade)
    partes = [f"{(rotulos or {}).get(k, k)} {_limpo(atual.get(k)) or '—'} → {_limpo(v) or '—'}" for k, v in campos.items()]
    linha = _linha_multipla(partes, fonte, canal, motivo, autor, conversa_url, hoje)
    return {**campos, obs: inserir_linha(atual.get(obs), linha)}, linha


def _linha_multipla(partes: list[str], fonte: str, canal: str, motivo: str, autor: str, conversa_url: Optional[str], hoje: Optional[date]) -> str:
    m, a = exigir_motivo(motivo, autor)
    d = (hoje or date.today()).strftime("%d/%m/%y")
    corpo = f"{d} {_limpo(fonte) or 'NoctusAI'} informa via {_limpo(canal) or 'NoctusAI'}: {'; '.join(partes)}. {m}."
    if conversa_url:
        corpo += f" Conversa: {_limpo(conversa_url)}"
    return f"{corpo} ({a})"

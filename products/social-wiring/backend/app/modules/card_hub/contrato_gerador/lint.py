"""Post-render lint (spec §4.6) — runs on the GENERATED text; any hit blocks saving.

Numbers and references are computed, so in a correct build this finds
nothing. It exists because "computed" is a claim about the code, and the
document is what gets signed: each rule below names the sample-contract
error it would have caught.
"""
from __future__ import annotations

import re
from typing import Mapping, Sequence

from noctusai_lib.domain.texto_ptbr import (
    ordinal_por_extenso,
    parse_brl,
    reais_por_extenso,
)

from app.modules.card_hub.contrato_gerador.numeracao import TITULO_CLAUSULA, letra

_MAX = 60
_ORD_FEM_UPPER = {ordinal_por_extenso(n, feminino=True).upper(): n for n in range(1, _MAX)}
_ORD_FEM_LOWER = {ordinal_por_extenso(n, feminino=True): n for n in range(1, _MAX)}
_ORD_MASC_TITLE = {ordinal_por_extenso(n).title(): n for n in range(1, _MAX)}

_RE_HEADING = re.compile(r"^CLÁUSULA (.+?) [–-] (.+)$")
_RE_REF = re.compile(r"[Cc]láusula ([A-Za-zÀ-ÿ]+)(?: ([A-Za-zÀ-ÿ]+))?")
_RE_PAR = re.compile(r"^Parágrafo ([A-Za-zÀ-ÿ]+(?: [A-Za-zÀ-ÿ]+)?):")
_RE_PARCELA_DEF = re.compile(r"^Parcela (\d{2}):")
_RE_PARCELA_REF = re.compile(r"[Pp]arcelas? (\d{2}(?:(?:, | e )\d{2})*)")
_RE_LETRA = re.compile(r"^([a-z]{1,2})-\) ")
_RE_BRL = re.compile(r"R\$ ([\d.]+,\d{2}) \(([^)]*)\)")
_RE_ANO5 = re.compile(r"\b\d{2}/\d{2}/\d{5,}\b")


def _hit(hits: list[dict], codigo: str, mensagem: str) -> None:
    hits.append({"codigo": codigo, "mensagem": mensagem})


def _checar_paragrafos(hits: list[dict], clausula: int, rotulos: list[str]) -> None:
    """Restart per clause, consecutive, "Único" only alone (06 and 01's ¶1→¶3)."""
    if not rotulos:
        return
    if len(rotulos) == 1:
        if rotulos[0] != "Único":
            _hit(hits, "PARAGRAFO_UNICO", f"Cláusula {clausula}: parágrafo solitário deveria ser 'Único'.")
        return
    for i, rotulo in enumerate(rotulos, start=1):
        if _ORD_MASC_TITLE.get(rotulo) != i:
            _hit(hits, "PARAGRAFO_FORA_DE_SEQUENCIA", f"Cláusula {clausula}: 'Parágrafo {rotulo}' na posição {i}.")


def lint(
    paragrafos: Sequence[str],
    *,
    referencias: Mapping[str, int],
    clausulas: Mapping[str, int],
) -> list[dict]:
    hits: list[dict] = []
    titulos: dict[int, str] = {}
    esperado = 1
    atual = 0
    rotulos: list[str] = []
    ocorrencias: dict[int, int] = {}
    parcelas_definidas: set[str] = set()
    parcelas_citadas: set[str] = set()
    letras: list[str] = []

    def fechar_letras() -> None:
        if letras and letras != [letra(i) for i in range(len(letras))]:
            _hit(hits, "LETRAS_COM_LACUNA", f"Lista de pendências com letras fora de ordem: {'-'.join(letras)}.")
        letras.clear()

    for i, texto in enumerate(paragrafos):
        for proibido in ("{{", "{%", "…………"):
            if proibido in texto:
                _hit(hits, "MARCADOR_NAO_RENDERIZADO", f"Parágrafo {i + 1} contém '{proibido}'.")
        if _RE_ANO5.search(texto):
            _hit(hits, "ANO_INVALIDO", f"Parágrafo {i + 1} tem uma data com ano de 5 dígitos.")
        for m in _RE_BRL.finditer(texto):
            try:
                valor = parse_brl(m.group(1))
            except ValueError:
                _hit(hits, "VALOR_INVALIDO", f"Valor ilegível: R$ {m.group(1)}.")
                continue
            if reais_por_extenso(valor) != m.group(2):
                _hit(hits, "EXTENSO_DIVERGENTE", f"R$ {m.group(1)} não confere com '({m.group(2)})'.")

        if texto.rstrip().endswith("a seguir:"):
            seguinte = paragrafos[i + 1] if i + 1 < len(paragrafos) else ""
            if not seguinte.strip() or _RE_HEADING.match(seguinte):
                _hit(hits, "LISTA_VAZIA", f"Parágrafo {i + 1} anuncia itens 'a seguir' e nada segue.")

        m_letra = _RE_LETRA.match(texto)
        if m_letra:
            letras.append(m_letra.group(1))
        else:
            fechar_letras()

        m_def = _RE_PARCELA_DEF.match(texto)
        if m_def:
            parcelas_definidas.add(m_def.group(1))
        for m in _RE_PARCELA_REF.finditer(texto):
            parcelas_citadas.update(re.findall(r"\d{2}", m.group(1)))

        cab = _RE_HEADING.match(texto)
        if cab:
            _checar_paragrafos(hits, atual, rotulos)
            rotulos = []
            n = _ORD_FEM_UPPER.get(cab.group(1))
            if n is None:
                _hit(hits, "CLAUSULA_ORDINAL_INVALIDO", f"Título de cláusula ilegível: '{cab.group(1)}'.")
                continue
            if n in titulos:
                _hit(hits, "CLAUSULA_DUPLICADA", f"Duas cláusulas numeradas {cab.group(1)}.")
            elif n != esperado:
                _hit(hits, "CLAUSULA_FORA_DE_SEQUENCIA", f"Esperada a cláusula {esperado}, encontrada {cab.group(1)}.")
            titulos[n] = cab.group(2)
            esperado = n + 1
            atual = n
            continue

        m_par = _RE_PAR.match(texto)
        if m_par:
            rotulos.append(m_par.group(1))
        for m in _RE_REF.finditer(texto):
            duas = f"{m.group(1)} {m.group(2)}".lower() if m.group(2) else None
            n = _ORD_FEM_LOWER.get(duas) if duas else None
            if n is None:
                n = _ORD_FEM_LOWER.get(m.group(1).lower())
            if n is not None:
                ocorrencias[n] = ocorrencias.get(n, 0) + 1
    _checar_paragrafos(hits, atual, rotulos)
    fechar_letras()

    for n in ocorrencias:
        if n not in titulos:
            _hit(hits, "REFERENCIA_CLAUSULA_INEXISTENTE", f"O texto cita a cláusula {n}, que não existe.")
    esperadas: dict[int, int] = {}
    for chave, vezes in referencias.items():
        if not vezes:
            continue
        n = clausulas.get(chave)
        if n is None:
            _hit(hits, "REFERENCIA_CLAUSULA_EXCLUIDA", f"Referência à cláusula '{chave}', que não foi incluída.")
            continue
        esperadas[n] = esperadas.get(n, 0) + vezes
        if not titulos.get(n, "").startswith(TITULO_CLAUSULA[chave]):
            _hit(hits, "REFERENCIA_TOPICO", f"A referência a '{chave}' aponta para a cláusula {n}, de outro assunto.")
    if ocorrencias != esperadas:
        _hit(hits, "REFERENCIA_CLAUSULA_ERRADA", "As citações de cláusulas no texto não batem com as referências geradas.")

    faltantes = sorted(parcelas_citadas - parcelas_definidas)
    if faltantes:
        _hit(hits, "REFERENCIA_PARCELA_INEXISTENTE", f"O texto cita parcelas inexistentes: {', '.join(faltantes)}.")
    return hits


__all__ = ["lint"]

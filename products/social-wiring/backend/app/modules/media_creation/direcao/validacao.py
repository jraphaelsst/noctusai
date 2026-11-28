"""The decision-free guards of a production run. Pure functions.

Two families, both already decided by the owner's standing rules (so they bind every future planner / generator / renderer):

* :func:`validar_plano` -- the plan is anchored by WORD ID and adds NO new text (``diretor-de-edicao`` hard rules: "no new
  content", "text on screen equals a transcript span or an approved string"). What it deliberately does NOT enforce is the
  composition: scenes may overlap, leave gaps or nest -- storytelling is open, so coverage is MEASURED (:func:`cobertura`),
  not required.
* :func:`avaliar_medicoes` -- the checks of ``script-to-media-production.md`` section 4 against the owner's defaults
  (``video-edit-spec.md`` section 6: -14 LUFS / -1.5 dBTP, 9:16). A core measurement that is missing is a FAILURE
  (``nao_medido``), never a pass: the agent cannot hear or see the render. Hook / sync, when the montador did not measure
  them, are advisories carried in the review package, not blockers.

Violations carry stable codes and never echo script or plan text.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from app.modules.media_creation.direcao.tipos import EntradaCongelada, PlanoDeCenas, Violacao

_PUNCT = re.compile(r"[^\w]+", re.UNICODE)


def _tokens(texto: str) -> list[str]:
    return _PUNCT.sub(" ", unicodedata.normalize("NFC", texto)).casefold().split()


def _contem_subsequencia(fala: list[str], trecho: list[str]) -> bool:
    n = len(trecho)
    return n > 0 and any(fala[i : i + n] == trecho for i in range(len(fala) - n + 1))


def _indice(entrada: EntradaCongelada) -> dict[str, int]:
    return {p.id: i for i, p in enumerate(entrada.palavras)}


def validar_plano(entrada: EntradaCongelada, plano: PlanoDeCenas) -> list[Violacao]:
    if not plano.cenas:
        return [Violacao("plano_sem_cenas")]
    out: list[Violacao] = []
    idx = _indice(entrada)
    fala = _tokens(" ".join(p.texto for p in entrada.palavras))
    permitidos = {tuple(_tokens(r)) for r in plano.rotulos_aprovados}
    vistos: set[str] = set()
    for c in plano.cenas:
        if c.id in vistos:
            out.append(Violacao("cena_id_duplicado", c.id))
        vistos.add(c.id)
        ini, fim = idx.get(c.palavra_inicio), idx.get(c.palavra_fim)
        if ini is None or fim is None:
            out.append(Violacao("ancora_desconhecida", c.id))
        elif ini > fim:
            out.append(Violacao("cena_invertida", c.id))
        for texto in c.texto_na_tela:
            t = _tokens(texto)
            if tuple(t) in permitidos:
                continue
            if not _contem_subsequencia(fala, t):
                out.append(Violacao("texto_novo_na_tela", c.id))
    return out


def cobertura(entrada: EntradaCongelada, plano: PlanoDeCenas) -> dict[str, int]:
    """How the plan covers the speech -- MEASURED, never required (composition is open). Unknown anchors are ignored here
    (``validar_plano`` already reports them)."""
    idx = _indice(entrada)
    contagem = [0] * len(entrada.palavras)
    for c in plano.cenas:
        ini, fim = idx.get(c.palavra_inicio), idx.get(c.palavra_fim)
        if ini is None or fim is None or ini > fim:
            continue
        for i in range(ini, fim + 1):
            contagem[i] += 1
    return {
        "palavras": len(contagem),
        "palavras_cobertas": sum(1 for n in contagem if n),
        "palavras_sem_cena": sum(1 for n in contagem if n == 0),
        "sobreposicoes": sum(1 for n in contagem if n > 1),
    }


@dataclass(frozen=True)
class Alvos:
    """The measured targets (owner defaults 2026-11-13; ``motion_render.preset`` carries the same loudness numbers)."""

    lufs: float = -14.0
    tolerancia_lufs: float = 1.0
    pico_dbtp: float = -1.5
    largura: int = 1080
    altura: int = 1920


#: measurements a montador MUST report; a missing one fails the checks as ``nao_medido``.
CAMPOS_OBRIGATORIOS = ("lufs", "true_peak_db", "violacoes_zona_segura", "duracao_s", "largura", "altura")


def avaliar_medicoes(medicoes: dict[str, Any], alvos: Alvos) -> list[Violacao]:
    out = [Violacao("nao_medido", c) for c in CAMPOS_OBRIGATORIOS if medicoes.get(c) is None]
    if out:
        return out
    if abs(float(medicoes["lufs"]) - alvos.lufs) > alvos.tolerancia_lufs:
        out.append(Violacao("loudness_fora_do_alvo"))
    if float(medicoes["true_peak_db"]) > alvos.pico_dbtp:
        out.append(Violacao("pico_acima_do_alvo"))
    if medicoes["violacoes_zona_segura"]:
        out.append(Violacao("zona_segura_violada"))
    if (int(medicoes["largura"]), int(medicoes["altura"])) != (alvos.largura, alvos.altura):
        out.append(Violacao("formato_fora_do_alvo"))
    if medicoes.get("gancho_quadro_0") is False:
        out.append(Violacao("gancho_reprovado"))
    if medicoes.get("sincronia_ok") is False:
        out.append(Violacao("sincronia_reprovada"))
    return out


def avisos_nao_medidos(medicoes: dict[str, Any]) -> list[str]:
    """Advisories for the human reviewer: the optional checks the montador did not measure."""
    return [c for c in ("gancho_quadro_0", "sincronia_ok") if medicoes.get(c) is None]


__all__ = ["Alvos", "CAMPOS_OBRIGATORIOS", "avaliar_medicoes", "avisos_nao_medidos", "cobertura", "validar_plano"]

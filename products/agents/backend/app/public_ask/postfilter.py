"""Deterministic post-filter for the public ``/ask`` answer (limiar-open-question S4).

Every check runs over the S1 engine's normalized text (accent/case-insensitive, word-bounded,
letter-run squeezed), so spelling variants of a banned phrase are caught. ANY failure replaces
the answer with the pack's fixed fallback - there is no regeneration loop.

Privacy: ``ResultadoPosfiltro.motivos`` carries check ids only - never any part of the answer
or the user's text. Lexicons / fallback / path enum are DATA (``safety_pack/limiar/posfiltro.json``,
a DRAFT pending Monica's approval, covered by ``SOURCE.lock``).

Word-boundary decision: matching is whole-word, so ``garanto`` trips but ``garantia`` (a
different word) does not; stems are explicit (``depressiv*`` = word prefix).
"""

from __future__ import annotations

import json
import re
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .safety_pack.engine import (
    PACK_DIR,
    LOCK_PATH,
    PackError,
    SafetyEngine,
    _squeeze_pattern,
    load_engine,
    verify_lock,
)

POSFILTRO_FILE = "posfiltro.json"

# Stable check ids (the vocabulary of ``motivos``).
MOTIVO_PALAVRAS = "palavras_fora_da_faixa"
MOTIVO_CAMINHOS_EXCESSO = "caminhos_excedem_limite"
MOTIVO_CAMINHO_INVALIDO = "caminho_fora_do_enum"
MOTIVO_FONTE = "fonte_nao_recuperada"
MOTIVO_TRIAGEM = "triagem_saida_acima_de_verde"

_WORD = re.compile(r"[^\W_]+(?:[-'][^\W_]+)*", re.UNICODE)


@dataclass(frozen=True)
class ResultadoPosfiltro:
    ok: bool
    texto: str
    caminhos: tuple[str, ...]
    motivos: tuple[str, ...]


@dataclass(frozen=True)
class PacotePosfiltro:
    versao: str
    rascunho: bool
    palavras_min: int
    palavras_max: int
    max_caminhos: int
    caminhos_permitidos: frozenset[str]
    fallback_texto: str
    fallback_caminhos: tuple[str, ...]
    verificacoes: tuple[tuple[str, re.Pattern[str]], ...]  # (check id, compiled over normalized text)
    engine: SafetyEngine


def _phrase_regex(engine: SafetyEngine, phrase: str) -> str:
    star = phrase.endswith("*")
    norm = engine.normalize(phrase.rstrip("*"))
    if not norm:
        raise PackError(f"posfiltro lexicon phrase normalizes to nothing: {phrase!r}")
    return re.escape(norm).replace(r"\ ", " ") + (r"\w*" if star else "")


def _build(engine: SafetyEngine, data: dict) -> PacotePosfiltro:
    try:
        verificacoes: list[tuple[str, re.Pattern[str]]] = []
        for vid, spec in data["verificacoes"].items():
            alts = [_phrase_regex(engine, p) for p in spec.get("frases", [])]
            alts += [_squeeze_pattern(p) for p in spec.get("padroes", [])]
            if not alts:
                raise PackError(f"posfiltro check {vid!r} has no phrases/patterns")
            verificacoes.append((vid, re.compile(r"\b(?:" + "|".join(alts) + r")\b", re.ASCII)))
        fb = data["fallback"]
        enum = frozenset(data["caminhos_permitidos"])
        pacote = PacotePosfiltro(
            versao=data["versao"],
            rascunho=data.get("status") == "rascunho",
            palavras_min=int(data["palavras"]["min"]),
            palavras_max=int(data["palavras"]["max"]),
            max_caminhos=int(data["max_caminhos"]),
            caminhos_permitidos=enum,
            fallback_texto=fb["texto"],
            fallback_caminhos=tuple(fb["caminhos"]),
            verificacoes=tuple(verificacoes),
            engine=engine,
        )
    except (KeyError, TypeError, ValueError, re.error) as exc:
        raise PackError(f"safety pack {POSFILTRO_FILE} malformed: {exc!r}") from exc
    if not pacote.fallback_caminhos or not set(pacote.fallback_caminhos) <= enum or (
        len(pacote.fallback_caminhos) > pacote.max_caminhos
    ):
        raise PackError("posfiltro fallback paths must be a non-empty subset of the enum within the limit")
    return pacote


def carregar_pacote_posfiltro(
    app: str = "limiar", *, pack_dir: Path = PACK_DIR, lock_path: Path = LOCK_PATH
) -> PacotePosfiltro:
    """Verify the lock (covers ``posfiltro.json``), then build the post-filter pack."""
    if app != "limiar":
        raise PackError(f"unknown public-ask app {app!r}")
    verify_lock(pack_dir, lock_path)
    try:
        data = json.loads((pack_dir / POSFILTRO_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PackError(f"safety pack {POSFILTRO_FILE} unreadable: {exc}") from exc
    return _build(load_engine(pack_dir, lock_path), data)


@lru_cache(maxsize=1)
def _pacote_padrao() -> PacotePosfiltro:
    return carregar_pacote_posfiltro()


def pacote_posfiltro_padrao() -> PacotePosfiltro:
    """Cached singleton for the route (lock verified once per process)."""
    return _pacote_padrao()


def aplicar_posfiltro(
    resposta: str,
    caminhos: Sequence[str],
    *,
    fonte_ids: Sequence[str],
    fonte_ids_recuperadas: Collection[str],
    pacote: PacotePosfiltro,
) -> ResultadoPosfiltro:
    motivos: list[str] = []
    norm = pacote.engine.normalize(resposta)
    for vid, rx in pacote.verificacoes:
        if rx.search(norm):
            motivos.append(vid)
    n = len(_WORD.findall(resposta))
    if not pacote.palavras_min <= n <= pacote.palavras_max:
        motivos.append(MOTIVO_PALAVRAS)
    if len(caminhos) > pacote.max_caminhos:
        motivos.append(MOTIVO_CAMINHOS_EXCESSO)
    if any(c not in pacote.caminhos_permitidos for c in caminhos):
        motivos.append(MOTIVO_CAMINHO_INVALIDO)
    recuperadas = set(fonte_ids_recuperadas)
    if any(f not in recuperadas for f in fonte_ids):
        motivos.append(MOTIVO_FONTE)
    if pacote.engine.triage(resposta).nivel != "verde":
        motivos.append(MOTIVO_TRIAGEM)
    if motivos:
        return ResultadoPosfiltro(False, pacote.fallback_texto, pacote.fallback_caminhos, tuple(motivos))
    return ResultadoPosfiltro(True, resposta, tuple(caminhos), ())

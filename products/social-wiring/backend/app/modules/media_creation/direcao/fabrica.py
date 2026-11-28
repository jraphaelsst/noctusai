"""``make_adaptadores`` -- the Fake-or-refuse factory of the four seams.

No Real adapter exists: each is an open owner decision (project ``diretor-edicao-reels``, section 6). So nothing is
"configured": the factory returns the Fakes only on an EXPLICIT ``allow_fake=True`` (tests / local dev) and otherwise
REFUSES with the coded :class:`DecisaoPendente` -- a missing decision never degrades silently into a fake video.

NOC-REMEDIATE[direcao-adapters-reais]: when the owner decides D2..D6, add the Real classes next to the Fakes, a
``configured`` predicate per seam here, and keep the refusal for the seams still undecided -- 2026-11-27.
"""
from __future__ import annotations

from noctusai_lib.integrations.fake_or_refuse import resolve_fake_or_refuse

from app.modules.media_creation.direcao.fakes import adaptadores_fake
from app.modules.media_creation.direcao.portas import Adaptadores, DecisaoPendente


def _recusar() -> Adaptadores:
    raise DecisaoPendente(
        "os adaptadores reais da direção de vídeo ainda dependem de decisões do dono (estilo, planejamento, geração, montagem)"
    )


def _real() -> Adaptadores:  # unreachable while ``configured`` is False; kept so the day a Real exists the wiring is here
    return _recusar()


def make_adaptadores(*, allow_fake: bool = False) -> Adaptadores:
    return resolve_fake_or_refuse(
        configured=False, build_real=_real, build_fake=adaptadores_fake, allow_fake=allow_fake, unconfigured=_recusar,
    )


__all__ = ["make_adaptadores"]

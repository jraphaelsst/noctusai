"""Deterministic Fakes of the four seams. No IO, no files, no network, no cost.

Every output is flagged ``sintetico=True``: the handlers refuse to deliver a synthetic run for human review unless the
caller explicitly allows it (``DirecaoDeps.permitir_sintetico``, a test / local-dev opt-in) -- a Fake can never put a
fake video in front of an approver.

The Fake planner is NOT a storytelling proposal: it cuts the script into equal word blocks only so the graph, the ledger
and the validators have something valid to carry. It decides nothing about composition.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from app.modules.media_creation.direcao.portas import Adaptadores
from app.modules.media_creation.direcao.tipos import (
    CenaPlanejada,
    EntradaCongelada,
    EstiloRef,
    ItemMidia,
    MidiaGerada,
    Montagem,
    PlanoDeCenas,
)

PALAVRAS_POR_CENA_FAKE = 8
SEGUNDOS_POR_PALAVRA_FAKE = 0.36


class FakeResolvedorDeEstilo:
    def resolver(self, entrada: EntradaCongelada) -> EstiloRef:
        return EstiloRef("estilo-fake", "0", "fake")


class FakePlanejadorDeCenas:
    def planejar(self, entrada: EntradaCongelada, estilo: EstiloRef) -> PlanoDeCenas:
        ids = entrada.ids()
        palavras = entrada.palavras
        cenas = []
        for n, i in enumerate(range(0, len(ids), PALAVRAS_POR_CENA_FAKE), 1):
            fim = min(i + PALAVRAS_POR_CENA_FAKE, len(ids)) - 1
            literal = " ".join(p.texto for p in palavras[i : min(i + 3, fim + 1)])
            cenas.append(CenaPlanejada(f"c{n}", ids[i], ids[fim], (literal,), "fake", {}))
        return PlanoDeCenas("fake", "0", estilo, tuple(cenas), (), Decimal("0"))


class FakeGeradorDeMidia:
    def estimar_usd(self, plano: PlanoDeCenas) -> Optional[Decimal]:
        return None  # no vendor, no spend to check

    def gerar(self, entrada: EntradaCongelada, plano: PlanoDeCenas) -> MidiaGerada:
        base = f"fake/{entrada.org_id}/{entrada.post_id}/r{entrada.rodada}"
        itens = [ItemMidia("voz", f"{base}/voz.mp3", None, len(entrada.palavras) * SEGUNDOS_POR_PALAVRA_FAKE)]
        itens += [ItemMidia("visual", f"{base}/{c.id}.png", c.id) for c in plano.cenas]
        return MidiaGerada("fake", "0", tuple(itens), True, "fake-request", {"itens": len(itens)}, Decimal("0"))


class FakeMontador:
    def montar(self, entrada: EntradaCongelada, plano: PlanoDeCenas, midia: MidiaGerada) -> Montagem:
        duracao = round(len(entrada.palavras) * SEGUNDOS_POR_PALAVRA_FAKE, 3)
        # In-target numbers on purpose: the Fake exercises the checks' PASS path; the synthetic flag keeps it out of review.
        medicoes = {
            "lufs": -14.0, "true_peak_db": -2.0, "violacoes_zona_segura": [], "duracao_s": duracao,
            "largura": 1080, "altura": 1920,
        }
        chave = f"fake/{entrada.org_id}/{entrada.post_id}/r{entrada.rodada}/reel.mp4"
        return Montagem("fake", "0", chave, True, medicoes, Decimal("0"))


def adaptadores_fake(*, resolvedor=None, planejador=None, gerador=None, montador=None) -> Adaptadores:
    """The four Fakes (any of them replaceable by a test double)."""
    return Adaptadores(
        resolvedor or FakeResolvedorDeEstilo(), planejador or FakePlanejadorDeCenas(),
        gerador or FakeGeradorDeMidia(), montador or FakeMontador(),
    )


__all__ = [
    "FakeGeradorDeMidia", "FakeMontador", "FakePlanejadorDeCenas", "FakeResolvedorDeEstilo", "adaptadores_fake",
]

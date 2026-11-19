"""Headline generated from a picked roteiro (roteiro-first flow; contract 16.3 / 16.6 step 4). **DRAFT for owner validation.**

ONE model call, ONE headline. The roteiro is untrusted text and travels fenced as ``<material>`` (``cerca()``), with
the brand's bio and cerebros; the principal Estrutura's ``formula_headline`` (when it has one) is the rhetorical
model, never text to copy. The output is validated server-side by the existing headline validator; this module only
builds the prompt.
"""
from __future__ import annotations

from typing import Optional, Sequence

from app.modules.media_creation.prompts.chat_headline import REGRAS_MATERIAL
from app.modules.media_creation.saida_ia import MAX_HEADLINE_PALAVRAS
from app.modules.media_creation.services.chat_contexto import bloco

PROMPT_VERSAO = "headline-do-roteiro-v1-draft"

MAX_PALAVRAS = MAX_HEADLINE_PALAVRAS  # one derivation: the guard that judges the output
MAX_ROTEIRO_CHARS = 12_000
MAX_CEREBRO_CHARS = 6_000
MAX_CEREBROS = 5

SYSTEM_PROMPT = f"""Você é um redator especialista em ganchos (headlines) de vídeos curtos e posts para Instagram,
treinado no Método. Recebe um ROTEIRO completo que o criador já aprovou e escreve UMA headline para ele.

## Como trabalhar
- A headline resume a promessa ou a virada do roteiro, no tom do criador (bio e cérebros do material).
- Se o material trouxer `formula_headline`, use-a como modelo do recurso retórico; nunca copie o assunto nem as frases
  de outro vídeo, e preencha qualquer parte variável com dados reais do roteiro, da bio e dos cérebros.
- Responda SOMENTE com a headline: UMA linha, no MÁXIMO {MAX_PALAVRAS} palavras, em português do Brasil, sem aspas, sem
  colchetes, sem numeração, sem markdown, sem explicação, sem citação de estrutura.
- Específica, sem clichê, sem promessa que o roteiro ou a marca não cumpram.

{REGRAS_MATERIAL}
"""


def build_headline_do_roteiro(
    roteiro: str,
    formula_headline: Optional[str],
    perfil: Optional[str],
    cerebros: Sequence[str] = (),
) -> tuple[str, str]:
    """Return ``(system, user)``. Every untrusted piece is fenced; ``formula_headline`` of ``None`` omits that block."""
    partes: list[str] = []
    if (perfil or "").strip():
        partes.append(bloco("perfil", perfil[:MAX_CEREBRO_CHARS]))
    for c in [c for c in cerebros if (c or "").strip()][:MAX_CEREBROS]:
        partes.append(bloco("cerebro", c[:MAX_CEREBRO_CHARS]))
    if (formula_headline or "").strip():
        partes.append(bloco("formula_headline", formula_headline))
    partes.append(bloco("roteiro", (roteiro or "")[:MAX_ROTEIRO_CHARS]))
    partes.append(f"Escreva a headline deste roteiro (uma linha, até {MAX_PALAVRAS} palavras).")
    return SYSTEM_PROMPT, "\n\n".join(partes)


__all__ = ["MAX_PALAVRAS", "PROMPT_VERSAO", "SYSTEM_PROMPT", "build_headline_do_roteiro"]

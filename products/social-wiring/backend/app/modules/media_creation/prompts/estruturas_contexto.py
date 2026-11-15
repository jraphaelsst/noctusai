"""Rendering of the Estruturas material for the chat context (estruturas-contract.md section 8.1) and the fixed
rule texts that travel INSIDE the material (placeholder rule, profile-resolution rules).

The caller (``services/chat_contexto.py``) wraps every rendered string in ``bloco(...)`` which runs the whole
content through ``cerca()`` -- the prompt-injection fence for untrusted library text (a creator's formula / block
text can never close or open a ``<material>`` tag). ``PROMPT_VERSAO`` is the bump-me marker for this wording.
"""
from __future__ import annotations

from typing import Any, Sequence

PROMPT_VERSAO = "estruturas-contexto-v1-draft"

#: Each rendered Estrutura stays within this many characters (blocks are cut with a marker, never mid-word).
MAX_CHARS_ESTRUTURA = 700
MARCADOR_BLOCOS = " […]"

REGRA_PLACEHOLDERS = """Regras das Estruturas (valem para toda headline deste turno):
- Cada [placeholder] da FÓRMULA (ex.: [autoridade teórica]) é preenchido com dados REAIS do bloco `perfil_da_marca`
  (bio) e dos blocos `cerebro` (Cérebro da marca) presentes neste material. Nunca deixe colchetes numa headline.
- Se o material não permitir preencher um [placeholder], diga o que falta (ou use outra Estrutura); não invente
  e não mantenha o colchete.
- Você pode combinar até 3 Estruturas do MESMO formato quando a combinação servir ao pedido; ao fazê-lo, diga qual
  Estrutura e quais blocos vieram de cada uma (`### Estruturas usadas`: `#N (@perfil): Bloco A, Bloco B`).
- Cite apenas códigos presentes neste material: `(estrutura #N)` ou `(estrutura #N + #M)` (máximo 3 códigos).
- Você não usa ferramentas: tudo o que pode consultar está neste material."""

BIBLIOTECA_VAZIA = "não há estruturas na biblioteca para este pedido"

REGRA_PERFIL_AMBIGUO = (
    "O usuário citou um nome de perfil que pode ser mais de um. Pergunte qual perfil ele quis (liste os candidatos "
    "abaixo pelo @handle) e NÃO escolha estrutura nem gere headlines até ele responder."
)
REGRA_PERFIL_NAO_ENCONTRADO = (
    "O usuário citou um perfil que não existe na biblioteca. Diga isso, ofereça as sugestões abaixo (se houver) e "
    "pergunte como prosseguir; não invente perfil nem estrutura."
)


def _cortar_palavra(texto: str, limite: int) -> str:
    if len(texto) <= limite:
        return texto
    corte = texto[:limite]
    if texto[limite] != " " and " " in corte:
        corte = corte[: corte.rfind(" ")]
    return corte.rstrip(" ;,.—-")


def _bloco_texto(i: int, b: Any) -> str:
    tempo = f" [{b.tempo}]" if b.tempo else ""
    instr = f" — {b.instrucao}" if b.instrucao else ""
    nota = f" ({b.nota})" if b.nota else ""
    rep = f" × {b.repeticoes}" if b.repeticoes and b.repeticoes > 1 else ""
    tipo = f"{b.tipo} " if b.tipo else ""
    return f"{i}. {tipo}«{b.nome}»{tempo}{instr}{nota}{rep}"


def renderizar_estrutura(e: Any, *, limite: int = MAX_CHARS_ESTRUTURA) -> str:
    """``estrutura #<codigo> (@<handle>) | formato: f | objetivos: a, b | FÓRMULA: ... | BLOCOS: 1. ...; 2. ...``,
    <= ``limite`` chars: blocks are dropped from the end (with a marker) rather than cut mid-word."""
    quem = f" (@{e.handle})" if e.handle else ""
    cab = f"estrutura #{e.codigo}{quem} | formato: {e.formato or '-'} | objetivos: {', '.join(e.objetivos) or '-'}"
    formula = f" | FÓRMULA: {e.formula}" if e.formula else ""
    base = cab + formula
    if len(base) > limite:
        return _cortar_palavra(base, limite - len(MARCADOR_BLOCOS)) + MARCADOR_BLOCOS
    if not e.blocos:
        return base
    prefixo = base + " | BLOCOS: "
    partes: list[str] = []
    cortado = False
    for i, b in enumerate(e.blocos, 1):
        parte = _bloco_texto(i, b)
        reserva = len(MARCADOR_BLOCOS) if i < len(e.blocos) else 0
        if len(prefixo) + len("; ".join(partes + [parte])) + reserva > limite:
            cortado = True
            if not partes:  # even the first block does not fit: keep its start, cut at a word boundary
                folga = max(limite - len(prefixo) - len(MARCADOR_BLOCOS), 0)
                partes.append(_cortar_palavra(parte, folga) if folga else "")
            break
        partes.append(parte)
    corpo = "; ".join(p for p in partes if p)
    return prefixo + corpo + (MARCADOR_BLOCOS if cortado else "")


def renderizar_resolucao(resolucao: Any, *, modo: str) -> str:
    """The ``resolucao_de_perfis`` material: candidates (ambiguous) or suggestions (not found) + the rule."""
    linhas: list[str] = []
    if modo == "perfil_ambiguo":
        linhas.append(REGRA_PERFIL_AMBIGUO)
        for a in resolucao.ambiguos:
            quem = "; ".join(f"@{c.handle}" + (f" ({c.nome})" if c.nome else "") for c in a.candidatos)
            linhas.append(f"- trecho «{a.trecho}»: candidatos: {quem}")
    else:
        linhas.append(REGRA_PERFIL_NAO_ENCONTRADO)
        for n in resolucao.nao_encontrados:
            sug = "; ".join(f"@{c.handle}" + (f" ({c.nome})" if c.nome else "") for c in n.sugestoes) or "(nenhuma)"
            linhas.append(f"- trecho «{n.trecho}»: sugestões: {sug}")
    return "\n".join(linhas)


def renderizar_lista(estruturas: Sequence[Any]) -> list[tuple[str, str]]:
    """``[(codigo, linha)]`` in order -- the caller fits lines into the context budget one by one."""
    return [(e.codigo, renderizar_estrutura(e)) for e in estruturas]


__all__ = [
    "BIBLIOTECA_VAZIA", "MAX_CHARS_ESTRUTURA", "PROMPT_VERSAO", "REGRA_PLACEHOLDERS", "renderizar_estrutura",
    "renderizar_lista", "renderizar_resolucao",
]

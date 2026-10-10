"""Minha Pesquisa — AI classifier prompt + output parser.

DRAFT — awaiting owner validation.

Drafted from CoreStudio's captured classifier prompt
(``projects/core-studio/prompts/pesquisa-classifier-prompt.md``): same strict
``{{SLUG}}`` / ``[conteúdo literal]`` pair output and the same tie-break
hierarchy, extended from CoreStudio's 13 slugs to all 36 classifiable
variables. The variables table is RENDERED from
``pesquisa_variables.CLASSIFIABLE`` (the same source the migration seed uses),
never hand-duplicated.

Parser contract (pesquisa-contract.md section 3, "Classify"): only slugs that
are classifiable variables are accepted; a pair under an unknown slug, and any
input line absent from the output, is ``unclassified``. Nothing is guessed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.modules.media_creation.pesquisa_variables import (
    CLASSIFIABLE,
    CLASSIFIABLE_SLUGS,
)

_VARIABLES_TABLE = "\n".join(f"{{{{{v.slug}}}}} | {v.description}" for v in CLASSIFIABLE)
#: Public handle: the extractor prompt renders the SAME table (never a copy).
VARIABLES_TABLE = _VARIABLES_TABLE

PESQUISA_CLASSIFIER_SYSTEM_PROMPT = f"""Você é um classificador automático de variáveis de pesquisa de avatar para copywriting.
Sua função: receber um ou mais itens (um por linha) e retornar APENAS a classificação no formato padronizado. Nada mais.

Variáveis disponíveis:
Variável | O que é
{_VARIABLES_TABLE}

Hierarquia de desempate (se um item puder pertencer a mais de uma):
DORES (vive agora) > MEDOS (teme no futuro) > FRUSTRACOES (falhou no passado) > OBJECOES (impede ação) > CRENCAS-LIMITANTES (identidade) > DESEJOS (quer alcançar)

Regras ABSOLUTAS:
- A resposta contém SOMENTE os pares variável/conteúdo
- ZERO explicação, raciocínio, introdução, conclusão, resumo ou comentário
- ZERO texto antes, entre ou depois dos pares
- Cada item = uma variável na linha de cima + conteúdo na linha de baixo
- Uma linha em branco separa cada par
- Texto original literal, sem reescrita
- Cada item de entrada aparece exatamente uma vez
- Nunca invente variáveis fora da tabela

Formato de saída (ÚNICO permitido):
{{{{VARIAVEL}}}}
[conteúdo literal]

{{{{VARIAVEL}}}}
[conteúdo literal]

Exemplo
Entrada:
Mulheres acima de 40 anos
insônia
A princesa Sofia
já tentei várias dietas
perder 8kg em 3 meses

Saída:
{{{{CARACTERISTICAS-DEMOGRAFICAS-DO-AVATAR}}}}
[Mulheres acima de 40 anos]

{{{{DORES-TANGIVEIS-DO-AVATAR}}}}
[insônia]

{{{{PESSOAS-PERSONAGENS-CONHECIDOS-PELO-AVATAR}}}}
[A princesa Sofia]

{{{{FRUSTRACOES-DO-AVATAR}}}}
[já tentei várias dietas]

{{{{DESEJOS-TANGIVEIS-DO-AVATAR}}}}
[perder 8kg em 3 meses]

Se você incluir QUALQUER texto além dos pares {{{{VARIAVEL}}}} + [conteúdo], a resposta está ERRADA."""


@dataclass
class ClassifierResult:
    classified: dict[str, list[str]] = field(default_factory=dict)
    unclassified: list[str] = field(default_factory=list)


_SLUG_LINE = re.compile(r"^\s*\{\{\s*([A-Za-z0-9_-]+)\s*\}\}\s*$")
_LIST_MARKER = re.compile(r"^\s*(?:\d+[.)]|[-*•])\s+")


def split_input_lines(text: str) -> list[str]:
    """The user's newline-separated items: stripped, blanks dropped, order kept."""
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", _LIST_MARKER.sub("", s)).strip().lower()


def _unwrap(s: str) -> str:
    s = s.strip()
    if len(s) >= 2 and s.startswith("[") and s.endswith("]"):
        s = s[1:-1].strip()
    return s


def parse_classifier_output(reply: str, input_lines: list[str]) -> ClassifierResult:
    """Parse the model reply against the input lines. Never raises on chatter."""
    result = ClassifierResult()
    seen: set[str] = set()
    covered: set[str] = set()
    raw = [ln for ln in reply.splitlines()]
    i = 0
    while i < len(raw):
        m = _SLUG_LINE.match(raw[i])
        if not m:
            i += 1  # model chatter outside a pair: ignored, never saved
            continue
        slug = m.group(1).upper()
        j = i + 1
        while j < len(raw) and not raw[j].strip():
            j += 1
        if j >= len(raw) or _SLUG_LINE.match(raw[j]):
            i = j  # slug with no content line
            continue
        content = _unwrap(raw[j])
        i = j + 1
        key = _norm(content)
        if not key or key in seen:
            continue
        seen.add(key)
        covered.add(key)
        if slug in CLASSIFIABLE_SLUGS:
            result.classified.setdefault(slug, []).append(content)
        else:
            result.unclassified.append(content)
    for line in input_lines:
        key = _norm(line)
        if key and key not in covered:
            covered.add(key)
            result.unclassified.append(line)
    return result

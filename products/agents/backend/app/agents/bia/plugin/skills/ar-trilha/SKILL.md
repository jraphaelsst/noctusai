---
name: ar-trilha
description: Monta trilha, ementa ou grade de curso — dispara em "trilha", "ementa", "grade do curso", "sequência de aulas", "por onde começa o treinamento". Define sequência, duração e o que cada módulo entrega.
version: 1.0.0
---

# ar-trilha — a sequência do curso

## Antes de montar

- **Público** — busque no conhecimento do projeto (categoria `contexto`). Incompleto ou
  ausente → pergunte antes de montar.
- **Método** — busque (categoria `dominio`). Vazio → a trilha *é* o primeiro rascunho do
  método; diga isso e leve o resultado para `/ar-entrevista metodologia`.
- **Oferta** — busque (categoria `contexto`). Em aberto → não decida sozinha se a trilha é
  vendida inteira, por módulo ou por assinatura; registre a pergunta.

## Forma

Para cada módulo: **objetivo de aprendizagem** (o que a pessoa passa a fazer, não a saber) ·
aulas com duração estimada · pré-requisito · como se verifica que funcionou.

Regras de sequência:

- Comece pelo que a pessoa **encontra no próprio posto de trabalho**. Abstração antes de
  reconhecimento perde a plateia no primeiro minuto.
- Um conceito novo por aula. Dois é onde a retenção desaba.
- Erro comum vale mais que regra correta: as pessoas aprendem no contraste.

## Depois

`mcp__academia__conteudo_salvar` (tipo `trilha`), e leve para `/ar-capturar` o que a
montagem revelou sobre o método — normalmente revela bastante.

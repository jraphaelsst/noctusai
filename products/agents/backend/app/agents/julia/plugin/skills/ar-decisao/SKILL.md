---
name: ar-decisao
description: Registra uma decisão do projeto com seu motivo, ou substitui uma anterior — dispara em "decidimos", "vamos de", "melhor fazer X em vez de Y", "mudei de ideia sobre". Append-only, numerada D-nn.
version: 1.0.0
---

# ar-decisao — decisões que sobrevivem à memória

## Registrar

`mcp__academia__decisao_registrar` com estes campos:

- **Título** — a decisão em uma linha, no imperativo.
- **Contexto** — o que estava em jogo, o que tornou isso uma escolha.
- **Decisão** — o que foi escolhido.
- **Motivo** — por quê. **Este é o campo que importa.** Daqui a seis meses ninguém lembra
  o porquê, e sem ele a decisão será revisitada por alguém que acha que teve uma ideia nova.

Registre também o que foi **rejeitado e por quê**, quando houve alternativa real
(`alternativas_rejeitadas`).

## Substituir

`mcp__academia__decisao_substituir` com o código da decisão anterior em `substitui`. Isso
escreve uma decisão nova apontando para a antiga e marca a antiga como superada.

**Nunca proponha editar a decisão antiga.** A história de por que a decisão mudou é o
ativo — perdê-la é perder exatamente a informação que evita repetir o erro.

## Quando não registrar

- Escolha de implementação que ninguém vai questionar.
- Preferência momentânea. Se não sobreviver à semana, não é decisão.
- O que ainda está em discussão — isso é `mcp__academia__pergunta_adicionar`.

## Fechamento

Depois de registrar, diga o código: "registrado como D-nn".

---
name: ar-sessao
description: Abre e fecha uma sessão de trabalho — dispara em "vamos trabalhar", "o que fazemos hoje", "por hoje é isso", "encerra a sessão", "wrap up". Garante que o começo tenha plano e o fim tenha captura.
version: 1.0.0
---

# ar-sessao — começo e fim de sessão

O trabalho se perde nas bordas: começa sem plano e termina sem captura.

## Abrir

1. `mcp__academia__tarefa_preparar_sessao` — o que vem agora, o que travou.
2. `mcp__academia__pergunta_listar` — filtre só o que afeta o trabalho de hoje.
3. Proponha **um** objetivo para a sessão. Um. Sessão com três objetivos entrega zero.
4. Confirme com quem está no chat antes de executar.

## Fechar

1. **Capture antes de qualquer outra coisa** (`/ar-capturar`) — decisões, fatos, perguntas
   que apareceram. É aqui que a informação evapora.
2. `mcp__academia__tarefa_atualizar` no que andou; `mcp__academia__tarefa_criar` no que
   apareceu.
3. `mcp__academia__historico_append` — o que aconteceu e o que mudou por causa disso.
4. Devolva em quatro linhas: feito · decidido · aberto · próximo passo.

## Guardrails

- Não feche uma sessão sem o passo 1. Uma sessão sem captura é uma sessão que não aconteceu.
- Não declare feito o que não foi verificado.

---
name: ar-capturar
description: Escreve no conhecimento do projeto o que acabou de ser decidido ou afirmado — dispara em "anota isso", "guarda isso", "decidimos que", "a partir de agora", "nunca mais", e automaticamente sempre que um fato durável ou uma decisão aparecer na conversa.
version: 1.0.0
---

# ar-capturar — o conhecimento entra no projeto

Uma conversa que não vira registro é uma conversa perdida.

## 1 · Classifique o que apareceu

| É | Ferramenta |
|---|---|
| Uma decisão com motivo | `mcp__academia__decisao_registrar` |
| Um fato durável do negócio ou uma preferência de trabalho | `mcp__academia__kb_escrever` |
| Um fato técnico do domínio — **só com fonte** | `mcp__academia__pesquisa_capturar_fonte` |
| Algo que aconteceu | `mcp__academia__historico_append` |
| Algo que ninguém respondeu | `mcp__academia__pergunta_adicionar` |

## 2 · Toda escrita passa por aprovação

O que muda é quanto você mostra antes de propor:

- Só atrapalha internamente → proponha em uma linha: "vou registrar X em Y".
- Chega a alguém de fora do projeto → mostre o rascunho inteiro antes de propor.
- A informação não existe em lugar nenhum → não é captura, é `/ar-entrevista`.

Reconhecer o que merece captura continua sendo seu trabalho — a aprovação é sobre *o quê e
onde*, nunca sobre *se*.

## 3 · Escreva

- Registre **o motivo**, não só o conteúdo. Em seis meses ninguém lembra por quê, e é o
  porquê que evita repetir a mesma discussão.
- Uma decisão que substitui outra usa `mcp__academia__decisao_substituir` — nunca proponha
  reescrever a antiga.
- Marque o que ficou faltando e registre a pergunta correspondente.

## Guardrails

- Não capture o que já está estruturado em outro lugar do projeto.
- Não capture opinião momentânea marcada como "acho que".
- Não capture o que você **inferiu**. Captura é do que foi dito. Inferência vira pergunta.
- Nunca proponha uma escrita silenciosamente, e nunca deixe de propor por receio de
  incomodar.

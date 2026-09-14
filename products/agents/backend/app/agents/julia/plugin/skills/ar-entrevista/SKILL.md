---
name: ar-entrevista
description: Entrevista quem está no chat sobre um tópico e escreve o resultado no projeto — dispara em "/ar-entrevista <tópico>", "me entrevista sobre", "vamos definir X", "preciso tirar isso da minha cabeça". O modo para o que existe só na cabeça de quem está conversando e em lugar nenhum — metodologia, oferta, público, marca.
version: 1.0.0
---

# ar-entrevista — extrair o que só quem está no chat sabe

Pesquisa produz o método de outra pessoa. Para o que é do projeto, só entrevista funciona.

## Como conduzir

1. **Leia o que já existe** sobre o tópico antes de abrir a conversa (`mcp__academia__kb_buscar`).
   Perguntar o que já está registrado queima confiança.
2. **Pergunte em rodadas de no máximo quatro.** Rodada 1 = as bifurcações estruturais, as
   que mudam todas as outras respostas. Só depois o detalhe.
3. **Ofereça opções quando elas existirem** — escolher é mais rápido que redigir, e uma
   opção errada na lista faz a pessoa corrigir com precisão. Deixe sempre a saída livre.
4. **Pergunta aberta só quando não há opção honesta.** História, motivo e contexto não têm
   múltipla escolha.
5. **Não avance sobre resposta ambígua.** Uma resposta que contradiz outra é a informação
   mais valiosa da entrevista — volte nela na hora.
6. **Nunca infira para preencher lacuna.** Lacuna vira `mcp__academia__pergunta_adicionar`.

## Como fechar

1. Proponha a escrita no destino certo — o de verdade, não um resumo solto.
2. Registre as decisões que saíram, com motivo (`mcp__academia__decisao_registrar`).
3. Registre o que ficou em aberto (`mcp__academia__pergunta_adicionar`).
4. Devolva um resumo curto: o que ficou decidido, o que ficou aberto, e o que isso destrava.

## Guardrails

- Não termine uma entrevista "completa" com lacunas escondidas. Lacuna declarada é entrega;
  lacuna escondida é dívida.
- Não escreva na voz de quem está no chat o que a pessoa não disse. Se a frase precisa de
  invenção, é pergunta.

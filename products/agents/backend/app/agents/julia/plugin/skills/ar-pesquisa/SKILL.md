---
name: ar-pesquisa
description: Pesquisa externa com captura de fonte no projeto — dispara em "pesquisa sobre", "o que diz a lei", "procura", "qual a norma", "confirma se". O único caminho legítimo para um fato regulatório ou técnico entrar no conhecimento do projeto.
version: 1.0.0
---

# ar-pesquisa — pesquisar e capturar

Pesquisa que não vira registro é pesquisa que será refeita. E fato regulatório sem fonte é
passivo esperando alguém de fora perguntar.

## Procedimento

1. **Busque a fonte primária** com `WebSearch`. Para regulação brasileira: `planalto.gov.br`,
   `gov.br`, `sinir.gov.br`, ABNT. Blog e resumo de terceiros servem para *achar* a norma,
   nunca para *citá-la*.
2. **Leia a fonte**, não o resumo do buscador.
3. `mcp__academia__pesquisa_capturar_fonte` — URL, título, trecho citado, resumo, e o slug
   do KB ao qual a fonte se vincula (`kb_slug`).
4. **Escreva o que aquilo significa para o projeto**: o que a norma exige e o que disso vira
   conteúdo de treinamento (`mcp__academia__kb_escrever`). A norma crua não é conhecimento
   utilizável.

## Guardrails

- **Não afirme o que a fonte não diz.** Entre "a lei exige" e "a lei sugere" há um processo.
- **Não confie na sua memória de legislação.** Números de norma, edições e vigência mudam —
  e uma norma revogada citada com confiança é o pior resultado possível.
- Não capture conteúdo com direito autoral como se fosse do projeto. Cite.
- Quando a fonte primária for paga (norma ABNT), registre isso explicitamente em vez de
  substituir por um resumo de terceiro.

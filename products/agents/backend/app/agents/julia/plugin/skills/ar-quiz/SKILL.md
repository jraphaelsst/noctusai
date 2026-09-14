---
name: ar-quiz
description: Escreve quiz de avaliação para uma aula ou módulo de treinamento — dispara em "quiz", "avaliação", "perguntas da aula", "como testar se aprenderam". PT-BR, ancorado em fonte, focado em decisão prática.
version: 1.0.0
---

# ar-quiz — avaliação

## Regra central

Teste **decisão**, não memória. "Em que ano foi promulgada a lei X" mede nada. Uma situação
concreta do dia a dia de quem faz o curso mede o que o treinamento realmente ensinou.

## Forma

- 5 a 8 questões por módulo. Mais que isso, a pessoa abandona.
- Situação concreta do ambiente de trabalho dela, não exemplo genérico.
- Distratores **plausíveis** — o erro comum real é o melhor distrator que existe.
- Cada questão traz o gabarito **com explicação**: o feedback é onde o aprendizado acontece.
- Toda questão técnica ancora numa fonte já capturada (busque com `mcp__academia__kb_buscar`,
  categoria `dominio`). Item sem fonte confirmada não vira questão.

## Depois

`mcp__academia__conteudo_salvar` (tipo `quiz`), referenciando a aula ou o módulo.

## Guardrails

- Não escreva pegadinha. Avaliação que humilha destrói a adesão ao programa.
- Não invente estatística no enunciado.
- Se o certificado tiver valor formal — isso é uma pergunta em aberto, não uma suposição —
  registre a dúvida (`mcp__academia__pergunta_adicionar`) antes de tratar o quiz como
  formalidade.

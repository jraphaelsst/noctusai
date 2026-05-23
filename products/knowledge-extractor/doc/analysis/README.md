# Auditoria de Cobertura — Transcrições → Metodologia

> **Pergunta.** Quão fielmente a metodologia consolidada (em `data/methodology/`)
> absorveu o conteúdo útil das **transcrições** (fonte da verdade — o registro
> textual das aulas em áudio)? Uma auditoria por módulo (branching-dispatch,
> 7 agentes em paralelo). Detalhe por módulo: `modulo-1.md` … `modulo-7.md`.
> Data: 2026-05-22.

## Placar de cobertura

| Módulo | Nota | Maior lacuna |
|---|---|---|
| 1 · Plano para Crescer | 6.5/10 | Exercício "por que deveriam me seguir?" (ausente); cadeia causal atenção→audiência→demanda→funil→venda |
| 2 · Algoritmo | 6.0/10 | Exercício de análise comparativa (média de views → acima/abaixo → variável causal); frame "o que é meu vs. do algoritmo" |
| 3 · Assuntos Virais | 7.5/10 | Método vivencial de persona (5 passos, dia-a-dia); cadeia emoção→comportamento→algoritmo |
| 4 · Ciência da Atenção | 7.5/10 | Princípio de **gatilhos em camadas** (combinar 2–4); meta-regra de seleção de gatilho |
| 5 · Criando Headlines | 7.2/10 | **Especificidade** como princípio transversal; protocolo de engenharia reversa (7 passos); 2 estruturas não catalogadas |
| 6 · Conteúdos Notáveis | 7.5/10 | Mecanismo de suspense de fatos curiosos; 2 critérios de curadoria de notícias + ciclo de vida editorial |
| 7 · Núcleo de Influência | 6.5/10 | **Tipologia de inimigos** (4 categorias); 5 categorias de bordões; checklist de provas por crença |

**Média ≈ 7/10.** Absorvemos bem o *esqueleto* (taxonomias, frameworks, listas),
mas perdemos *profundidade operacional* (o "como": exercícios, protocolos passo a
passo e critérios de seleção).

## Padrões transversais (o que se repete entre módulos)

1. **Profundidade operacional perdida.** Os resumos preservaram a estrutura mas
   reduziram o "como" a instruções genéricas (M2, M3, M5, M6, M7).
2. **Princípios transversais nunca promovidos a regra explícita:** especificidade
   (M5), gatilhos em camadas (M4), cadeias causais (M1, M2, M3).
3. **Exercícios práticos descartados:** análise comparativa de métricas (M2),
   persona vivencial (M3), engenharia reversa / "cientista da atenção" (M5, M6),
   "por que deveriam me seguir?" (M1).
4. **Alguns resumos são pior que peso-morto — são enganosos:** M4 introduziu um
   framework sem base no transcript ("Revelação Gradual"); resumos de M7 dão falsa
   impressão de cobertura completa.
5. **Inconsistência interna:** a correção sobre dopamina ("querer" vs. "gostar")
   está no arquivo do Módulo 4 mas não na seção consolidada de `METHODOLOGY.md`.
6. **Conteúdo não-metodológico:** M1 carrega um item de oferta comercial
   ("agendar diagnóstico") que não é metodologia replicável.

## Veredito sobre os arquivos (peso-morto)

- **Transcrições** = fonte da verdade. NÃO são peso-morto e NÃO devem ser apagadas.
  ⚠️ Não estão no git (gitignored) — apagá-las é **permanente**, sem recuperação.
- **Resumos** = derivados, **regeneráveis** a partir das transcrições pelo pipeline.
  Vários classificados como *Redundantes* (M4: 2, M7: 5) ou enganosos. Uma vez que
  as lacunas forem absorvidas na metodologia, os resumos tornam-se candidatos a
  remoção — desde que as transcrições sejam preservadas.

## Próximos passos

1. **Absorver as lacunas** acima na metodologia (`data/methodology/`), promovendo
   os princípios transversais a regras explícitas e recuperando os exercícios.
2. **Reconciliar** a inconsistência da dopamina entre os dois arquivos.
3. **Preservar as transcrições**; só então remover os resumos redundantes
   (regeneráveis) — sob confirmação explícita (irreversível).

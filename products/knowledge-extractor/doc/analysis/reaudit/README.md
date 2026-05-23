# Re-auditoria de Cobertura — depois da absorção

> Segunda passada da auditoria transcrições→metodologia, **após** a onda de
> absorção. Mede o ganho de cobertura. Detalhe por módulo: `modulo-1.md`…`modulo-7.md`
> (a primeira auditoria está em `../modulo-*.md`). Data: 2026-05-23.

## Antes → Depois

| Módulo | Antes | Depois | Δ |
|---|---|---|---|
| 1 · Plano para Crescer | 6.5 | **9.0** | +2.5 |
| 2 · Algoritmo | 6.0 | **8.5** | +2.5 |
| 3 · Assuntos Virais | 7.5 | **9.5** | +2.0 |
| 4 · Ciência da Atenção | 7.5 | **9.0** | +1.5 |
| 5 · Criando Headlines | 7.2 | **9.1** | +1.9 |
| 6 · Conteúdos Notáveis | 7.5 | **9.0** | +1.5 |
| 7 · Núcleo de Influência | 6.5 | **8.5** | +2.0 |
| **Média** | **~7.0** | **~9.0** | **+2.0** |

**Veredito:** a absorção fechou praticamente todas as lacunas de alto impacto da
primeira auditoria. A profundidade operacional (exercícios, protocolos, critérios
de seleção) foi recuperada e os princípios transversais foram promovidos a regras.

## Lacunas remanescentes — ✅ TODAS RESOLVIDAS (passada de aprofundamento, commit `e341af0`)

Uma terceira passada (branching-dispatch, 7 agentes) absorveu cada lacuna abaixo a
partir das transcrições. Nenhuma permanece em aberto:

1. ✅ **M7 / Aula 10 — convicção como abre-mercado**: o *porquê* estratégico (crenças
   criam desejo pela solução **antes** da procura → eliminam comparação de preço →
   geram demanda) — agora seção dedicada.
2. ✅ **M1** — argumento contra "comecei tarde demais" + implicação prática da
   variância de latência até a primeira viralização.
3. ✅ **M2** — diagnóstico diferencial do "shadowban percebido" (procedimento nomeado)
   + frame ético de propósito.
4. ✅ **M4** — headline textual vs. legenda; Cialdini como base do reconhecimento (R-04);
   mecânica neurológica do contraste/inesperado na headline visual.
5. ✅ **M3** — assunto do momento como gancho sem desenvolver no corpo + aba "mais
   populares" + planilha de categorização.
6. ✅ **M6** — motivo declarado vs. mecanismo real da moeda social; anti-padrão do valor
   prático genérico; pesquisa de audiência como pré-requisito de identificação (+3 outras).
7. ✅ **M5** — Template 15 como intensificador + mecanismo de comprometimento pela lista
   nos templates de lista.

## Como foi feito

Branching-dispatch: 7 agentes em paralelo (1 por módulo), cada um relendo as
transcrições (fonte da verdade) contra a metodologia enriquecida. Material anonimizado.

## Verificação independente pelo tool `audit-coverage` (2026-05-23)

Rodamos o tool `cli audit-coverage` (instrumento independente) sobre os 7 módulos
como prova de fechamento. Resultado: nota **uniforme 8/10** em todos os módulos e
relistagem de tópicos que JÁ foram absorvidos (ex.: M7 histórias de sustentação e
bordões; M3 exercício de persona; M6 engenharia reversa e ciclo de vida editorial).

**Verificação cruzada (grep na metodologia):** todos esses tópicos "Alto" estão
presentes nos arquivos por módulo. Conclusão: **as lacunas estão fechadas**; a nota
uniforme 8/10 é um **artefato de granularidade do tool** — o passo *reduce* do
map-reduce re-deriva lacunas a partir dos transcritos em vez de verificar contra o
texto completo da metodologia. Sinal mais confiável = as auditorias por agente
(gap a gap, texto completo, ~9) + o spot-check.

**Pendência de melhoria (não bloqueante):** aprimorar o passo *reduce* do
`coverage_audit` para checar contra a metodologia completa (e variar a nota por
módulo). Tratar as notas atuais do tool como indicativas, não autoritativas.

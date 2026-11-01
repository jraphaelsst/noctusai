---
titulo: "Precisa da Mônica: contradições e lacunas do guia"
tipo: sintese
resumo: "Pontos em que o guia se contradiz, não decide ou foi escrito para a web. Nesses casos o guardião não escolhe: cita os trechos, dá opções e diz 'precisa da Mônica'."
proveniencia:
  origem: "projects/app/entre-sessoes/context/01-EVALUATION.md e 02-PLAN.md (§0 decisões D1 a D6, §4 itens que precisam de Mônica)"
  notas: "Sintetizado em 2026-11-01. Remover um item daqui só quando Mônica decidir e o guia (ou o texto oficial) for atualizado."
---
# Precisa da Mônica

Regra: diante de qualquer item desta lista, não escolha. Cite os trechos que se contradizem, ofereça de duas a quatro opções com o efeito prático para a analisanda, recomende uma e escreva **precisa da Mônica**.

## Decisões já tomadas por João (valem; não são pendência)
- D1 a D2: o app é construído no repositório Expo; o conteúdo antigo (atividades, jogos, reflexões) foi removido.
- D3 e D4: **base visual = design system v2.1**. Não vale o template publicado do artefato ("v21" ali é só versão de template) nem a variante escura de teste. Onde eles diferem do design system v2.1, vale o design system. Sem variantes alternáveis.
- D5: nome "Entre sessões"; D6: distribuição por Expo Go, trilhas internas e um link web.
- Sem Mônica, por serem correção de comportamento: o erro de passo some assim que o campo fica válido; limite de 40 cartões vira "Ver mais registros"; empate no merge de backup mantém o registro local e conta como "ignorado"; `questionText` é gravado com cada registro (ADR-10).

## Contradições e lacunas do guia (precisam dela)
1. **Textos oficiais da variante de teste.** O guia diz que o publicado é o oficial, mas aponta a variante de teste como fonte do código; alguns textos (ex.: passo 2 do Como usar, sem nome) vêm dela. Qual texto vale em cada ponto de divergência?
2. **Citação do dia.** Glossário e RN-14: muda a cada abertura do app (contador que começa em valor aleatório de 0 a 999). O plano sugere uma por dia. Qual?
3. **Etiquetas e filtros que parecem inconsistentes.** Registro com "Sim" desmarcado na aba Levar não mostra etiqueta; registro "Talvez" marcado continua sob o filtro Talvez levar (RN-10, RN-13). Manter ou mudar?
4. **Total do Resumo conta exemplos** (RN-24), enquanto exemplos nunca entram em Levar (RN-17). Manter?
5. **Busca ignora o texto da pergunta escolhida** (RN-11). Incluir?
6. **"Botões redondos"** no Como usar, mas os filtros são quadrados. Qual redação?
7. **Textos de navegador no app nativo.** "Este navegador não está guardando dados…", "neste aparelho e neste navegador", "aba anônima" não fazem sentido no app. Reescrita precisa de aprovação dela.
8. **Textos que não existem ainda:** trocar meu nome, backup (exportar, importar, resumo "N novos, M atualizados"), importação do diário web. Todo texto novo é proposta.
9. **Aba com 13 px** é desvio aprovado do design system (mín. 14 px), com a nota "revisar se houver aba nova". Qualquer mudança nas abas é dela.
10. **ADRs de status "Proposta" ou "Em aberto"** (ADR-10 a ADR-13). ADR-10 (ids estáveis) o guia e o dono já adotam; ADR-13 (servidor com criptografia) segue em aberto e depende dela.
11. **Citações sem fonte:** #7 e #12 estão como "obra a confirmar"; três frases sugeridas por ela aguardam fonte.

## O que o guia diz da web e deve ser relido para o app nativo
Critério de peso de 400 KB, CSP, `innerHTML`, Google Fonts e largura de navegador (critérios de aceite 2 e 5, privacidade). O contrato (comportamento, dados, textos) vale 1 para 1; a técnica de cumprir é do `mobile-dev`.

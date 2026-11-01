---
nome: revisar-regra
descricao: "Revisa uma mudança de comportamento, dados ou código do Entre sessões contra as regras de negócio RN-01 a RN-28, as decisões ADR-xx, os critérios de aceite e a regra de migração que preserva dados. Use em PR, diff ou plano antes de implementar."
ordem: 30
---
## Quando usar
Mudança em regra de filtro, busca, levar, envio, resumo, exemplos, catálogos, armazenamento, backup, importação ou formato de dados.

## Antes de começar
Leia o diff ou o plano e o código afetado. Liste os RN e ADR que a mudança toca; sem essa lista a revisão não começou.

## Procedimento
1. Para cada RN afetado, confirme que o comportamento do código bate com a regra (inclusive casos de borda: 23h59 e 00h00, empate, `levar:false` com `bring:'sim'`, exemplo nunca em Levar). Há teste por RN?
2. **Catálogos**: ids estáveis (p1..p5, d1..d6, ids de emoção, `sim|talvez|nao`) e ordem fixa. Reordenar, renomear id ou apagar item = **bloqueia** (corrompe registros antigos, ADR-10).
3. **Dados**: mudança de formato exige migração testada que preserva tudo; dado inválido é guardado e reportado, nunca descartado em silêncio; importação nunca apaga.
4. **Escopo**: a mudança toca algo de "depende de aprovação expressa"? Então bloqueie e encaminhe a Mônica.
5. **Decisões**: a mudança contradiz um ADR vigente? Peça novo ADR (linha com motivo e status) e cite o número.
6. **Commit**: a mensagem cita os códigos RN- e ADR-.
7. Regra ambígua ou contraditória no guia: **precisa da Mônica**.
8. Como implementar (armazenamento, criptografia, desempenho): é do `mobile-dev`.

## Entrega
Tabela RN/ADR afetado → conforme ou não → evidência (arquivo:linha ou teste) → ação. Fecha com o veredito: pode seguir, ajustar antes, ou parar e perguntar a Mônica.

## Armadilhas
Tratar o comportamento atual do código como regra (o código pode ter bug); aceitar migração sem teste com dados v1 reais ou exemplos; esquecer que "Sim" e "marcado para levar" são campos diferentes (`bring` x `levar`, ADR-06).

## Aprofundar
Conhecimento regras/regras-rn, regras/decisoes-adr, regras/criterios-de-aceite, privacidade/backup-e-migracoes.

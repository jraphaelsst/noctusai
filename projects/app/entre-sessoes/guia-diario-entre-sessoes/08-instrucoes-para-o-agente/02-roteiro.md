# Roteiro por fases

## Fase 0.5: correções no arquivo atual (baixo risco)

| # | Tarefa | Regra/ADR | Aprovação |
|---|---|---|---|
| 0.1 | Decidir com Mônica entre versão oficial (v21) e versão de teste escura | | sim |
| 0.2 | Trocar "Os botões redondos filtram" por texto coerente com os quadrados atuais em Como usar | texto oficial | sim |
| 0.3 | Remover o limite de 40 cartões ou paginar ("Ver mais registros") | RN-12 | não |
| 0.4 | Link discreto "Trocar meu nome" | RN-03 | sim (texto) |
| 0.5 | Gravar `questionText` junto de `q` nos registros novos | ADR-10 | não |

## Fase 1: app local robusto

Ordem obrigatória (cada passo depende do anterior):

1. Separar o código em módulos (`02-arquitetura/02-arquitetura-alvo.md`) sem mudar comportamento. Testes E1 a E13 passando antes e depois.
2. Extrair catálogos para `conteudo/` com ids estáveis.
3. Implementar `dados/repositorio.js` sobre localStorage (mesmo formato v1). Telas passam a usar só o repositório.
4. Implementar IndexedDB e a migração v1→v2 (`03-dados/05-backup-e-migracoes.md`). Teste E14.
5. Exportar e importar backup, com cifra opcional. Teste E15.
6. Servir fontes localmente (woff2, só os pesos usados, subconjunto latino).
7. PWA: manifest, ícones, service worker com cache versionado.
8. Orientação para adicionar à tela de início (Safari) e lembrete de backup.
9. Hospedagem em domínio da marca com HTTPS e CSP.
10. Comunicação às analisandas (texto aprovado por Mônica) sobre a nova versão e como levar os registros para o novo endereço, se o endereço mudar (exportar no antigo, importar no novo).

Atenção ao passo 10: o localStorage pertence à origem. Mudar de endereço **não leva os registros junto**. Antes de trocar de endereço, a versão antiga precisa ganhar o botão de exportar.

## Fase 2: somente com aprovação

Pré-requisitos jurídicos em `06-privacidade-e-seguranca/`. Esquema em `03-dados/schemas/banco.sql`. Sequência: autenticação, cadastro com consentimento, sincronização cifrada, caixa de envios de Mônica, exclusão de conta e exportação.

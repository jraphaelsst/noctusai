# Armazenamento local

## Fase 0 (hoje): localStorage

| Chave | Valor | Escrito quando |
|---|---|---|
| `diario-entre-sessoes:v1` | JSON `{records: Registro v1[], seeded: boolean}` (`schemas/store-localstorage.v1.schema.json`) | Salvar, apagar, marcar levar, semear e apagar exemplos |
| `diario-entre-sessoes:nome` | texto | Abertura e campo "Meu nome" |
| `diario-entre-sessoes:sessao` | texto | A cada tecla no campo "Minha sessão" |
| `diario-entre-sessoes:abertura` | `'1'` | Ao concluir a abertura |
| `diario-entre-sessoes:citacao` | número em texto | A cada carregamento (contador + 1) |
| `diario-entre-sessoes:teste` | `'1'` | Ao carregar, para detectar se o armazenamento funciona |

Toda leitura e escrita passa por `lsGet` e `lsSet`, com `try/catch`. Se falhar, `storageOK = false` e aparece o aviso de aba anônima.

## Fase 1: IndexedDB

Esquema em `schemas/indexeddb.md`. Regras:

1. Pedir `navigator.storage.persist()` depois do primeiro registro real salvo e guardar `persistenciaPedida`.
2. Depois de 7 dias sem backup e com pelo menos 5 registros reais, mostrar na Semana um lembrete discreto para exportar (não modal, dispensável).
3. Se o app não estiver instalado na tela de início e o navegador for Safari, mostrar uma vez, em Como usar, a orientação para adicionar à tela de início, explicando que isso protege os registros.
4. Manter o localStorage v1 intacto por 30 dias depois da migração (somente leitura) como garantia; depois apagar as chaves antigas.

## Riscos documentados

| Risco | Efeito | Mitigação |
|---|---|---|
| Safari apaga armazenamento de sites sem interação por 7 dias de uso | Perda total de registros | PWA na tela de início, backup, aviso |
| Analisanda limpa dados do navegador | Perda total | Backup, nota em Como usar |
| Aba anônima | Dados somem ao fechar | Aviso já existente |
| Troca de aparelho | Registros não vão junto | Exportar e importar backup |
| Cota excedida | Falha ao salvar | Tratar `QuotaExceededError` e avisar sem perder o texto digitado |

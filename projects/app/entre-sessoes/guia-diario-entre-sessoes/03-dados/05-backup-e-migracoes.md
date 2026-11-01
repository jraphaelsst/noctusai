# Backup e migrações

## Migração v1 (localStorage) para v2 (IndexedDB)

Executada uma vez, na primeira abertura da versão da fase 1. Idempotente.

1. Ler `diario-entre-sessoes:v1`. Se ausente ou inválido, pular para o passo 6.
2. Validar cada registro contra `registro.v1.schema.json`. Inválidos: guardar o JSON original em `meta.registrosInvalidos` e seguir (não descartar em silêncio).
3. Converter cada registro:

```js
const PERG = ['p1','p2','p3','p4','p5'];
const DESP = ['d1','d2','d3','d4','d5','d6'];
function v1paraV2(r) {
  return {
    schema: 2,
    id: r.id,
    example: !!r.example,
    ts: r.ts,
    updatedTs: r.ts,
    happened: r.happened || '',
    mind: r.mind || '',
    emotions: r.emotions || [],
    did: r.did || '',
    questionId: PERG[r.q],
    questionText: PERGUNTAS_V1[r.q],      // texto vigente em 31/10/2026
    answer: r.answer || '',
    awakenedIds: (r.awakened || []).map(i => DESP[i]),
    extra: r.extra || '',
    bring: r.bring,
    levar: typeof r.levar === 'boolean' ? r.levar : r.bring === 'sim'
  };
}
```

4. Gravar tudo numa transação. Se falhar, abortar e continuar usando v1 (nunca deixar a analisanda sem dados).
5. Migrar configuração: `nome`, `sessao`, `abertura` → `aberturaVista`, `citacao` → `citacaoN`, `seeded` → `exemplosSemeados`.
6. Gravar `schemaVersion = 2` e `meta.migradoDeV1Em`.
7. Manter as chaves v1 por 30 dias. Depois, apagar.

Teste obrigatório: carregar os três exemplos v1 e um registro com `levar: false` e `bring: 'sim'`; conferir que o resultado v2 valida no schema e que a aba Levar mostra as mesmas marcações de antes.

## Backup (exportar e importar)

- Formato: `schemas/backup.schema.json`. Arquivo `diario-entre-sessoes-AAAA-MM-DD.json`.
- Exportar inclui registros reais (sem exemplos), `nome` e `sessao`.
- Cifra opcional: senha escolhida pela analisanda; PBKDF2-SHA256 com no mínimo 600.000 iterações, sal de 16 bytes, AES-GCM 256 com IV de 12 bytes. O app avisa que **senha esquecida significa backup perdido**.
- Importar: valida o arquivo, decifra se preciso, mescla por `id`. Mesmo `id`: fica a versão com `updatedTs` maior. Mostra resumo: "N registros novos, M atualizados".
- Nunca apagar registros locais ao importar.

## Versionamento de schema

- Cada mudança de formato incrementa `schema` no registro e a versão do IndexedDB.
- Toda migração tem função pura testada e é reversível por backup.

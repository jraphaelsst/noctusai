# Esquema do IndexedDB (fase 1)

Banco: `diario-entre-sessoes`, versão `2` (o número 1 fica reservado ao formato legado em localStorage).

## Object stores

| Store | keyPath | Índices | Conteúdo |
|---|---|---|---|
| `registros` | `id` | `por_ts` em `ts`; `por_levar` em `levar`; `por_exemplo` em `example` | Objetos no formato `registro.v2.schema.json` |
| `config` | (chave externa) | nenhum | Valores de `config.schema.json`, uma entrada por chave |
| `meta` | (chave externa) | nenhum | `migradoDeV1Em` (ms), `appVersao` (string) |

Observação: IndexedDB não indexa booleanos. Gravar `levar` e `example` também como inteiros (`levarIdx`, `exemploIdx` com 0 ou 1) se os índices forem usados; ou filtrar em memória, que é suficiente para algumas centenas de registros. Recomendação: filtrar em memória e manter só o índice `por_ts`.

## Abertura e atualização

```js
const req = indexedDB.open('diario-entre-sessoes', 2);
req.onupgradeneeded = (e) => {
  const db = req.result;
  if (e.oldVersion < 2) {
    const r = db.createObjectStore('registros', { keyPath: 'id' });
    r.createIndex('por_ts', 'ts');
    db.createObjectStore('config');
    db.createObjectStore('meta');
  }
};
```

Depois de abrir, `repositorio.iniciar()` executa a migração do localStorage (ver `../05-backup-e-migracoes.md`) dentro de uma única transação `readwrite` sobre `registros` e `config`.

## Falhas

- `indexedDB` indisponível (aba anônima antiga, bloqueio): cair para o modo legado em localStorage e mostrar o aviso de armazenamento.
- `QuotaExceededError`: avisar a analisanda e sugerir exportar backup e apagar exemplos.

# Schemas

| Arquivo | O que descreve | Fase |
|---|---|---|
| `registro.v1.schema.json` | Registro como é gravado hoje | 0 |
| `store-localstorage.v1.schema.json` | Valor da chave `diario-entre-sessoes:v1` | 0 |
| `registro.v2.schema.json` | Registro com ids estáveis | 1 |
| `catalogos.schema.json` | Emoções, perguntas, despertares, opções do passo 7, citações | 0 em diante |
| `config.schema.json` | Nome, sessão, contador de citação e controles locais | 0 em diante |
| `backup.schema.json` | Arquivo de exportação, em claro ou cifrado | 1 |
| `envio.schema.json` | Envio a Mônica pelo app | 2 |
| `indexeddb.md` | Object stores e índices do banco local | 1 |
| `banco.sql` | PostgreSQL: tabelas, tipos, políticas de acesso por linha, carga dos catálogos | 2 (proposta) |

JSON Schema draft 2020-12. Os `$id` usam o domínio provisório `nosnolimiar.app` só como identificador; trocar pelo domínio real quando houver. Referências entre arquivos são relativas a esse `$id`.

Validação conferida em 31/10/2026 com `jsonschema` (Python): exemplos do app em v1, conversão para v2, backup e configuração passam; `q` fora de 0 a 4 é rejeitado.

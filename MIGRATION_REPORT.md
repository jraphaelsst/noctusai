# Relatório de Migração: Sistema Antigo de Permutas → ERP Imobiliário

## Resumo

| Tabela Origem | Registros | Destino | Status |
|---|---|---|---|
| `imovel_imovel` | 264 | `erp.ativos` (natureza='imovel') | ✅ Migrado |
| `permuta_permutaimovel` | 13 | `erp.ativos` (natureza='permuta_imovel') | ✅ Migrado |
| `imovel_interesseimovel` | 118 | `erp.ativos.interesses` (JSONB) | ✅ Embutido |
| `imovel_interesseautomovel` | 5 | `erp.ativos.interesses` (JSONB) | ✅ Embutido |
| `permuta_interessepermutaimovel` | 13 | `erp.ativos.interesses` (JSONB) | ✅ Embutido |
| `permuta_match` | 4 | `erp.matches` | ⏭️ Não migrado (preenchido automaticamente pelo algoritmo) |

**Total: 413 registros fonte → 277 ativos + ~214 clientes placeholder + ~147 condominios placeholder**
**Matches**: A tabela `erp.matches` já existe no schema e será preenchida automaticamente pelo algoritmo de matching quando rodar contra os ativos migrados.

## Dados Reais Migrados (sem perda)

Todos os dados reais foram preservados:

- **264 imóveis**: ref, valor_venda, tipo, zona, condominio_id, proprietario_id, corretor_id
- **13 permutas de imóvel**: tipo, endereço completo (cep, estado, cidade, bairro, logradouro), valor, proprietario, ref, codigo
- **118 interesses de imóvel**: tipo_imovel desejado, faixa de valor (min/max), zona, estado, observações textuais (ex: "Permuta em ate 50%. São Paulo ou granja")
- **5 interesses de automóvel**: tipo_automovel, faixa de valor
- **13 interesses de permuta**: critérios de busca com observações detalhadas
- **4 matches**: NÃO migrados — `erp.matches` é populada automaticamente pelo algoritmo de matching ao rodar contra os ativos migrados

## Dados FAKE / Mock (precisa de ação)

### 🔴 Crítico — Necessário para funcionamento

| Campo | Onde | Problema | Ação Necessária |
|---|---|---|---|
| `owner_id` | Todos os `erp.ativos` | Precisa do UUID real do `auth.users` | Substituir `YOUR_AUTH_USER_UUID_HERE` no script antes de rodar |
| `profile_id` | Todos os `erp.clientes` (campo `usuario_id`) | Precisa do UUID real do `erp.profiles` | Mesmo UUID que `owner_id` se o user tem profile |

### 🟡 Importante — Necessário para matching funcionar bem

| Campo | Onde | Valor Mock | Ação |
|---|---|---|---|
| `tipo_imovel` | Todos os ativos | Mapeamento inferido (ver abaixo) | **Revisar tabela de mapeamento** |
| `zona` | Todos os ativos | Mapeamento inferido | **Revisar tabela de mapeamento** |
| `erp.matches` | Tabela inteira | Vazia (não migrada) | Será populada automaticamente pelo algoritmo de matching |

### 🟢 Baixa prioridade — Dados de enriquecimento

| Campo | Onde | Valor Mock | Ação |
|---|---|---|---|
| `titulo_anuncio` | 264 imóveis | `[MOCK] REF - Atualizar título do anúncio` | Preencher com título real |
| `fotos` | Todos os ativos | `[]` (array vazio) | Upload de fotos |
| `plantas` | Todos os ativos | `[]` (array vazio) | Upload de plantas |
| `palavras_chave` | Todos os ativos | `[]` (array vazio) | Preencher SEO |
| `pontos_de_interesse` | Todos os ativos | `[]` (array vazio) | Preencher |
| `corretor` | Todos os ativos | `Corretor #N` | Substituir por nome real |
| `clientes.nome` | 214 clientes | `Proprietário #N` | Substituir por nome real |
| `clientes.email` | 214 clientes | `proprietario_N@migrado.placeholder` | Substituir por email real |
| `condominios.nome` | 147 condominios | `Condomínio #N` | Substituir por nome real |
| Colunas novas do ERP sem correspondente | Todos | NULL/default | Preencher conforme uso |

## Mapeamento tipo_id (⚠️ REVISAR)

Inferido a partir dos prefixos das referências dos imóveis:

| tipo_id antigo | Novo tipo_imovel | Evidência | Confiança |
|---|---|---|---|
| 1 | `apartamento` | Refs como AP0576, AP0687 | 🟢 Alta |
| 2 | `casa` | Refs genéricas (ONE*), Bertioga | 🟡 Média |
| 3 | `terreno` | Refs como TE0883, TE0280 | 🟢 Alta |
| 6 | `comercial` | Ref GA0124 (galpão?) | 🟡 Média |
| 7 | `casa` | 204/264 registros (77%), refs ONE* | 🟢 Alta |
| 8 | `rural` | 1 registro, ref ONE7320 | 🔴 Baixa |
| 9 | `comercial` | 2 registros | 🔴 Baixa |
| 10 | `apartamento` | 4 registros, possivelmente cobertura | 🟡 Média |
| 11 | `comercial` | Refs PR0013, PR0007 (prédio) | 🟡 Média |
| 13 | `rural` | Sem endereço preenchido | 🔴 Baixa |
| 14 | `terreno` | Refs AR0019, AR0035 (área) | 🟡 Média |

## Mapeamento zona_id (⚠️ REVISAR)

| zona_id antigo | Nova zona | Evidência | Confiança |
|---|---|---|---|
| 1 | `norte` | | 🔴 Baixa |
| 4 | `oeste` | 97% dos registros, negócio opera em SP Oeste (Barueri, Cotia, Alphaville) | 🟡 Média |
| 6 | `sul` | | 🔴 Baixa |
| 7 | `leste` | | 🔴 Baixa |
| 8 | `norte` | | 🔴 Baixa |

## Colunas Novas no ERP Sem Correspondente no Sistema Antigo

Estas colunas existem no `erp.ativos` mas o sistema antigo não tinha dados equivalentes. Ficam como NULL/default:

| Coluna | Tipo | Default | Impacto no Matching |
|---|---|---|---|
| `area_privativa` | NUMERIC | NULL | Sim - afeta `compatibilidade_specs` |
| `area_total` | NUMERIC | NULL | Sim - afeta `compatibilidade_specs` |
| `quartos` | INTEGER | NULL | Sim - afeta `compatibilidade_specs` |
| `suites` | INTEGER | NULL | Não |
| `banheiros` | INTEGER | NULL | Não |
| `vagas` | INTEGER | NULL | Sim - afeta `compatibilidade_specs` |
| `andar` | INTEGER | NULL | Não |
| `ano_construcao` | INTEGER | NULL | Não |
| `complemento` | TEXT | NULL | Não |
| `finalidade` | TEXT | `'venda'` | Não |
| `iptu` | NUMERIC | NULL | Não |
| `pronto_para_portais` | BOOLEAN | `false` | Não |
| `descricao_seo` | TEXT | NULL | Sim - afeta `qualidade_anuncio` |
| `tour_virtual_url` | TEXT | NULL | Sim - afeta `qualidade_anuncio` |
| `latitude` | NUMERIC | NULL | Não |
| `longitude` | NUMERIC | NULL | Não |
| `lqs_score_hint` | TEXT | NULL | Não |
| `aceita_completar_diferenca` | BOOLEAN | `false` | Sim - afeta `compatibilidade_preco` |
| `limite_complemento` | NUMERIC | NULL | Sim - afeta `compatibilidade_preco` |
| `metragem_min` | NUMERIC | NULL | Sim - afeta `compatibilidade_specs` |
| `metragem_max` | NUMERIC | NULL | Sim - afeta `compatibilidade_specs` |
| `quartos_min` | INTEGER | NULL | Sim - afeta `compatibilidade_specs` |
| `vagas_min` | INTEGER | NULL | Sim - afeta `compatibilidade_specs` |

## Impacto no Algoritmo de Matching

Com os dados migrados como estão, o matching vai funcionar de forma **parcial**:

### ✅ Funciona
- **Compatibilidade região** (30 pts): zona, cidade, bairro, estado estão preenchidos
- **Compatibilidade preço** (25 pts): valor, faixa_preco_min/max populados
- **Alinhamento interesses** (15 pts): interesses JSONB populado com tipo e valores

### ⚠️ Funciona parcialmente
- **Compatibilidade specs** (20 pts): Sem dados de quartos, área, vagas → score sempre 0 nessa dimensão
- **Qualidade anúncio** (10 pts): Sem fotos, título mock, sem descrição SEO → score mínimo (2 pts no máximo pelo título)

### Score estimado máximo sem enriquecer dados: ~72/100
Para atingir 100%, precisa preencher: quartos, área, vagas, fotos (3+), descrição SEO, tour virtual.

## Como Rodar

### Passo 1: Gerar os INSERTs
```bash
cd migratingDB
python3 migrate_load_data.py > inserts.sql
```

### Passo 2: Configurar o script SQL
Editar `migrate_to_erp.sql` e substituir:
- `YOUR_AUTH_USER_UUID_HERE` pelo UUID real do seu usuário em `auth.users`

### Passo 3: Executar no Supabase SQL Editor
1. Rodar `migrate_to_erp.sql` (cria staging tables e mappings)
2. Rodar `inserts.sql` (carrega dados nas staging tables)
3. Rodar o restante de `migrate_to_erp.sql` (STEPs 1-9)

### Passo 4: Validar
Rodar as queries de validação no final do `migrate_to_erp.sql`.

### Passo 5: Enriquecer dados
1. Atualizar nomes/emails dos 214 clientes placeholder
2. Atualizar nomes/endereços dos 147 condominios placeholder
3. Revisar mapeamentos tipo_imovel e zona
4. Preencher dados de quartos, área, vagas nos imóveis
5. Recalcular matches rodando o algoritmo de matching

## Dados Que Ficaram de Fora

O sistema antigo tinha tabelas que **não foram exportadas nos CSVs**:
- `proprietario_proprietario` — nomes e contatos dos proprietários (214 registros na produção)
- `condominio_condominio` — dados completos dos condomínios (147 registros)
- `authsys_user` / `authsys_profile` — dados dos corretores/usuários
- `permuta_permutaautomovel` — veículos oferecidos em permuta (0 registros no CSV)
- Tabelas de lookup: `tipo_imovel`, `zona`, `tipo_automovel` — mapeamento dos IDs numéricos

**Recomendação**: Se possível, exportar essas tabelas do banco antigo e rodar um script complementar para enriquecer os placeholders.

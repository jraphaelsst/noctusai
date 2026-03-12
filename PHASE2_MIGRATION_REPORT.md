# Relatório de Migração — Fase 2: Correção + Enriquecimento

**Data:** 2026-03-09
**Arquivo:** `migratingDB/05_second_migration.sql`
**Pré-requisito:** Fase 1 concluída (arquivos 01-04)

---

## Resumo

A Fase 1 migrou 264 imóveis e 13 permutas para `erp.ativos`, criando placeholders para clientes (~214) e condominios (~147). Os mapeamentos de `tipo_imovel` e `zona` foram **inferidos** a partir de prefixos de ref e análise de frequência, já que as lookup tables não estavam disponíveis.

A Fase 2 corrige esses mapeamentos com os **dados reais** das lookup tables e enriquece os placeholders com nomes, telefones, emails e endereços reais.

---

## Etapas Executadas

### ETAPA 1 — Staging + Data Loading
- Re-cria tabelas temporárias para JOINs via `ref`
- Carrega 264 imóveis + 13 permutas (dados originais da Fase 1)
- Carrega 6 lookup tables novas: tipo_imovel (17), zona (11), tipo_automovel (3), corretor (17), proprietário (231), condomínio (159)

### ETAPA 2 — Mapeamentos Corretos
Cria tabelas de mapeamento `tipo_imovel_correct` e `zona_correct` com valores normalizados compatíveis com o enum `erp.tipo_imovel`.

### ETAPA 3 — Correção de tipo_imovel nos ativos
**3 correções efetivas** (os demais já estavam corretos):

| tipo_id | Nome Real | Fase 1 (errado) | Fase 2 (correto) |
|---------|-----------|------------------|-------------------|
| 8 | Loja | `rural` | `comercial` |
| 9 | Casa em condominio | `comercial` | `casa` |
| 10 | Sala | `apartamento` | `comercial` |

Registros afetados: ~7 ativos (1 Loja, 2 Casa condominio, 4 Sala).

### ETAPA 4 — Correção de zona nos ativos
**4 correções efetivas**:

| zona_id | Nome Real | Fase 1 (errado) | Fase 2 (correto) |
|---------|-----------|------------------|-------------------|
| 1 | Sul | `norte` | `sul` |
| 6 | Litoral Sudeste | `sul` | `litoral_sudeste` |
| 7 | São Paulo | `leste` | `sao_paulo` |
| 8 | Litoral Norte | `norte` | `litoral_norte` |

zona_id=4 (`oeste`) já estava correto.

### ETAPA 5 — Corretores com nomes reais
Substitui `"Corretor #N"` pelo nome real do corretor. Limpa `"Corretor #0"` (era NULL no sistema antigo) para NULL.

**17 corretores** mapeados (ex: Corretor #2 → "Cindy", Corretor #13 → "Fernanda").

### ETAPA 6 — Correção do JSONB interesses
Corrige `tipo_imovel` e `zona` dentro dos objetos JSONB do array `interesses`. Usa substituição in-place (sem ambiguidade nos dados reais):
- `"comercial"` → `"casa"` (3 interesses afetados)
- `"rural"` → `"comercial"` (1 interesse afetado)
- `"norte"` → `"sul"`, `"sul"` → `"litoral_sudeste"`, `"leste"` → `"sao_paulo"`

### ETAPA 7 — Enriquecimento de clientes
Substitui placeholders `"Proprietário #N"` com dados reais:
- **nome**: nome real do proprietário
- **telefone**: telefone real
- **email**: email real (quando disponível, ~12 têm email)
- **observacoes**: marcado como `[MIGRADO-ENRIQUECIDO]`

~214 clientes enriquecidos.

### ETAPA 8 — Enriquecimento de condominios
Substitui placeholders `"Condomínio #N"` com dados reais:
- **nome**: nome real (ex: "São Paulo 2 - Km 26", "Fazendinha - Km 23")
- **endereco**: endereço + número (quando disponível)
- **bairro, cidade, estado, cep**: dados de localização
- **valor_condominio**: valor mensal (quando > 0)
- **observacoes**: inclui Km da Raposo Tavares

~147 condominios enriquecidos.

### ETAPA 9 — Localização dos imóveis
Propaga cidade, bairro, estado, cep, logradouro e condominio_nome dos condominios enriquecidos para os ativos. Na Fase 1, imóveis não tinham dados de localização (apenas FK para condominio).

~230+ ativos ganham dados de localização.

### ETAPA 10 — Validação
12 queries de validação verificam:
- Distribuição de tipo_imovel e zona
- Ausência de placeholders restantes
- Contagem de registros enriquecidos
- Amostras de dados corrigidos

---

## Dados que NÃO mudam

| Campo | Motivo |
|-------|--------|
| `interesses` (estrutura) | Mesmos registros, apenas valores corrigidos |
| `aceita_permutas` | Flag baseada em existência de interesses, não mudou |
| `valor` | Valores financeiros não dependem de lookup |
| `observacoes` / `observacoes_negociacao` | Texto livre dos interesses originais |
| `titulo_anuncio` | Mantém `[MOCK]` como marcador de migração |
| `fotos, plantas, palavras_chave` | Arrays vazios — precisam de dados reais |

---

## Ações Necessárias Pós-Migração

### Prioridade Alta
1. **Atualizar `titulo_anuncio`** — Todos os 277 ativos migrados têm `[MOCK] REF - Atualizar título do anúncio`. Substituir por títulos reais de anúncio.
2. **Adicionar fotos** — Arrays de fotos estão vazios. Upload manual necessário.
3. **Revisar clientes sem email real** — ~202 clientes mantêm email placeholder (`proprietario_N@migrado.placeholder`). Atualizar com emails reais quando disponíveis.

### Prioridade Média
4. **Remover registros de teste** — Condominios de teste detectados: "Condo Teste" (#147), "Teste2 Condo" (#148), "Teste3 Condo" (#149), "testeformcondo" (#150), "teste" (#151). Proprietário de teste: "Teste PP" (#212).
5. **Revisar condominios sem localização** — ~12 condominios têm CEP mas sem cidade/estado (ex: "Condomínio Mar Aberto Il", "Vila Verde", condominios "Km 39-45").
6. **Completar dados de condominios** — Amenidades (piscina, academia, etc.) estão com defaults. Preencher conforme dados reais.

### Prioridade Baixa
7. **Enriquecer permutas com dados adicionais** — Permutas já tinham dados de localização da Fase 1. Verificar se `area_privativa`, `quartos`, etc. estão disponíveis.
8. **Gerar embeddings** — Após corrigir títulos e adicionar dados, rodar `/api/matching/embed-batch` para gerar embeddings de matching.
9. **Rodar matching** — Após embeddings, executar `/api/matching/gerar` para popular `erp.matches`.

---

## Inventário de Dados

| Entidade | Total | Enriquecidos | Com dados completos |
|----------|-------|--------------|---------------------|
| Ativos (imóveis) | 264 | 264 (tipo/zona/corretor/localização) | ~230 (os com condomínio com cidade) |
| Ativos (permutas) | 13 | 13 (tipo/zona/corretor) | 13 (já tinham localização) |
| Clientes | ~214 | ~214 (nome/telefone) | ~12 (com email real) |
| Condominios | ~147 | ~147 (nome/localização) | ~135 (com cidade/bairro) |
| Corretores (campo em ativos) | — | ~180 ativos atualizados | 17 nomes únicos |
| Interesses (JSONB) | ~115 ativos | ~5 com tipo/zona corrigidos | — |

---

## Como Executar

```sql
-- No Supabase SQL Editor, executar o arquivo inteiro:
-- migratingDB/05_second_migration.sql
--
-- O script roda em uma transação (BEGIN...COMMIT).
-- Se qualquer etapa falhar, NADA é aplicado.
--
-- Tempo estimado: < 5 segundos (todas operações são UPDATEs indexados)
```

# Guia de Datas e Fusos Horários

## 📅 Padrão de Datas da Plataforma

Esta plataforma utiliza o fuso horário **America/Sao_Paulo (Brasília)** como padrão para todas as operações de data e hora.

## 🎯 Regras Fundamentais

### 1. Armazenamento no Banco de Dados
- **TODAS** as datas são armazenadas em `America/Sao_Paulo` timezone
- O PostgreSQL está configurado com `timezone = "America/Sao_Paulo"`
- Triggers automáticos normalizam timestamps para o fuso correto no momento do salvamento

### 2. Processamento no Backend
- Todas as Edge Functions usam `Deno.env.get('TZ')` configurado como `America/Sao_Paulo`
- Funções SQL personalizadas:
  - `current_date_sao_paulo()` - retorna a data atual em SP
  - `now_sao_paulo()` - retorna o timestamp atual em SP
  - `normalize_timestamp_sp(ts)` - normaliza qualquer timestamp para SP

### 3. Exibição no Frontend
- **Formato padrão**: `DD/MM/YYYY` (ex: 25/10/2025)
- **Com horário**: `DD/MM/YYYY às HH:mm` (ex: 25/10/2025 às 14:30)
- **Filtros**: Mantêm formato por extenso via `format(date, "PPP", { locale: ptBR })` (ex: 25 de outubro de 2025)
- **Filtros de data**: Usam `getTodayAtMidnight()` para garantir comparações consistentes

### 4. Criação de Metas
- **Criação Manual** (botão "Nova Meta"): Sempre cria nova meta, mesmo que já exista outra do mesmo tipo/categoria/período
- **Criação Automática** (configurações): 
  - Usa `ensure_scaffold_meta()` que APENAS busca metas existentes - **NÃO cria nova** nem **atualiza existente**
  - Se meta não existir no banco, o sistema de configurações cria uma nova
  - Se meta já existir, apenas reutiliza (não atualiza valores)
  - **IMPORTANTE**: Sistema de automação não sobrescreve metas criadas manualmente

## 🛠️ Utilitários Disponíveis

### Em `src/lib/utils.ts`:

```typescript
// Formatar data para exibição (DD/MM/YYYY)
formatDate(dateString: string, includeTime?: boolean): string

// Exemplos:
formatDate("2025-10-25T14:30:00Z")           // "25/10/2025"
formatDate("2025-10-25T14:30:00Z", true)     // "25/10/2025 às 14:30"
formatDate("2025-10-25")                     // "25/10/2025"

// Obter data atual sem horário (para filtros)
getTodayAtMidnight(): Date

// Remove horário de uma data
stripTime(date: Date): Date
```

### Para Filtros de Data:

Os filtros de data devem usar `getTodayAtMidnight()` como ponto de partida para garantir que as comparações sejam feitas apenas na parte de data, sem interferência de horários.

```typescript
// ✅ CORRETO - Filtros
import { getTodayAtMidnight } from '@/lib/utils';
import { startOfDay, endOfDay } from 'date-fns';

const hoje = getTodayAtMidnight(); // Data às 00:00:00
const inicio = startOfDay(hoje);
const fim = endOfDay(hoje);
```

Os componentes de filtro mantêm a formatação por extenso usando `format(date, "PPP", { locale: ptBR })`.

### No Banco de Dados:

```sql
-- Obter data atual em São Paulo
SELECT current_date_sao_paulo();

-- Obter timestamp atual em São Paulo
SELECT now_sao_paulo();

-- Normalizar timestamp para São Paulo
SELECT normalize_timestamp_sp(created_at);
```

## 📋 Checklist para Desenvolvimento

Ao trabalhar com datas, sempre:

- [ ] ✅ Usar `formatDate()` para exibir datas ao usuário (DD/MM/YYYY)
- [ ] ✅ Usar `getTodayAtMidnight()` em filtros para data inicial
- [ ] ✅ Usar dados calculados no banco (`dias_restantes`, `status`) em vez de cálculos locais
- [ ] ✅ Deixar o banco processar timestamps automáticamente via triggers
- [ ] ✅ Para consultas SQL, usar `current_date_sao_paulo()` ou `now_sao_paulo()`
- [ ] ✅ Não fazer comparações de data com `new Date(meta.data_prazo)`
- [ ] ✅ Confiar nos dados que vêm do banco (já estão em SP timezone)
- [ ] ✅ Manter formato por extenso em filtros usando date-fns

## ❌ O Que NÃO Fazer

- ❌ Não usar `new Date()` diretamente para comparações de data
- ❌ Não fazer cálculos locais de data (usar dados do banco como `dias_restantes`)
- ❌ Não converter manualmente timezones no frontend
- ❌ Não usar `new Date(meta.data_prazo)` para comparações
- ❌ Não criar lógica de data duplicada (usar sempre os dados calculados no banco)

## 🔄 Migração de Código Legado

Se encontrar código antigo que não segue este padrão:

1. Substitua formatações manuais de data por `formatDate()`
2. Remova conversões de timezone no frontend
3. Use as funções SQL do banco para datas atuais
4. Verifique se os triggers estão ativos nas tabelas
5. **CRÍTICO**: Substitua cálculos locais de data por dados do banco (`dias_restantes`, `status`, etc.)
6. Remova comparações como `new Date(meta.data_prazo) > new Date()`

## 📚 Referências

- Timezone configurado: `America/Sao_Paulo`
- Migration principal: `20251020224010_*.sql`
- Arquivo de configuração: `supabase/config.toml`
- Funções utilitárias: `src/lib/utils.ts`

## 💡 Exemplos Completos

### Exibição de Datas

```typescript
// ✅ CORRETO - Exibir datas
import { formatDate } from "@/lib/utils";

// Data simples
<p>{formatDate(meta.created_at)}</p>              // "25/10/2025"

// Data com horário
<p>{formatDate(meta.finalizada_em, true)}</p>     // "25/10/2025 às 14:30"
```

### Filtros de Data

```typescript
// ✅ CORRETO - Filtros
import { getTodayAtMidnight } from "@/lib/utils";
import { startOfMonth, endOfMonth, format } from "date-fns";
import { ptBR } from "date-fns/locale";

const hoje = getTodayAtMidnight();
const inicio = startOfMonth(hoje);
const fim = endOfMonth(hoje);

// Exibir no filtro (formato por extenso)
<Button>
  {format(inicio, "PPP", { locale: ptBR })}
</Button>
// Exibe: "1 de outubro de 2025"
```

### Salvar Dados

```typescript
// ✅ CORRETO - Salvar dados
// Deixe o backend processar timestamps
await supabase.from('metas').insert({
  // created_at e updated_at preenchidos pelo trigger
  data_prazo: '2025-10-25' // formato YYYY-MM-DD
});
```

### Comparações e Validações

```typescript
// ❌ ERRADO - Cálculos locais de data
const prazo = new Date(meta.data_prazo);
const isOverdue = new Date() > prazo;

// ✅ CORRETO - Usar dados do banco
const isOverdue = (meta.dias_restantes ?? 0) < 0 && meta.status !== 'concluida';
const diasRestantes = meta.dias_restantes ?? 0;
```

```sql
-- ✅ CORRETO - Backend/SQL
-- Obter metas de hoje
SELECT * FROM metas 
WHERE data_prazo = current_date_sao_paulo();

-- Criar registro (timestamps automáticos via trigger)
INSERT INTO metas (usuario_id, tipo, data_prazo)
VALUES (uuid, 'diaria', current_date_sao_paulo());
```

## 🚨 Troubleshooting

### Datas aparecem com -1 dia
- Problema comum: `new Date("YYYY-MM-DD")` interpreta como UTC, não como data local
- **Solução**: A função `formatDate()` já trata isso corretamente interpretando YYYY-MM-DD como data local
- Verifique se está usando `formatDate()` em vez de conversão manual
- Confirme que os triggers estão ativos na tabela

### Horários inconsistentes
- Verifique se `timezone` está configurado no `config.toml`
- Confirme que edge functions usam `TZ=America/Sao_Paulo`

### Comparações de data incorretas
- Use dados calculados no banco (`meta.dias_restantes`, `meta.status`)
- Não faça comparações locais com `new Date(meta.data_prazo)`
- Use funções SQL do banco (`current_date_sao_paulo()`) para queries

### Múltiplas metas da mesma categoria
- A plataforma permite múltiplas metas do mesmo tipo/categoria/período
- Criação manual sempre cria novas metas
- Sistema de automação reutiliza metas existentes sem criar duplicatas

---

**Última atualização**: 2025-10-20  
**Versão do Guia**: 2.0.0

**Changelog**:
- v2.0.0 (2025-10-20): BREAKING - Removida constraint de unicidade; criação manual sempre cria novas metas; sistema de automação apenas reutiliza metas existentes
- v1.3.0 (2025-10-20): Corrigido `formatDate()` para interpretar datas DATE (YYYY-MM-DD) como locais, não UTC
- v1.2.0 (2025-10-20): Adicionadas regras críticas sobre uso de dados calculados no banco (dias_restantes, status)
- v1.1.0 (2025-10-20): Adicionadas funções utilitárias para filtros (`getTodayAtMidnight`, `stripTime`)
- v1.0.0 (2025-10-20): Versão inicial com padrão de timezone America/Sao_Paulo

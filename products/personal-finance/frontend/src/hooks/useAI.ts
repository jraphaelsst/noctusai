/**
 * Personal Finance AI hooks (Phase 7 P1 indicators).
 *
 * Read side of the indicator pattern lives in `<AIIndicator refType refId/>`
 * from `@noctusai/lib/design-system`, which fetches `/api/ai/outputs`.
 * These hooks are write-side: trigger the inference + persist + invalidate
 * the matching query so the indicator rerenders.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { api } from '@noctusai/seed/infra';

interface AIOutputResult {
  ref_type: string;
  ref_id: string;
  kind: string;
  label: string;
  score?: number | null;
  chip?: string | null;
  explanation?: string | null;
  confidence?: number | null;
  prompt_version?: string | null;
  matched_categoria_id?: string | null;
}

function invalidateOutputs(qc: ReturnType<typeof useQueryClient>, refType: string, refId: string) {
  qc.invalidateQueries({ queryKey: ['ai_outputs', refType, refId] });
}

/** P1-opp — suggest a category for a transaction. */
export function useCategorizeTransaction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (params: { transacao_id: string }) => {
      const result = await api.post(`/api/ai/transacoes/${params.transacao_id}/categorize`, {});
      return result.data as AIOutputResult;
    },
    onSuccess: (_d, v) => {
      // "transacoes" (whole list) DROPPED — `categorize_transaction_endpoint`
      // (routers/ai.py) only reads the transação to build the LLM prompt
      // and persists an `ai_outputs` row via `_persist_indicator`; it
      // never writes to the `transacoes` table itself (no `.update()`
      // anywhere in that path). Applying a suggested category is a
      // separate write (not wired to this hook today) that would go
      // through `useUpdateTransacao`, which already invalidates
      // "transacoes" correctly on its own. Invalidating the whole list
      // here — for a read-only suggestion — was pure waste.
      invalidateOutputs(qc, 'transacao', v.transacao_id);
    },
    onError: (error: Error) =>
      toast.error('Erro ao categorizar transação', { description: error.message }),
  });
}

/** P3-opp — flag whether a transaction looks like a recurring expense. */
export function useRecurringFlag() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (params: { transacao_id: string }) => {
      const result = await api.post(`/api/ai/transacoes/${params.transacao_id}/recurring-flag`, {});
      return result.data as AIOutputResult;
    },
    onSuccess: (_d, v) => invalidateOutputs(qc, 'transacao', v.transacao_id),
    onError: (error: Error) =>
      toast.error('Erro ao avaliar recorrência', { description: error.message }),
  });
}

// ---------------------------------------------------------------------------
// P2-opp — monthly financial narrative (Phase 10). Dashboard card consumer.
// ---------------------------------------------------------------------------

export interface MonthlyNarrativeSummary {
  period_days: number;
  period_label: string;
  receita_total: number;
  despesa_total: number;
  fluxo_liquido: number;
  taxa_poupanca: number;
  top_categorias: Array<{ nome: string; total: number }>;
  transacoes_count: number;
  narrative: string;
}

export interface MonthlyNarrativeResponse {
  subject: string;
  html: string;
  text: string;
  summary: MonthlyNarrativeSummary;
}

export function useMonthlyNarrative(periodDays = 30) {
  return useQuery<MonthlyNarrativeResponse, Error>({
    queryKey: ['ai_monthly_narrative', periodDays],
    queryFn: async () => {
      const result = await api.get(`/api/ai/monthly-narrative?period_days=${periodDays}`);
      return result.data as MonthlyNarrativeResponse;
    },
    staleTime: 1000 * 60 * 30, // 30 min — narrative is stable
    retry: false,
  });
}

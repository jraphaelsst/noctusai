import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { api } from '@noctusai/seed/infra';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface AIDescriptionResult {
  titulo_sugerido: string;
  descricao: string;
}

export interface AILeadScoreResult {
  score: number;
  justificativa: string;
  recomendacao: string;
}

export interface AIPriceResult {
  preco_sugerido: number;
  faixa_min: number;
  faixa_max: number;
  analise: string;
  total_comparaveis: number;
}

export interface AIFollowUpDraft {
  channel: 'whatsapp' | 'email';
  subject: string | null;
  body: string;
  days_since_activity: number;
}

// ---------------------------------------------------------------------------
// Hooks
// ---------------------------------------------------------------------------

export function useGenerateDescription() {
  return useMutation({
    mutationFn: async (params: { imovel_id?: string; imovel_data?: Record<string, any> }) => {
      const result = await api.post('/api/ai/generate-description', params);
      return result.data as AIDescriptionResult;
    },
    onError: (error: Error) => {
      toast.error('Erro ao gerar descrição', { description: error.message });
    },
  });
}

export function useLeadScore() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (params: { cliente_id?: string; cliente_data?: Record<string, any> }) => {
      const result = await api.post('/api/ai/lead-score', params);
      return result.data as AILeadScoreResult;
    },
    onSuccess: (_data, variables) => {
      if (variables.cliente_id) {
        queryClient.invalidateQueries({ queryKey: ['cliente', variables.cliente_id] });
      }
    },
    onError: (error: Error) => {
      toast.error('Erro ao pontuar lead', { description: error.message });
    },
  });
}

export function useSuggestPrice() {
  return useMutation({
    mutationFn: async (params: { imovel_id?: string; imovel_data?: Record<string, any> }) => {
      const result = await api.post('/api/ai/suggest-price', params);
      return result.data as AIPriceResult;
    },
    onError: (error: Error) => {
      toast.error('Erro ao sugerir preço', { description: error.message });
    },
  });
}

/**
 * E4 — draft a personalized follow-up message for a stalled lead.
 *
 * Used by the Pipeline view to surface a "Rascunho de reengajamento"
 * button on leads with no activity > 14 days. User reviews the draft
 * before sending; this hook never sends the message itself.
 */
export function useFollowUpDraft() {
  return useMutation({
    mutationFn: async (params: { lead_id: string; imovel_interesse?: string }) => {
      const result = await api.post(`/api/ai/leads/${params.lead_id}/follow-up-draft`, {
        cliente_id: params.lead_id,
        imovel_interesse: params.imovel_interesse,
      });
      return result.data as AIFollowUpDraft;
    },
    onError: (error: Error) => {
      toast.error('Erro ao gerar rascunho de follow-up', { description: error.message });
    },
  });
}

// ---------------------------------------------------------------------------
// Phase 6 P1 indicators — write-side hooks. Read side via <AIIndicator
// refType refId/> from `@noctusai/lib/design-system`, which auto-fetches
// `/api/ai/outputs?ref_type=&ref_id=` and rerenders when our mutations
// invalidate that query key.
// ---------------------------------------------------------------------------

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
}

function invalidateOutputs(qc: ReturnType<typeof useQueryClient>, refType: string, refId: string) {
  qc.invalidateQueries({ queryKey: ['ai_outputs', refType, refId] });
}

/** E2 — classify a WhatsApp message into a sales intent. */
export function useWhatsAppIntent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (params: { cliente_id: string; message_text: string; cliente_nome?: string }) => {
      const result = await api.post('/api/ai/whatsapp-intent', params);
      return result.data as AIOutputResult;
    },
    onSuccess: (_d, v) => invalidateOutputs(qc, 'cliente', v.cliente_id),
    onError: (error: Error) => toast.error('Erro ao classificar intenção', { description: error.message }),
  });
}

/** E6 — score a client's certidões health. */
export function useCertidoesScore() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (params: { cliente_id: string }) => {
      const result = await api.post(`/api/ai/clientes/${params.cliente_id}/certidoes-score`, {});
      return result.data as AIOutputResult;
    },
    onSuccess: (_d, v) => invalidateOutputs(qc, 'cliente', v.cliente_id),
    onError: (error: Error) => toast.error('Erro ao calcular saúde de certidões', { description: error.message }),
  });
}

/** E7 — generate a coaching tip from current metas progress. */
export function useMetasCoachTip() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (params: {
      user_id: string;
      user_nome: string;
      progresso_percent: number;
      dias_restantes: number;
      eventos_recentes?: string[];
    }) => {
      const result = await api.post('/api/ai/metas/coach-tip', params);
      return result.data as AIOutputResult;
    },
    onSuccess: (_d, v) => invalidateOutputs(qc, 'user_metas', v.user_id),
    onError: (error: Error) => toast.error('Erro ao gerar dica de coach', { description: error.message }),
  });
}

/** E8 — assess listing-photo compliance. */
export function usePhotoCompliance() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (params: { imovel_id: string }) => {
      const result = await api.post(`/api/ai/imoveis/${params.imovel_id}/photo-compliance`, {});
      return result.data as AIOutputResult;
    },
    onSuccess: (_d, v) => invalidateOutputs(qc, 'ativo', v.imovel_id),
    onError: (error: Error) => toast.error('Erro ao analisar fotos', { description: error.message }),
  });
}

/** E10 — score how relevant a property is to a search query. */
export function useSearchRelevance() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (params: { imovel_id: string; query: string }) => {
      const result = await api.post('/api/ai/search-relevance', params);
      return result.data as AIOutputResult;
    },
    onSuccess: (_d, v) => invalidateOutputs(qc, 'ativo', v.imovel_id),
    onError: (error: Error) => toast.error('Erro ao calcular relevância', { description: error.message }),
  });
}

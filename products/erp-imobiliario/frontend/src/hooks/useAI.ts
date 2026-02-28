import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { api } from '@/lib/api-client';

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
      toast.error('Erro ao gerar descricao', { description: error.message });
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
      toast.error('Erro ao sugerir preco', { description: error.message });
    },
  });
}

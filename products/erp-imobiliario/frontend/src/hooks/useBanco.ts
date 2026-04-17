import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { api, useAuthStore } from '@noctusai/seed/infra';

export interface ExtratoBancario {
  id: string;
  banco: string;
  agencia?: string;
  conta?: string;
  data_importacao: string;
  arquivo_nome: string;
  periodo_inicio?: string;
  periodo_fim?: string;
  total_registros: number;
  created_at: string;
}

export interface MovimentacaoBancaria {
  id: string;
  extrato_id: string;
  data: string;
  descricao: string;
  valor: number;
  tipo: 'credito' | 'debito';
  conciliado: boolean;
  lancamento_id?: string;
  created_at: string;
}

export interface Remessa {
  id: string;
  tipo: 'cnab240' | 'cnab400';
  banco: string;
  arquivo_nome?: string;
  total_titulos: number;
  valor_total: number;
  status: 'gerado' | 'enviado' | 'processado' | 'erro';
  created_at: string;
}

interface FiltrosExtratos {
  banco?: string;
  data_inicio?: string;
  data_fim?: string;
  page?: number;
  page_size?: number;
}

interface FiltrosConciliacao {
  extrato_id?: string;
  conciliado?: boolean;
  tipo?: string;
  page?: number;
  page_size?: number;
}

export function useExtratos(filtros?: FiltrosExtratos) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['extratos', filtros],
    queryFn: async () => {
      const result = await api.get('/api/banco/extratos', {
        banco: filtros?.banco,
        data_inicio: filtros?.data_inicio,
        data_fim: filtros?.data_fim,
        page: filtros?.page || 1,
        page_size: filtros?.page_size || 50,
      });
      return {
        data: (result.data || []) as ExtratoBancario[],
        pagination: result.pagination,
      };
    },
    enabled: !!user,
    staleTime: 3 * 60 * 1000,
  });
}

export function useConciliacao(filtros?: FiltrosConciliacao) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['conciliacao', filtros],
    queryFn: async () => {
      const result = await api.get('/api/banco/conciliacao', {
        extrato_id: filtros?.extrato_id,
        conciliado: filtros?.conciliado,
        tipo: filtros?.tipo,
        page: filtros?.page || 1,
        page_size: filtros?.page_size || 50,
      });
      return {
        data: (result.data || []) as MovimentacaoBancaria[],
        pagination: result.pagination,
      };
    },
    enabled: !!user,
    staleTime: 3 * 60 * 1000,
  });
}

export function useImportarExtrato() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: {
      banco: string;
      agencia?: string;
      conta?: string;
      movimentacoes: Array<{
        data: string;
        descricao: string;
        valor: number;
        tipo: 'credito' | 'debito';
      }>;
    }) => {
      const result = await api.post('/api/banco/importar', data);
      return result.data as ExtratoBancario;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['extratos'] });
      queryClient.invalidateQueries({ queryKey: ['conciliacao'] });
      toast.success('Extrato importado!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao importar extrato', { description: error.message });
    },
  });
}

export function useConciliar() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: { movimentacao_id: string; lancamento_id: string }) => {
      const result = await api.post('/api/banco/conciliar', data);
      return result.data as MovimentacaoBancaria;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['conciliacao'] });
      toast.success('Conciliação realizada!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao conciliar movimentação', { description: error.message });
    },
  });
}

export function useGerarRemessa() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: { tipo: 'cnab240' | 'cnab400'; banco: string }) => {
      const result = await api.post('/api/banco/gerar-remessa', data);
      return result.data as Remessa;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['extratos'] });
      queryClient.invalidateQueries({ queryKey: ['conciliacao'] });
      toast.success('Remessa gerada!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao gerar remessa', { description: error.message });
    },
  });
}

export function useRetornoRemessa(remessaId?: string) {
  return useQuery({
    queryKey: ['retorno', remessaId],
    queryFn: async () => {
      if (!remessaId) return null;
      const result = await api.get(`/api/banco/retorno/${remessaId}`);
      return result.data as Remessa;
    },
    enabled: !!remessaId,
    staleTime: 5 * 60 * 1000,
  });
}

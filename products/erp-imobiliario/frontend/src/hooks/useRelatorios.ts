import { useQuery } from '@tanstack/react-query';
import { api, useAuthStore } from '@noctusai/seed/infra';
import type {
  RankingCorretor,
  ConversaoFunil,
  AtividadeMensal,
} from '@/types/locacoes';

export function useRankingCorretores(periodo: number = 30) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['relatorios', 'ranking-corretores', periodo],
    queryFn: async () => {
      const result = await api.get('/api/relatorios/ranking-corretores', { periodo });
      return (result.data || []) as RankingCorretor[];
    },
    enabled: !!user,
    staleTime: 5 * 60 * 1000,
    placeholderData: (prev) => prev,
  });
}

export function useConversaoFunil() {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['relatorios', 'conversao-funil'],
    queryFn: async () => {
      const result = await api.get('/api/relatorios/conversao-funil');
      return (result.data || []) as ConversaoFunil[];
    },
    enabled: !!user,
    staleTime: 5 * 60 * 1000,
  });
}

export function useAtividadeMensal(meses: number = 6) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['relatorios', 'atividade-mensal', meses],
    queryFn: async () => {
      const result = await api.get('/api/relatorios/atividade-mensal', { meses });
      return (result.data || []) as AtividadeMensal[];
    },
    enabled: !!user,
    staleTime: 5 * 60 * 1000,
    placeholderData: (prev) => prev,
  });
}

export function useExportCSV() {
  const exportCSV = async (tipo: string, params?: { periodo?: number; meses?: number }) => {
    const queryParams: Record<string, any> = { tipo };
    if (params?.periodo) queryParams.periodo = params.periodo;
    if (params?.meses) queryParams.meses = params.meses;

    const result = await api.get('/api/relatorios/export/csv', queryParams);

    // The response is CSV text — trigger download
    const blob = new Blob([result], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${tipo.replace(/-/g, '_')}.csv`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  return { exportCSV };
}

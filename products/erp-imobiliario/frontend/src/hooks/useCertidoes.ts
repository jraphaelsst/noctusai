import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { api } from '@/lib/api-client';
import { useAuthStore } from '@/store/authStore';

export interface CertidaoResultado {
  id: string;
  consulta_id: string;
  tipo: string;
  nome_display: string;
  ordem: number;
  status: 'pendente' | 'processando' | 'sucesso' | 'erro';
  analise_ia?: string;
  arquivo_url?: string;
  arquivo_nome?: string;
  erro_mensagem?: string;
  created_at: string;
}

export interface CertidaoConsulta {
  id: string;
  tipo_documento: 'cpf' | 'cnpj';
  documento: string;
  nome: string;
  data_nascimento?: string;
  genero?: string;
  rg?: string;
  nome_mae?: string;
  nome_pai?: string;
  status: 'pendente' | 'processando' | 'concluida' | 'erro';
  total_certidoes: number;
  concluidas: number;
  created_at: string;
  resultados?: CertidaoResultado[];
}

export interface ConsultaCreateData {
  tipo_documento: 'cpf' | 'cnpj';
  documento: string;
  nome: string;
  data_nascimento?: string;
  genero?: string;
  rg?: string;
  nome_mae?: string;
  nome_pai?: string;
}

interface FiltrosConsultas {
  busca?: string;
  status?: string;
}

export function useCertidaoConsultas(filtros?: FiltrosConsultas) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['certidao-consultas', filtros],
    queryFn: async () => {
      const params: Record<string, string> = {};
      if (filtros?.busca) params.busca = filtros.busca;
      if (filtros?.status && filtros.status !== 'todos') params.status = filtros.status;
      const result = await api.get('/api/certidoes/consultas', params);
      return (result.data || []) as CertidaoConsulta[];
    },
    enabled: !!user,
    staleTime: 30 * 1000, // 30s — data changes during processing
  });
}

export function useCertidaoConsulta(id?: string) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['certidao-consulta', id],
    queryFn: async () => {
      if (!id) return null;
      const result = await api.get(`/api/certidoes/consultas/${id}`);
      return result.data as CertidaoConsulta;
    },
    enabled: !!user && !!id,
    staleTime: 10 * 1000, // 10s — poll frequently during processing
    refetchInterval: (query) => {
      const data = query.state.data as CertidaoConsulta | null | undefined;
      if (data && (data.status === 'pendente' || data.status === 'processando')) {
        return 5000; // Poll every 5s while processing
      }
      return false;
    },
  });
}

export function useCreateConsulta() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: ConsultaCreateData) => {
      const result = await api.post('/api/certidoes/consultas', data);
      return result.data as CertidaoConsulta;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['certidao-consultas'] });
      toast.success('Consulta de certidões iniciada!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao criar consulta', { description: error.message });
    },
  });
}

export function useReprocessarConsulta() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string) => {
      await api.post(`/api/certidoes/consultas/${id}/reprocessar`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['certidao-consultas'] });
      queryClient.invalidateQueries({ queryKey: ['certidao-consulta'] });
      toast.success('Reprocessamento iniciado!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao reprocessar', { description: error.message });
    },
  });
}

export function useDeleteConsulta() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/api/certidoes/consultas/${id}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['certidao-consultas'] });
      toast.success('Consulta excluída com sucesso!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao excluir consulta', { description: error.message });
    },
  });
}

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { api } from '@/lib/api-client';
import { useAuthStore } from '@/store/authStore';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface Campanha {
  id: string;
  nome: string;
  tipo: 'email' | 'whatsapp' | 'alerta_imovel';
  status: 'rascunho' | 'ativa' | 'pausada' | 'concluida';
  template: string;
  filtros: Record<string, any>;
  total_enviados: number;
  total_abertos: number;
  total_cliques: number;
  created_at: string;
  updated_at: string;
  stats?: CampanhaStats;
}

export interface CampanhaStats {
  total: number;
  pendente: number;
  enviado: number;
  aberto: number;
  clicado: number;
  erro: number;
}

export interface AlertaMatch {
  cliente_id: string;
  cliente_nome: string;
  cliente_email: string;
  imovel_id: string;
  imovel_titulo: string;
  motivo: string;
}

interface FiltrosCampanhas {
  status?: string;
  tipo?: string;
  page?: number;
  page_size?: number;
}

interface CreateCampanhaData {
  nome: string;
  tipo: 'email' | 'whatsapp' | 'alerta_imovel';
  template: string;
  filtros?: Record<string, any>;
  status?: string;
}

interface UpdateCampanhaData {
  id: string;
  nome?: string;
  tipo?: string;
  template?: string;
  filtros?: Record<string, any>;
  status?: string;
}

// ---------------------------------------------------------------------------
// Hooks
// ---------------------------------------------------------------------------

export function useCampanhas(filtros?: FiltrosCampanhas) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['campanhas', filtros],
    queryFn: async () => {
      const result = await api.get('/api/marketing/campanhas', {
        status: filtros?.status,
        tipo: filtros?.tipo,
        page: filtros?.page || 1,
        page_size: filtros?.page_size || 50,
      });
      return result as { data: Campanha[]; pagination: any };
    },
    enabled: !!user,
    staleTime: 3 * 60 * 1000,
  });
}

export function useCampanha(id?: string) {
  return useQuery({
    queryKey: ['campanha', id],
    queryFn: async () => {
      if (!id) return null;
      const result = await api.get(`/api/marketing/campanhas/${id}`);
      return result.data as Campanha;
    },
    enabled: !!id,
    staleTime: 2 * 60 * 1000,
  });
}

export function useCreateCampanha() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: CreateCampanhaData) => {
      const result = await api.post('/api/marketing/campanhas', data);
      return result.data as Campanha;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['campanhas'] });
      toast.success('Campanha criada com sucesso!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao criar campanha', { description: error.message });
    },
  });
}

export function useUpdateCampanha() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, ...data }: UpdateCampanhaData) => {
      const result = await api.patch(`/api/marketing/campanhas/${id}`, data);
      return result.data as Campanha;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['campanhas'] });
      toast.success('Campanha atualizada!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao atualizar campanha', { description: error.message });
    },
  });
}

export function useDeleteCampanha() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/api/marketing/campanhas/${id}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['campanhas'] });
      toast.success('Campanha excluída!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao excluir campanha', { description: error.message });
    },
  });
}

export function useEnviarCampanha() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string) => {
      const result = await api.post(`/api/marketing/campanhas/${id}/enviar`);
      return result.data as { campanha_id: string; total_destinatarios: number; mensagem: string };
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['campanhas'] });
      toast.success(data.mensagem);
    },
    onError: (error: Error) => {
      toast.error('Erro ao enviar campanha', { description: error.message });
    },
  });
}

export function useAlertasMarketing() {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['marketing-alertas'],
    queryFn: async () => {
      const result = await api.get('/api/marketing/alertas');
      return (result.data || []) as AlertaMatch[];
    },
    enabled: !!user,
    staleTime: 5 * 60 * 1000,
  });
}

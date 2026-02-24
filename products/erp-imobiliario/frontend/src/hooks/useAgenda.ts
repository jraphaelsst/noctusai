import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { api } from '@/lib/api-client';
import { useAuthStore } from '@/store/authStore';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type TipoEvento = 'visita' | 'reuniao' | 'ligacao' | 'vistoria' | 'assinatura' | 'outro';
export type StatusEvento = 'agendado' | 'confirmado' | 'realizado' | 'cancelado';

export interface Evento {
  id: string;
  corretor_id: string;
  titulo: string;
  descricao?: string;
  tipo: TipoEvento;
  data_inicio: string;
  data_fim: string;
  local?: string;
  cliente_id?: string;
  imovel_id?: string;
  status: StatusEvento;
  cor: string;
  created_at: string;
  updated_at: string;
  _conflito?: {
    evento_id: string;
    titulo: string;
    mensagem: string;
  };
}

interface FiltrosEvento {
  data_inicio?: string;
  data_fim?: string;
  corretor_id?: string;
  tipo?: string;
  status?: string;
  page?: number;
  page_size?: number;
}

interface CreateEventoData {
  titulo: string;
  tipo: TipoEvento;
  data_inicio: string;
  data_fim: string;
  descricao?: string;
  local?: string;
  cliente_id?: string;
  imovel_id?: string;
  status?: StatusEvento;
  cor?: string;
}

interface UpdateEventoData {
  id: string;
  titulo?: string;
  tipo?: TipoEvento;
  data_inicio?: string;
  data_fim?: string;
  descricao?: string;
  local?: string;
  cliente_id?: string;
  imovel_id?: string;
  status?: StatusEvento;
  cor?: string;
}

// ---------------------------------------------------------------------------
// Hooks
// ---------------------------------------------------------------------------

export function useEventos(filtros?: FiltrosEvento) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['eventos', filtros],
    queryFn: async () => {
      const result = await api.get('/api/agenda', {
        data_inicio: filtros?.data_inicio,
        data_fim: filtros?.data_fim,
        corretor_id: filtros?.corretor_id,
        tipo: filtros?.tipo,
        status: filtros?.status,
        page: filtros?.page || 1,
        page_size: filtros?.page_size || 100,
      });
      return result as { data: Evento[]; pagination: any };
    },
    enabled: !!user,
    staleTime: 2 * 60 * 1000,
  });
}

export function useEvento(id?: string) {
  return useQuery({
    queryKey: ['evento', id],
    queryFn: async () => {
      if (!id) return null;
      const result = await api.get(`/api/agenda/${id}`);
      return result.data as Evento;
    },
    enabled: !!id,
    staleTime: 5 * 60 * 1000,
  });
}

export function useEventosHoje() {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['eventos-hoje'],
    queryFn: async () => {
      const result = await api.get('/api/agenda/hoje');
      return (result.data || []) as Evento[];
    },
    enabled: !!user,
    staleTime: 2 * 60 * 1000,
  });
}

export function useEventosSemana() {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['eventos-semana'],
    queryFn: async () => {
      const result = await api.get('/api/agenda/semana');
      return (result.data || []) as Evento[];
    },
    enabled: !!user,
    staleTime: 2 * 60 * 1000,
  });
}

export function useCreateEvento() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: CreateEventoData) => {
      const result = await api.post('/api/agenda', data);
      return result.data as Evento;
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['eventos'] });
      queryClient.invalidateQueries({ queryKey: ['eventos-hoje'] });
      queryClient.invalidateQueries({ queryKey: ['eventos-semana'] });
      if (data._conflito) {
        toast.warning('Evento criado com conflito de horario', {
          description: data._conflito.mensagem,
        });
      } else {
        toast.success('Evento criado com sucesso!');
      }
    },
    onError: (error: Error) => {
      toast.error('Erro ao criar evento', { description: error.message });
    },
  });
}

export function useUpdateEvento() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, ...data }: UpdateEventoData) => {
      const result = await api.patch(`/api/agenda/${id}`, data);
      return result.data as Evento;
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['eventos'] });
      queryClient.invalidateQueries({ queryKey: ['eventos-hoje'] });
      queryClient.invalidateQueries({ queryKey: ['eventos-semana'] });
      if (data._conflito) {
        toast.warning('Evento atualizado com conflito', {
          description: data._conflito.mensagem,
        });
      } else {
        toast.success('Evento atualizado!');
      }
    },
    onError: (error: Error) => {
      toast.error('Erro ao atualizar evento', { description: error.message });
    },
  });
}

export function useDeleteEvento() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/api/agenda/${id}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['eventos'] });
      queryClient.invalidateQueries({ queryKey: ['eventos-hoje'] });
      queryClient.invalidateQueries({ queryKey: ['eventos-semana'] });
      toast.success('Evento excluido!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao excluir evento', { description: error.message });
    },
  });
}

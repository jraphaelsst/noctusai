import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { api, useAuthStore } from '@noctusai/seed/infra';

export interface Filial {
  id: string;
  org_id: string;
  nome: string;
  codigo: string;
  endereco?: string | null;
  cidade?: string | null;
  estado?: string | null;
  telefone?: string | null;
  responsavel_id?: string | null;
  is_active: boolean;
  created_at: string;
  total_imoveis?: number;
  total_clientes?: number;
}

export interface ConsolidadoFiliais {
  filiais: Filial[];
  totais: {
    imoveis: number;
    clientes: number;
    filiais: number;
  };
}

export function useFiliais(filters?: { is_active?: boolean }) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['filiais', filters],
    queryFn: async () => {
      const result = await api.get('/api/filiais', filters);
      return (result.data || []) as Filial[];
    },
    enabled: !!user,
    staleTime: 5 * 60 * 1000,
    placeholderData: (prev) => prev,
  });
}

export function useFilial(id?: string) {
  return useQuery({
    queryKey: ['filial', id],
    queryFn: async () => {
      if (!id) return null;
      const result = await api.get(`/api/filiais/${id}`);
      return result.data as Filial;
    },
    enabled: !!id,
  });
}

export function useCreateFilial() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: {
      nome: string;
      codigo: string;
      endereco?: string;
      cidade?: string;
      estado?: string;
      telefone?: string;
      responsavel_id?: string;
    }) => {
      const result = await api.post('/api/filiais', data);
      return result.data as Filial;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['filiais'] });
      queryClient.invalidateQueries({ queryKey: ['filiais-consolidado'] });
      toast.success('Filial criada com sucesso!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao criar filial', { description: error.message });
    },
  });
}

export function useUpdateFilial() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, ...data }: Partial<Filial> & { id: string }) => {
      const result = await api.patch(`/api/filiais/${id}`, data);
      return result.data as Filial;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['filiais'] });
      queryClient.invalidateQueries({ queryKey: ['filiais-consolidado'] });
      toast.success('Filial atualizada!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao atualizar filial', { description: error.message });
    },
  });
}

export function useDeleteFilial() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/api/filiais/${id}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['filiais'] });
      queryClient.invalidateQueries({ queryKey: ['filiais-consolidado'] });
      toast.success('Filial desativada!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao desativar filial', { description: error.message });
    },
  });
}

export function useConsolidadoFiliais() {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['filiais-consolidado'],
    queryFn: async () => {
      const result = await api.get('/api/filiais/consolidado');
      return result.data as ConsolidadoFiliais;
    },
    enabled: !!user,
  });
}

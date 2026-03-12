import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { api } from '@/lib/api-client';
import { useAuthStore } from '@/store/authStore';
import type {
  Vistoria,
  VistoriaCreateData,
  VistoriaUpdateData,
  ChecklistItem,
} from '@/types/locacoes';

interface FiltrosVistorias {
  imovel_id?: string;
  tipo?: string;
  status?: string;
}

export function useVistorias(filtros?: FiltrosVistorias) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['vistorias', filtros],
    queryFn: async () => {
      const params: Record<string, any> = {};
      if (filtros?.imovel_id) params.imovel_id = filtros.imovel_id;
      if (filtros?.tipo && filtros.tipo !== 'todos') params.tipo = filtros.tipo;
      if (filtros?.status && filtros.status !== 'todos') params.status = filtros.status;
      const result = await api.get('/api/vistorias', params);
      return (result.data || []) as Vistoria[];
    },
    enabled: !!user,
    staleTime: 3 * 60 * 1000,
  });
}

export function useVistoria(id?: string) {
  return useQuery({
    queryKey: ['vistoria', id],
    queryFn: async () => {
      if (!id) return null;
      const result = await api.get(`/api/vistorias/${id}`);
      return result.data as Vistoria;
    },
    enabled: !!id,
    staleTime: 5 * 60 * 1000,
  });
}

export function useTemplateChecklist() {
  return useQuery({
    queryKey: ['vistoria-template-checklist'],
    queryFn: async () => {
      const result = await api.get('/api/vistorias/template-checklist');
      return (result.data || []) as ChecklistItem[];
    },
    staleTime: 60 * 60 * 1000, // 1 hour — template is static
  });
}

export function useCreateVistoria() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: VistoriaCreateData) => {
      const result = await api.post('/api/vistorias', data);
      return result.data as Vistoria;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['vistorias'] });
      queryClient.invalidateQueries({ queryKey: ['locacoes'] });
      toast.success('Vistoria criada com sucesso!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao criar vistoria', { description: error.message });
    },
  });
}

export function useUpdateVistoria() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, ...data }: VistoriaUpdateData) => {
      const result = await api.patch(`/api/vistorias/${id}`, data);
      return result.data as Vistoria;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['vistorias'] });
      queryClient.invalidateQueries({ queryKey: ['vistoria'] });
      toast.success('Vistoria atualizada com sucesso!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao atualizar vistoria', { description: error.message });
    },
  });
}

export function useDeleteVistoria() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/api/vistorias/${id}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['vistorias'] });
      toast.success('Vistoria excluída com sucesso!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao excluir vistoria', { description: error.message });
    },
  });
}

export function useAddFotosVistoria() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, urls }: { id: string; urls: string[] }) => {
      const result = await api.post(`/api/vistorias/${id}/fotos`, { urls });
      return result.data as Vistoria;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['vistorias'] });
      queryClient.invalidateQueries({ queryKey: ['vistoria'] });
      toast.success('Fotos adicionadas com sucesso!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao adicionar fotos', { description: error.message });
    },
  });
}

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { api, useAuthStore } from '@noctusai/seed/infra';
import { Cliente, EtapaFunil } from '@/types/clientes';

interface FiltrosClientes {
  busca?: string;
  responsavelId?: string;
  origem?: string;
  incluirArquivados?: boolean;
  dataInicio?: Date;
  dataFim?: Date;
  etapa?: EtapaFunil;
}

export function useClientes(filtros?: FiltrosClientes) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['clientes', filtros],
    queryFn: async () => {
      const result = await api.get('/api/clientes', {
        busca: filtros?.busca,
        responsavel_id: filtros?.responsavelId,
        origem: filtros?.origem,
        etapa: filtros?.etapa,
        incluir_arquivados: filtros?.incluirArquivados || false,
      });
      return (result.data || []) as Cliente[];
    },
    enabled: !!user,
    staleTime: 3 * 60 * 1000,
  });
}

export function useCliente(id?: string) {
  return useQuery({
    queryKey: ['cliente', id],
    queryFn: async () => {
      if (!id) return null;
      const result = await api.get(`/api/clientes/${id}`);
      return result.data as Cliente;
    },
    enabled: !!id,
    staleTime: 5 * 60 * 1000,
  });
}

interface CreateClienteData {
  nome: string;
  email?: string;
  telefone?: string;
  origem?: string;
  interesse?: string;
  observacoes?: string;
  probabilidade?: number;
  valor_estimado?: number;
}

export function useCreateCliente() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: CreateClienteData) => {
      const result = await api.post('/api/clientes', data);
      return result.data as Cliente;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['clientes'] });
      queryClient.invalidateQueries({ queryKey: ['funil'] });
      toast.success('Cliente criado com sucesso!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao criar cliente', { description: error.message });
    },
  });
}

interface UpdateClienteData {
  id: string;
  nome?: string;
  email?: string;
  telefone?: string;
  origem?: string;
  interesse?: string;
  observacoes?: string;
  probabilidade?: number;
  valor_estimado?: number;
}

export function useUpdateCliente() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, ...data }: UpdateClienteData) => {
      const result = await api.patch(`/api/clientes/${id}`, data);
      return result.data as Cliente;
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['clientes'] });
      queryClient.invalidateQueries({ queryKey: ['funil'] });
      queryClient.invalidateQueries({ queryKey: ['cliente', variables.id] });
      toast.success('Cliente atualizado com sucesso!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao atualizar cliente', { description: error.message });
    },
  });
}

export function useToggleArquivarCliente() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string) => {
      const result = await api.post(`/api/clientes/${id}/arquivar`);
      return result.data as Cliente;
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['clientes'] });
      queryClient.invalidateQueries({ queryKey: ['funil'] });
      toast.success(data?.arquivado ? 'Cliente arquivado' : 'Cliente desarquivado');
    },
    onError: (error: Error) => {
      toast.error('Erro ao arquivar cliente', { description: error.message });
    },
  });
}

export function useDeleteCliente() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/api/clientes/${id}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['clientes'] });
      queryClient.invalidateQueries({ queryKey: ['funil'] });
      toast.success('Cliente excluído com sucesso!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao excluir cliente', { description: error.message });
    },
  });
}

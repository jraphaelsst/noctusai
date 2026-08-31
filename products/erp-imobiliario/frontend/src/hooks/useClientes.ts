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
    placeholderData: (prev) => prev,
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
      // 'funil' dropped: since the P1.5.4 reshape (see useFunil.ts's
      // docblock) the board's cards are `negociacoes_venda` rows, not
      // clientes — `criar_cliente` (backend/app/routers/clientes.py) only
      // INSERTs into `clientes`, never `negociacoes_venda`, so a brand-new
      // cliente has no deal and cannot appear on the board yet.
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
      // Kept: the funil board's cards nest the cliente as a join
      // (`cliente:clientes!...(id, nome, email, telefone, origem)` —
      // backend/app/services/negociacoes_venda_service.py NEGOCIACAO_SELECT),
      // so editing nome/email/telefone/origem here changes what an open
      // deal's card renders.
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
    // Optimistic: flips `arquivado` on the matching row of every cached
    // `['clientes', ...]` list immediately, so the button feels instant
    // instead of waiting a round-trip + the onSuccess invalidation below.
    // `onError` rolls back to the pre-mutation snapshot. Same rollback
    // discipline as products/social-wiring/frontend/src/hooks/useCardHub.ts
    // useSetClienteTagsMutation (~L235).
    onMutate: async (id: string) => {
      await queryClient.cancelQueries({ queryKey: ['clientes'] });
      const previousQueries = queryClient.getQueriesData<Cliente[]>({ queryKey: ['clientes'] });
      previousQueries.forEach(([queryKey, data]) => {
        if (!data) return;
        queryClient.setQueryData<Cliente[]>(
          queryKey,
          data.map((c) => (c.id === id ? { ...c, arquivado: !c.arquivado } : c)),
        );
      });
      return { previousQueries };
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['clientes'] });
      // 'funil' dropped: the board filters on the NEGOCIAÇÃO's own
      // `arquivado` column (backend/app/routers/funil.py `incluir_arquivados`
      // → `.eq("arquivado", False)` on negociacoes_venda), not the cliente's —
      // a distinct field toggled by useFunil.ts's useArquivarNegociacao. The
      // nested cliente join also doesn't project `arquivado`
      // (NEGOCIACAO_SELECT: id, nome, email, telefone, origem), so nothing
      // on a card changes here either.
      toast.success(data?.arquivado ? 'Cliente arquivado' : 'Cliente desarquivado');
    },
    onError: (error: Error, _id, context) => {
      context?.previousQueries?.forEach(([queryKey, data]) => {
        queryClient.setQueryData(queryKey, data);
      });
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
      // Kept: `negociacoes_venda.cliente_id` is `REFERENCES erp.clientes(id)
      // ON DELETE CASCADE` (migrations/040_negociacoes_venda.sql) — deleting
      // a cliente deletes its open deals too, which removes cards from the
      // board.
      queryClient.invalidateQueries({ queryKey: ['funil'] });
      toast.success('Cliente excluído com sucesso!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao excluir cliente', { description: error.message });
    },
  });
}

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { api, useAuthStore } from '@noctusai/seed/infra';

export interface PortalFeed {
  portal: string;
  nome: string;
  descricao: string;
  formato: string;
  url: string;
  imoveis_prontos: number;
}

export interface ImovelPortal {
  id: string;
  titulo_anuncio?: string | null;
  cidade?: string | null;
  bairro?: string | null;
  estado?: string | null;
  tipo_imovel?: string | null;
  valor: number;
  pronto_para_portais: boolean;
  status: string;
  fotos?: string[] | null;
  descricao_seo?: string | null;
}

export function usePortaisFeeds() {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['portais-feeds'],
    queryFn: async () => {
      const result = await api.get('/api/portais/feeds');
      return (result.data || []) as PortalFeed[];
    },
    enabled: !!user,
    staleTime: 30 * 60 * 1000,
  });
}

export function useImoveisPortal(prontoParaPortais?: boolean) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['portais-imoveis', prontoParaPortais],
    queryFn: async () => {
      const params: Record<string, any> = { page_size: 200 };
      if (prontoParaPortais !== undefined) {
        params.pronto_para_portais = prontoParaPortais;
      }
      const result = await api.get('/api/portais/imoveis', params);
      return (result.data || []) as ImovelPortal[];
    },
    enabled: !!user,
    staleTime: 5 * 60 * 1000,
    placeholderData: (prev) => prev,
  });
}

export function useTogglePortal() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ imovelId, prontoParaPortais }: { imovelId: string; prontoParaPortais: boolean }) => {
      const result = await api.patch(`/api/portais/toggle/${imovelId}`, {
        pronto_para_portais: prontoParaPortais,
      });
      return result.data;
    },
    // Optimistic toggle: flips `pronto_para_portais` on the matching row of
    // every cached `['portais-imoveis', ...]` list immediately; `onError`
    // rolls back to the pre-mutation snapshot. Same rollback discipline as
    // products/social-wiring/frontend/src/hooks/useCardHub.ts
    // useSetClienteTagsMutation (~L235). The three invalidateQueries calls in
    // onSuccess below — incl. the root `['imoveis']` key — are Category C
    // (root-key invalidation, out of scope for this slice) and stay as-is.
    onMutate: async ({ imovelId, prontoParaPortais }: { imovelId: string; prontoParaPortais: boolean }) => {
      await queryClient.cancelQueries({ queryKey: ['portais-imoveis'] });
      const previousQueries = queryClient.getQueriesData<ImovelPortal[]>({ queryKey: ['portais-imoveis'] });
      previousQueries.forEach(([queryKey, data]) => {
        if (!data) return;
        queryClient.setQueryData<ImovelPortal[]>(
          queryKey,
          data.map((imv) => (imv.id === imovelId ? { ...imv, pronto_para_portais: prontoParaPortais } : imv)),
        );
      });
      return { previousQueries };
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['portais-feeds'] });
      queryClient.invalidateQueries({ queryKey: ['portais-imoveis'] });
      queryClient.invalidateQueries({ queryKey: ['imoveis'] });
      const label = variables.prontoParaPortais ? 'ativado' : 'desativado';
      toast.success(`Portal ${label} para o imovel`);
    },
    onError: (error: Error, _variables, context) => {
      context?.previousQueries?.forEach(([queryKey, data]) => {
        queryClient.setQueryData(queryKey, data);
      });
      toast.error('Erro ao alterar status do portal', { description: error.message });
    },
  });
}

export function usePortalFeedUrl(portal: string) {
  const backendUrl = import.meta.env.VITE_BACKEND_API_URL || 'http://localhost:8001';
  return `${backendUrl}/api/portais/feed/${portal}`;
}

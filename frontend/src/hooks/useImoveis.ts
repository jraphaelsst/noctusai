import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { supabase } from '@/integrations/supabase/client';
import { toast } from 'sonner';
import { useAuthStore } from '@/store/authStore';
import { useIsAdmin } from './useUserRole';

// Ativo with natureza='imovel'
export interface Imovel {
  id: string;
  owner_id: string;
  natureza: 'imovel';
  valor: number;
  status: string;
  observacoes?: string | null;
  created_at: string;
  updated_at: string;
  // Property
  tipo_imovel?: string | null;
  cep?: string | null;
  logradouro?: string | null;
  numero?: string | null;
  complemento?: string | null;
  bairro?: string | null;
  cidade?: string | null;
  estado?: string | null;
  zona?: string | null;
  condominio_id?: string | null;
  condominio_nome?: string | null;
  area_privativa?: number | null;
  area_total?: number | null;
  quartos?: number | null;
  suites?: number | null;
  banheiros?: number | null;
  vagas?: number | null;
  andar?: number | null;
  ano_construcao?: number | null;
  // Imóvel-only
  ref?: string | null;
  corretor?: string | null;
  proprietario_id?: string | null;
  aceita_permutas?: boolean;
  finalidade?: string | null;
  iptu?: number | null;
  pronto_para_portais?: boolean;
  titulo_anuncio?: string | null;
  descricao_seo?: string | null;
  fotos?: string[] | null;
  plantas?: string[] | null;
  palavras_chave?: string[] | null;
  pontos_de_interesse?: string[] | null;
  tour_virtual_url?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  lqs_score_hint?: string | null;
  observacoes_negociacao?: string | null;
  interesses?: any[];
}

export type NovoImovelForm = Omit<Imovel, 'id' | 'owner_id' | 'natureza' | 'created_at' | 'updated_at'>;

export function useImoveis() {
  const { user } = useAuthStore();
  const { isAdmin } = useIsAdmin();

  return useQuery({
    queryKey: ['imoveis', user?.id],
    queryFn: async () => {
      if (!user) return [];

      let query = supabase
        .from('ativos')
        .select('*')
        .eq('natureza', 'imovel')
        .order('created_at', { ascending: false });

      if (!isAdmin) {
        query = query.eq('owner_id', user.id);
      }

      const { data, error } = await query;
      if (error) throw error;
      return data as Imovel[];
    },
    enabled: !!user,
  });
}

export function useImovel(id?: string) {
  return useQuery({
    queryKey: ['imovel', id],
    queryFn: async () => {
      if (!id) return null;
      const { data, error } = await supabase
        .from('ativos')
        .select('*')
        .eq('id', id)
        .eq('natureza', 'imovel')
        .single();
      if (error) throw error;
      return data as Imovel;
    },
    enabled: !!id,
  });
}

export function useCreateImovel() {
  const queryClient = useQueryClient();
  const { user } = useAuthStore();

  return useMutation({
    mutationFn: async (data: NovoImovelForm) => {
      if (!user) throw new Error('Usuário não autenticado');

      const { data: imovel, error } = await supabase
        .from('ativos')
        .insert({
          ...data,
          owner_id: user.id,
          natureza: 'imovel',
          fotos: data.fotos || [],
          plantas: data.plantas || [],
          palavras_chave: data.palavras_chave || [],
          pontos_de_interesse: data.pontos_de_interesse || [],
          interesses: data.interesses || [],
        })
        .select()
        .single();

      if (error) throw error;

      supabase.from('user_actions_log').insert([{
        usuario_id: user.id,
        tipo_acao: 'criar',
        tipo_entidade: 'ativo',
        entidade_id: imovel.id,
        descricao: `Criou imóvel ${imovel.id}`,
      }]).then();

      return imovel as Imovel;
    },
    onSuccess: (imovel) => {
      queryClient.invalidateQueries({ queryKey: ['imoveis'] });
      queryClient.invalidateQueries({ queryKey: ['ativos'] });
      toast.success('Imóvel criado com sucesso!');

      if (imovel?.id && imovel.aceita_permutas) {
        import('@/lib/matching-api').then(({ triggerMatching }) =>
          triggerMatching({ ativo_origem_id: imovel.id }).then((data) => {
            const total = data?.total || 0;
            if (total > 0) {
              toast.info(`${total} match${total !== 1 ? 'es' : ''} de permuta encontrado${total !== 1 ? 's' : ''}!`);
            }
            queryClient.invalidateQueries({ queryKey: ['matches'] });
            queryClient.invalidateQueries({ queryKey: ['match-counts'] });
          })
        ).catch((err) => {
          console.warn('Auto-matching failed (non-blocking):', err);
        });
      }
    },
    onError: (error: Error) => {
      toast.error('Erro ao criar imóvel', { description: error.message });
    },
  });
}

export function useUpdateImovel() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, ...data }: Partial<Imovel> & { id: string }) => {
      const { data: imovel, error } = await supabase
        .from('ativos')
        .update(data)
        .eq('id', id)
        .select()
        .single();

      if (error) throw error;

      const { data: { user } } = await supabase.auth.getUser();
      if (user) {
        supabase.from('user_actions_log').insert([{
          usuario_id: user.id,
          tipo_acao: 'editar',
          tipo_entidade: 'ativo',
          entidade_id: id,
          descricao: `Editou imóvel ${id}`,
        }]).then();
      }

      return imovel as Imovel;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['imoveis'] });
      queryClient.invalidateQueries({ queryKey: ['imovel'] });
      queryClient.invalidateQueries({ queryKey: ['ativos'] });
      toast.success('Imóvel atualizado com sucesso!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao atualizar imóvel', { description: error.message });
    },
  });
}

export function useDeleteImovel() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string) => {
      const { error } = await supabase.from('ativos').delete().eq('id', id);
      if (error) throw error;

      const { data: { user } } = await supabase.auth.getUser();
      if (user) {
        supabase.from('user_actions_log').insert([{
          usuario_id: user.id,
          tipo_acao: 'excluir',
          tipo_entidade: 'ativo',
          entidade_id: id,
          descricao: `Excluiu imóvel ${id}`,
        }]).then();
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['imoveis'] });
      queryClient.invalidateQueries({ queryKey: ['ativos'] });
      toast.success('Imóvel excluído com sucesso!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao excluir imóvel', { description: error.message });
    },
  });
}

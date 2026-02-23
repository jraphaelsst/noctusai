import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { supabase } from '@/integrations/supabase/client';
import { toast } from 'sonner';
import { useAuthStore } from '@/store/authStore';
import { useIsAdmin } from './useUserRole';

// Ativo with natureza='permuta_imovel' or 'permuta_automovel'
export interface PerfilPermuta {
  id: string;
  owner_id: string;
  natureza: 'permuta_imovel' | 'permuta_automovel';
  valor: number;
  status: string;
  observacoes?: string | null;
  created_at: string;
  updated_at: string;
  // Property fields (permuta_imovel)
  tipo_imovel?: string | null;
  cep?: string | null;
  bairro?: string | null;
  cidade?: string | null;
  estado?: string | null;
  zona?: string | null;
  condominio_nome?: string | null;
  area_privativa?: number | null;
  area_total?: number | null;
  quartos?: number | null;
  vagas?: number | null;
  // Vehicle fields (permuta_automovel)
  tipo_veiculo?: string | null;
  marca?: string | null;
  modelo?: string | null;
  motor?: string | null;
  ano?: number | null;
  quilometragem?: number | null;
  // Flexibility / preference fields
  faixa_preco_min?: number | null;
  faixa_preco_max?: number | null;
  regiao_preferida?: string[] | null;
  aceita_completar_diferenca?: boolean;
  limite_complemento?: number | null;
  metragem_min?: number | null;
  metragem_max?: number | null;
  quartos_min?: number | null;
  vagas_min?: number | null;
  ano_min?: number | null;
  ano_max?: number | null;
  quilometragem_max?: number | null;
}

export type NovoPerfilPermutaForm = Omit<PerfilPermuta, 'id' | 'owner_id' | 'created_at' | 'updated_at'>;

export function usePerfilsPermuta() {
  const { user } = useAuthStore();
  const { isAdmin } = useIsAdmin();

  return useQuery({
    queryKey: ['permutas', user?.id],
    queryFn: async () => {
      if (!user) return [];

      let query = supabase
        .from('ativos')
        .select('*')
        .in('natureza', ['permuta_imovel', 'permuta_automovel'])
        .order('created_at', { ascending: false });

      if (!isAdmin) {
        query = query.eq('owner_id', user.id);
      }

      const { data, error } = await query;
      if (error) throw error;
      return data as PerfilPermuta[];
    },
    enabled: !!user,
  });
}

export function usePerfilPermuta(id?: string) {
  return useQuery({
    queryKey: ['permuta', id],
    queryFn: async () => {
      if (!id) return null;
      const { data, error } = await supabase
        .from('ativos')
        .select('*')
        .eq('id', id)
        .single();
      if (error) throw error;
      return data as PerfilPermuta;
    },
    enabled: !!id,
  });
}

export function useCreatePerfilPermuta() {
  const queryClient = useQueryClient();
  const { user } = useAuthStore();

  return useMutation({
    mutationFn: async (data: NovoPerfilPermutaForm) => {
      if (!user) throw new Error('Usuário não autenticado');

      const { data: perfil, error } = await supabase
        .from('ativos')
        .insert({
          ...data,
          owner_id: user.id,
          valor: data.valor || data.faixa_preco_min || 0,
        })
        .select()
        .single();

      if (error) throw error;

      supabase.from('user_actions_log').insert([{
        usuario_id: user.id,
        tipo_acao: 'criar',
        tipo_entidade: 'ativo',
        entidade_id: perfil.id,
        descricao: `Criou permuta ${perfil.natureza} ${perfil.id}`,
      }]).then();

      return perfil as PerfilPermuta;
    },
    onSuccess: (perfil) => {
      queryClient.invalidateQueries({ queryKey: ['permutas'] });
      queryClient.invalidateQueries({ queryKey: ['ativos'] });
      toast.success('Perfil de permuta criado com sucesso!');

      if (perfil?.id) {
        import('@/lib/matching-api').then(({ triggerMatching }) =>
          triggerMatching({ ativo_destino_id: perfil.id }).then((data) => {
            const total = data?.total || 0;
            if (total > 0) {
              toast.info(`${total} match${total !== 1 ? 'es' : ''} encontrado${total !== 1 ? 's' : ''} automaticamente!`);
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
      toast.error('Erro ao criar perfil de permuta', { description: error.message });
    },
  });
}

export function useUpdatePerfilPermuta() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, ...data }: Partial<PerfilPermuta> & { id: string }) => {
      const { data: perfil, error } = await supabase
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
          descricao: `Editou permuta ${id}`,
        }]).then();
      }

      return perfil as PerfilPermuta;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['permutas'] });
      queryClient.invalidateQueries({ queryKey: ['ativos'] });
      toast.success('Permuta atualizada com sucesso!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao atualizar permuta', { description: error.message });
    },
  });
}

export function useDeletePerfilPermuta() {
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
          descricao: `Excluiu permuta ${id}`,
        }]).then();
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['permutas'] });
      queryClient.invalidateQueries({ queryKey: ['ativos'] });
      toast.success('Permuta excluída com sucesso!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao excluir permuta', { description: error.message });
    },
  });
}

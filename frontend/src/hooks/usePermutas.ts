import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { supabase } from '@/integrations/supabase/client';
import { toast } from 'sonner';
import { PerfilPermuta, NovoPerfilPermutaForm } from '@/types/imoveis';
import { useAuthStore } from '@/store/authStore';
import { useIsAdmin } from './useUserRole';

export function usePerfilsPermuta() {
  const { user } = useAuthStore();
  const { isAdmin } = useIsAdmin();

  return useQuery({
    queryKey: ['perfis-permuta', user?.id],
    queryFn: async () => {
      if (!user) return [];

      let query = supabase
        .from('perfis_permutas')
        .select('*')
        .order('created_at', { ascending: false });

      if (!isAdmin) {
        query = query.eq('cliente_ofertante_id', user.id);
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
    queryKey: ['perfil-permuta', id],
    queryFn: async () => {
      if (!id) return null;

      const { data, error } = await supabase
        .from('perfis_permutas')
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
        .from('perfis_permutas')
        .insert({
          ...data,
          cliente_ofertante_id: user.id,
          regiao_preferida: data.regiao_preferida || [],
        })
        .select()
        .single();

      if (error) throw error;

      // Registrar ação
      supabase.from('user_actions_log').insert([{
        usuario_id: user.id,
        tipo_acao: 'criar',
        tipo_entidade: 'perfil_permuta',
        entidade_id: perfil.id,
        descricao: `Criou perfil de permuta ${perfil.id}`,
      }]).then();

      return perfil as PerfilPermuta;
    },
    onSuccess: (perfil) => {
      queryClient.invalidateQueries({ queryKey: ['perfis-permuta'] });
      toast.success('Perfil de permuta criado com sucesso!');

      // Fire-and-forget: trigger server-side matching for the new perfil
      if (perfil?.id) {
        import('@/lib/matching-api').then(({ triggerMatching }) =>
          triggerMatching({ perfil_permuta_id: perfil.id }).then((data) => {
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
      toast.error('Erro ao criar perfil de permuta', {
        description: error.message,
      });
    },
  });
}

export function useUpdatePerfilPermuta() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, ...data }: Partial<PerfilPermuta> & { id: string }) => {
      const { data: perfil, error } = await supabase
        .from('perfis_permutas')
        .update(data)
        .eq('id', id)
        .select()
        .single();

      if (error) throw error;

      // Registrar ação
      const { data: { user } } = await supabase.auth.getUser();
      if (user) {
        supabase.from('user_actions_log').insert([{
          usuario_id: user.id,
          tipo_acao: 'editar',
          tipo_entidade: 'perfil_permuta',
          entidade_id: id,
          descricao: `Editou perfil de permuta ${id}`,
        }]).then();
      }

      return perfil as PerfilPermuta;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['perfis-permuta'] });
      queryClient.invalidateQueries({ queryKey: ['perfil-permuta'] });
      toast.success('Perfil de permuta atualizado com sucesso!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao atualizar perfil de permuta', {
        description: error.message,
      });
    },
  });
}

export function useDeletePerfilPermuta() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string) => {
      const { error } = await supabase
        .from('perfis_permutas')
        .delete()
        .eq('id', id);

      if (error) throw error;

      // Registrar ação
      const { data: { user } } = await supabase.auth.getUser();
      if (user) {
        supabase.from('user_actions_log').insert([{
          usuario_id: user.id,
          tipo_acao: 'excluir',
          tipo_entidade: 'perfil_permuta',
          entidade_id: id,
          descricao: `Excluiu perfil de permuta ${id}`,
        }]).then();
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['perfis-permuta'] });
      toast.success('Perfil de permuta excluído com sucesso!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao excluir perfil de permuta', {
        description: error.message,
      });
    },
  });
}

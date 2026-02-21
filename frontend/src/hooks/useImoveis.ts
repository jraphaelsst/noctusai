import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { supabase } from '@/integrations/supabase/client';
import { toast } from 'sonner';
import { Imovel, NovoImovelForm } from '@/types/imoveis';
import { useAuthStore } from '@/store/authStore';
import { useIsAdmin } from './useUserRole';

export function useImoveis() {
  const { user } = useAuthStore();
  const { isAdmin } = useIsAdmin();

  return useQuery({
    queryKey: ['imoveis', user?.id],
    queryFn: async () => {
      if (!user) return [];

      let query = supabase
        .from('imoveis')
        .select('*')
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
        .from('imoveis')
        .select('*')
        .eq('id', id)
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
        .from('imoveis')
        .insert({
          ...data,
          owner_id: user.id,
          fotos: [],
          plantas: [],
          palavras_chave: data.palavras_chave || [],
          pontos_de_interesse: data.pontos_de_interesse || [],
        })
        .select()
        .single();

      if (error) throw error;

      // Registrar ação
      supabase.from('user_actions_log').insert([{
        usuario_id: user.id,
        tipo_acao: 'criar',
        tipo_entidade: 'imovel',
        entidade_id: imovel.id,
        descricao: `Criou imóvel ${imovel.id}`,
      }]).then();

      return imovel as Imovel;
    },
    onSuccess: (imovel) => {
      queryClient.invalidateQueries({ queryKey: ['imoveis'] });
      toast.success('Imóvel criado com sucesso!');

      // Fire-and-forget: trigger server-side matching if the imóvel accepts permutas
      if (imovel?.id && imovel.aceita_permutas) {
        import('@/lib/matching-api').then(({ triggerMatching }) =>
          triggerMatching({ imovel_id: imovel.id }).then((data) => {
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
      toast.error('Erro ao criar imóvel', {
        description: error.message,
      });
    },
  });
}

export function useUpdateImovel() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, ...data }: Partial<Imovel> & { id: string }) => {
      const { data: imovel, error } = await supabase
        .from('imoveis')
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
          tipo_entidade: 'imovel',
          entidade_id: id,
          descricao: `Editou imóvel ${id}`,
        }]).then();
      }

      return imovel as Imovel;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['imoveis'] });
      queryClient.invalidateQueries({ queryKey: ['imovel'] });
      toast.success('Imóvel atualizado com sucesso!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao atualizar imóvel', {
        description: error.message,
      });
    },
  });
}

export function useDeleteImovel() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string) => {
      const { error } = await supabase
        .from('imoveis')
        .delete()
        .eq('id', id);

      if (error) throw error;

      // Registrar ação
      const { data: { user } } = await supabase.auth.getUser();
      if (user) {
        supabase.from('user_actions_log').insert([{
          usuario_id: user.id,
          tipo_acao: 'excluir',
          tipo_entidade: 'imovel',
          entidade_id: id,
          descricao: `Excluiu imóvel ${id}`,
        }]).then();
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['imoveis'] });
      toast.success('Imóvel excluído com sucesso!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao excluir imóvel', {
        description: error.message,
      });
    },
  });
}

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { supabase } from '@/integrations/supabase/client';
import { toast } from 'sonner';
import { useAuthStore } from '@/store/authStore';
import { useIsAdmin } from './useUserRole';

export interface Condominio {
  id: string;
  owner_id: string;
  nome: string;
  endereco?: string | null;
  bairro?: string | null;
  cidade?: string | null;
  estado?: string | null;
  cep?: string | null;
  valor_condominio?: number | null;
  sindico?: string | null;
  telefone_sindico?: string | null;
  administradora?: string | null;
  torres?: number | null;
  unidades_por_andar?: number | null;
  total_unidades?: number | null;
  possui_portaria?: boolean;
  possui_piscina?: boolean;
  possui_academia?: boolean;
  possui_salao_festas?: boolean;
  possui_playground?: boolean;
  possui_churrasqueira?: boolean;
  observacoes?: string | null;
  created_at: string;
  updated_at: string;
}

export type NovoCondominioForm = Omit<Condominio, 'id' | 'owner_id' | 'created_at' | 'updated_at'>;

export function useCondominios() {
  const { user } = useAuthStore();
  const { isAdmin } = useIsAdmin();

  return useQuery({
    queryKey: ['condominios', user?.id],
    queryFn: async () => {
      if (!user) return [];
      let query = supabase
        .from('condominios')
        .select('*')
        .order('nome', { ascending: true });

      if (!isAdmin) {
        query = query.eq('owner_id', user.id);
      }

      const { data, error } = await query;
      if (error) throw error;
      return data as Condominio[];
    },
    enabled: !!user,
  });
}

export function useCondominio(id?: string) {
  return useQuery({
    queryKey: ['condominio', id],
    queryFn: async () => {
      if (!id) return null;
      const { data, error } = await supabase
        .from('condominios')
        .select('*')
        .eq('id', id)
        .single();
      if (error) throw error;
      return data as Condominio;
    },
    enabled: !!id,
  });
}

export function useCreateCondominio() {
  const queryClient = useQueryClient();
  const { user } = useAuthStore();

  return useMutation({
    mutationFn: async (data: NovoCondominioForm) => {
      if (!user) throw new Error('Usuário não autenticado');

      const { data: condominio, error } = await supabase
        .from('condominios')
        .insert({ ...data, owner_id: user.id })
        .select()
        .single();

      if (error) throw error;

      supabase.from('user_actions_log').insert([{
        usuario_id: user.id,
        tipo_acao: 'criar',
        tipo_entidade: 'condominio',
        entidade_id: condominio.id,
        descricao: `Criou condomínio ${condominio.nome}`,
      }]).then();

      return condominio as Condominio;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['condominios'] });
      toast.success('Condomínio criado com sucesso!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao criar condomínio', { description: error.message });
    },
  });
}

export function useUpdateCondominio() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, ...data }: Partial<Condominio> & { id: string }) => {
      const { data: condominio, error } = await supabase
        .from('condominios')
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
          tipo_entidade: 'condominio',
          entidade_id: id,
          descricao: `Editou condomínio ${id}`,
        }]).then();
      }

      return condominio as Condominio;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['condominios'] });
      queryClient.invalidateQueries({ queryKey: ['condominio'] });
      toast.success('Condomínio atualizado com sucesso!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao atualizar condomínio', { description: error.message });
    },
  });
}

export function useDeleteCondominio() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string) => {
      const { error } = await supabase.from('condominios').delete().eq('id', id);
      if (error) throw error;

      const { data: { user } } = await supabase.auth.getUser();
      if (user) {
        supabase.from('user_actions_log').insert([{
          usuario_id: user.id,
          tipo_acao: 'excluir',
          tipo_entidade: 'condominio',
          entidade_id: id,
          descricao: `Excluiu condomínio ${id}`,
        }]).then();
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['condominios'] });
      toast.success('Condomínio excluído com sucesso!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao excluir condomínio', { description: error.message });
    },
  });
}

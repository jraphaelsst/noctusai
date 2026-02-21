import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { supabase } from '@/integrations/supabase/client';
import { Profile } from '@/types';
import { toast } from 'sonner';

// Sanitize database errors to prevent leaking sensitive information
function sanitizeError(error: any): string {
  // Map known error patterns to user-friendly messages
  const errorMessage = error?.message?.toLowerCase() || '';
  
  if (errorMessage.includes('already registered') || errorMessage.includes('duplicate')) {
    return 'Este email já está cadastrado';
  }
  
  if (errorMessage.includes('invalid') || errorMessage.includes('violates')) {
    return 'Dados inválidos fornecidos';
  }
  
  if (errorMessage.includes('permission') || errorMessage.includes('policy')) {
    return 'Você não tem permissão para realizar esta ação';
  }
  
  if (errorMessage.includes('network') || errorMessage.includes('fetch')) {
    return 'Erro de conexão. Verifique sua internet';
  }
  
  // Generic fallback - don't expose database details
  return 'Ocorreu um erro. Tente novamente';
}

export function useProfiles() {
  return useQuery({
    queryKey: ['profiles'],
    queryFn: async () => {
      const { data, error } = await supabase
        .from('profiles')
        .select('*')
        .order('created_at', { ascending: false });

      if (error) throw error;
      return data as Profile[];
    },
  });
}

// Format name with first letter of each word capitalized
function formatNome(nome: string): string {
  return nome
    .toLowerCase()
    .split(' ')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

export function useCreateProfile() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (formData: { nome: string; email: string; telefone: string; password: string }) => {
      // Criar usuário na autenticação
      const { data: authData, error: authError } = await supabase.auth.signUp({
        email: formData.email,
        password: formData.password,
        options: {
          emailRedirectTo: `${window.location.origin}/`,
          data: {
            nome: formatNome(formData.nome),
            telefone: formData.telefone,
          },
        },
      });

      if (authError) throw authError;

      // Registrar ação
      const { data: { user } } = await supabase.auth.getUser();
      if (user && authData.user) {
        supabase.from("user_actions_log").insert({
          usuario_id: user.id,
          tipo_acao: 'criar',
          tipo_entidade: 'usuario',
          entidade_id: authData.user.id,
          descricao: `Criou usuário ${formData.nome}`,
          detalhes: { email: formData.email }
        }).then();
      }

      // O perfil será criado automaticamente pelo trigger
      return authData;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['profiles'] });
      toast.success('Corretor cadastrado com sucesso!', {
        description: 'Um email de confirmação foi enviado.',
      });
    },
    onError: (error: any) => {
      toast.error('Erro ao cadastrar corretor', {
        description: sanitizeError(error),
      });
    },
  });
}

export function useUpdateProfile() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, ...updates }: Partial<Profile> & { id: string }) => {
      // Buscar nome do usuário antes de atualizar
      const { data: profileAntes } = await supabase
        .from('profiles')
        .select('nome')
        .eq('id', id)
        .single();

      const { data, error } = await supabase
        .from('profiles')
        .update(updates)
        .eq('id', id)
        .select()
        .single();

      if (error) throw error;

      // Registrar ação
      const { data: { user } } = await supabase.auth.getUser();
      if (user) {
        supabase.from("user_actions_log").insert({
          usuario_id: user.id,
          tipo_acao: 'editar',
          tipo_entidade: 'usuario',
          entidade_id: id,
          descricao: `Editou usuário ${profileAntes?.nome || data.nome}`,
          detalhes: updates
        }).then();
      }

      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['profiles'] });
      toast.success('Perfil atualizado com sucesso!');
    },
    onError: (error: any) => {
      toast.error('Erro ao atualizar perfil', {
        description: sanitizeError(error),
      });
    },
  });
}

export function useDeleteProfile() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string) => {
      // Buscar nome antes de excluir
      const { data: profile } = await supabase
        .from('profiles')
        .select('nome')
        .eq('id', id)
        .single();

      // Primeiro deletar o profile (cascade irá deletar user_roles)
      const { error: profileError } = await supabase
        .from('profiles')
        .delete()
        .eq('id', id);

      if (profileError) throw profileError;

      // Depois deletar o usuário do auth
      const { error: authError } = await supabase.auth.admin.deleteUser(id);
      
      if (authError) {
        console.error('Erro ao deletar usuário do auth:', authError);
        // Não lançar erro aqui pois o profile já foi deletado
      }

      // Registrar ação
      const { data: { user } } = await supabase.auth.getUser();
      if (user && profile) {
        supabase.from("user_actions_log").insert({
          usuario_id: user.id,
          tipo_acao: 'excluir',
          tipo_entidade: 'usuario',
          entidade_id: id,
          descricao: `Excluiu usuário ${profile.nome}`,
        }).then();
      }

      return { id };
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['profiles'] });
      toast.success('Usuário excluído com sucesso!');
    },
    onError: (error: any) => {
      toast.error('Erro ao excluir usuário', {
        description: sanitizeError(error),
      });
    },
  });
}

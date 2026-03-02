import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { api } from '@/lib/api-client';
import { Profile } from '@/types';

function getErrorMessage(error: any): string {
  return error?.message || 'Ocorreu um erro. Tente novamente';
}

export function useProfiles() {
  return useQuery({
    queryKey: ['profiles'],
    queryFn: async () => {
      const result = await api.get('/api/profiles');
      return (result.data || []) as Profile[];
    },
  });
}

export function useCreateProfile() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (formData: { nome: string; email: string; telefone: string; password: string }) => {
      // User creation now happens SECURELY on the backend (service role)
      return api.post('/api/profiles', formData);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['profiles'] });
      toast.success('Corretor cadastrado com sucesso!', {
        description: 'Usuário criado no servidor.',
      });
    },
    onError: (error: any) => {
      toast.error('Erro ao cadastrar corretor', { description: getErrorMessage(error) });
    },
  });
}

export function useUpdateProfile() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, ...updates }: Partial<Profile> & { id: string }) => {
      const result = await api.patch(`/api/profiles/${id}`, updates);
      return result.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['profiles'] });
      toast.success('Perfil atualizado com sucesso!');
    },
    onError: (error: any) => {
      toast.error('Erro ao atualizar perfil', { description: getErrorMessage(error) });
    },
  });
}

export function useDeleteProfile() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string) => {
      // admin.deleteUser now runs SECURELY on the backend
      await api.delete(`/api/profiles/${id}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['profiles'] });
      toast.success('Usuário excluído com sucesso!');
    },
    onError: (error: any) => {
      toast.error('Erro ao excluir usuário', { description: getErrorMessage(error) });
    },
  });
}

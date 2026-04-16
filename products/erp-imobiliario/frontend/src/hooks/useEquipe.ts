import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api-client';
import { useAuthStore } from '@/store/authStore';
import { toast } from 'sonner';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface TeamMember {
  id: string;
  nome: string;
  email: string;
  telefone?: string;
  avatar?: string;
  roles: string[];
  created_at: string;
}

export interface Invitation {
  id: string;
  email: string;
  role: string;
  expires_at: string;
  created_at: string;
  status: string;
}

// ---------------------------------------------------------------------------
// Hooks
// ---------------------------------------------------------------------------

export function useTeamMembers(enabled: boolean) {
  const { user } = useAuthStore();

  return useQuery<TeamMember[]>({
    queryKey: ['team-members'],
    queryFn: async () => {
      const res = await api.get('/api/team');
      return res.data ?? res;
    },
    enabled: !!user && enabled,
  });
}

export function useTeamInvitations(enabled: boolean) {
  const { user } = useAuthStore();

  return useQuery<Invitation[]>({
    queryKey: ['team-invitations'],
    queryFn: async () => {
      const res = await api.get('/api/team/invitations');
      return res.data ?? res;
    },
    enabled: !!user && enabled,
  });
}

export function useSendInvite(onSuccess?: () => void) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: { email: string; role: string }) => {
      return api.post('/api/team/invite', data);
    },
    onSuccess: () => {
      toast.success('Convite enviado com sucesso!');
      queryClient.invalidateQueries({ queryKey: ['team-invitations'] });
      onSuccess?.();
    },
    onError: (err: Error) => {
      toast.error('Erro ao enviar convite', { description: err.message });
    },
  });
}

export function useCancelInvite() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string) => {
      return api.delete(`/api/team/invitations/${id}`);
    },
    onSuccess: () => {
      toast.success('Convite cancelado.');
      queryClient.invalidateQueries({ queryKey: ['team-invitations'] });
    },
    onError: (err: Error) => {
      toast.error('Erro ao cancelar convite', { description: err.message });
    },
  });
}

export function useRemoveMember() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string) => {
      return api.delete(`/api/team/members/${id}`);
    },
    onSuccess: () => {
      toast.success('Membro removido da equipe.');
      queryClient.invalidateQueries({ queryKey: ['team-members'] });
    },
    onError: (err: Error) => {
      toast.error('Erro ao remover membro', { description: err.message });
    },
  });
}

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api, useAuthStore } from '@noctusai/seed/infra';
import { toast } from 'sonner';

const KEYS = {
  dashboard: ['admin', 'dashboard'] as const,
  therapists: (filters?: Record<string, string>) => ['admin', 'therapists', filters] as const,
  therapist: (id: string) => ['admin', 'therapists', id] as const,
  clinics: (filters?: Record<string, string>) => ['admin', 'clinics', filters] as const,
  clinic: (id: string) => ['admin', 'clinics', id] as const,
  patients: (filters?: Record<string, string>) => ['admin', 'patients', filters] as const,
  patient: (id: string) => ['admin', 'patients', id] as const,
  appointments: (filters?: Record<string, string>) => ['admin', 'appointments', filters] as const,
  pending: ['admin', 'pending'] as const,
  reports: ['admin', 'reports'] as const,
  blocks: ['admin', 'blocks'] as const,
  reviews: ['admin', 'reviews'] as const,
  supportConversations: ['admin', 'support'] as const,
};

export function useAdminDashboard() {
  const { user } = useAuthStore();
  return useQuery({
    queryKey: KEYS.dashboard,
    queryFn: async () => {
      const res = await api.get('/api/admin/dashboard');
      return res.data ?? res;
    },
    enabled: !!user,
    staleTime: 60 * 1000,
  });
}

export function useAdminTherapists(filters?: Record<string, string>) {
  const { user } = useAuthStore();
  return useQuery<{ data: unknown[]; total: number }>({
    queryKey: KEYS.therapists(filters),
    queryFn: async () => {
      const params = new URLSearchParams(filters);
      const qs = params.toString();
      return api.get(`/api/admin/therapists${qs ? `?${qs}` : ''}`);
    },
    enabled: !!user,
    staleTime: 30 * 1000,
  });
}

export function useAdminTherapist(id?: string) {
  const { user } = useAuthStore();
  return useQuery({
    queryKey: KEYS.therapist(id!),
    queryFn: async () => {
      const res = await api.get(`/api/admin/therapists/${id}`);
      return res.data ?? res;
    },
    enabled: !!user && !!id,
    staleTime: 30 * 1000,
  });
}

export function useAdminClinics(filters?: Record<string, string>) {
  const { user } = useAuthStore();
  return useQuery<{ data: unknown[]; total: number }>({
    queryKey: KEYS.clinics(filters),
    queryFn: async () => {
      const params = new URLSearchParams(filters);
      const qs = params.toString();
      return api.get(`/api/admin/clinics${qs ? `?${qs}` : ''}`);
    },
    enabled: !!user,
    staleTime: 30 * 1000,
  });
}

export function useAdminClinic(id?: string) {
  const { user } = useAuthStore();
  return useQuery({
    queryKey: KEYS.clinic(id!),
    queryFn: async () => {
      const res = await api.get(`/api/admin/clinics/${id}`);
      return res.data ?? res;
    },
    enabled: !!user && !!id,
    staleTime: 30 * 1000,
  });
}

export function useAdminPatients(filters?: Record<string, string>) {
  const { user } = useAuthStore();
  return useQuery<{ data: unknown[]; total: number }>({
    queryKey: KEYS.patients(filters),
    queryFn: async () => {
      const params = new URLSearchParams(filters);
      const qs = params.toString();
      return api.get(`/api/admin/patients${qs ? `?${qs}` : ''}`);
    },
    enabled: !!user,
    staleTime: 30 * 1000,
  });
}

export function useAdminPatient(id?: string) {
  const { user } = useAuthStore();
  return useQuery({
    queryKey: KEYS.patient(id!),
    queryFn: async () => {
      const res = await api.get(`/api/admin/patients/${id}`);
      return res.data ?? res;
    },
    enabled: !!user && !!id,
    staleTime: 30 * 1000,
  });
}

export function useAdminAppointments(filters?: Record<string, string>) {
  const { user } = useAuthStore();
  return useQuery<{ data: unknown[]; total: number }>({
    queryKey: KEYS.appointments(filters),
    queryFn: async () => {
      const params = new URLSearchParams(filters);
      const qs = params.toString();
      return api.get(`/api/admin/appointments${qs ? `?${qs}` : ''}`);
    },
    enabled: !!user,
    staleTime: 30 * 1000,
  });
}

export function usePendingApprovals() {
  const { user } = useAuthStore();
  return useQuery({
    queryKey: KEYS.pending,
    queryFn: async () => {
      const res = await api.get('/api/admin/pending');
      return res.data ?? res;
    },
    enabled: !!user,
    staleTime: 30 * 1000,
  });
}

export function useApproveEntity() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ type, id }: { type: string; id: string }) => {
      return api.post(`/api/admin/approve/${type}/${id}`, {});
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin'] });
      toast.success('Aprovado com sucesso');
    },
    onError: () => {
      toast.error('Erro ao aprovar');
    },
  });
}

export function useRejectEntity() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ type, id, reason }: { type: string; id: string; reason: string }) => {
      return api.post(`/api/admin/reject/${type}/${id}`, { reason });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin'] });
      toast.success('Rejeitado com sucesso');
    },
    onError: () => {
      toast.error('Erro ao rejeitar');
    },
  });
}

export function useSuspendEntity() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ type, id }: { type: string; id: string }) => {
      return api.post(`/api/admin/suspend/${type}/${id}`, {});
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin'] });
      toast.success('Suspenso com sucesso');
    },
    onError: () => {
      toast.error('Erro ao suspender');
    },
  });
}

export function useAdminReports() {
  const { user } = useAuthStore();
  return useQuery<{ data: unknown[]; total: number }>({
    queryKey: KEYS.reports,
    queryFn: async () => api.get('/api/admin/reports'),
    enabled: !!user,
    staleTime: 30 * 1000,
  });
}

export function useResolveReport() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, resolution }: { id: string; resolution: string }) => {
      return api.post(`/api/admin/reports/${id}/resolve`, { resolution });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: KEYS.reports });
      toast.success('Denuncia resolvida');
    },
    onError: () => {
      toast.error('Erro ao resolver denuncia');
    },
  });
}

export function useAdminBlocks() {
  const { user } = useAuthStore();
  return useQuery<{ data: unknown[]; total: number }>({
    queryKey: KEYS.blocks,
    queryFn: async () => api.get('/api/admin/blocks'),
    enabled: !!user,
    staleTime: 60 * 1000,
  });
}

export function useAdminReviews() {
  const { user } = useAuthStore();
  return useQuery<{ data: unknown[]; total: number }>({
    queryKey: KEYS.reviews,
    queryFn: async () => api.get('/api/admin/reviews/flagged'),
    enabled: !!user,
    staleTime: 30 * 1000,
  });
}

export function useDismissReviewFlag() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      return api.post(`/api/admin/reviews/${id}/dismiss`, {});
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: KEYS.reviews });
      toast.success('Flag removida');
    },
    onError: () => {
      toast.error('Erro ao remover flag');
    },
  });
}

export function useHideReview() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      return api.post(`/api/admin/reviews/${id}/hide`, {});
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: KEYS.reviews });
      toast.success('Avaliacao ocultada');
    },
    onError: () => {
      toast.error('Erro ao ocultar avaliacao');
    },
  });
}

export function useAdminSupportConversations() {
  const { user } = useAuthStore();
  return useQuery<{ data: unknown[]; total: number }>({
    queryKey: KEYS.supportConversations,
    queryFn: async () => api.get('/api/admin/support/conversations'),
    enabled: !!user,
    staleTime: 15 * 1000,
  });
}

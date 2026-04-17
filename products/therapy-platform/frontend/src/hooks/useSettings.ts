import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api, useAuthStore } from '@noctusai/seed/infra';
import { toast } from 'sonner';

const KEYS = {
  platform: ['settings', 'platform'] as const,
  aiPrompts: ['settings', 'ai-prompts'] as const,
  aiPromptHistory: (type: string) => ['settings', 'ai-prompts', type, 'history'] as const,
  therapist: ['settings', 'therapist'] as const,
  clinicBranding: ['settings', 'clinic', 'branding'] as const,
  patient: ['settings', 'patient'] as const,
};

// ── Platform Settings ──────────────────────────────────────

export function usePlatformSettings() {
  const { user } = useAuthStore();
  return useQuery({
    queryKey: KEYS.platform,
    queryFn: async () => {
      const res = await api.get('/api/settings/platform');
      return res.data ?? res;
    },
    enabled: !!user,
    staleTime: 5 * 60 * 1000,
  });
}

export function useUpdatePlatformSetting() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ key, value }: { key: string; value: unknown }) => {
      return api.patch('/api/settings/platform', { key, value });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: KEYS.platform });
      toast.success('Configuracao atualizada');
    },
    onError: () => {
      toast.error('Erro ao atualizar configuracao');
    },
  });
}

// ── AI Prompts ─────────────────────────────────────────────

export function useAIPrompts() {
  const { user } = useAuthStore();
  return useQuery({
    queryKey: KEYS.aiPrompts,
    queryFn: async () => {
      const res = await api.get('/api/settings/platform/ai-prompts');
      return res.data ?? res;
    },
    enabled: !!user,
    staleTime: 5 * 60 * 1000,
  });
}

export function useUpdateAIPrompt() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ type, prompt }: { type: string; prompt: string }) => {
      return api.patch('/api/settings/platform/ai-prompts', { type, prompt });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: KEYS.aiPrompts });
      toast.success('Prompt atualizado');
    },
    onError: () => {
      toast.error('Erro ao atualizar prompt');
    },
  });
}

export function useAIPromptHistory(type: string) {
  const { user } = useAuthStore();
  return useQuery({
    queryKey: KEYS.aiPromptHistory(type),
    queryFn: async () => {
      const res = await api.get(`/api/settings/platform/ai-prompts/${type}/history`);
      return res.data ?? res;
    },
    enabled: !!user && !!type,
    staleTime: 5 * 60 * 1000,
  });
}

// ── Therapist Settings ─────────────────────────────────────

export function useTherapistSettings() {
  const { user } = useAuthStore();
  return useQuery({
    queryKey: KEYS.therapist,
    queryFn: async () => {
      const res = await api.get('/api/settings/therapist');
      return res.data ?? res;
    },
    enabled: !!user,
    staleTime: 5 * 60 * 1000,
  });
}

export function useUpdateTherapistSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (data: Record<string, unknown>) => {
      return api.patch('/api/settings/therapist', data);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: KEYS.therapist });
      toast.success('Configuracoes atualizadas');
    },
    onError: () => {
      toast.error('Erro ao atualizar configuracoes');
    },
  });
}

// ── Clinic Branding ────────────────────────────────────────

export function useClinicBranding() {
  const { user } = useAuthStore();
  return useQuery({
    queryKey: KEYS.clinicBranding,
    queryFn: async () => {
      const res = await api.get('/api/settings/clinic/branding');
      return res.data ?? res;
    },
    enabled: !!user,
    staleTime: 5 * 60 * 1000,
  });
}

export function useUpdateClinicBranding() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (data: Record<string, unknown>) => {
      return api.patch('/api/settings/clinic/branding', data);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: KEYS.clinicBranding });
      toast.success('Branding atualizado');
    },
    onError: () => {
      toast.error('Erro ao atualizar branding');
    },
  });
}

// ── Patient Settings ───────────────────────────────────────

export function usePatientSettings() {
  const { user } = useAuthStore();
  return useQuery({
    queryKey: KEYS.patient,
    queryFn: async () => {
      const res = await api.get('/api/settings/patient');
      return res.data ?? res;
    },
    enabled: !!user,
    staleTime: 5 * 60 * 1000,
  });
}

export function useUpdatePatientSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (data: Record<string, unknown>) => {
      return api.patch('/api/settings/patient', data);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: KEYS.patient });
      toast.success('Configuracoes atualizadas');
    },
    onError: () => {
      toast.error('Erro ao atualizar configuracoes');
    },
  });
}

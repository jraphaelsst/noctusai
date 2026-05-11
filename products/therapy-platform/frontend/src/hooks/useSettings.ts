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

/**
 * Clinic branding DTO — mirrors `app/schemas/settings.py::ClinicBrandingUpdate`
 * plus the read-side `clinic_id` field returned by `branding_service.get_clinic_branding`.
 *
 * NOTE (Phase 8.d): the response includes `clinic_id` only on the persisted-row
 * branch; the defaults-branch returns `{...DEFAULT_BRANDING, clinic_id}`. Both
 * branches set `clinic_id`. See `app/services/branding_service.py`.
 */
export interface ClinicBranding {
  clinic_id?: string;
  primary_color?: string | null;
  secondary_color?: string | null;
  logo_url?: string | null;
  favicon_url?: string | null;
}

/**
 * Update payload — strict subset of read-side fields (no `clinic_id` write).
 * Mirrors `ClinicBrandingUpdate` Pydantic schema.
 *
 * NOTE (Phase 8.b/d): the mutation `mutationFn` signature stays `Record<string, unknown>`
 * because today `pages/clinic/Settings.tsx` calls `updateBranding.mutate()` with
 * Profile/Bank/Commission payloads that aren't branding fields — those are
 * silently dropped by the backend Pydantic `ClinicBrandingUpdate` schema (
 * unknown-field exclusion is Pydantic default). Tightening to `ClinicBrandingUpdate`
 * here surfaces 3 TS errors in Settings.tsx that reflect REAL clinic-portal
 * misrouting bugs (Profile → `/api/clinics/:id` PATCH; Bank/Commission →
 * `/api/clinics/settings` PATCH). Filed as the `therapy-clinic-settings-misrouting`
 * follow-up; the read-side typing is the safer-to-tighten win.
 */
export interface ClinicBrandingUpdate {
  primary_color?: string;
  secondary_color?: string;
  logo_url?: string;
  favicon_url?: string;
}

export function useClinicBranding() {
  const { user } = useAuthStore();
  return useQuery<ClinicBranding>({
    queryKey: KEYS.clinicBranding,
    queryFn: async () => {
      const res = await api.get('/api/settings/clinic/branding');
      return (res.data ?? res) as ClinicBranding;
    },
    enabled: !!user,
    staleTime: 5 * 60 * 1000,
  });
}

export function useUpdateClinicBranding() {
  const qc = useQueryClient();
  return useMutation({
    // Intentionally NOT `ClinicBrandingUpdate` — see ClinicBrandingUpdate
    // JSDoc above. Follow-up: `therapy-clinic-settings-misrouting`.
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

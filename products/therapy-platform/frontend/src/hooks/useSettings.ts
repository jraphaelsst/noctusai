import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api, useAuthStore } from '@noctusai/seed/infra';
import { toast } from 'sonner';

const KEYS = {
  platform: ['settings', 'platform'] as const,
  aiPrompts: ['settings', 'ai-prompts'] as const,
  aiPromptHistory: (type: string) => ['settings', 'ai-prompts', type, 'history'] as const,
  therapist: ['settings', 'therapist'] as const,
  clinicBranding: ['settings', 'clinic', 'branding'] as const,
  clinicProfile: (clinicId: string) => ['clinics', clinicId] as const,
  clinicAdminSettings: ['clinics', 'settings'] as const,
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
 * NOTE (`therapy-clinic-settings-misrouting`, 2026-05-11): the misrouting bug
 * filed in Phase 8.b/d is now FIXED. Settings.tsx Profile section uses
 * `useUpdateClinicProfile` (→ `PATCH /api/clinics/{id}`); Bank + Commission
 * use `useUpdateClinicAdminSettings` (→ `PATCH /api/clinics/settings`); only
 * Branding stays on `useUpdateClinicBranding`. The mutation `mutationFn`
 * signature for `useUpdateClinicBranding` stays `Record<string, unknown>`
 * because the consumer (Branding section) currently passes
 * `{primary_color, secondary_color}` directly; tightening to
 * `ClinicBrandingUpdate` is a follow-up typing win, not a correctness fix.
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

// ── Clinic Profile (PATCH /api/clinics/{clinic_id}) ────────
//
// Filed under `therapy-clinic-settings-misrouting` (2026-05-11). Profile
// fields (name/cnpj/phone/contact_email) live on the `clinics` table and
// must hit the `ClinicUpdate` Pydantic schema route — NOT the branding route.

/**
 * Clinic profile DTO — mirrors `app/schemas/clinic.py::ClinicResponse`.
 */
export interface ClinicProfile {
  id: string;
  name: string;
  cnpj?: string | null;
  responsible_person?: string | null;
  contact_email?: string | null;
  phone?: string | null;
  logo_url?: string | null;
  description?: string | null;
  tagline?: string | null;
  specialties_offered?: string[];
  is_approved?: boolean;
  created_at?: string | null;
  is_active?: boolean;
}

/**
 * Clinic profile update payload — mirrors `ClinicUpdate` Pydantic schema.
 */
export interface ClinicProfileUpdate {
  name?: string;
  cnpj?: string;
  responsible_person?: string;
  contact_email?: string;
  phone?: string;
  logo_url?: string;
  description?: string;
  tagline?: string;
  specialties_offered?: string[];
}

export function useClinicProfile(clinicId: string | undefined) {
  const { user } = useAuthStore();
  return useQuery<ClinicProfile>({
    queryKey: KEYS.clinicProfile(clinicId ?? ''),
    queryFn: async () => {
      const res = await api.get(`/api/clinics/${clinicId}`);
      return (res.data ?? res) as ClinicProfile;
    },
    enabled: !!user && !!clinicId,
    staleTime: 5 * 60 * 1000,
  });
}

export function useUpdateClinicProfile(clinicId: string | undefined) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (data: ClinicProfileUpdate) => {
      if (!clinicId) {
        throw new Error('clinic_id is required to update clinic profile');
      }
      return api.patch(`/api/clinics/${clinicId}`, data);
    },
    onSuccess: () => {
      if (clinicId) {
        qc.invalidateQueries({ queryKey: KEYS.clinicProfile(clinicId) });
      }
      toast.success('Perfil atualizado');
    },
    onError: () => {
      toast.error('Erro ao atualizar perfil');
    },
  });
}

// ── Clinic Admin Settings (PATCH /api/clinics/settings) ────
//
// Filed under `therapy-clinic-settings-misrouting` (2026-05-11). Bank +
// commission fields live on the `clinic_settings` table and must hit the
// `ClinicSettingsUpdate` Pydantic schema route.

/**
 * Clinic admin settings DTO — mirrors `app/schemas/clinic.py::ClinicSettingsUpdate`
 * plus the read-side `clinic_id` field.
 */
export interface ClinicAdminSettings {
  clinic_id?: string;
  bank_name?: string | null;
  bank_agency?: string | null;
  bank_account?: string | null;
  pix_key?: string | null;
  notification_email_to?: string | null;
  default_commission_pct_clinic_sourced?: number | null;
  default_commission_pct_therapist_sourced?: number | null;
}

/**
 * Clinic admin settings update payload — mirrors `ClinicSettingsUpdate` schema.
 */
export interface ClinicAdminSettingsUpdate {
  bank_name?: string;
  bank_agency?: string;
  bank_account?: string;
  pix_key?: string;
  notification_email_to?: string;
  default_commission_pct_clinic_sourced?: number;
  default_commission_pct_therapist_sourced?: number;
}

export function useClinicAdminSettings() {
  const { user } = useAuthStore();
  return useQuery<ClinicAdminSettings>({
    queryKey: KEYS.clinicAdminSettings,
    queryFn: async () => {
      const res = await api.get('/api/clinics/settings');
      return (res.data ?? res) as ClinicAdminSettings;
    },
    enabled: !!user,
    staleTime: 5 * 60 * 1000,
  });
}

export function useUpdateClinicAdminSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (data: ClinicAdminSettingsUpdate) => {
      return api.patch('/api/clinics/settings', data);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: KEYS.clinicAdminSettings });
      toast.success('Configuracoes atualizadas');
    },
    onError: () => {
      toast.error('Erro ao atualizar configuracoes');
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

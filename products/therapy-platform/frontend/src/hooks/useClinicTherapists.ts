/**
 * useClinicTherapists — clinic-admin-scoped therapist list.
 *
 * Pattern-D extraction (Phase 8.a of therapy-platform-wiring):
 *   - was: `pages/clinic/Therapists.tsx` direct `useQuery` over `/api/clinic/therapists`
 *     (no backend route — 404).
 *   - now: calls the canonical `/api/clinics/{clinic_id}/therapists` endpoint
 *     (see `app/routers/clinics.py::list_clinic_therapists` — public route returning
 *     all therapists affiliated with the clinic). clinic_id is derived client-side
 *     from `user.user_metadata.clinic_id` (Supabase JWT shape; mirrors backend
 *     `get_clinic_id_for_user(user)` in `app/dependencies.py`).
 *
 * DTO gap (documented in §5.4.3 follow-up — same shape as Phase 6.a + 8.a patients):
 *   The backend currently returns raw `therapist_profiles` rows; the frontend
 *   `ClinicTherapist` interface expects enriched fields (`commission_pct`,
 *   `session_count`, `status`, `nota_media`) that aren't directly on
 *   `therapist_profiles`. `commission_pct` lives on `clinic_therapist_configs`;
 *   `session_count` + `nota_media` need aggregate queries. Filed in PROJECT.md
 *   Phase 8 Improvements as part of the broader `therapy-patient-dto-enrichment`
 *   follow-up. Page handles missing fields gracefully via `?? 0` / conditional
 *   render; hook signature is stable.
 *
 * Mirrors Phase 6.a `useTherapistPatients` shape — identical wiring, role-gating
 * happens server-side via RLS on `therapist_profiles`.
 */
import { useQuery } from '@tanstack/react-query';
import { api, useAuthStore } from '@noctusai/seed/infra';

// ─── Types ─────────────────────────────────────────────────────────────
export interface ClinicTherapist {
  id: string;
  nome: string;
  crp: string;
  commission_pct?: number;
  session_count?: number;
  status: 'ativo' | 'inativo';
  nota_media?: number;
}

interface ClinicTherapistsResponse {
  data: ClinicTherapist[];
}

// ─── Hook ──────────────────────────────────────────────────────────────
export function useClinicTherapists() {
  const { user } = useAuthStore();
  const clinicId = (user?.user_metadata as { clinic_id?: string } | undefined)?.clinic_id;

  return useQuery<ClinicTherapistsResponse>({
    queryKey: ['clinic', 'therapists', clinicId ?? ''],
    queryFn: async () => {
      if (!clinicId) {
        // No clinic_id in JWT — return empty shape. The page renders the
        // empty-state CTA; no 4xx surfaces. Mirrors the defensive fallback
        // pattern used by Phase 6 hooks when JWT metadata is incomplete.
        return { data: [] };
      }
      return api.get(`/api/clinics/${clinicId}/therapists`);
    },
    enabled: !!user,
    staleTime: 60 * 1000,
  });
}

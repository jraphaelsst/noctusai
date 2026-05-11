/**
 * useClinicPatients — clinic-admin-scoped patient list.
 *
 * Pattern-D extraction (Phase 8.a of therapy-platform-wiring):
 *   - was: `pages/clinic/Patients.tsx` direct `useQuery` over `/api/clinic/patients`
 *     (no backend route — 404).
 *   - now: calls the canonical `/api/patients` endpoint which is role-filtered
 *     server-side (see `app/routers/patients.py::list_patients` — clinic_admin role
 *     scopes via `clinic_id == get_clinic_id_for_user(user)`).
 *
 * DTO gap (documented in §5.4.3 follow-up — same shape as Phase 6.a):
 *   The backend currently returns raw `patient_profiles` rows; the frontend
 *   `ClinicPatient` interface expects enriched fields (`nome`, `email`,
 *   `terapeuta_nome`, `session_count`, `origin`) that are NOT in `patient_profiles`
 *   today. Filed in PROJECT.md Phase 8 Improvements as part of the broader
 *   `therapy-patient-dto-enrichment` follow-up (covers admin + therapist + clinic
 *   surfaces — N=3 enrichment recurrence). The page handles missing fields
 *   gracefully (`?? 0`, conditional render); the hook signature is stable and
 *   survives the future enrichment.
 *
 * Mirrors Phase 6.a `useTherapistPatients` shape — identical wiring, role-gating
 * happens server-side via the JWT.
 */
import { useQuery } from '@tanstack/react-query';
import { api, useAuthStore } from '@noctusai/seed/infra';

// ─── Types ─────────────────────────────────────────────────────────────
// Mirror frontend display contract; enrichment fields are optional until
// the backend DTO mapper lands. See PROJECT.md §6 Phase 8 Improvements.
export interface ClinicPatient {
  id: string;
  nome: string;
  email?: string;
  terapeuta_nome?: string;
  session_count?: number;
  origin?: string;
}

interface ClinicPatientsResponse {
  data: ClinicPatient[];
  pagination?: { page: number; page_size: number; total: number; total_pages: number };
}

// ─── Hook ──────────────────────────────────────────────────────────────
export function useClinicPatients(busca?: string) {
  const { user } = useAuthStore();

  return useQuery<ClinicPatientsResponse>({
    queryKey: ['clinic', 'patients', { busca: busca ?? '' }],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (busca && busca.trim()) params.set('busca', busca.trim());
      const qs = params.toString();
      return api.get(`/api/patients${qs ? `?${qs}` : ''}`);
    },
    enabled: !!user,
    staleTime: 60 * 1000,
  });
}

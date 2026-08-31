/**
 * useTherapistPatients — therapist-scoped patient list.
 *
 * Pattern-D extraction (Phase 6.a of therapy-platform-wiring):
 *   - was: `pages/therapist/Patients.tsx` direct `useQuery` over `/api/therapist/patients`
 *     (no backend route — 404).
 *   - now: calls the canonical `/api/patients` endpoint which is role-filtered
 *     server-side (see `app/routers/patients.py::list_patients` — therapist role
 *     scopes via `current_therapist_id == user.id`).
 *
 * DTO gap (documented in §5.4.3 follow-up): the backend currently returns raw
 * `patient_profiles` rows; the frontend `TherapistPatient` interface expects
 * enriched fields (`nome`, `email`, `origin`, `session_count`, `next_appointment`,
 * `last_session`) that are NOT in `patient_profiles` today. Filed in PROJECT.md
 * Phase 6 Improvements as `therapist-patient-dto-enrichment` follow-up — same
 * shape as Phase 1/2 admin enrichment (Phase 1 identity resolver + Phase 2
 * `_resolve_session_counts` helpers). The page handles missing fields gracefully
 * (`?? 0`, conditional render); the hook signature is stable and survives the
 * future enrichment.
 *
 * Shape mirrors the seed hook pattern at `products/seed/frontend/src/hooks/useExample.ts`
 * (AbortController + alive flag + typed return), adapted to React Query (which is
 * the established pattern across `products/therapy-platform/frontend/src/hooks/`).
 */
import { useQuery } from '@tanstack/react-query';
import { api, useAuthStore } from '@noctusai/seed/infra';

// ─── Types ─────────────────────────────────────────────────────────────
// Mirror frontend display contract; enrichment fields are optional until
// the backend DTO mapper lands. See PROJECT.md §6 Improvements.
export interface TherapistPatient {
  id: string;
  nome: string;
  email?: string;
  origin?: string;
  session_count?: number;
  next_appointment?: string;
  last_session?: string;
}

interface TherapistPatientsResponse {
  data: TherapistPatient[];
  pagination?: { page: number; page_size: number; total: number; total_pages: number };
}

// ─── Hook ──────────────────────────────────────────────────────────────
export function useTherapistPatients(busca?: string) {
  const { user } = useAuthStore();

  return useQuery<TherapistPatientsResponse>({
    queryKey: ['therapist', 'patients', { busca: busca ?? '' }],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (busca && busca.trim()) params.set('busca', busca.trim());
      const qs = params.toString();
      return api.get(`/api/patients${qs ? `?${qs}` : ''}`);
    },
    placeholderData: (prev) => prev,
    enabled: !!user,
    staleTime: 2 * 60 * 1000,
  });
}

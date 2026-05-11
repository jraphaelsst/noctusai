/**
 * useTherapistReviews — reviews for the logged-in therapist.
 *
 * Pattern-D extraction (Phase 6.a of therapy-platform-wiring):
 *   - was: `pages/therapist/Reviews.tsx` direct `useQuery` over `/api/therapist/reviews`
 *     (no backend route — 404).
 *   - now: calls the canonical `/api/reviews/therapist/:therapist_id` endpoint
 *     (see `app/routers/reviews.py::list_therapist_reviews`), substituting
 *     the auth-store user id for `:therapist_id`.
 *
 * DTO gaps (documented in PROJECT.md §6 Improvements):
 *   1. Backend response is paginated `{data, pagination}` only — no `summary`
 *      (`{average, total, distribution}`) that the page renders. The page falls
 *      back to `{average: 0, total: 0, distribution: {}}` defaults today, so
 *      missing summary renders as "0.0 stars / 0 reviews" — graceful degradation.
 *   2. Backend `reviews` rows lack `patient_name` (it lives in `auth.users`) —
 *      same shape as Phase 1's identity resolver. Page handles missing
 *      `patient_name` via the anonymous fallback (`is_anonymous` flag).
 *
 * Filed as `therapist-reviews-dto-enrichment` follow-up — add a service-layer
 * summary aggregate (avg + count + per-star distribution via SQL `count(*) group by nota`)
 * plus identity resolution. Hook signature stable.
 */
import { useQuery } from '@tanstack/react-query';
import { api, useAuthStore } from '@noctusai/seed/infra';

// ─── Types ─────────────────────────────────────────────────────────────
export interface TherapistReview {
  id: string;
  nota: number;
  comentario?: string;
  patient_name?: string;
  tags?: string[];
  created_at: string;
  is_anonymous: boolean;
}

export interface TherapistReviewSummary {
  average: number;
  total: number;
  distribution: Record<number, number>;
}

interface TherapistReviewsResponse {
  data: TherapistReview[];
  summary?: TherapistReviewSummary;
  pagination?: { page: number; page_size: number; total: number; total_pages: number };
}

// ─── Hook ──────────────────────────────────────────────────────────────
export function useTherapistReviews() {
  const { user } = useAuthStore();

  return useQuery<TherapistReviewsResponse>({
    queryKey: ['therapist', 'reviews', user?.id],
    queryFn: async () => {
      if (!user?.id) {
        return { data: [] };
      }
      return api.get(`/api/reviews/therapist/${user.id}`);
    },
    enabled: !!user?.id,
    staleTime: 5 * 60 * 1000,
  });
}

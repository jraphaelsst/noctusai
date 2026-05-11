import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";

// AI feature hooks — ai-expansion Phase 14 (Mailing M1, M2, M5, M6, M7) + Phase 8 (M3) + Phase 12 (M4 debrief).
//
// Phase 2 (2026-05-11, mailing-wiring) orphan-hook triage:
// Deleted 5 test-only AI hooks: useGenerateSubjects / useDraftTemplate /
// useReengagementVariants / useDeliverabilityReview / useTranslateTemplate.
// Each had backend route + test coverage but ZERO UI consumers — corresponding
// backend routes are KEPT per Q2 (planned UI work). Re-add the hook surface
// when the designs land; backend contract is unchanged.

/** M4 — campaign debrief narrative. Read-only; calls AI service via consent guard. */
export interface CampaignDebriefResponse {
  subject: string;
  html: string;
  text: string;
  metrics?: Record<string, unknown>;
}

export function useCampaignDebrief(campaignId: string | null | undefined) {
  return useQuery<CampaignDebriefResponse, Error>({
    queryKey: ["ai_campaign_debrief", campaignId],
    queryFn: async () => {
      const result = await api.get(`/api/ai/campaigns/${encodeURIComponent(campaignId!)}/debrief`);
      return result.data as CampaignDebriefResponse;
    },
    enabled: Boolean(campaignId),
    // Debrief content is stable per campaign; long stale window keeps cache warm.
    staleTime: 1000 * 60 * 30,
    retry: false,
  });
}

// ---------------------------------------------------------------------------
// M3 — Contact segmentation (Phase 8). Read-side via <AIIndicator
// refType="contact" refId={contact.id}/>; this hook triggers the inference
// + persists N rows server-side and invalidates each per-contact query.
// ---------------------------------------------------------------------------

export interface SegmentResult {
  segmented: number;
  persisted: Array<{
    ref_type: string;
    ref_id: string;
    label: string;
    chip?: string | null;
    metadata?: Record<string, unknown>;
  }>;
}

export function useSegmentContacts() {
  const qc = useQueryClient();
  return useMutation<
    SegmentResult,
    Error,
    { list_id?: string; threshold?: number; max_segments?: number }
  >({
    mutationFn: async (body) => {
      const { data } = await api.post("/api/ai/segment-contacts", body);
      return data as SegmentResult;
    },
    onSuccess: (data) => {
      for (const row of data.persisted) {
        qc.invalidateQueries({ queryKey: ["ai_outputs", row.ref_type, row.ref_id] });
      }
    },
  });
}

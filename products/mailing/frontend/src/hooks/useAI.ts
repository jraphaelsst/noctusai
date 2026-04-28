import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";

// AI feature hooks — ai-expansion Phase 14 (Mailing M1, M2, M5, M6, M7) + Phase 8 (M3) + Phase 12 (M4 debrief).

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

export interface SubjectVariant {
  text: string;
  tone: string;
}

export interface ReengagementVariant {
  tone: string;
  subject: string;
  body_html: string;
}

export interface DeliverabilityFinding {
  code: string;
  severity: "info" | "warning" | "error";
  message: string;
}

export function useGenerateSubjects() {
  return useMutation<SubjectVariant[], Error, { campaign_summary: string }>({
    mutationFn: async (body) => {
      const { data } = await api.post("/api/ai/subjects", body);
      return data?.variants ?? [];
    },
  });
}

export function useDraftTemplate() {
  return useMutation<string, Error, { prompt: string }>({
    mutationFn: async (body) => {
      const { data } = await api.post("/api/ai/template-draft", body);
      return data?.html ?? "";
    },
  });
}

export function useReengagementVariants() {
  return useMutation<ReengagementVariant[], Error, { context: string }>({
    mutationFn: async (body) => {
      const { data } = await api.post("/api/ai/reengagement", body);
      return data?.variants ?? [];
    },
  });
}

export function useDeliverabilityReview() {
  return useMutation<
    { findings: DeliverabilityFinding[] },
    Error,
    { html: string; subject?: string }
  >({
    mutationFn: async (body) => {
      const { data } = await api.post("/api/ai/deliverability", body);
      return { findings: data?.findings ?? [] };
    },
  });
}

export function useTranslateTemplate() {
  return useMutation<string, Error, { html: string; target_lang: "en" | "es" | "fr" }>({
    mutationFn: async (body) => {
      const { data } = await api.post("/api/ai/translate", body);
      return data?.html ?? body.html;
    },
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

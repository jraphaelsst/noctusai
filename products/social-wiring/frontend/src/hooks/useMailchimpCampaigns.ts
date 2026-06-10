/**
 * Mailchimp campaigns hooks.
 *
 * Wraps `/api/mailchimp/campaigns` and campaign action endpoints
 * (send/schedule/unschedule/test).
 *
 * Built on @tanstack/react-query v5. queryFns never return undefined.
 */
import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { api } from "@/lib/api";

// ─── Types ───────────────────────────────────────────────────────────────────

export type CampaignStatus =
  | "save"
  | "paused"
  | "schedule"
  | "sending"
  | "sent";

export interface CampaignOut {
  id: string;
  web_id: number;
  title: string;
  status: CampaignStatus;
  subject_line: string | null;
  preview_text: string | null;
  from_name: string | null;
  reply_to: string | null;
  segment_id: number | null;
  template_id: number | null;
  send_time: string | null;
  create_time: string;
  emails_sent: number | null;
  opens: number | null;
  clicks: number | null;
  archive_url: string | null;
}

export interface CampaignsOut {
  items: CampaignOut[];
  total: number;
}

export interface CreateCampaignBody {
  title: string;
  subject_line: string;
  preview_text?: string;
  from_name: string;
  reply_to: string;
  segment_id?: number;
  template_id?: number;
}

export interface UpdateCampaignBody {
  title?: string;
  subject_line?: string;
  preview_text?: string;
  from_name?: string;
  reply_to?: string;
  segment_id?: number;
  template_id?: number;
}

export interface ScheduleCampaignBody {
  schedule_time: string; // ISO8601 UTC, quarter-hour aligned
}

export interface SendTestBody {
  emails: string[]; // 1..10 emails
}

export interface ListCampaignsParams {
  count?: number;
  offset?: number;
}

const BASE = "/api/mailchimp/campaigns";
const FAMILY_KEY = ["mailchimp"] as const;
const CAMPAIGNS_KEY = [...FAMILY_KEY, "campaigns"] as const;

// ─── Queries ─────────────────────────────────────────────────────────────────

export function useMailchimpCampaigns(params?: ListCampaignsParams) {
  const searchParams = new URLSearchParams();
  if (params?.count != null) searchParams.set("count", String(params.count));
  if (params?.offset != null) searchParams.set("offset", String(params.offset));
  const qs = searchParams.toString();

  return useQuery<CampaignsOut>({
    queryKey: [...CAMPAIGNS_KEY, params],
    queryFn: () => api.get<CampaignsOut>(qs ? `${BASE}?${qs}` : BASE),
  });
}

export function useMailchimpCampaign(campaignId: string | null) {
  return useQuery<CampaignOut>({
    queryKey: [...CAMPAIGNS_KEY, campaignId],
    queryFn: () => api.get<CampaignOut>(`${BASE}/${campaignId}`),
    enabled: !!campaignId,
  });
}

// ─── Mutations ───────────────────────────────────────────────────────────────

export function useMailchimpCampaignMutations() {
  const qc = useQueryClient();
  const invalidateFamily = () => qc.invalidateQueries({ queryKey: FAMILY_KEY });

  const create = useMutation<CampaignOut, unknown, CreateCampaignBody>({
    mutationFn: (body) => api.post<CampaignOut>(BASE, body),
    onSuccess: invalidateFamily,
  });

  const update = useMutation<
    CampaignOut,
    unknown,
    { id: string; body: UpdateCampaignBody }
  >({
    mutationFn: ({ id, body }) => api.patch<CampaignOut>(`${BASE}/${id}`, body),
    onSuccess: invalidateFamily,
  });

  const remove = useMutation<unknown, unknown, string>({
    mutationFn: (id) => api.delete(`${BASE}/${id}`),
    onSuccess: invalidateFamily,
  });

  const send = useMutation<CampaignOut, unknown, string>({
    mutationFn: (id) =>
      api.post<CampaignOut>(`${BASE}/${id}/actions/send`, {}),
    onSuccess: invalidateFamily,
  });

  const schedule = useMutation<
    CampaignOut,
    unknown,
    { id: string; body: ScheduleCampaignBody }
  >({
    mutationFn: ({ id, body }) =>
      api.post<CampaignOut>(`${BASE}/${id}/actions/schedule`, body),
    onSuccess: invalidateFamily,
  });

  const unschedule = useMutation<CampaignOut, unknown, string>({
    mutationFn: (id) =>
      api.post<CampaignOut>(`${BASE}/${id}/actions/unschedule`, {}),
    onSuccess: invalidateFamily,
  });

  const sendTest = useMutation<
    { ok: boolean },
    unknown,
    { id: string; body: SendTestBody }
  >({
    mutationFn: ({ id, body }) =>
      api.post<{ ok: boolean }>(`${BASE}/${id}/actions/test`, body),
    onSuccess: invalidateFamily,
  });

  return { create, update, remove, send, schedule, unschedule, sendTest };
}

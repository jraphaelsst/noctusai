/**
 * Mailchimp segments (Listas) hooks.
 *
 * Wraps `/api/mailchimp/segments` — static segments inside one Mailchimp
 * audience. Also handles segment member management.
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

export interface SegmentOut {
  id: number;
  name: string;
  member_count: number;
  created_at: string;
  updated_at: string;
}

export interface SegmentsOut {
  items: SegmentOut[];
  total: number;
}

export interface SegmentMemberOut {
  email: string;
  status: string;
  first_name: string | null;
  last_name: string | null;
}

export interface SegmentMembersOut {
  items: SegmentMemberOut[];
  total: number;
}

export interface CreateSegmentBody {
  name: string;
}

export interface UpdateSegmentBody {
  name: string;
}

export interface ListSegmentsParams {
  count?: number;
  offset?: number;
}

const BASE = "/api/mailchimp/segments";
const FAMILY_KEY = ["mailchimp"] as const;
const SEGMENTS_KEY = [...FAMILY_KEY, "segments"] as const;

// ─── Queries ─────────────────────────────────────────────────────────────────

export function useMailchimpSegments(params?: ListSegmentsParams) {
  const searchParams = new URLSearchParams();
  if (params?.count != null) searchParams.set("count", String(params.count));
  if (params?.offset != null) searchParams.set("offset", String(params.offset));
  const qs = searchParams.toString();

  return useQuery<SegmentsOut>({
    queryKey: [...SEGMENTS_KEY, params],
    queryFn: () => api.get<SegmentsOut>(qs ? `${BASE}?${qs}` : BASE),
  });
}

export function useMailchimpSegmentMembers(
  segmentId: number | null,
  params?: { count?: number; offset?: number },
) {
  const searchParams = new URLSearchParams();
  if (params?.count != null) searchParams.set("count", String(params.count));
  if (params?.offset != null) searchParams.set("offset", String(params.offset));
  const qs = searchParams.toString();

  return useQuery<SegmentMembersOut>({
    queryKey: [...SEGMENTS_KEY, segmentId, "members", params],
    queryFn: () =>
      api.get<SegmentMembersOut>(
        qs
          ? `${BASE}/${segmentId}/members?${qs}`
          : `${BASE}/${segmentId}/members`,
      ),
    enabled: segmentId != null,
  });
}

// ─── Mutations ───────────────────────────────────────────────────────────────

export function useMailchimpSegmentMutations() {
  const qc = useQueryClient();
  const invalidateFamily = () => qc.invalidateQueries({ queryKey: FAMILY_KEY });

  const create = useMutation<SegmentOut, unknown, CreateSegmentBody>({
    mutationFn: (body) => api.post<SegmentOut>(BASE, body),
    onSuccess: invalidateFamily,
  });

  const update = useMutation<
    SegmentOut,
    unknown,
    { id: number; body: UpdateSegmentBody }
  >({
    mutationFn: ({ id, body }) =>
      api.patch<SegmentOut>(`${BASE}/${id}`, body),
    onSuccess: invalidateFamily,
  });

  const remove = useMutation<unknown, unknown, number>({
    mutationFn: (id) => api.delete(`${BASE}/${id}`),
    onSuccess: invalidateFamily,
  });

  const addMember = useMutation<
    unknown,
    unknown,
    { segmentId: number; email: string }
  >({
    mutationFn: ({ segmentId, email }) =>
      api.post(`${BASE}/${segmentId}/members`, { email }),
    onSuccess: invalidateFamily,
  });

  const removeMember = useMutation<
    unknown,
    unknown,
    { segmentId: number; email: string }
  >({
    mutationFn: ({ segmentId, email }) =>
      api.delete(`${BASE}/${segmentId}/members/${encodeURIComponent(email)}`),
    onSuccess: invalidateFamily,
  });

  return { create, update, remove, addMember, removeMember };
}

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
  useQueryClient,
  keepPreviousData,
  useQuery,
} from "@tanstack/react-query";
import { listOps, useCacheWriteMutation } from "@noctusai/lib/cache-writes";
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
    // The key varies only by `offset`/`count` — paging through the SAME
    // list, never a different entity — so keeping the previous page
    // visible while the next one loads is safe (standard pagination UX,
    // no cross-entity mismatch hazard).
    placeholderData: keepPreviousData,
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
    // NO placeholderData — `segmentId` is part of the key. Reusing a
    // different segment's member page while its drawer re-opens for a
    // NEW segment would render segment A's members under segment B's
    // header, the exact cross-entity hazard this product has shipped
    // before (leads-under-wrong-broker). Offset-only re-pagination
    // within the SAME segment re-fetches from a cold cache anyway
    // (each offset is its own query key) so there is no smooth-paging
    // upside here to trade against that risk.
  });
}

// ─── Mutations ───────────────────────────────────────────────────────────────

/** Mailchimp ids are numbers, so these edits go through `listOps.within` (untyped rows) instead of the string-id ops. */
export function useMailchimpSegmentMutations() {
  const qc = useQueryClient();
  const segmentos = (edit: (l: SegmentOut[]) => SegmentOut[], totalDelta = 0) =>
    (old: SegmentsOut | undefined) => {
      const next = listOps.within(old, "items", edit);
      return next && totalDelta ? { ...next, total: Math.max(0, next.total + totalDelta) } : next;
    };

  const create = useCacheWriteMutation<SegmentOut, CreateSegmentBody>({
    mutationFn: (body) => api.post<SegmentOut>(BASE, body),
    // The default (param-less) list; paged / offset lists settle.
    targets: [
      {
        queryKey: [...SEGMENTS_KEY, undefined],
        commit: (old: SegmentsOut | undefined, saved) =>
          old?.items?.some((s) => s.id === saved.id) ? old : segmentos((l) => [...l, saved], 1)(old),
      },
    ],
    invalidate: [FAMILY_KEY],
  });

  const update = useCacheWriteMutation<SegmentOut, { id: number; body: UpdateSegmentBody }>({
    mutationFn: ({ id, body }) => api.patch<SegmentOut>(`${BASE}/${id}`, body),
    targets: ({ id }) => [
      {
        queryKey: SEGMENTS_KEY,
        match: "prefix",
        commit: (old: SegmentsOut | undefined, saved) =>
          segmentos((l) => l.map((s) => (s.id === id ? { ...s, ...saved } : s)))(old),
      },
    ],
    invalidate: [FAMILY_KEY],
  });

  const remove = useCacheWriteMutation<unknown, number>({
    mutationFn: (id) => api.delete(`${BASE}/${id}`),
    targets: (id) => [
      {
        queryKey: SEGMENTS_KEY,
        match: "prefix",
        optimistic: (old: SegmentsOut | undefined) =>
          old?.items?.some((s) => s.id === id) ? segmentos((l) => l.filter((s) => s.id !== id), -1)(old) : old,
      },
    ],
    invalidate: [FAMILY_KEY],
  });

  const addMember = useMutation<unknown, unknown, { segmentId: number; email: string }>({ // noc-allow: invalidate-only — the answer carries no member row: name/status of the added contact come from Mailchimp via a refetch
    mutationFn: ({ segmentId, email }) =>
      api.post(`${BASE}/${segmentId}/members`, { email }),
    onSuccess: () => qc.invalidateQueries({ queryKey: FAMILY_KEY }),
  });

  const removeMember = useCacheWriteMutation<unknown, { segmentId: number; email: string }>({
    mutationFn: ({ segmentId, email }) =>
      api.delete(`${BASE}/${segmentId}/members/${encodeURIComponent(email)}`),
    targets: ({ segmentId, email }) => [
      {
        queryKey: [...SEGMENTS_KEY, segmentId, "members"],
        match: "prefix",
        optimistic: (old: SegmentMembersOut | undefined) => {
          if (!old?.items?.some((m) => m.email === email)) return old;
          const next = listOps.within(old, "items", (l) => l.filter((m) => m.email !== email));
          return next ? { ...next, total: Math.max(0, next.total - 1) } : old;
        },
      },
      {
        queryKey: SEGMENTS_KEY,
        match: "prefix",
        optimistic: (old: SegmentsOut | undefined) =>
          segmentos((l) =>
            l.map((s) => (s.id === segmentId ? { ...s, member_count: Math.max(0, s.member_count - 1) } : s)),
          )(old),
      },
    ],
    invalidate: [FAMILY_KEY],
  });

  return { create, update, remove, addMember, removeMember };
}

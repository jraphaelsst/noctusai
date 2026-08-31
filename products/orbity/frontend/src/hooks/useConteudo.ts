/**
 * Content / Social Studio hooks for Orbity — campaigns, posts, approvals.
 *
 * All list endpoints return { items, total, page, page_size }.
 * Single-resource endpoints (GET/PATCH/DELETE /:id) return the resource directly.
 * Approvals list returns a plain array.
 *
 * Convention: one file per domain entity, TanStack Query throughout.
 * `api` is imported from `@/lib/api` (the local seam, not seed directly).
 */
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useAuthStore } from "@noctusai/seed/infra";

// ---------------------------------------------------------------------------
// Domain types (mirrors backend schemas/social_content.py)
// ---------------------------------------------------------------------------

export type Platform = "instagram" | "facebook" | "tiktok" | "linkedin" | "twitter";
export type PostStatus = "draft" | "pending_approval" | "approved" | "revision" | "published";
export type CampaignStatus = "active" | "paused" | "completed" | "archived";
export type ApprovalStatus = "pending" | "approved" | "revision";

export interface Campaign {
  id: string;
  org_id: string;
  client_id: string | null;
  name: string;
  month: string; // YYYY-MM
  status: CampaignStatus;
  created_at: string;
  updated_at: string;
}

export interface Post {
  id: string;
  org_id: string;
  campaign_id: string | null;
  client_id: string | null;
  platform: Platform;
  caption: string | null;
  hashtags: string | null;
  scheduled_for: string | null;
  status: PostStatus;
  assignee_user_id: string | null;
  media_url: string | null;
  created_at: string;
  updated_at: string;
}

export interface Approval {
  id: string;
  org_id: string;
  post_id: string;
  public_token: string;
  status: ApprovalStatus;
  client_feedback: string | null;
  expires_at: string;
  decided_at: string | null;
  created_at: string;
  updated_at: string;
}

interface ListResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

// ---------------------------------------------------------------------------
// Campaigns
// ---------------------------------------------------------------------------

export interface CampaignFilters {
  client_id?: string;
  month?: string;
  status?: CampaignStatus;
  page?: number;
  page_size?: number;
}

export interface CampaignCreate {
  name: string;
  month: string; // YYYY-MM
  client_id?: string;
  status?: CampaignStatus;
}

export interface CampaignUpdate {
  id: string;
  name?: string;
  month?: string;
  client_id?: string;
  status?: CampaignStatus;
}

export function useCampaigns(filters?: CampaignFilters) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ["content-campaigns", filters],
    queryFn: async () => {
      return api.get<ListResponse<Campaign>>("/api/content/campaigns", {
        client_id: filters?.client_id,
        month: filters?.month,
        status: filters?.status,
        page: filters?.page ?? 1,
        page_size: filters?.page_size ?? 50,
      });
    },
    enabled: !!user,
    staleTime: 3 * 60 * 1000,
  });
}

export function useCreateCampaign() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: CampaignCreate) => {
      return api.post<Campaign>("/api/content/campaigns", data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["content-campaigns"] });
      toast.success("Campanha criada com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao criar campanha", { description: error.message });
    },
  });
}

export function useUpdateCampaign() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, ...data }: CampaignUpdate) => {
      return api.patch<Campaign>(`/api/content/campaigns/${id}`, data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["content-campaigns"] });
      toast.success("Campanha atualizada com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao atualizar campanha", { description: error.message });
    },
  });
}

export function useDeleteCampaign() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string) => {
      return api.delete<{ ok: boolean; id: string }>(`/api/content/campaigns/${id}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["content-campaigns"] });
      queryClient.invalidateQueries({ queryKey: ["content-posts"] });
      toast.success("Campanha removida com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao remover campanha", { description: error.message });
    },
  });
}

// ---------------------------------------------------------------------------
// Posts
// ---------------------------------------------------------------------------

export interface PostFilters {
  campaign_id?: string;
  client_id?: string;
  platform?: Platform;
  status?: PostStatus;
  page?: number;
  page_size?: number;
}

export interface PostCreate {
  platform: Platform;
  caption?: string;
  hashtags?: string;
  scheduled_for?: string;
  status?: PostStatus;
  campaign_id?: string;
  client_id?: string;
  media_url?: string;
}

export interface PostUpdate {
  id: string;
  platform?: Platform;
  caption?: string;
  hashtags?: string;
  scheduled_for?: string;
  status?: PostStatus;
  campaign_id?: string;
  client_id?: string;
  media_url?: string;
}

export function usePosts(filters?: PostFilters) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ["content-posts", filters],
    queryFn: async () => {
      return api.get<ListResponse<Post>>("/api/content/posts", {
        campaign_id: filters?.campaign_id,
        client_id: filters?.client_id,
        platform: filters?.platform,
        status: filters?.status,
        page: filters?.page ?? 1,
        page_size: filters?.page_size ?? 50,
      });
    },
    placeholderData: (prev) => prev,
    enabled: !!user,
    staleTime: 2 * 60 * 1000,
  });
}

export function useCreatePost() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: PostCreate) => {
      return api.post<Post>("/api/content/posts", data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["content-posts"] });
      toast.success("Post criado com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao criar post", { description: error.message });
    },
  });
}

export function useUpdatePost() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, ...data }: PostUpdate) => {
      return api.patch<Post>(`/api/content/posts/${id}`, data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["content-posts"] });
      toast.success("Post atualizado com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao atualizar post", { description: error.message });
    },
  });
}

export function useDeletePost() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string) => {
      return api.delete<{ ok: boolean; id: string }>(`/api/content/posts/${id}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["content-posts"] });
      queryClient.invalidateQueries({ queryKey: ["content-approvals"] });
      toast.success("Post removido com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao remover post", { description: error.message });
    },
  });
}

// ---------------------------------------------------------------------------
// Approvals (authed side)
// ---------------------------------------------------------------------------

export interface ApprovalCreate {
  expires_in_days?: number;
}

export function useApprovals(postId?: string) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ["content-approvals", postId],
    queryFn: async () => {
      if (postId) {
        return api.get<Approval[]>(`/api/content/posts/${postId}/approvals`);
      }
      return api.get<Approval[]>("/api/content/approvals");
    },
    enabled: !!user,
    staleTime: 2 * 60 * 1000,
  });
}

export function useCreateApproval() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      postId,
      expires_in_days = 7,
    }: {
      postId: string;
      expires_in_days?: number;
    }) => {
      return api.post<Approval>(`/api/content/posts/${postId}/approvals`, {
        expires_in_days,
      });
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ["content-approvals", variables.postId] });
      queryClient.invalidateQueries({ queryKey: ["content-posts"] });
      toast.success("Link de aprovacao criado!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao criar link de aprovacao", { description: error.message });
    },
  });
}

// ---------------------------------------------------------------------------
// Public approval — token-gated, no auth required
//
// GET  /api/content/approve/{token}  → PublicApproval (200) | 404 | 410
// POST /api/content/approve/{token}  → { ok: true } (200)
//
// Both endpoints take NO JWT. Plain fetch is used (no api client auth header).
// Mirror of usePublicReport in useRelatorios.ts.
// ---------------------------------------------------------------------------

export interface PublicApprovalPost {
  id: string;
  platform: Platform;
  caption: string | null;
  hashtags: string | null;
  media_url: string | null;
  scheduled_for: string | null;
}

export interface PublicApproval {
  approval_id: string;
  post_id: string;
  token: string;
  status: ApprovalStatus;
  expires_at: string;
  decided_at: string | null;
  post: PublicApprovalPost;
}

export type ApprovalDecision = "approved" | "revision";

export interface DecideApprovalPayload {
  decision: ApprovalDecision;
  feedback?: string;
}

export function usePublicApproval(token: string | null) {
  return useQuery({
    queryKey: ["public-approval", token],
    queryFn: async () => {
      return api.get<PublicApproval>(`/api/content/approve/${token}`);
    },
    enabled: !!token,
    staleTime: 5 * 60 * 1000,
    retry: false,
  });
}

export function useDecideApproval(token: string | null) {
  return useMutation({
    mutationFn: async (payload: DecideApprovalPayload) => {
      return api.post<{ ok: boolean }>(`/api/content/approve/${token}`, payload);
    },
  });
}

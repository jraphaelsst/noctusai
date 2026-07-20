/**
 * Meta (Instagram + Facebook) hooks — TanStack Query wrappers over the
 * account-scoped `/api/meta/*` routers (Wave 3 contract, Slice 3A/3B).
 *
 * Every hook reads `activeAccountId` from `useActiveAccountStore` (set by
 * `<ConnectedAccountSwitcher provider="meta" />`) and threads it as
 * `?account_id=` — the same convention as the YouTube hooks
 * (useVideos / useDashboardStats). No more path-param `{ig_user_id}` /
 * local `AccountPicker` — that model is retired with `InstagramInsights.tsx`.
 *
 * App Review gate: any write endpoint MAY return `{ requires_app_review:
 * true, error }` as a 200 (not a thrown error) — the UI renders a distinct
 * "Requer Revisão do app Meta" state, never a fake success. Every mutation
 * hook here returns that shape verbatim in `.data`; callers must check the
 * flag before treating the mutation as a success.
 *
 * BE-contract notes (flagged for backend-engineer reconciliation — see
 * delivery note): the Wave 3 contract text does not specify (a) a
 * Facebook posts-LIST endpoint (only publish + insights + comments-by-post)
 * — `useFbPosts` below assumes `GET /api/meta/facebook/posts`; (b) a
 * comment-hide endpoint — assumed `POST /api/meta/instagram/comments/hide`
 * and `POST /api/meta/facebook/comments/hide`, body `{comment_id}`.
 */
import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";
import { useActiveAccountStore } from "@/state/useActiveAccount";

// ─── Shared gate shape ───────────────────────────────────────────────────────

/** Every Meta write MAY come back gated instead of thrown. */
export interface AppReviewGate {
  requires_app_review: true;
  error: string | null;
}

export type GatedResult<T> = T | AppReviewGate;

export function isAppReviewGate(x: unknown): x is AppReviewGate {
  return !!x && typeof x === "object" && (x as AppReviewGate).requires_app_review === true;
}

/**
 * The app lacks the Meta *product* behind an endpoint (Graph code 3 —
 * "Application does not have the capability to make this API call"). A
 * READ can come back gated this way — e.g. Instagram DMs when the
 * Messenger / Instagram-messaging product is not set up on the app. The
 * backend returns `{ requires_setup: true, error }` as a 200 (never a
 * 502), so the UI renders an actionable "finish the Meta setup" card
 * instead of a scary error toast. Distinct from `AppReviewGate`: the
 * remedy is a dashboard configuration step, not App Review submission.
 */
export interface MetaSetupGate {
  requires_setup: true;
  error: string | null;
}

export function isMetaSetupGate(x: unknown): x is MetaSetupGate {
  return !!x && typeof x === "object" && (x as MetaSetupGate).requires_setup === true;
}

/** A READ endpoint's success payload OR a `MetaSetupGate` (both 200). */
export type SetupGatedResult<T> = T | MetaSetupGate;

// ─── Types (mirror the Wave 3 backend contract) ─────────────────────────────

export interface IGAccount {
  id: string;
  username: string;
  name?: string | null;
  profile_picture_url?: string | null;
  followers_count?: number | null;
  follows_count?: number | null;
  media_count?: number | null;
  biography?: string | null;
  website?: string | null;
  page_id?: string | null;
}

export interface FacebookPage {
  id: string;
  name: string;
  category?: string | null;
  picture_url?: string | null;
}

export interface MetaContext {
  instagram: IGAccount | null;
  pages: FacebookPage[];
  user: { id: string; name: string } | null;
}

export interface MetaInsights {
  object_id: string;
  metrics: Record<string, number>;
  series: unknown[];
  error?: string | null;
}

export interface IGMediaItem {
  id: string;
  caption?: string | null;
  media_type?: string | null;
  permalink?: string | null;
  thumbnail_url?: string | null;
  timestamp?: string | null;
  like_count: number;
  comments_count: number;
  insights: Record<string, number> | null;
}

export interface IGMediaResponse {
  media: IGMediaItem[];
}

export interface IGSnapshot {
  captured_at: string;
  followers_count?: number | null;
  follows_count?: number | null;
  media_count?: number | null;
  reach?: number | null;
  profile_views?: number | null;
}

export interface IGSnapshotsResponse {
  snapshots: IGSnapshot[];
}

export interface FacebookPost {
  id: string;
  message?: string | null;
  permalink_url?: string | null;
  full_picture?: string | null;
  created_time?: string | null;
  likes_count?: number | null;
  comments_count?: number | null;
}

export interface FacebookPostsResponse {
  posts: FacebookPost[];
}

export interface MetaComment {
  id: string;
  text: string;
  from_username?: string | null;
  timestamp?: string | null;
  hidden?: boolean;
}

export interface MetaCommentsResponse {
  comments: MetaComment[];
}

export interface IGConversation {
  id: string;
  participant_name: string | null;
  participant_id: string | null;
  updated_time: string | null;
  snippet: string | null;
  unread_count: number;
}

export interface IGConversationsResponse {
  conversations: IGConversation[];
}

export interface IGMessage {
  id: string;
  from_id: string;
  /** Mirrors the WhatsApp Message DTO shape (direction) so Wave 4's shared
   * ChatWindow can consume both adapters uniformly. */
  direction: "inbound" | "outbound";
  text: string;
  created_at: string;
}

export interface IGMessagesResponse {
  messages: IGMessage[];
}

export type IGPublishKind = "media" | "carousel" | "reel" | "story";
export interface IGPublishInput {
  kind: IGPublishKind;
  media_urls: string[];
  caption?: string;
}

export type FbPublishKind = "post" | "photo" | "video";
export interface FbPublishInput {
  kind: FbPublishKind;
  page_id: string;
  message?: string;
  media_url?: string;
}

export interface PublishedResult {
  id: string;
  permalink?: string | null;
}

// ─── Query keys ──────────────────────────────────────────────────────────────

const FAMILY_KEY = ["meta"] as const;
const CONTEXT_KEY = (accountId: string | null) => [...FAMILY_KEY, "context", accountId] as const;
const IG_INSIGHTS_KEY = (accountId: string | null, days: number) =>
  [...FAMILY_KEY, "instagram", "insights", accountId, days] as const;
const IG_MEDIA_KEY = (accountId: string | null, limit: number) =>
  [...FAMILY_KEY, "instagram", "media", accountId, limit] as const;
const IG_SNAPSHOTS_KEY = (accountId: string | null, days: number) =>
  [...FAMILY_KEY, "instagram", "snapshots", accountId, days] as const;
const IG_COMMENTS_KEY = (accountId: string | null, mediaId: string | null) =>
  [...FAMILY_KEY, "instagram", "comments", accountId, mediaId] as const;
const IG_CONVERSATIONS_KEY = (accountId: string | null) =>
  [...FAMILY_KEY, "instagram", "conversations", accountId] as const;
const IG_MESSAGES_KEY = (accountId: string | null, conversationId: string | null) =>
  [...FAMILY_KEY, "instagram", "messages", accountId, conversationId] as const;
const FB_INSIGHTS_KEY = (accountId: string | null, pageId: string | null) =>
  [...FAMILY_KEY, "facebook", "insights", accountId, pageId] as const;
const FB_POSTS_KEY = (accountId: string | null, pageId: string | null) =>
  [...FAMILY_KEY, "facebook", "posts", accountId, pageId] as const;
const FB_COMMENTS_KEY = (accountId: string | null, postId: string | null) =>
  [...FAMILY_KEY, "facebook", "comments", accountId, postId] as const;

// ─── Active-account convenience ─────────────────────────────────────────────

/** Reads the shared store — call from a subtab to avoid prop-drilling. */
export function useActiveMetaAccountId(): string | null {
  return useActiveAccountStore((s) => s.activeAccountId);
}

function qs(params: Record<string, string | number | boolean | null | undefined>): string {
  const usp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== null && v !== undefined && v !== "") usp.set(k, String(v));
  }
  const s = usp.toString();
  return s ? `?${s}` : "";
}

// ─── Context (accounts/pages the connection can see) ────────────────────────

export function useMetaContext(accountId: string | null) {
  return useQuery<MetaContext>({
    queryKey: CONTEXT_KEY(accountId),
    queryFn: () =>
      api.get<MetaContext>(`/api/meta/context${qs({ account_id: accountId })}`),
    enabled: !!accountId,
  });
}

// ─── Instagram — insights / media / snapshots ───────────────────────────────

export function useIgInsights(accountId: string | null, days = 30) {
  return useQuery<MetaInsights>({
    queryKey: IG_INSIGHTS_KEY(accountId, days),
    queryFn: () =>
      api.get<MetaInsights>(
        `/api/meta/instagram/insights${qs({ account_id: accountId, period: "day", days })}`,
      ),
    enabled: !!accountId,
  });
}

export function useIgMedia(accountId: string | null, limit = 25) {
  return useQuery<IGMediaResponse>({
    queryKey: IG_MEDIA_KEY(accountId, limit),
    queryFn: () =>
      api.get<IGMediaResponse>(
        `/api/meta/instagram/media${qs({ account_id: accountId, limit, with_insights: true })}`,
      ),
    enabled: !!accountId,
  });
}

export function useIgSnapshots(accountId: string | null, days = 90) {
  return useQuery<IGSnapshotsResponse>({
    queryKey: IG_SNAPSHOTS_KEY(accountId, days),
    queryFn: () =>
      api.get<IGSnapshotsResponse>(
        `/api/meta/instagram/snapshots${qs({ account_id: accountId, days })}`,
      ),
    enabled: !!accountId,
  });
}

export function useCaptureIgSnapshot(accountId: string | null) {
  const qc = useQueryClient();
  return useMutation<IGSnapshot, unknown, void>({
    mutationFn: () =>
      api.post<IGSnapshot>(`/api/meta/instagram/snapshot${qs({ account_id: accountId })}`, {}),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: [...FAMILY_KEY, "instagram", "snapshots"] });
    },
  });
}

// ─── Instagram — publish ─────────────────────────────────────────────────────

export function useIgPublish(accountId: string | null) {
  const qc = useQueryClient();
  return useMutation<GatedResult<PublishedResult>, unknown, IGPublishInput>({
    mutationFn: (body) =>
      api.post<GatedResult<PublishedResult>>(
        `/api/meta/instagram/publish${qs({ account_id: accountId })}`,
        body,
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: [...FAMILY_KEY, "instagram", "media"] });
    },
  });
}

// ─── Instagram — comments ────────────────────────────────────────────────────

export function useIgComments(accountId: string | null, mediaId: string | null) {
  return useQuery<MetaCommentsResponse>({
    queryKey: IG_COMMENTS_KEY(accountId, mediaId),
    queryFn: () =>
      api.get<MetaCommentsResponse>(
        `/api/meta/instagram/comments${qs({ account_id: accountId, media_id: mediaId })}`,
      ),
    enabled: !!accountId && !!mediaId,
  });
}

export function useIgReplyComment(accountId: string | null, mediaId: string | null) {
  const qc = useQueryClient();
  return useMutation<GatedResult<MetaComment>, unknown, { message: string; parent_comment_id?: string }>({
    mutationFn: (body) =>
      api.post<GatedResult<MetaComment>>(
        `/api/meta/instagram/comments${qs({ account_id: accountId })}`,
        { media_id: mediaId, ...body },
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: IG_COMMENTS_KEY(accountId, mediaId) });
    },
  });
}

export function useIgHideComment(accountId: string | null, mediaId: string | null) {
  const qc = useQueryClient();
  return useMutation<GatedResult<{ ok: true }>, unknown, { commentId: string; hide: boolean }>({
    mutationFn: ({ commentId, hide }) =>
      api.post<GatedResult<{ ok: true }>>(
        `/api/meta/instagram/comments/hide${qs({ account_id: accountId })}`,
        { comment_id: commentId, hide },
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: IG_COMMENTS_KEY(accountId, mediaId) });
    },
  });
}

export function useIgDeleteComment(accountId: string | null, mediaId: string | null) {
  const qc = useQueryClient();
  return useMutation<GatedResult<{ ok: true }>, unknown, string>({
    mutationFn: (commentId) =>
      api.delete<GatedResult<{ ok: true }>>(
        `/api/meta/instagram/comments/${commentId}${qs({ account_id: accountId })}`,
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: IG_COMMENTS_KEY(accountId, mediaId) });
    },
  });
}

// ─── Instagram — DMs ─────────────────────────────────────────────────────────

export function useIgConversations(accountId: string | null) {
  // Returns the list OR a `MetaSetupGate` (200, not thrown) when the app
  // lacks the Instagram-messaging capability — callers branch via
  // `isMetaSetupGate` before reading `.conversations`.
  return useQuery<SetupGatedResult<IGConversationsResponse>>({
    queryKey: IG_CONVERSATIONS_KEY(accountId),
    queryFn: () =>
      api.get<SetupGatedResult<IGConversationsResponse>>(
        `/api/meta/instagram/conversations${qs({ account_id: accountId })}`,
      ),
    enabled: !!accountId,
    refetchInterval: 15_000,
  });
}

export function useIgMessages(accountId: string | null, conversationId: string | null) {
  return useQuery<SetupGatedResult<IGMessagesResponse>>({
    queryKey: IG_MESSAGES_KEY(accountId, conversationId),
    queryFn: () =>
      api.get<SetupGatedResult<IGMessagesResponse>>(
        `/api/meta/instagram/messages${qs({ account_id: accountId, conversation_id: conversationId })}`,
      ),
    enabled: !!accountId && !!conversationId,
    refetchInterval: 8_000,
  });
}

export function useSendIgMessage(accountId: string | null, conversationId: string | null) {
  const qc = useQueryClient();
  return useMutation<GatedResult<IGMessage>, unknown, { recipient_id: string; text: string }>({
    mutationFn: (body) =>
      api.post<GatedResult<IGMessage>>(
        `/api/meta/instagram/messages${qs({ account_id: accountId })}`,
        body,
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: IG_MESSAGES_KEY(accountId, conversationId) });
      qc.invalidateQueries({ queryKey: IG_CONVERSATIONS_KEY(accountId) });
    },
  });
}

// ─── Facebook — insights / posts ─────────────────────────────────────────────

export function useFbInsights(accountId: string | null, pageId: string | null) {
  return useQuery<MetaInsights>({
    queryKey: FB_INSIGHTS_KEY(accountId, pageId),
    queryFn: () =>
      api.get<MetaInsights>(
        `/api/meta/facebook/insights${qs({ account_id: accountId, page_id: pageId })}`,
      ),
    enabled: !!accountId && !!pageId,
  });
}

/** BE-contract assumption — see file header. */
export function useFbPosts(accountId: string | null, pageId: string | null) {
  return useQuery<FacebookPostsResponse>({
    queryKey: FB_POSTS_KEY(accountId, pageId),
    queryFn: () =>
      api.get<FacebookPostsResponse>(
        `/api/meta/facebook/posts${qs({ account_id: accountId, page_id: pageId })}`,
      ),
    enabled: !!accountId && !!pageId,
  });
}

export function useFbPublish(accountId: string | null) {
  const qc = useQueryClient();
  return useMutation<GatedResult<PublishedResult>, unknown, FbPublishInput>({
    mutationFn: (body) =>
      api.post<GatedResult<PublishedResult>>(
        `/api/meta/facebook/publish${qs({ account_id: accountId })}`,
        body,
      ),
    onSuccess: (_, variables) => {
      qc.invalidateQueries({ queryKey: FB_POSTS_KEY(accountId, variables.page_id) });
    },
  });
}

// ─── Facebook — comments ─────────────────────────────────────────────────────

export function useFbComments(accountId: string | null, postId: string | null) {
  return useQuery<MetaCommentsResponse>({
    queryKey: FB_COMMENTS_KEY(accountId, postId),
    queryFn: () =>
      api.get<MetaCommentsResponse>(
        `/api/meta/facebook/comments${qs({ account_id: accountId, post_id: postId })}`,
      ),
    enabled: !!accountId && !!postId,
  });
}

export function useFbReplyComment(accountId: string | null, postId: string | null) {
  const qc = useQueryClient();
  return useMutation<GatedResult<MetaComment>, unknown, { message: string }>({
    mutationFn: (body) =>
      api.post<GatedResult<MetaComment>>(
        `/api/meta/facebook/comments${qs({ account_id: accountId })}`,
        { post_id: postId, ...body },
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: FB_COMMENTS_KEY(accountId, postId) });
    },
  });
}

export function useFbHideComment(accountId: string | null, postId: string | null) {
  const qc = useQueryClient();
  return useMutation<GatedResult<{ ok: true }>, unknown, { commentId: string; hide: boolean }>({
    mutationFn: ({ commentId, hide }) =>
      api.post<GatedResult<{ ok: true }>>(
        `/api/meta/facebook/comments/hide${qs({ account_id: accountId })}`,
        { comment_id: commentId, hide },
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: FB_COMMENTS_KEY(accountId, postId) });
    },
  });
}

export function useFbDeleteComment(accountId: string | null, postId: string | null) {
  const qc = useQueryClient();
  return useMutation<GatedResult<{ ok: true }>, unknown, string>({
    mutationFn: (commentId) =>
      api.delete<GatedResult<{ ok: true }>>(
        `/api/meta/facebook/comments/${commentId}${qs({ account_id: accountId })}`,
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: FB_COMMENTS_KEY(accountId, postId) });
    },
  });
}

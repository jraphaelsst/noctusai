/**
 * Conteudo — Social/Content Studio page for Orbity.
 *
 * Sections (tabs):
 *   1. Pipeline  — posts grouped by status (board view): draft → pending_approval
 *                  → approved / revision → published
 *   2. Posts     — flat list with full CRUD + "Send for approval" action that
 *                  creates an approval link and surfaces the shareable token.
 *   3. Campanhas — campaign list with full CRUD; acts as a filter context for
 *                  Posts tab.
 *
 * Every section ships all four states: loading / empty / error / success.
 *
 * Nav: registered under route key "conteudo" — requires a status_pagina
 * row with page_key = "conteudo" (see return note).
 *
 * status_pagina keys required:
 *   - "conteudo"
 */
import { useState } from "react";
import {
  LayoutGrid,
  List,
  Megaphone,
  Plus,
  Pencil,
  Trash2,
  Loader2,
  AlertCircle,
  FileText,
  Send,
  Link2,
  X,
  Clock,
  CheckCircle2,
  RotateCcw,
  Globe,
  Instagram,
  Facebook,
  Linkedin,
  Twitter,
} from "lucide-react";
import {
  useCampaigns,
  useCreateCampaign,
  useUpdateCampaign,
  useDeleteCampaign,
  usePosts,
  useCreatePost,
  useUpdatePost,
  useDeletePost,
  useCreateApproval,
  type Campaign,
  type Post,
  type Platform,
  type PostStatus,
  type CampaignStatus,
  type CampaignCreate,
  type PostCreate,
} from "@/hooks/useConteudo";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmtDateTime(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("pt-BR", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

type TabKey = "pipeline" | "posts" | "campanhas";

// ---------------------------------------------------------------------------
// Platform icon + label maps
// ---------------------------------------------------------------------------

const PLATFORM_LABELS: Record<Platform, string> = {
  instagram: "Instagram",
  facebook: "Facebook",
  tiktok: "TikTok",
  linkedin: "LinkedIn",
  twitter: "Twitter / X",
};

const PLATFORM_COLORS: Record<Platform, string> = {
  instagram: "bg-pink-100 text-pink-700 dark:bg-pink-900/30 dark:text-pink-400",
  facebook: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
  tiktok: "bg-gray-100 text-gray-700 dark:bg-gray-800/50 dark:text-gray-300",
  linkedin: "bg-sky-100 text-sky-700 dark:bg-sky-900/30 dark:text-sky-400",
  twitter: "bg-slate-100 text-slate-700 dark:bg-slate-800/50 dark:text-slate-300",
};

function PlatformIcon({ platform, className = "h-3.5 w-3.5" }: { platform: Platform; className?: string }) {
  switch (platform) {
    case "instagram": return <Instagram className={className} />;
    case "facebook": return <Facebook className={className} />;
    case "linkedin": return <Linkedin className={className} />;
    case "twitter": return <Twitter className={className} />;
    default: return <Globe className={className} />; // tiktok fallback
  }
}

// ---------------------------------------------------------------------------
// Post status maps
// ---------------------------------------------------------------------------

const POST_STATUS_LABELS: Record<PostStatus, string> = {
  draft: "Rascunho",
  pending_approval: "Aguard. aprovacao",
  approved: "Aprovado",
  revision: "Em revisao",
  published: "Publicado",
};

const POST_STATUS_COLORS: Record<PostStatus, string> = {
  draft: "bg-gray-100 text-gray-600 dark:bg-gray-800/40 dark:text-gray-400",
  pending_approval: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400",
  approved: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
  revision: "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400",
  published: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
};

const POST_STATUS_ICONS: Record<PostStatus, React.ElementType> = {
  draft: FileText,
  pending_approval: Clock,
  approved: CheckCircle2,
  revision: RotateCcw,
  published: Globe,
};

// ---------------------------------------------------------------------------
// Campaign status maps
// ---------------------------------------------------------------------------

const CAMPAIGN_STATUS_LABELS: Record<CampaignStatus, string> = {
  active: "Ativa",
  paused: "Pausada",
  completed: "Concluida",
  archived: "Arquivada",
};

const CAMPAIGN_STATUS_COLORS: Record<CampaignStatus, string> = {
  active: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
  paused: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400",
  completed: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
  archived: "bg-gray-100 text-gray-600 dark:bg-gray-800/40 dark:text-gray-400",
};

// ---------------------------------------------------------------------------
// Shared state components
// ---------------------------------------------------------------------------

function LoadingState({ label }: { label: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 gap-3">
      <Loader2 className="h-7 w-7 animate-spin text-primary" />
      <p className="text-sm text-muted-foreground">{label}</p>
    </div>
  );
}

function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 gap-3 text-destructive">
      <AlertCircle className="h-7 w-7" />
      <p className="text-sm font-medium">Erro ao carregar dados</p>
      <p className="text-xs text-muted-foreground max-w-sm text-center">{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-1 rounded-md border border-destructive/30 bg-destructive/10 px-4 py-1.5 text-xs font-medium text-destructive hover:bg-destructive/20 transition-colors"
        >
          Tentar novamente
        </button>
      )}
    </div>
  );
}

function EmptyState({ label, onAdd }: { label: string; onAdd?: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 gap-3">
      <FileText className="h-8 w-8 text-muted-foreground/40" />
      <p className="text-sm text-muted-foreground">{label}</p>
      {onAdd && (
        <button
          onClick={onAdd}
          className="mt-1 inline-flex items-center gap-1.5 rounded-md bg-primary px-4 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
        >
          <Plus className="h-3.5 w-3.5" />
          Adicionar
        </button>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Approval link dialog — surface the shareable token
// ---------------------------------------------------------------------------

function ApprovalLinkDialog({
  postId,
  postCaption,
  open,
  onClose,
}: {
  postId: string;
  postCaption: string | null;
  open: boolean;
  onClose: () => void;
}) {
  const createApproval = useCreateApproval();
  const [expiresInDays, setExpiresInDays] = useState(7);
  const [createdToken, setCreatedToken] = useState<string | null>(null);

  if (!open) return null;

  async function handleCreate() {
    const result = await createApproval.mutateAsync({
      postId,
      expires_in_days: expiresInDays,
    });
    // result.public_token is the UUID token the client uses
    setCreatedToken(result.public_token);
  }

  // Build a shareable URL path — the actual host is env-resolved at runtime
  const approveUrl = createdToken
    ? `${window.location.origin}/api/content/approve/${createdToken}`
    : null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={onClose}
    >
      <div
        className="w-full max-w-[calc(100vw-2rem)] sm:max-w-md rounded-lg border border-border bg-card p-6 shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-foreground">Enviar para aprovacao</h2>
          <button
            onClick={onClose}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-muted transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {postCaption && (
          <p className="mb-4 text-xs text-muted-foreground line-clamp-2 border-l-2 border-border pl-3 italic">
            {postCaption}
          </p>
        )}

        {!createdToken ? (
          <>
            <div className="mb-4">
              <label className="mb-1 block text-sm font-medium text-foreground">
                Validade do link (dias)
              </label>
              <input
                type="number"
                min={1}
                max={90}
                value={expiresInDays}
                onChange={(e) => setExpiresInDays(Math.max(1, parseInt(e.target.value) || 7))}
                className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </div>
            <div className="flex justify-end gap-3">
              <button
                onClick={onClose}
                className="rounded-md border border-border bg-background px-4 py-2 text-sm text-foreground hover:bg-muted transition-colors"
              >
                Cancelar
              </button>
              <button
                onClick={handleCreate}
                disabled={createApproval.isPending}
                className="inline-flex items-center gap-2 rounded-md bg-primary px-5 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50"
              >
                {createApproval.isPending ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Gerando...
                  </>
                ) : (
                  <>
                    <Send className="h-4 w-4" />
                    Gerar link
                  </>
                )}
              </button>
            </div>
          </>
        ) : (
          <>
            <div className="mb-4 rounded-md bg-muted/50 border border-border p-3">
              <p className="mb-1 text-xs font-medium text-muted-foreground">Link de aprovacao:</p>
              <p className="break-all text-xs text-foreground font-mono">{approveUrl}</p>
            </div>
            <p className="mb-4 text-xs text-muted-foreground">
              Compartilhe este link com o cliente. O post foi movido para{" "}
              <strong>Aguardando aprovacao</strong>.
            </p>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => {
                  if (approveUrl) navigator.clipboard.writeText(approveUrl);
                }}
                className="inline-flex items-center gap-2 rounded-md border border-border bg-background px-4 py-2 text-sm text-foreground hover:bg-muted transition-colors"
              >
                <Link2 className="h-4 w-4" />
                Copiar link
              </button>
              <button
                onClick={onClose}
                className="rounded-md bg-primary px-5 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
              >
                Fechar
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Post dialog (create / edit)
// ---------------------------------------------------------------------------

function PostDialog({
  open,
  editing,
  campaigns,
  onClose,
}: {
  open: boolean;
  editing: Post | null;
  campaigns: Campaign[];
  onClose: () => void;
}) {
  const createMut = useCreatePost();
  const updateMut = useUpdatePost();

  const [form, setForm] = useState<PostCreate>({
    platform: editing?.platform ?? "instagram",
    caption: editing?.caption ?? "",
    hashtags: editing?.hashtags ?? "",
    scheduled_for: editing?.scheduled_for ?? "",
    status: editing?.status ?? "draft",
    campaign_id: editing?.campaign_id ?? "",
    media_url: editing?.media_url ?? "",
  });

  if (!open) return null;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const payload = {
      ...form,
      caption: form.caption || undefined,
      hashtags: form.hashtags || undefined,
      scheduled_for: form.scheduled_for || undefined,
      campaign_id: form.campaign_id || undefined,
      media_url: form.media_url || undefined,
    };
    if (editing) {
      await updateMut.mutateAsync({ id: editing.id, ...payload });
    } else {
      await createMut.mutateAsync(payload);
    }
    onClose();
  }

  const isPending = createMut.isPending || updateMut.isPending;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={onClose}
    >
      <div
        className="w-full max-w-[calc(100vw-2rem)] sm:max-w-lg rounded-lg border border-border bg-card p-6 shadow-lg max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-foreground">
            {editing ? "Editar post" : "Novo post"}
          </h2>
          <button
            onClick={onClose}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-muted transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-sm font-medium text-foreground">Plataforma *</label>
              <select
                value={form.platform}
                onChange={(e) =>
                  setForm((f) => ({ ...f, platform: e.target.value as Platform }))
                }
                className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <option value="instagram">Instagram</option>
                <option value="facebook">Facebook</option>
                <option value="tiktok">TikTok</option>
                <option value="linkedin">LinkedIn</option>
                <option value="twitter">Twitter / X</option>
              </select>
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-foreground">Status</label>
              <select
                value={form.status}
                onChange={(e) =>
                  setForm((f) => ({ ...f, status: e.target.value as PostStatus }))
                }
                className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <option value="draft">Rascunho</option>
                <option value="pending_approval">Aguard. aprovacao</option>
                <option value="approved">Aprovado</option>
                <option value="revision">Em revisao</option>
                <option value="published">Publicado</option>
              </select>
            </div>
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-foreground">Campanha</label>
            <select
              value={form.campaign_id ?? ""}
              onChange={(e) =>
                setForm((f) => ({ ...f, campaign_id: e.target.value || undefined }))
              }
              className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <option value="">— Sem campanha —</option>
              {campaigns.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name} ({c.month})
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-foreground">
              Legenda / Caption
            </label>
            <textarea
              rows={4}
              value={form.caption ?? ""}
              onChange={(e) => setForm((f) => ({ ...f, caption: e.target.value }))}
              placeholder="Escreva a legenda do post..."
              className="flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring resize-none"
            />
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-foreground">Hashtags</label>
            <input
              type="text"
              value={form.hashtags ?? ""}
              onChange={(e) => setForm((f) => ({ ...f, hashtags: e.target.value }))}
              placeholder="#hashtag1 #hashtag2"
              className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-sm font-medium text-foreground">
                Agendamento
              </label>
              <input
                type="datetime-local"
                value={
                  form.scheduled_for
                    ? form.scheduled_for.replace("Z", "").slice(0, 16)
                    : ""
                }
                onChange={(e) =>
                  setForm((f) => ({
                    ...f,
                    scheduled_for: e.target.value ? `${e.target.value}:00Z` : "",
                  }))
                }
                className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-foreground">URL da midia</label>
              <input
                type="url"
                value={form.media_url ?? ""}
                onChange={(e) => setForm((f) => ({ ...f, media_url: e.target.value }))}
                placeholder="https://..."
                className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </div>
          </div>

          <div className="flex justify-end gap-3 pt-1">
            <button
              type="button"
              onClick={onClose}
              className="rounded-md border border-border bg-background px-4 py-2 text-sm text-foreground hover:bg-muted transition-colors"
            >
              Cancelar
            </button>
            <button
              type="submit"
              disabled={isPending}
              className="inline-flex items-center gap-2 rounded-md bg-primary px-5 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isPending ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Salvando...
                </>
              ) : editing ? (
                "Salvar alteracoes"
              ) : (
                "Criar post"
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Pipeline tab — board view grouped by status
// ---------------------------------------------------------------------------

const PIPELINE_COLUMNS: PostStatus[] = [
  "draft",
  "pending_approval",
  "approved",
  "revision",
  "published",
];

function PipelineTab({
  campaigns,
  campaignFilter,
  onEditPost,
}: {
  campaigns: Campaign[];
  campaignFilter?: string;
  onEditPost: (post: Post) => void;
}) {
  const { data, isLoading, error, refetch } = usePosts(
    campaignFilter ? { campaign_id: campaignFilter } : undefined,
  );
  const [approvalPostId, setApprovalPostId] = useState<string | null>(null);
  const approvalPost = approvalPostId
    ? (data?.items ?? []).find((p) => p.id === approvalPostId) ?? null
    : null;

  if (isLoading) return <LoadingState label="Carregando pipeline..." />;
  if (error) return <ErrorState message={error.message} onRetry={() => refetch()} />;

  const posts = data?.items ?? [];
  const grouped = PIPELINE_COLUMNS.reduce<Record<PostStatus, Post[]>>(
    (acc, status) => {
      acc[status] = posts.filter((p) => p.status === status);
      return acc;
    },
    {} as Record<PostStatus, Post[]>,
  );

  const getCampaignName = (id: string | null) => {
    if (!id) return null;
    return campaigns.find((c) => c.id === id)?.name ?? null;
  };

  if (posts.length === 0) {
    return (
      <EmptyState
        label="Nenhum post no pipeline"
      />
    );
  }

  return (
    <>
      <div className="overflow-x-auto pb-4">
        <div className="flex gap-4 min-w-max">
          {PIPELINE_COLUMNS.map((status) => {
            const StatusIcon = POST_STATUS_ICONS[status];
            const colPosts = grouped[status];
            return (
              <div
                key={status}
                className="w-64 flex-shrink-0 rounded-lg border border-border bg-muted/30"
              >
                {/* Column header */}
                <div className="flex items-center justify-between px-3 py-2.5 border-b border-border">
                  <div className="flex items-center gap-2">
                    <StatusIcon className="h-3.5 w-3.5 text-muted-foreground" />
                    <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                      {POST_STATUS_LABELS[status]}
                    </span>
                  </div>
                  <span className="flex items-center justify-center h-5 min-w-[20px] rounded-full bg-muted text-xs font-medium text-muted-foreground px-1.5">
                    {colPosts.length}
                  </span>
                </div>
                {/* Cards */}
                <div className="flex flex-col gap-2 p-2 min-h-[120px]">
                  {colPosts.length === 0 ? (
                    <p className="text-xs text-muted-foreground text-center py-6">Vazio</p>
                  ) : (
                    colPosts.map((post) => {
                      const campaignName = getCampaignName(post.campaign_id);
                      return (
                        <div
                          key={post.id}
                          className="rounded-md border border-border bg-card p-3 shadow-sm hover:shadow-md transition-shadow"
                        >
                          {/* Platform badge */}
                          <span
                            className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium mb-2 ${PLATFORM_COLORS[post.platform]}`}
                          >
                            <PlatformIcon platform={post.platform} />
                            {PLATFORM_LABELS[post.platform]}
                          </span>
                          {/* Caption preview */}
                          {post.caption && (
                            <p className="text-xs text-foreground line-clamp-2 mb-2">
                              {post.caption}
                            </p>
                          )}
                          {/* Campaign */}
                          {campaignName && (
                            <p className="text-xs text-muted-foreground truncate mb-1">
                              <Megaphone className="h-3 w-3 inline mr-1" />
                              {campaignName}
                            </p>
                          )}
                          {/* Scheduled */}
                          {post.scheduled_for && (
                            <p className="text-xs text-muted-foreground mb-2">
                              <Clock className="h-3 w-3 inline mr-1" />
                              {fmtDateTime(post.scheduled_for)}
                            </p>
                          )}
                          {/* Actions */}
                          <div className="flex items-center gap-1 mt-2 border-t border-border pt-2">
                            <button
                              onClick={() => onEditPost(post)}
                              className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
                              title="Editar"
                            >
                              <Pencil className="h-3.5 w-3.5" />
                            </button>
                            {(post.status === "draft" ||
                              post.status === "revision") && (
                              <button
                                onClick={() => setApprovalPostId(post.id)}
                                className="rounded p-1 text-muted-foreground hover:bg-primary/10 hover:text-primary transition-colors"
                                title="Enviar para aprovacao"
                              >
                                <Send className="h-3.5 w-3.5" />
                              </button>
                            )}
                          </div>
                        </div>
                      );
                    })
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {approvalPost && (
        <ApprovalLinkDialog
          postId={approvalPost.id}
          postCaption={approvalPost.caption}
          open={!!approvalPostId}
          onClose={() => setApprovalPostId(null)}
        />
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// Posts tab — flat list with full CRUD
// ---------------------------------------------------------------------------

function PostsTab({
  campaigns,
  campaignFilter,
}: {
  campaigns: Campaign[];
  campaignFilter?: string;
}) {
  const { data, isLoading, error, refetch } = usePosts(
    campaignFilter ? { campaign_id: campaignFilter } : undefined,
  );
  const deleteMut = useDeletePost();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<Post | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<Post | null>(null);
  const [approvalPostId, setApprovalPostId] = useState<string | null>(null);
  const approvalPost = approvalPostId
    ? (data?.items ?? []).find((p) => p.id === approvalPostId) ?? null
    : null;

  if (isLoading) return <LoadingState label="Carregando posts..." />;
  if (error) return <ErrorState message={error.message} onRetry={() => refetch()} />;

  const items = data?.items ?? [];

  const getCampaignName = (id: string | null) => {
    if (!id) return null;
    return campaigns.find((c) => c.id === id)?.name ?? null;
  };

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <button
          onClick={() => {
            setEditing(null);
            setDialogOpen(true);
          }}
          className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
        >
          <Plus className="h-4 w-4" />
          Novo post
        </button>
      </div>

      {items.length === 0 ? (
        <EmptyState
          label="Nenhum post encontrado"
          onAdd={() => {
            setEditing(null);
            setDialogOpen(true);
          }}
        />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-border bg-muted/50">
              <tr>
                <th className="px-4 py-3 font-medium text-muted-foreground">Post</th>
                <th className="px-4 py-3 font-medium text-muted-foreground hidden sm:table-cell">Plataforma</th>
                <th className="px-4 py-3 font-medium text-muted-foreground hidden md:table-cell">Campanha</th>
                <th className="px-4 py-3 font-medium text-muted-foreground hidden lg:table-cell">Agendamento</th>
                <th className="px-4 py-3 font-medium text-muted-foreground">Status</th>
                <th className="px-4 py-3 font-medium text-muted-foreground">Acoes</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {items.map((post) => {
                const StatusIcon = POST_STATUS_ICONS[post.status];
                const campaignName = getCampaignName(post.campaign_id);
                return (
                  <tr key={post.id} className="bg-card hover:bg-muted/20 transition-colors">
                    <td className="px-4 py-3 font-medium text-foreground">
                      <div className="max-w-[240px] truncate">
                        {post.caption || <span className="text-muted-foreground italic">Sem legenda</span>}
                      </div>
                      {post.hashtags && (
                        <div className="text-xs text-muted-foreground truncate max-w-[200px]">
                          {post.hashtags}
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-3 hidden sm:table-cell">
                      <span
                        className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${PLATFORM_COLORS[post.platform]}`}
                      >
                        <PlatformIcon platform={post.platform} />
                        {PLATFORM_LABELS[post.platform]}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-foreground hidden md:table-cell">
                      {campaignName ? (
                        <span className="text-xs">{campaignName}</span>
                      ) : (
                        <span className="text-xs text-muted-foreground">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-foreground hidden lg:table-cell text-xs">
                      {fmtDateTime(post.scheduled_for)}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ${POST_STATUS_COLORS[post.status]}`}
                      >
                        <StatusIcon className="h-3 w-3" />
                        {POST_STATUS_LABELS[post.status]}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1">
                        <button
                          onClick={() => {
                            setEditing(post);
                            setDialogOpen(true);
                          }}
                          className="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
                          title="Editar"
                        >
                          <Pencil className="h-4 w-4" />
                        </button>
                        {(post.status === "draft" || post.status === "revision") && (
                          <button
                            onClick={() => setApprovalPostId(post.id)}
                            className="rounded-md p-1.5 text-muted-foreground hover:bg-primary/10 hover:text-primary transition-colors"
                            title="Enviar para aprovacao"
                          >
                            <Send className="h-4 w-4" />
                          </button>
                        )}
                        <button
                          onClick={() => setConfirmDelete(post)}
                          className="rounded-md p-1.5 text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-colors"
                          title="Remover"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <PostDialog
        open={dialogOpen}
        editing={editing}
        campaigns={campaigns}
        onClose={() => setDialogOpen(false)}
      />

      {approvalPost && (
        <ApprovalLinkDialog
          postId={approvalPost.id}
          postCaption={approvalPost.caption}
          open={!!approvalPostId}
          onClose={() => setApprovalPostId(null)}
        />
      )}

      {confirmDelete && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
          onClick={() => setConfirmDelete(null)}
        >
          <div
            className="w-full max-w-[calc(100vw-2rem)] sm:max-w-md rounded-lg border border-border bg-card p-6 shadow-lg"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="mb-2 text-lg font-semibold text-foreground">Remover post</h2>
            <p className="mb-6 text-sm text-muted-foreground">
              Tem certeza que deseja remover este post? Esta acao nao pode ser desfeita.
            </p>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setConfirmDelete(null)}
                className="rounded-md border border-border bg-background px-4 py-2 text-sm text-foreground hover:bg-muted transition-colors"
              >
                Cancelar
              </button>
              <button
                onClick={() => {
                  deleteMut.mutate(confirmDelete.id, {
                    onSettled: () => setConfirmDelete(null),
                  });
                }}
                disabled={deleteMut.isPending}
                className="inline-flex items-center gap-2 rounded-md bg-destructive px-5 py-2 text-sm font-medium text-destructive-foreground hover:bg-destructive/90 transition-colors disabled:opacity-50"
              >
                {deleteMut.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : null}
                Confirmar remocao
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Campaign dialog (create / edit)
// ---------------------------------------------------------------------------

function CampaignDialog({
  open,
  editing,
  onClose,
}: {
  open: boolean;
  editing: Campaign | null;
  onClose: () => void;
}) {
  const createMut = useCreateCampaign();
  const updateMut = useUpdateCampaign();

  const [form, setForm] = useState<CampaignCreate>({
    name: editing?.name ?? "",
    month: editing?.month ?? new Date().toISOString().slice(0, 7),
    status: editing?.status ?? "active",
  });

  if (!open) return null;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (editing) {
      await updateMut.mutateAsync({ id: editing.id, ...form });
    } else {
      await createMut.mutateAsync(form);
    }
    onClose();
  }

  const isPending = createMut.isPending || updateMut.isPending;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={onClose}
    >
      <div
        className="w-full max-w-[calc(100vw-2rem)] sm:max-w-md rounded-lg border border-border bg-card p-6 shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-foreground">
            {editing ? "Editar campanha" : "Nova campanha"}
          </h2>
          <button
            onClick={onClose}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-muted transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium text-foreground">Nome *</label>
            <input
              type="text"
              required
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              placeholder="Ex: Campanha Junho 2026"
              className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-sm font-medium text-foreground">Mes *</label>
              <input
                type="month"
                required
                value={form.month}
                onChange={(e) => setForm((f) => ({ ...f, month: e.target.value }))}
                className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-foreground">Status</label>
              <select
                value={form.status}
                onChange={(e) =>
                  setForm((f) => ({ ...f, status: e.target.value as CampaignStatus }))
                }
                className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <option value="active">Ativa</option>
                <option value="paused">Pausada</option>
                <option value="completed">Concluida</option>
                <option value="archived">Arquivada</option>
              </select>
            </div>
          </div>
          <div className="flex justify-end gap-3 pt-1">
            <button
              type="button"
              onClick={onClose}
              className="rounded-md border border-border bg-background px-4 py-2 text-sm text-foreground hover:bg-muted transition-colors"
            >
              Cancelar
            </button>
            <button
              type="submit"
              disabled={isPending}
              className="inline-flex items-center gap-2 rounded-md bg-primary px-5 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isPending ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Salvando...
                </>
              ) : editing ? (
                "Salvar alteracoes"
              ) : (
                "Criar campanha"
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Campaigns tab
// ---------------------------------------------------------------------------

function CampanhasTab({
  onSelectCampaign,
}: {
  onSelectCampaign: (id: string | undefined) => void;
}) {
  const { data, isLoading, error, refetch } = useCampaigns();
  const deleteMut = useDeleteCampaign();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<Campaign | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<Campaign | null>(null);
  const [activeCampaignId, setActiveCampaignId] = useState<string | undefined>(undefined);

  if (isLoading) return <LoadingState label="Carregando campanhas..." />;
  if (error) return <ErrorState message={error.message} onRetry={() => refetch()} />;

  const items = data?.items ?? [];

  function handleSelectToggle(id: string) {
    const next = activeCampaignId === id ? undefined : id;
    setActiveCampaignId(next);
    onSelectCampaign(next);
  }

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <button
          onClick={() => {
            setEditing(null);
            setDialogOpen(true);
          }}
          className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
        >
          <Plus className="h-4 w-4" />
          Nova campanha
        </button>
      </div>

      {items.length === 0 ? (
        <EmptyState
          label="Nenhuma campanha encontrada"
          onAdd={() => {
            setEditing(null);
            setDialogOpen(true);
          }}
        />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-border bg-muted/50">
              <tr>
                <th className="px-4 py-3 font-medium text-muted-foreground">Nome</th>
                <th className="px-4 py-3 font-medium text-muted-foreground hidden sm:table-cell">Mes</th>
                <th className="px-4 py-3 font-medium text-muted-foreground">Status</th>
                <th className="px-4 py-3 font-medium text-muted-foreground">Acoes</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {items.map((campaign) => (
                <tr
                  key={campaign.id}
                  className={`transition-colors ${
                    activeCampaignId === campaign.id
                      ? "bg-primary/5 dark:bg-primary/10"
                      : "bg-card hover:bg-muted/20"
                  }`}
                >
                  <td className="px-4 py-3 font-medium text-foreground">
                    <button
                      onClick={() => handleSelectToggle(campaign.id)}
                      className="text-left hover:underline"
                    >
                      {campaign.name}
                    </button>
                    {activeCampaignId === campaign.id && (
                      <span className="ml-2 text-xs text-primary font-normal">
                        (filtro ativo)
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-foreground hidden sm:table-cell text-xs">
                    {campaign.month}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${CAMPAIGN_STATUS_COLORS[campaign.status]}`}
                    >
                      {CAMPAIGN_STATUS_LABELS[campaign.status]}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => {
                          setEditing(campaign);
                          setDialogOpen(true);
                        }}
                        className="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
                        title="Editar"
                      >
                        <Pencil className="h-4 w-4" />
                      </button>
                      <button
                        onClick={() => setConfirmDelete(campaign)}
                        className="rounded-md p-1.5 text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-colors"
                        title="Remover"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <CampaignDialog
        open={dialogOpen}
        editing={editing}
        onClose={() => setDialogOpen(false)}
      />

      {confirmDelete && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
          onClick={() => setConfirmDelete(null)}
        >
          <div
            className="w-full max-w-[calc(100vw-2rem)] sm:max-w-md rounded-lg border border-border bg-card p-6 shadow-lg"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="mb-2 text-lg font-semibold text-foreground">Remover campanha</h2>
            <p className="mb-6 text-sm text-muted-foreground">
              Tem certeza que deseja remover a campanha{" "}
              <strong className="text-foreground">{confirmDelete.name}</strong>? Esta acao nao pode ser desfeita.
            </p>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setConfirmDelete(null)}
                className="rounded-md border border-border bg-background px-4 py-2 text-sm text-foreground hover:bg-muted transition-colors"
              >
                Cancelar
              </button>
              <button
                onClick={() => {
                  deleteMut.mutate(confirmDelete.id, {
                    onSettled: () => setConfirmDelete(null),
                  });
                }}
                disabled={deleteMut.isPending}
                className="inline-flex items-center gap-2 rounded-md bg-destructive px-5 py-2 text-sm font-medium text-destructive-foreground hover:bg-destructive/90 transition-colors disabled:opacity-50"
              >
                {deleteMut.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : null}
                Confirmar remocao
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

const TABS: { key: TabKey; label: string; icon: React.ElementType }[] = [
  { key: "pipeline", label: "Pipeline", icon: LayoutGrid },
  { key: "posts", label: "Posts", icon: List },
  { key: "campanhas", label: "Campanhas", icon: Megaphone },
];

export default function Conteudo() {
  const [activeTab, setActiveTab] = useState<TabKey>("pipeline");
  const [campaignFilter, setCampaignFilter] = useState<string | undefined>(undefined);
  const [editingPost, setEditingPost] = useState<Post | null>(null);
  const [postDialogOpen, setPostDialogOpen] = useState(false);

  // Campaigns data is shared across tabs for campaign name resolution
  const { data: campaignsData } = useCampaigns();
  const campaigns = campaignsData?.items ?? [];

  function handleEditPost(post: Post) {
    setEditingPost(post);
    setPostDialogOpen(true);
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <Megaphone className="h-6 w-6 text-primary" />
          <div>
            <h1 className="text-2xl font-bold text-foreground">Conteudo</h1>
            <p className="text-sm text-muted-foreground">
              Studio de conteudo social — posts, campanhas e aprovacoes
            </p>
          </div>
        </div>
        {campaignFilter && (
          <div className="flex items-center gap-2 rounded-md bg-primary/10 border border-primary/20 px-3 py-1.5">
            <span className="text-xs text-primary font-medium">
              Filtrando por campanha
            </span>
            <button
              onClick={() => setCampaignFilter(undefined)}
              className="rounded p-0.5 text-primary hover:bg-primary/20 transition-colors"
              title="Remover filtro"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        )}
      </div>

      {/* Tabs */}
      <div className="border-b border-border">
        <nav className="flex gap-0 -mb-px">
          {TABS.map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              onClick={() => setActiveTab(key)}
              className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
                activeTab === key
                  ? "border-primary text-primary"
                  : "border-transparent text-muted-foreground hover:text-foreground hover:border-border"
              }`}
            >
              <Icon className="h-4 w-4" />
              <span className="hidden sm:inline">{label}</span>
            </button>
          ))}
        </nav>
      </div>

      {/* Tab content */}
      <div>
        {activeTab === "pipeline" && (
          <PipelineTab
            campaigns={campaigns}
            campaignFilter={campaignFilter}
            onEditPost={handleEditPost}
          />
        )}
        {activeTab === "posts" && (
          <PostsTab
            campaigns={campaigns}
            campaignFilter={campaignFilter}
          />
        )}
        {activeTab === "campanhas" && (
          <CampanhasTab onSelectCampaign={setCampaignFilter} />
        )}
      </div>

      {/* Post edit dialog (opened from Pipeline tab) */}
      <PostDialog
        open={postDialogOpen}
        editing={editingPost}
        campaigns={campaigns}
        onClose={() => {
          setPostDialogOpen(false);
          setEditingPost(null);
        }}
      />
    </div>
  );
}

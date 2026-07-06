/**
 * FbComentarios — Facebook "Comentários" subtab: pick a post, moderate its
 * comments (reply/hide/delete). Mirrors `IgComentarios.tsx` structurally —
 * kept as a separate file (per-network subtab convention, contract §3B)
 * rather than parameterizing one component, since the underlying hooks
 * (useFbPosts vs useIgMedia) and DTOs already diverge.
 */
import { useEffect, useState } from "react";
import { CircleAlert, EyeOff, Loader2, Send, Trash2 } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

import {
  isAppReviewGate,
  useActiveMetaAccountId,
  useFbComments,
  useFbDeleteComment,
  useFbHideComment,
  useFbPosts,
  useFbReplyComment,
} from "@/hooks/useMeta";
import { AppReviewNotice } from "./AppReviewNotice";
import {
  FbContextError,
  FbContextLoading,
  FbNoPages,
  FbPageSelect,
  useFbPages,
} from "./FbPageSelect";

function CommentsList({ accountId, postId }: { accountId: string; postId: string }) {
  const { data, isLoading, isError } = useFbComments(accountId, postId);
  const reply = useFbReplyComment(accountId, postId);
  const hide = useFbHideComment(accountId, postId);
  const del = useFbDeleteComment(accountId, postId);
  const [replyText, setReplyText] = useState("");

  const gate =
    (reply.data && isAppReviewGate(reply.data) && reply.data) ||
    (hide.data && isAppReviewGate(hide.data) && hide.data) ||
    (del.data && isAppReviewGate(del.data) && del.data) ||
    null;

  if (isLoading) {
    return (
      <div className="space-y-2" data-testid="fb-comments-loading">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-12 w-full rounded-md" />
        ))}
      </div>
    );
  }

  if (isError) {
    return (
      <div className="rounded-md border border-dashed p-6 text-center text-sm text-destructive" data-testid="fb-comments-error">
        Erro ao carregar comentários.
      </div>
    );
  }

  const comments = data?.comments ?? [];

  return (
    <div className="space-y-4">
      {gate && <AppReviewNotice error={gate.error} />}

      {comments.length === 0 ? (
        <div className="rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground" data-testid="fb-comments-empty">
          Nenhum comentário nesta publicação.
        </div>
      ) : (
        <ul className="space-y-2" data-testid="fb-comments-list">
          {comments.map((c) => (
            <li key={c.id} className="flex items-start justify-between gap-3 rounded-md border p-3 text-sm">
              <div>
                <div className="font-medium">{c.from_username ?? "Usuário"}</div>
                <div className={c.hidden ? "text-muted-foreground line-through" : ""}>{c.text}</div>
              </div>
              <div className="flex shrink-0 gap-1">
                <Button
                  variant="ghost"
                  size="sm"
                  data-testid={`fb-comment-hide-${c.id}`}
                  onClick={() => hide.mutate({ commentId: c.id, hide: !c.hidden })}
                  disabled={hide.isPending}
                >
                  <EyeOff className="h-4 w-4" />
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  data-testid={`fb-comment-delete-${c.id}`}
                  onClick={() => del.mutate(c.id)}
                  disabled={del.isPending}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}

      <form
        className="flex gap-2"
        data-testid="fb-comment-reply-form"
        onSubmit={(e) => {
          e.preventDefault();
          if (!replyText.trim()) return;
          reply.mutate(
            { message: replyText },
            { onSuccess: (res) => !isAppReviewGate(res) && setReplyText("") },
          );
        }}
      >
        <Input
          value={replyText}
          onChange={(e) => setReplyText(e.target.value)}
          placeholder="Responder..."
          data-testid="fb-comment-reply-input"
        />
        <Button type="submit" disabled={reply.isPending} data-testid="fb-comment-reply-submit">
          {reply.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
        </Button>
      </form>
    </div>
  );
}

export default function FbComentarios() {
  const accountId = useActiveMetaAccountId();
  const { data: context, isLoading: contextLoading, isError: contextError } = useFbPages(accountId);
  const [pageId, setPageId] = useState<string | null>(null);

  const pages = context?.pages ?? [];
  const resolvedPageId = pageId ?? (pages[0]?.id ?? null);

  const { data: postsData, isLoading: postsLoading, isError: postsError } = useFbPosts(
    accountId,
    resolvedPageId,
  );
  const posts = postsData?.posts ?? [];
  const [selectedPostId, setSelectedPostId] = useState<string | null>(null);

  useEffect(() => {
    if (!selectedPostId && posts.length > 0) {
      setSelectedPostId(posts[0].id);
    }
  }, [posts, selectedPostId]);

  if (!accountId) {
    return (
      <Card>
        <CardContent className="p-6 text-center text-sm text-muted-foreground" data-testid="fb-comments-no-account">
          Selecione uma conta conectada acima para moderar comentários.
        </CardContent>
      </Card>
    );
  }

  if (contextLoading) return <FbContextLoading />;
  if (contextError) return <FbContextError />;
  if (pages.length === 0) return <FbNoPages />;

  return (
    <Card>
      <CardHeader className="space-y-3">
        <CardTitle>Comentários por publicação</CardTitle>
        <FbPageSelect accountId={accountId} pages={pages} selectedId={pageId} onSelect={setPageId} />
        {postsLoading ? (
          <Skeleton className="h-10 w-64" />
        ) : postsError ? (
          <div className="flex items-center gap-2 text-sm text-destructive">
            <CircleAlert className="h-4 w-4" /> Erro ao carregar publicações.
          </div>
        ) : posts.length === 0 ? (
          <div className="text-sm text-muted-foreground" data-testid="fb-comments-no-posts">
            Nenhuma publicação disponível para moderar comentários.
          </div>
        ) : (
          <Select value={selectedPostId ?? undefined} onValueChange={setSelectedPostId}>
            <SelectTrigger className="w-full max-w-md" data-testid="fb-comments-post-select">
              <SelectValue placeholder="Selecione uma publicação" />
            </SelectTrigger>
            <SelectContent>
              {posts.map((p) => (
                <SelectItem key={p.id} value={p.id}>
                  {p.message ? p.message.slice(0, 60) : `Publicação ${p.id}`}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
      </CardHeader>
      <CardContent>
        {selectedPostId && <CommentsList accountId={accountId} postId={selectedPostId} />}
      </CardContent>
    </Card>
  );
}

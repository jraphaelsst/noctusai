/**
 * IgComentarios — Instagram "Comentários" subtab: pick a media item, list its
 * comments, reply / hide / delete each. Every write (reply/hide/delete) can
 * come back App-Review-gated — rendered via the shared `AppReviewNotice`.
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
  useIgComments,
  useIgDeleteComment,
  useIgHideComment,
  useIgMedia,
  useIgReplyComment,
} from "@/hooks/useMeta";
import { AppReviewNotice } from "./AppReviewNotice";

function CommentsList({
  accountId,
  mediaId,
}: {
  accountId: string;
  mediaId: string;
}) {
  // `isPending`, not `isLoading` — v5's `isLoading` goes FALSE mid-refetch
  // and would unmount this comment list on every background refresh.
  // No `placeholderData` — `mediaId` is part of the key, and reusing a
  // different post's comments while switching posts would show them
  // under the wrong post. → KB § PATTERNS/frontend/lying-loading-state.md
  const { data, isPending, isError } = useIgComments(accountId, mediaId);
  const reply = useIgReplyComment(accountId, mediaId);
  const hide = useIgHideComment(accountId, mediaId);
  const del = useIgDeleteComment(accountId, mediaId);
  const [replyText, setReplyText] = useState("");

  const gate =
    (reply.data && isAppReviewGate(reply.data) && reply.data) ||
    (hide.data && isAppReviewGate(hide.data) && hide.data) ||
    (del.data && isAppReviewGate(del.data) && del.data) ||
    null;

  if (isPending) {
    return (
      <div className="space-y-2" data-testid="ig-comments-loading">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-12 w-full rounded-md" />
        ))}
      </div>
    );
  }

  if (isError) {
    return (
      <div
        className="rounded-md border border-dashed p-6 text-center text-sm text-destructive"
        data-testid="ig-comments-error"
      >
        Erro ao carregar comentários.
      </div>
    );
  }

  const comments = data?.comments ?? [];

  return (
    <div className="space-y-4">
      {gate && <AppReviewNotice error={gate.error} />}

      {comments.length === 0 ? (
        <div
          className="rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground"
          data-testid="ig-comments-empty"
        >
          Nenhum comentário neste post.
        </div>
      ) : (
        <ul className="space-y-2" data-testid="ig-comments-list">
          {comments.map((c) => (
            <li
              key={c.id}
              className="flex items-start justify-between gap-3 rounded-md border p-3 text-sm"
            >
              <div>
                <div className="font-medium">{c.from_username ?? "Usuário"}</div>
                <div className={c.hidden ? "text-muted-foreground line-through" : ""}>
                  {c.text}
                </div>
              </div>
              <div className="flex shrink-0 gap-1">
                <Button
                  variant="ghost"
                  size="sm"
                  data-testid={`ig-comment-hide-${c.id}`}
                  onClick={() => hide.mutate({ commentId: c.id, hide: !c.hidden })}
                  disabled={hide.isPending}
                >
                  <EyeOff className="h-4 w-4" />
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  data-testid={`ig-comment-delete-${c.id}`}
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
        data-testid="ig-comment-reply-form"
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
          data-testid="ig-comment-reply-input"
        />
        <Button type="submit" disabled={reply.isPending} data-testid="ig-comment-reply-submit">
          {reply.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
        </Button>
      </form>
    </div>
  );
}

export default function IgComentarios() {
  const accountId = useActiveMetaAccountId();
  // `isPending`, not `isLoading` — same rule, media-list fetch.
  const { data, isPending, isError } = useIgMedia(accountId, 25);
  const media = data?.media ?? [];
  const [selectedMediaId, setSelectedMediaId] = useState<string | null>(null);

  useEffect(() => {
    if (!selectedMediaId && media.length > 0) {
      setSelectedMediaId(media[0].id);
    }
  }, [media, selectedMediaId]);

  if (!accountId) {
    return (
      <Card>
        <CardContent
          className="p-6 text-center text-sm text-muted-foreground"
          data-testid="ig-comments-no-account"
        >
          Selecione uma conta conectada acima para moderar comentários.
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="space-y-3">
        <CardTitle>Comentários por post</CardTitle>
        {isPending ? (
          <Skeleton className="h-10 w-64" />
        ) : isError ? (
          <div className="flex items-center gap-2 text-sm text-destructive">
            <CircleAlert className="h-4 w-4" /> Erro ao carregar posts.
          </div>
        ) : media.length === 0 ? (
          <div className="text-sm text-muted-foreground" data-testid="ig-comments-no-media">
            Nenhum post disponível para moderar comentários.
          </div>
        ) : (
          <Select value={selectedMediaId ?? undefined} onValueChange={setSelectedMediaId}>
            <SelectTrigger className="w-full max-w-md" data-testid="ig-comments-media-select">
              <SelectValue placeholder="Selecione um post" />
            </SelectTrigger>
            <SelectContent>
              {media.map((m) => (
                <SelectItem key={m.id} value={m.id}>
                  {m.caption ? m.caption.slice(0, 60) : `Post ${m.id}`}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
      </CardHeader>
      <CardContent>
        {selectedMediaId && (
          <CommentsList accountId={accountId} mediaId={selectedMediaId} />
        )}
      </CardContent>
    </Card>
  );
}

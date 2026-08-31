/**
 * FbConteudo — Facebook "Conteúdo" subtab: publish post/photo/video +
 * a recent-posts list.
 *
 * BE-contract note: the Wave 3 contract text specifies FB publish + FB
 * insights + FB comments-by-post but not an explicit posts-LIST endpoint.
 * `useFbPosts` (hooks/useMeta.ts) assumes `GET /api/meta/facebook/posts` —
 * flagged for backend-engineer reconciliation in the delivery note.
 */
import { useState } from "react";
import { CircleAlert, CircleCheck, Loader2, Send } from "lucide-react";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
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
  useFbPosts,
  useFbPublish,
  type FbPublishKind,
} from "@/hooks/useMeta";
import { AppReviewNotice } from "./AppReviewNotice";
import {
  FbContextError,
  FbContextLoading,
  FbNoPages,
  FbPageSelect,
  useFbPages,
} from "./FbPageSelect";

const KIND_LABEL: Record<FbPublishKind, string> = {
  post: "Texto",
  photo: "Foto",
  video: "Vídeo",
};

function PublishForm({ accountId, pageId }: { accountId: string; pageId: string }) {
  const [kind, setKind] = useState<FbPublishKind>("post");
  const [message, setMessage] = useState("");
  const [mediaUrl, setMediaUrl] = useState("");
  const publish = useFbPublish(accountId);

  const gated = publish.data && isAppReviewGate(publish.data) ? publish.data : null;
  const succeeded = publish.data && !isAppReviewGate(publish.data) ? publish.data : null;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Publicar no Facebook</CardTitle>
        <CardDescription>Texto, foto ou vídeo na página selecionada.</CardDescription>
      </CardHeader>
      <CardContent>
        <form
          className="space-y-4"
          data-testid="fb-publish-form"
          onSubmit={(e) => {
            e.preventDefault();
            publish.mutate(
              { kind, page_id: pageId, message: message || undefined, media_url: mediaUrl || undefined },
              {
                onSuccess: (res) => {
                  if (!isAppReviewGate(res)) {
                    setMessage("");
                    setMediaUrl("");
                  }
                },
              },
            );
          }}
        >
          <div className="space-y-1.5">
            <Label htmlFor="fb-publish-kind">Tipo</Label>
            <Select value={kind} onValueChange={(v) => setKind(v as FbPublishKind)}>
              <SelectTrigger id="fb-publish-kind" data-testid="fb-publish-kind">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {(Object.keys(KIND_LABEL) as FbPublishKind[]).map((k) => (
                  <SelectItem key={k} value={k}>
                    {KIND_LABEL[k]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {kind !== "post" && (
            <div className="space-y-1.5">
              <Label htmlFor="fb-publish-media">URL da mídia</Label>
              <Input
                id="fb-publish-media"
                data-testid="fb-publish-media"
                value={mediaUrl}
                onChange={(e) => setMediaUrl(e.target.value)}
                placeholder="https://..."
                required
              />
            </div>
          )}

          <div className="space-y-1.5">
            <Label htmlFor="fb-publish-message">Texto</Label>
            <Textarea
              id="fb-publish-message"
              data-testid="fb-publish-message"
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              placeholder="Escreva a publicação..."
              required={kind === "post"}
            />
          </div>

          {publish.isError && (
            <div className="flex items-center gap-2 text-sm text-destructive" data-testid="fb-publish-error">
              <CircleAlert className="h-4 w-4 shrink-0" />
              Erro ao publicar. Tente novamente.
            </div>
          )}

          {gated && <AppReviewNotice error={gated.error} />}

          {succeeded && (
            <div className="flex items-center gap-2 text-sm text-emerald-600" data-testid="fb-publish-success">
              <CircleCheck className="h-4 w-4 shrink-0" />
              Publicado com sucesso.
            </div>
          )}

          <Button type="submit" disabled={publish.isPending} data-testid="fb-publish-submit">
            {publish.isPending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Send className="mr-2 h-4 w-4" />
            )}
            Publicar
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

function PostsList({ accountId, pageId }: { accountId: string; pageId: string }) {
  // `isPending`, not `isLoading` — v5's `isLoading` goes FALSE mid-refetch
  // and would unmount this posts list on every background refresh.
  // → KB § PATTERNS/frontend/lying-loading-state.md
  const { data, isPending, isError } = useFbPosts(accountId, pageId);
  const posts = data?.posts ?? [];

  if (isPending) {
    return (
      <div className="space-y-2" data-testid="fb-posts-loading">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-16 w-full rounded-md" />
        ))}
      </div>
    );
  }

  if (isError) {
    return (
      <div className="rounded-md border border-dashed p-6 text-center text-sm text-destructive" data-testid="fb-posts-error">
        Erro ao carregar publicações.
      </div>
    );
  }

  if (posts.length === 0) {
    return (
      <div className="rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground" data-testid="fb-posts-empty">
        Nenhuma publicação encontrada para esta página.
      </div>
    );
  }

  return (
    <ul className="space-y-2" data-testid="fb-posts-list">
      {posts.map((p) => (
        <li key={p.id} className="rounded-md border p-3 text-sm">
          <div className="line-clamp-2">{p.message ?? "(sem texto)"}</div>
          <div className="mt-1 text-xs text-muted-foreground">
            {p.created_time ? new Date(p.created_time).toLocaleDateString("pt-BR") : "—"}
            {" · "}
            {p.likes_count ?? 0} curtidas · {p.comments_count ?? 0} comentários
          </div>
        </li>
      ))}
    </ul>
  );
}

export default function FbConteudo() {
  const accountId = useActiveMetaAccountId();
  // `isPending`, not `isLoading` — same rule, page-context fetch.
  const { data: context, isPending, isError } = useFbPages(accountId);
  const [pageId, setPageId] = useState<string | null>(null);

  if (!accountId) {
    return (
      <Card>
        <CardContent className="p-6 text-center text-sm text-muted-foreground" data-testid="fb-content-no-account">
          Selecione uma conta conectada acima para publicar conteúdo no Facebook.
        </CardContent>
      </Card>
    );
  }

  if (isPending) return <FbContextLoading />;
  if (isError) return <FbContextError />;

  const pages = context?.pages ?? [];
  if (pages.length === 0) return <FbNoPages />;

  const resolvedPageId = pageId ?? pages[0].id;

  return (
    <div className="space-y-6">
      <FbPageSelect accountId={accountId} pages={pages} selectedId={pageId} onSelect={setPageId} />
      <PublishForm accountId={accountId} pageId={resolvedPageId} />
      <Card>
        <CardHeader>
          <CardTitle>Publicações recentes</CardTitle>
        </CardHeader>
        <CardContent>
          <PostsList accountId={accountId} pageId={resolvedPageId} />
        </CardContent>
      </Card>
    </div>
  );
}

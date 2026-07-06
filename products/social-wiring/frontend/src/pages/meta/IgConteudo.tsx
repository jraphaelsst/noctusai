/**
 * IgConteudo — Instagram "Conteúdo" subtab: publish form (media / carousel /
 * reel / story, discriminated by `kind`) + a media grid of recent posts.
 *
 * Publish states: idle → publishing (loading) → success (toast-less inline
 * confirmation + form reset) → error (inline) → App Review gate
 * (`AppReviewNotice`, never a fake success).
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
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
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
  useIgMedia,
  useIgPublish,
  type IGPublishKind,
} from "@/hooks/useMeta";
import { AppReviewNotice } from "./AppReviewNotice";

const KIND_LABEL: Record<IGPublishKind, string> = {
  media: "Foto/vídeo único",
  carousel: "Carrossel",
  reel: "Reel",
  story: "Story",
};

function PublishForm({ accountId }: { accountId: string }) {
  const [kind, setKind] = useState<IGPublishKind>("media");
  const [mediaUrls, setMediaUrls] = useState("");
  const [caption, setCaption] = useState("");
  const publish = useIgPublish(accountId);

  const gated = publish.data && isAppReviewGate(publish.data) ? publish.data : null;
  const succeeded = publish.data && !isAppReviewGate(publish.data) ? publish.data : null;

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const urls = mediaUrls
      .split("\n")
      .map((u) => u.trim())
      .filter(Boolean);
    publish.mutate(
      { kind, media_urls: urls, caption: caption || undefined },
      {
        onSuccess: (res) => {
          if (!isAppReviewGate(res)) {
            setMediaUrls("");
            setCaption("");
          }
        },
      },
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Publicar no Instagram</CardTitle>
        <CardDescription>
          Informe a URL da mídia (uma por linha para carrossel) e a legenda.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form className="space-y-4" onSubmit={handleSubmit} data-testid="ig-publish-form">
          <div className="space-y-1.5">
            <Label htmlFor="ig-publish-kind">Tipo</Label>
            <Select value={kind} onValueChange={(v) => setKind(v as IGPublishKind)}>
              <SelectTrigger id="ig-publish-kind" data-testid="ig-publish-kind">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {(Object.keys(KIND_LABEL) as IGPublishKind[]).map((k) => (
                  <SelectItem key={k} value={k}>
                    {KIND_LABEL[k]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="ig-publish-urls">
              {kind === "carousel" ? "URLs da mídia (uma por linha)" : "URL da mídia"}
            </Label>
            <Textarea
              id="ig-publish-urls"
              data-testid="ig-publish-urls"
              value={mediaUrls}
              onChange={(e) => setMediaUrls(e.target.value)}
              placeholder="https://..."
              required
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="ig-publish-caption">Legenda</Label>
            <Textarea
              id="ig-publish-caption"
              data-testid="ig-publish-caption"
              value={caption}
              onChange={(e) => setCaption(e.target.value)}
              placeholder="Escreva a legenda (opcional)"
            />
          </div>

          {publish.isError && (
            <div
              className="flex items-center gap-2 text-sm text-destructive"
              data-testid="ig-publish-error"
            >
              <CircleAlert className="h-4 w-4 shrink-0" />
              Erro ao publicar. Tente novamente.
            </div>
          )}

          {gated && <AppReviewNotice error={gated.error} />}

          {succeeded && (
            <div
              className="flex items-center gap-2 text-sm text-emerald-600"
              data-testid="ig-publish-success"
            >
              <CircleCheck className="h-4 w-4 shrink-0" />
              Publicado com sucesso.
            </div>
          )}

          <Button type="submit" disabled={publish.isPending} data-testid="ig-publish-submit">
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

function MediaGrid({ accountId }: { accountId: string }) {
  const { data, isLoading, isError } = useIgMedia(accountId, 24);
  const media = data?.media ?? [];

  if (isLoading) {
    return (
      <div
        className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4"
        data-testid="ig-content-grid-loading"
      >
        {Array.from({ length: 8 }).map((_, i) => (
          <Skeleton key={i} className="aspect-square rounded-md" />
        ))}
      </div>
    );
  }

  if (isError) {
    return (
      <div
        className="rounded-md border border-dashed p-6 text-center text-sm text-destructive"
        data-testid="ig-content-grid-error"
      >
        Erro ao carregar mídias.
      </div>
    );
  }

  if (media.length === 0) {
    return (
      <div
        className="rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground"
        data-testid="ig-content-grid-empty"
      >
        Nenhuma mídia publicada ainda.
      </div>
    );
  }

  return (
    <div
      className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4"
      data-testid="ig-content-grid"
    >
      {media.map((item) => (
        <a
          key={item.id}
          href={item.permalink ?? undefined}
          target="_blank"
          rel="noreferrer"
          className="group relative block aspect-square overflow-hidden rounded-md border bg-muted"
        >
          {item.thumbnail_url ? (
            <img
              src={item.thumbnail_url}
              alt={item.caption ?? "Post do Instagram"}
              className="h-full w-full object-cover transition-opacity group-hover:opacity-80"
            />
          ) : (
            <div className="flex h-full w-full items-center justify-center text-xs text-muted-foreground">
              Sem miniatura
            </div>
          )}
        </a>
      ))}
    </div>
  );
}

export default function IgConteudo() {
  const accountId = useActiveMetaAccountId();

  if (!accountId) {
    return (
      <Card>
        <CardContent
          className="p-6 text-center text-sm text-muted-foreground"
          data-testid="ig-content-no-account"
        >
          Selecione uma conta conectada acima para publicar conteúdo.
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      <PublishForm accountId={accountId} />
      <Card>
        <CardHeader>
          <CardTitle>Mídias recentes</CardTitle>
        </CardHeader>
        <CardContent>
          <MediaGrid accountId={accountId} />
        </CardContent>
      </Card>
    </div>
  );
}

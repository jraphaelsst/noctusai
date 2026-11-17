/**
 * ImovelPostInstagramCard — "Post do Instagram": the posts/reels that advertise this imóvel. A lead who pastes one of these
 * links to Julia gets this listing. List / add / remove; admin-only writes are enforced by the API (its refusal is shown).
 */
import { useState } from "react";
import { Loader2, Trash2 } from "lucide-react";

import { Instagram } from "@noctusai/lib/brand-icons";
import { QueryErrorState } from "@noctusai/lib/components";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useImovelPostInstagramMutations, useImovelPostsInstagram } from "@/hooks/useImovelPostsInstagram";

export function ImovelPostInstagramCard({ codigo }: { codigo: string }) {
  const query = useImovelPostsInstagram(codigo);
  const { adicionar, remover } = useImovelPostInstagramMutations(codigo);
  const [url, setUrl] = useState("");
  const itens = query.data ?? [];
  const showSkeleton = query.isPending && !query.data;

  return (
    <Card data-testid="imovel-post-instagram">
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <Instagram className="h-4 w-4" />
          Post do Instagram
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-xs text-muted-foreground">
          Posts e reels que anunciam este imóvel. Quando um lead enviar o link do post para a Julia, ela mostra este imóvel.
        </p>
        <form
          className="space-y-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (!url.trim()) return;
            adicionar.mutate({ url: url.trim() }, { onSuccess: () => setUrl("") });
          }}
        >
          <Input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://www.instagram.com/reel/..."
            disabled={adicionar.isPending}
            aria-label="Link do post do Instagram"
            data-testid="imovel-post-instagram-url"
          />
          {adicionar.error && (
            <p className="text-sm text-destructive" role="alert" data-testid="imovel-post-instagram-add-erro">
              {adicionar.error.message}
            </p>
          )}
          <Button type="submit" size="sm" disabled={adicionar.isPending || !url.trim()} data-testid="imovel-post-instagram-adicionar">
            {adicionar.isPending && <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />}
            Adicionar post
          </Button>
        </form>

        {showSkeleton ? (
          <div data-testid="imovel-post-instagram-skeleton">
            <Skeleton className="h-10 w-full" />
          </div>
        ) : query.isError && !query.data ? (
          <QueryErrorState
            query={query}
            variant="inline"
            title="Não foi possível carregar os posts do Instagram."
            data-testid="imovel-post-instagram-erro"
          />
        ) : itens.length === 0 ? (
          <p className="text-sm text-muted-foreground" data-testid="imovel-post-instagram-vazio">
            Nenhum post vinculado a este imóvel.
          </p>
        ) : (
          <ul className="divide-y [&>li]:py-2" data-testid="imovel-post-instagram-lista">
            {itens.map((p) => (
              <li key={p.id} className="flex items-center justify-between gap-2" data-testid="imovel-post-instagram-item">
                <a
                  href={p.permalink ?? `https://www.instagram.com/p/${p.shortcode}/`}
                  target="_blank"
                  rel="noreferrer"
                  className="truncate text-sm underline"
                >
                  {p.shortcode}
                </a>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  aria-label={`Remover post ${p.shortcode}`}
                  data-testid="imovel-post-instagram-remover"
                  disabled={remover.isPending}
                  onClick={() => remover.mutate({ id: p.id })}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </li>
            ))}
          </ul>
        )}
        {remover.error && (
          <p className="text-sm text-destructive" role="alert" data-testid="imovel-post-instagram-remover-erro">
            {remover.error.message}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

/**
 * InstagramPostGrid — newest → oldest post grid with "Carregar mais" cursor
 * pagination; a card opens the insights modal (never a new tab).
 *
 * States: skeleton (isPending && !data) · error · empty (before first sync) ·
 * success. A background refetch keeps the grid mounted and shows a quiet
 * "Atualizando…" (isFetching && !!data, never an early return).
 */
import { useMemo, useState } from "react";
import { CircleAlert, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useInstagramMedia,
  type InstagramMediaItem,
} from "@/hooks/useInstagramInsights";
import { InstagramPostCard } from "./InstagramPostCard";
import { InstagramPostInsightsModal } from "./InstagramPostInsightsModal";

export function InstagramPostGrid({ accountId }: { accountId: string }) {
  const q = useInstagramMedia(accountId, 24);
  const [selected, setSelected] = useState<InstagramMediaItem | null>(null);
  const items = useMemo(() => q.data?.pages.flatMap((p) => p.items) ?? [], [q.data]);

  const showSkeleton = q.isPending && !q.data;
  const isRefreshing = q.isFetching && !!q.data && !q.isFetchingNextPage;
  const showError = q.isError && !q.data;

  let body;
  if (showSkeleton) {
    body = (
      <div data-testid="ig-grid-loading" className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
        {Array.from({ length: 8 }).map((_, i) => (
          <Skeleton key={i} className="aspect-[3/4] rounded-lg" />
        ))}
      </div>
    );
  } else if (showError) {
    body = (
      <div
        data-testid="ig-grid-error"
        className="flex flex-col items-center gap-2 rounded-md border border-dashed p-6 text-sm text-destructive"
      >
        <span className="flex items-center gap-2">
          <CircleAlert className="h-4 w-4" /> Erro ao carregar as publicações.
        </span>
        <Button variant="outline" size="sm" onClick={() => void q.refetch()}>
          Tentar novamente
        </Button>
      </div>
    );
  } else if (items.length === 0) {
    body = (
      <div
        data-testid="ig-grid-empty"
        className="rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground"
      >
        Nenhuma publicação coletada ainda. Use “Sincronizar agora” — depois disso, os dados passam a ser
        coletados diariamente.
      </div>
    );
  } else {
    body = (
      <>
        <div data-testid="ig-grid" className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
          {items.map((item) => (
            <InstagramPostCard key={item.id} item={item} onOpen={setSelected} />
          ))}
        </div>
        {q.hasNextPage && (
          <div className="flex justify-center pt-4">
            <Button
              variant="outline"
              onClick={() => void q.fetchNextPage()}
              disabled={q.isFetchingNextPage}
              data-testid="ig-grid-load-more"
            >
              {q.isFetchingNextPage && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Carregar mais
            </Button>
          </div>
        )}
      </>
    );
  }

  return (
    <div className="space-y-3">
      {isRefreshing && (
        <p className="flex items-center gap-2 text-xs text-muted-foreground" data-testid="ig-grid-refreshing">
          <Loader2 className="h-3.5 w-3.5 animate-spin" /> Atualizando…
        </p>
      )}
      {body}
      <InstagramPostInsightsModal
        accountId={accountId}
        media={selected}
        onClose={() => setSelected(null)}
      />
    </div>
  );
}

export default InstagramPostGrid;

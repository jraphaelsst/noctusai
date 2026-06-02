/**
 * Vídeos panel — YouTube Studio "Conteúdo do canal" table layout.
 *
 * Two kind-scoped sub-tabs: Vídeos (long-form) and Shorts, each backed
 * by a separate useVideos({ kind }) call so BE returns pre-filtered data.
 * Row click opens VideoDetailModal with per-video trend chart.
 *
 * Container-free panel rendered inside the YouTube page.
 */
import { useState } from "react";
import {
  Loader2,
  PlaySquare,
  RefreshCw,
  Smartphone,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

import { ChannelContentTable } from "@/components/ChannelContentTable";
import { VideoDetailModal } from "@/components/VideoDetailModal";
import {
  useVideos,
  useVideoSync,
  type Video,
} from "@/hooks/useVideos";

type FormatTab = "videos" | "shorts";

// ─── Sub-panel: one kind (video | short) ────────────────────────────────────

type ModalMode = "view" | "edit" | "delete";

function KindPanel({ kind }: { kind: "video" | "short" }) {
  const [selected, setSelected] = useState<{ video: Video; mode: ModalMode } | null>(null);

  const {
    items,
    totalKnown,
    loading,
    loadingMore,
    hasMore,
    loadMore,
    error,
  } = useVideos({ kind });

  const emptyMsg =
    totalKnown === 0
      ? "Nenhum vídeo no cache. Clique em Sincronizar."
      : kind === "video"
      ? "Nenhum vídeo longo encontrado."
      : "Nenhum Short encontrado.";

  return (
    <>
      {error ? (
        <Card>
          <CardContent className="p-6 text-sm text-destructive">{error}</CardContent>
        </Card>
      ) : (
        <ChannelContentTable
          items={items}
          loading={loading}
          loadingMore={loadingMore}
          hasMore={hasMore}
          onLoadMore={loadMore}
          onRowClick={(v) => setSelected({ video: v, mode: "view" })}
          onEdit={(v) => setSelected({ video: v, mode: "edit" })}
          onDelete={(v) => setSelected({ video: v, mode: "delete" })}
          emptyMessage={emptyMsg}
        />
      )}

      <VideoDetailModal
        video={selected?.video ?? null}
        initialMode={selected && selected.mode !== "view" ? selected.mode : null}
        onClose={() => setSelected(null)}
        onDeleted={() => setSelected(null)}
      />
    </>
  );
}

// ─── Panel ───────────────────────────────────────────────────────────────────

export default function VideosPanel() {
  const [tab, setTab] = useState<FormatTab>("videos");

  // Sync uses the active account from the store (wired in useVideoSync).
  const { sync, pending: syncing } = useVideoSync();

  return (
    <div className="space-y-4">
      {/* Header: title + sync button */}
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold">Conteúdo do canal</h2>
          <p className="text-sm text-muted-foreground">
            Clique em uma linha para ver detalhes e histórico do vídeo.
          </p>
        </div>
        <Button onClick={() => void sync()} disabled={syncing}>
          {syncing ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            <RefreshCw className="mr-2 h-4 w-4" />
          )}
          Sincronizar
        </Button>
      </div>

      <Tabs value={tab} onValueChange={(v) => setTab(v as FormatTab)}>
        <TabsList>
          <TabsTrigger value="videos">
            <PlaySquare className="mr-2 h-4 w-4" />
            Vídeos
          </TabsTrigger>
          <TabsTrigger value="shorts">
            <Smartphone className="mr-2 h-4 w-4" />
            Shorts
          </TabsTrigger>
        </TabsList>

        <TabsContent value="videos" className="mt-2">
          <KindPanel kind="video" />
        </TabsContent>

        <TabsContent value="shorts" className="mt-2">
          <KindPanel kind="short" />
        </TabsContent>
      </Tabs>
    </div>
  );
}

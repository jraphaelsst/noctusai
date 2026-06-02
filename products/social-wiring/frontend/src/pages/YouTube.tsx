/**
 * YouTube page — single sidebar entry for the channel surface.
 *
 * Top-level tabs:
 *   Visão geral  — channel KPI cards + subscribers/views trend + top-5
 *   Vídeos       — Studio "Conteúdo do canal" table (long-form, kind=video)
 *   Shorts       — Studio table (kind=short)
 *   Upload       — upload flow (Chat / Computador / Google Drive)
 *
 * Account switcher at top re-points every data hook via useActiveAccountStore.
 * All heavy panels are lazy so the initial paint is fast.
 */
import { lazy, Suspense, useState } from "react";
import {
  BarChart3,
  Loader2,
  PlaySquare,
  RefreshCw,
  Smartphone,
  Upload as UploadIcon,
} from "lucide-react";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ConnectedAccountSwitcher } from "@/components/ConnectedAccountSwitcher";
import { ChannelContentTable } from "@/components/ChannelContentTable";
import { VideoDetailModal } from "@/components/VideoDetailModal";
import { VisaoGeralPanel } from "@/components/VisaoGeralPanel";
import { useVideos, useVideoSync, type Video } from "@/hooks/useVideos";

// Lazy for upload only (heaviest panel)
const UploadPanel = lazy(() => import("@/pages/Upload"));

function PanelFallback() {
  return (
    <div className="flex items-center justify-center py-16">
      <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
    </div>
  );
}

// ─── Kind-scoped table panel ─────────────────────────────────────────────────

type ModalMode = "view" | "edit" | "delete";

function KindTablePanel({ kind }: { kind: "video" | "short" }) {
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
  const { sync, pending: syncing } = useVideoSync();

  const emptyMsg =
    totalKnown === 0
      ? "Nenhum vídeo no cache. Clique em Sincronizar."
      : kind === "video"
      ? "Nenhum vídeo longo encontrado."
      : "Nenhum Short encontrado.";

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold">
            {kind === "video" ? "Vídeos do canal" : "Shorts do canal"}
          </h2>
          <p className="text-sm text-muted-foreground">
            Clique em uma linha para ver detalhes e histórico.
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
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function YouTubePage() {
  return (
    <div className="container max-w-7xl space-y-6 py-6">
      {/* Page header */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">YouTube</h1>
          <p className="text-sm text-muted-foreground">
            Visão geral, catálogo do canal e envios de vídeo, num só lugar.
          </p>
        </div>
        {/* Live account/client switcher — re-points every YT data hook
            (visão geral, vídeos, shorts) via the shared useActiveAccountStore. */}
        <ConnectedAccountSwitcher />
      </div>

      <Tabs defaultValue="overview">
        <TabsList className="flex-wrap h-auto gap-0.5">
          <TabsTrigger value="overview">
            <BarChart3 className="mr-2 h-4 w-4" />
            Visão geral
          </TabsTrigger>
          <TabsTrigger value="videos">
            <PlaySquare className="mr-2 h-4 w-4" />
            Vídeos
          </TabsTrigger>
          <TabsTrigger value="shorts">
            <Smartphone className="mr-2 h-4 w-4" />
            Shorts
          </TabsTrigger>
          <TabsTrigger value="upload">
            <UploadIcon className="mr-2 h-4 w-4" />
            Upload
          </TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="mt-4">
          <VisaoGeralPanel />
        </TabsContent>

        <TabsContent value="videos" className="mt-4">
          <KindTablePanel kind="video" />
        </TabsContent>

        <TabsContent value="shorts" className="mt-4">
          <KindTablePanel kind="short" />
        </TabsContent>

        <TabsContent value="upload" className="mt-4">
          <Suspense fallback={<PanelFallback />}>
            <UploadPanel />
          </Suspense>
        </TabsContent>
      </Tabs>
    </div>
  );
}

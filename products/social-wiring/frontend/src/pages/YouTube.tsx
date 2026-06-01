/**
 * YouTube page — the single sidebar entry for the channel surface, with
 * top-level tabs:
 *
 *   Vídeos  (default)  the catalog → Vídeos / Shorts sub-tabs
 *   Upload             Chat / Computador / Google Drive sub-tabs
 *
 * This consolidates the former separate "Vídeos" and "Upload" pages under one
 * route. It is already the fused end-state shape: fusing the two further later
 * is just merging the two panels — no nav/route surgery.
 */
import { lazy, Suspense } from "react";
import { PlaySquare, Upload as UploadIcon, Loader2 } from "lucide-react";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ConnectedAccountSwitcher } from "@/components/ConnectedAccountSwitcher";

const VideosPanel = lazy(() => import("@/pages/Videos"));
const UploadPanel = lazy(() => import("@/pages/Upload"));

function PanelFallback() {
  return (
    <div className="flex items-center justify-center py-16">
      <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
    </div>
  );
}

export default function YouTubePage() {
  return (
    <div className="container max-w-7xl space-y-6 py-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">YouTube</h1>
          <p className="text-sm text-muted-foreground">
            Catálogo do canal e envios de vídeo, num só lugar.
          </p>
        </div>
        {/* Live account/client switcher — re-points every YT data hook
            (videos, dashboard) via the shared useActiveAccountStore. */}
        <ConnectedAccountSwitcher />
      </div>

      <Tabs defaultValue="videos">
        <TabsList>
          <TabsTrigger value="videos">
            <PlaySquare className="mr-2 h-4 w-4" />
            Vídeos
          </TabsTrigger>
          <TabsTrigger value="upload">
            <UploadIcon className="mr-2 h-4 w-4" />
            Upload
          </TabsTrigger>
        </TabsList>
        <TabsContent value="videos" className="mt-4">
          <Suspense fallback={<PanelFallback />}>
            <VideosPanel />
          </Suspense>
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

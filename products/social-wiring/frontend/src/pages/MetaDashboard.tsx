/**
 * MetaDashboard — the unified Meta (Instagram + Facebook) surface at /meta.
 *
 * Remodel of the retired flat `InstagramInsights.tsx` into a YouTube-style
 * shell (see `pages/YouTube.tsx`): account switcher header + an
 * Instagram|Facebook network toggle + subtabs, each subtab its own lazy
 * component under `pages/meta/` so this file stays a thin composition root.
 *
 * Every subtab reads the active account via `useActiveMetaAccountId()`
 * (`useActiveAccountStore`, re-pointed by `<ConnectedAccountSwitcher
 * provider="meta" />` below) — no more local `AccountPicker` / path-param
 * model.
 *
 * Wave 4 note: this shell + the DMs 2-pane are deliberately kept simple so a
 * shared `SocialDashboardShell` + `ChatWindow` extraction (YouTube + Meta +
 * WhatsApp) can lift them without a rewrite.
 */
import { lazy, Suspense, useEffect, useState } from "react";
import {
  BarChart3,
  Facebook,
  Grid3x3,
  Instagram,
  Loader2,
  MessageCircle,
  MessagesSquare,
} from "lucide-react";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { ConnectedAccountSwitcher } from "@/components/ConnectedAccountSwitcher";

type Network = "instagram" | "facebook";
type SubtabKey = "overview" | "content" | "comments" | "dms";

const IgVisaoGeral = lazy(() => import("@/pages/meta/IgVisaoGeral"));
const IgConteudo = lazy(() => import("@/pages/meta/IgConteudo"));
const IgComentarios = lazy(() => import("@/pages/meta/IgComentarios"));
const IgDMs = lazy(() => import("@/pages/meta/IgDMs"));
const FbVisaoGeral = lazy(() => import("@/pages/meta/FbVisaoGeral"));
const FbConteudo = lazy(() => import("@/pages/meta/FbConteudo"));
const FbComentarios = lazy(() => import("@/pages/meta/FbComentarios"));

function PanelFallback() {
  return (
    <div className="flex items-center justify-center py-16">
      <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
    </div>
  );
}

const IG_SUBTABS: { key: SubtabKey; label: string; icon: typeof BarChart3 }[] = [
  { key: "overview", label: "Visão geral", icon: BarChart3 },
  { key: "content", label: "Conteúdo", icon: Grid3x3 },
  { key: "comments", label: "Comentários", icon: MessageCircle },
  { key: "dms", label: "DMs", icon: MessagesSquare },
];

const FB_SUBTABS: { key: SubtabKey; label: string; icon: typeof BarChart3 }[] = [
  { key: "overview", label: "Visão geral", icon: BarChart3 },
  { key: "content", label: "Conteúdo", icon: Grid3x3 },
  { key: "comments", label: "Comentários", icon: MessageCircle },
];

export default function MetaDashboard() {
  const [network, setNetwork] = useState<Network>("instagram");
  const [activeTab, setActiveTab] = useState<SubtabKey>("overview");

  const subtabs = network === "instagram" ? IG_SUBTABS : FB_SUBTABS;

  // FB has no "dms" subtab — fall back to "overview" when the network is
  // switched while DMs was selected (rather than rendering a dead tab).
  useEffect(() => {
    if (!subtabs.some((t) => t.key === activeTab)) {
      setActiveTab("overview");
    }
  }, [network, subtabs, activeTab]);

  return (
    <div className="container max-w-7xl space-y-6 py-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Meta</h1>
          <p className="text-sm text-muted-foreground">
            Instagram e Facebook: visão geral, conteúdo, comentários e
            mensagens, num só lugar.
          </p>
        </div>
        <ConnectedAccountSwitcher provider="meta" providerLabel="Meta" />
      </div>

      {/* Network toggle */}
      <div
        className="inline-flex rounded-md border border-border bg-muted/30 p-1"
        role="group"
        aria-label="Rede social"
        data-testid="meta-network-toggle"
      >
        <Button
          type="button"
          variant={network === "instagram" ? "default" : "ghost"}
          size="sm"
          data-testid="meta-network-instagram"
          onClick={() => setNetwork("instagram")}
        >
          <Instagram className="mr-2 h-4 w-4" />
          Instagram
        </Button>
        <Button
          type="button"
          variant={network === "facebook" ? "default" : "ghost"}
          size="sm"
          data-testid="meta-network-facebook"
          onClick={() => setNetwork("facebook")}
        >
          <Facebook className="mr-2 h-4 w-4" />
          Facebook
        </Button>
      </div>

      <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as SubtabKey)}>
        <TabsList className="flex-wrap h-auto gap-0.5">
          {subtabs.map(({ key, label, icon: Icon }) => (
            <TabsTrigger key={key} value={key}>
              <Icon className="mr-2 h-4 w-4" />
              {label}
            </TabsTrigger>
          ))}
        </TabsList>

        <Suspense fallback={<PanelFallback />}>
          {network === "instagram" ? (
            <>
              <TabsContent value="overview" className="mt-4">
                <IgVisaoGeral />
              </TabsContent>
              <TabsContent value="content" className="mt-4">
                <IgConteudo />
              </TabsContent>
              <TabsContent value="comments" className="mt-4">
                <IgComentarios />
              </TabsContent>
              <TabsContent value="dms" className="mt-4">
                <IgDMs />
              </TabsContent>
            </>
          ) : (
            <>
              <TabsContent value="overview" className="mt-4">
                <FbVisaoGeral />
              </TabsContent>
              <TabsContent value="content" className="mt-4">
                <FbConteudo />
              </TabsContent>
              <TabsContent value="comments" className="mt-4">
                <FbComentarios />
              </TabsContent>
            </>
          )}
        </Suspense>
      </Tabs>
    </div>
  );
}

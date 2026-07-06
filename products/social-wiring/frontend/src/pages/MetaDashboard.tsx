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
 * The container/header/network-toggle/Radix-Tabs spine is
 * `SocialDashboardShell` (`@noctusai/lib/design-system`) — shared with
 * `YouTube.tsx`. This file now only owns the network→subtabs mapping (the
 * shell self-heals the active subtab when the set changes, e.g. Facebook
 * dropping "dms").
 */
import { lazy, Suspense, useState, type LazyExoticComponent } from "react";
import {
  BarChart3,
  Facebook,
  Grid3x3,
  Instagram,
  Loader2,
  MessageCircle,
  MessagesSquare,
} from "lucide-react";

import {
  SocialDashboardShell,
  type SocialDashboardSubtab,
} from "@noctusai/lib/design-system";
import { ConnectedAccountSwitcher } from "@/components/ConnectedAccountSwitcher";

type Network = "instagram" | "facebook";

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

function lazyPanel(Panel: LazyExoticComponent<() => JSX.Element>) {
  return () => (
    <Suspense fallback={<PanelFallback />}>
      <Panel />
    </Suspense>
  );
}

const IG_SUBTABS: SocialDashboardSubtab[] = [
  { key: "overview", label: "Visão geral", icon: BarChart3, render: lazyPanel(IgVisaoGeral) },
  { key: "content", label: "Conteúdo", icon: Grid3x3, render: lazyPanel(IgConteudo) },
  { key: "comments", label: "Comentários", icon: MessageCircle, render: lazyPanel(IgComentarios) },
  { key: "dms", label: "DMs", icon: MessagesSquare, render: lazyPanel(IgDMs) },
];

const FB_SUBTABS: SocialDashboardSubtab[] = [
  { key: "overview", label: "Visão geral", icon: BarChart3, render: lazyPanel(FbVisaoGeral) },
  { key: "content", label: "Conteúdo", icon: Grid3x3, render: lazyPanel(FbConteudo) },
  { key: "comments", label: "Comentários", icon: MessageCircle, render: lazyPanel(FbComentarios) },
];

export default function MetaDashboard() {
  const [network, setNetwork] = useState<Network>("instagram");

  const subtabs = network === "instagram" ? IG_SUBTABS : FB_SUBTABS;

  return (
    <SocialDashboardShell
      title="Meta"
      subtitle="Instagram e Facebook: visão geral, conteúdo, comentários e mensagens, num só lugar."
      accountSwitcher={<ConnectedAccountSwitcher provider="meta" providerLabel="Meta" />}
      networks={[
        { key: "instagram", label: "Instagram", icon: Instagram },
        { key: "facebook", label: "Facebook", icon: Facebook },
      ]}
      activeNetwork={network}
      onNetworkChange={(key) => setNetwork(key as Network)}
      subtabs={subtabs}
      defaultSubtab="overview"
    />
  );
}

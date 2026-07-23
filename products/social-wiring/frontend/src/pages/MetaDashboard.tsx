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
  DollarSign,
  Facebook,
  Grid3x3,
  History,
  Instagram,
  Loader2,
  Megaphone,
  MessageCircle,
  MessagesSquare,
  Table2,
} from "lucide-react";

import {
  SocialDashboardShell,
  type SocialDashboardSubtab,
} from "@noctusai/lib/design-system";
import { ConnectedAccountSwitcher } from "@/components/ConnectedAccountSwitcher";

type Network = "instagram" | "facebook" | "ads";

const IgVisaoGeral = lazy(() => import("@/pages/meta/IgVisaoGeral"));
const IgConteudo = lazy(() => import("@/pages/meta/IgConteudo"));
const IgComentarios = lazy(() => import("@/pages/meta/IgComentarios"));
const IgDMs = lazy(() => import("@/pages/meta/IgDMs"));
const FbVisaoGeral = lazy(() => import("@/pages/meta/FbVisaoGeral"));
const FbConteudo = lazy(() => import("@/pages/meta/FbConteudo"));
const FbComentarios = lazy(() => import("@/pages/meta/FbComentarios"));
const AdsVisaoGeral = lazy(() => import("@/pages/meta/AdsVisaoGeral"));
const AdsCampanhas = lazy(() => import("@/pages/meta/AdsCampanhas"));
const AdsHistorico = lazy(() => import("@/pages/meta/AdsHistorico"));
const AdsFinanceiro = lazy(() => import("@/pages/meta/AdsFinanceiro"));

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

// Anúncios (Meta Ads) — ad-account-scoped, spans IG+FB placements, so it's
// its own network rather than a per-network subtab. Reads the single
// workspace-configured System-User account, not the connection switcher.
const ADS_SUBTABS: SocialDashboardSubtab[] = [
  { key: "overview", label: "Visão geral", icon: BarChart3, render: lazyPanel(AdsVisaoGeral) },
  { key: "campaigns", label: "Campanhas", icon: Table2, render: lazyPanel(AdsCampanhas) },
  { key: "history", label: "Histórico", icon: History, render: lazyPanel(AdsHistorico) },
  { key: "financial", label: "Financeiro", icon: DollarSign, render: lazyPanel(AdsFinanceiro) },
];

export default function MetaDashboard() {
  const [network, setNetwork] = useState<Network>("instagram");

  const subtabs =
    network === "ads"
      ? ADS_SUBTABS
      : network === "instagram"
        ? IG_SUBTABS
        : FB_SUBTABS;

  return (
    <SocialDashboardShell
      title="Meta"
      subtitle="Instagram, Facebook e Anúncios: visão geral, conteúdo, comentários, mensagens e campanhas, num só lugar."
      accountSwitcher={
        network === "ads" ? undefined : (
          <ConnectedAccountSwitcher provider="meta" providerLabel="Meta" />
        )
      }
      networks={[
        { key: "instagram", label: "Instagram", icon: Instagram },
        { key: "facebook", label: "Facebook", icon: Facebook },
        { key: "ads", label: "Anúncios", icon: Megaphone },
      ]}
      activeNetwork={network}
      onNetworkChange={(key) => setNetwork(key as Network)}
      subtabs={subtabs}
      defaultSubtab="overview"
    />
  );
}

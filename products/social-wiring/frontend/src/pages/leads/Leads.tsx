/**
 * Leads — the Leads module's composition root at `/leads` (§6 of
 * leads-module-PROJECT.md). Nav item lives directly under Contatos.
 *
 * `SocialDashboardShell` (single-network — no `networks` prop, same as
 * `YouTube.tsx`) carries the 7 subtabs. `LeadsFilterBar` is mounted ONCE,
 * sticky, above the shell — the shared `useLeadsFilters()` state it writes
 * to the URL is read by every subtab, so a filter set here (or a drill-in
 * click from Origens/Corretores/Empreendimentos) re-scopes every chart/table
 * without each subtab needing its own copy of the bar.
 */
import { lazy, Suspense, type LazyExoticComponent } from "react";
import {
  BarChart3,
  ListChecks,
  Loader2,
  MapPin,
  Settings2,
  Table2,
  Upload,
  Users,
} from "lucide-react";

import {
  SocialDashboardShell,
  type SocialDashboardSubtab,
} from "@noctusai/lib/design-system";
import { LeadsFilterBar } from "./components/LeadsFilterBar";

const VisaoGeral = lazy(() => import("./VisaoGeral"));
const BaseDeLeads = lazy(() => import("./BaseDeLeads"));
const Origens = lazy(() => import("./Origens"));
const Corretores = lazy(() => import("./Corretores"));
const Empreendimentos = lazy(() => import("./Empreendimentos"));
const Importacao = lazy(() => import("./Importacao"));
const Configuracao = lazy(() => import("./Configuracao"));

function PanelFallback() {
  return (
    <div className="flex items-center justify-center py-16" data-testid="leads-panel-loading">
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

const SUBTABS: SocialDashboardSubtab[] = [
  { key: "overview", label: "Visão geral", icon: BarChart3, render: lazyPanel(VisaoGeral) },
  { key: "leads", label: "Base de Leads", icon: Table2, render: lazyPanel(BaseDeLeads) },
  { key: "origens", label: "Origens", icon: ListChecks, render: lazyPanel(Origens) },
  { key: "corretores", label: "Corretores", icon: Users, render: lazyPanel(Corretores) },
  { key: "empreendimentos", label: "Empreendimentos", icon: MapPin, render: lazyPanel(Empreendimentos) },
  { key: "importacao", label: "Importação", icon: Upload, render: lazyPanel(Importacao) },
  { key: "config", label: "Configuração", icon: Settings2, render: lazyPanel(Configuracao) },
];

export default function Leads() {
  return (
    <div data-testid="leads-page">
      <div className="sticky top-0 z-10 border-b border-border bg-background/95 px-4 py-2 backdrop-blur supports-[backdrop-filter]:bg-background/80">
        <div className="container max-w-7xl">
          <LeadsFilterBar />
        </div>
      </div>
      <SocialDashboardShell
        title="Leads"
        subtitle="Controle de leads — origens, corretores e empreendimentos, num só lugar."
        subtabs={SUBTABS}
        defaultSubtab="overview"
      />
    </div>
  );
}

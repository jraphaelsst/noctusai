/**
 * n8n page — single sidebar entry for managing a client's n8n workflows.
 *
 * Subtabs:
 *   Workflows      — the client's folder tree + workflows, built by the
 *                     operator via drag-and-drop from the "Sem marca"
 *                     bucket (n8n carries zero tags today; assigning a
 *                     workflow to a client IS applying that client's tag).
 *   Configurações  — the client's n8n connection (base_url / api_key / tag).
 *
 * Same design spine as `pages/YouTube.tsx` / `pages/WhatsAppChat.tsx` — the
 * container/header/Radix-Tabs shell is `SocialDashboardShell`
 * (`@noctusai/lib/design-system`); this file only supplies subtab content.
 */
import { Settings as SettingsIcon, Workflow } from "lucide-react";

import { SocialDashboardShell, type SocialDashboardSubtab } from "@noctusai/lib/design-system";
import { ConnectedAccountSwitcher } from "@/components/ConnectedAccountSwitcher";
import { WorkflowsPanel } from "@/components/n8n/WorkflowsPanel";
import { N8nSettingsPanel } from "@/components/n8n/N8nSettingsPanel";

const SUBTABS: SocialDashboardSubtab[] = [
  { key: "workflows", label: "Workflows", icon: Workflow, render: () => <WorkflowsPanel /> },
  {
    key: "settings",
    label: "Configurações",
    icon: SettingsIcon,
    render: () => <N8nSettingsPanel />,
  },
];

export default function N8nPage() {
  return (
    <SocialDashboardShell
      title="n8n"
      subtitle="Organize os fluxos n8n de cada marca numa árvore de pastas."
      accountSwitcher={<ConnectedAccountSwitcher provider="n8n" providerLabel="n8n" />}
      subtabs={SUBTABS}
      defaultSubtab="workflows"
    />
  );
}

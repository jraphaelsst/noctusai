/**
 * `/configuracoes/*` -- settings, one tab per sub-route (the seed `SectionTabsPage`). Grows by adding an entry to
 * `SECTIONS`: a new tab is one object (`key` = the URL segment), nothing else changes. Today: Conta (read-only
 * identity of the signed-in user / org, from the SSO context).
 */
import { SectionTabsPage, type SectionTab } from "@noctusai/lib/components";
import { useEffectiveSSOContext } from "@noctusai/lib/design-system";
import { useAuthStore } from "@noctusai/seed/infra";
import { UserCircle } from "lucide-react";

function Item({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-border bg-muted/50 px-4 py-3">
      <p className="text-xs font-medium text-muted-foreground">{label}</p>
      <p className="text-sm font-semibold text-foreground truncate">{value}</p>
    </div>
  );
}

function Conta() {
  const user = useAuthStore((s) => s.user);
  const sso = useEffectiveSSOContext();
  return (
    <div className="grid gap-3 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3" data-testid="configuracoes-conta">
      <Item label="Usuário" value={user?.email || "—"} />
      <Item label="Organização" value={sso.org.name || "—"} />
      <Item label="Papel na organização" value={sso.org.role || "—"} />
    </div>
  );
}

const SECTIONS: SectionTab[] = [
  { key: "conta", label: "Conta", icon: <UserCircle className="h-4 w-4" />, render: () => <Conta /> },
];

export default function Configuracoes() {
  return <SectionTabsPage basePath="/configuracoes" title="Configurações" description="Ajustes da sua conta." sections={SECTIONS} />;
}

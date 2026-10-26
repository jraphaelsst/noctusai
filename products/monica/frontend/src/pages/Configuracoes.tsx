/**
 * `/configuracoes/*` -- settings, one tab per sub-route (the seed `SectionTabsPage`). Designed to grow: a new
 * section is one entry in `SECTIONS`. Today: Conexões (the WhatsApp QR line, admin only).
 */
import { SectionTabsPage, WhatsAppConnectionsPage, type SectionTab } from "@noctusai/lib/components";
import { useIsOrgAdmin } from "@noctusai/lib/design-system";
import { Smartphone } from "lucide-react";

import { connectionsHooks } from "@/lib/crm";

function Conexoes({ isAdmin }: { isAdmin: boolean }) {
  if (!isAdmin) {
    return (
      <div className="rounded-lg border border-border bg-card p-4 text-sm text-muted-foreground" data-testid="conexoes-acesso-restrito">
        Esta página é restrita a administradores.
      </div>
    );
  }
  return (
    <WhatsAppConnectionsPage
      hooks={connectionsHooks}
      title="WhatsApp"
      emptyState={
        <p className="text-sm text-muted-foreground" data-testid="conexoes-vazio">
          Nenhum número conectado. Crie uma conexão e leia o QR code com o WhatsApp do celular.
        </p>
      }
    />
  );
}

export default function Configuracoes() {
  const isAdmin = useIsOrgAdmin();
  const sections: SectionTab[] = [
    { key: "conexoes", label: "Conexões", icon: <Smartphone className="h-4 w-4" />, render: () => <Conexoes isAdmin={isAdmin} /> },
  ];
  return <SectionTabsPage basePath="/configuracoes" title="Configurações" description="Ajustes da sua conta." sections={sections} />;
}

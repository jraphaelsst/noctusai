/**
 * Conexões WhatsApp — `/whatsapp`.
 *
 * Standalone page (not an Automação tab): the connection is org-level
 * infrastructure that Automação consumes today and Conteúdo/Relatórios may
 * consume later, and the QR pairing flow needs room. Automação links here when
 * disconnected. Admin-only (pairing a number is an org-admin action).
 *
 * Seed organ: `WhatsAppConnectionsPage` + `createWhatsAppConnectionsHooks`.
 */
import { WhatsAppConnectionsPage } from "@noctusai/lib/components";
import { isOrgAdmin, resolveSSOContext } from "@noctusai/lib";
import { useAuthStore } from "@noctusai/seed/infra";
import { waHooks } from "@/hooks/useWhatsApp";

export default function Whatsapp() {
  const user = useAuthStore((s) => s.user);
  const isAdmin = isOrgAdmin(resolveSSOContext(user?.user_metadata ?? undefined));

  return (
    <div className="space-y-6" data-testid="whatsapp-page">
      <div>
        <h1 className="text-2xl font-bold text-foreground">WhatsApp</h1>
        <p className="text-sm text-muted-foreground">
          Conecte o número da agência para que as automações enviem mensagens de verdade.
        </p>
      </div>
      {isAdmin ? (
        <WhatsAppConnectionsPage hooks={waHooks} />
      ) : (
        <div
          className="rounded-lg border border-border bg-card p-4 text-sm text-muted-foreground"
          data-testid="whatsapp-acesso-restrito"
        >
          Apenas administradores podem gerenciar a conexão do WhatsApp.
        </div>
      )}
    </div>
  );
}

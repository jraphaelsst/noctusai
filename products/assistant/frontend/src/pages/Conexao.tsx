/**
 * `/conexao` -- the pairing page: connection status + the QR code of the personal WhatsApp line (the seed
 * `WhatsAppConnectionsPage` organ). The Assistant answers 1:1 text messages through the owner's agent (only when the
 * live reply is switched on and the number is allowed); it never marks as read or shows a presence. The status/QR polling lives in the organ (paused while the tab is hidden, stops once paired).
 */
import { WhatsAppConnectionsPage } from "@noctusai/lib/components";
import { useIsOrgAdmin } from "@noctusai/lib/design-system";
import { ShieldCheck } from "lucide-react";

import { connectionsHooks } from "@/lib/whatsapp";

export default function Conexao() {
  const isAdmin = useIsOrgAdmin();
  if (!isAdmin) {
    return (
      <div className="rounded-lg border border-border bg-card p-4 text-sm text-muted-foreground" data-testid="conexao-acesso-restrito">
        Esta página é restrita a administradores.
      </div>
    );
  }
  return (
    <WhatsAppConnectionsPage
      hooks={connectionsHooks}
      title="Conexão do WhatsApp"
      banner={
        <p className="flex items-start gap-2 rounded-md border border-border bg-muted/50 px-3 py-2 text-sm text-muted-foreground" data-testid="conexao-resposta">
          <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0" />
          O Assistant só atende conversas individuais, por texto, e responde apenas quando o atendimento está ligado
          e o número é permitido. Nunca marca como lida e nunca aparece online.
        </p>
      }
      emptyState={
        <p className="text-sm text-muted-foreground" data-testid="conexao-vazio">
          Nenhuma linha conectada. Crie a conexão e leia o QR code com o WhatsApp do celular.
        </p>
      }
    />
  );
}

/**
 * Julia › Agente card "WhatsApp da Julia" (`#whatsapp`): the org's single WhatsApp line — QR to pair it, live status,
 * reconnect — using the seed `ConnectionPairingPanel`. The same number carries Julia's lead conversations and the
 * team notifications, so a disconnect stops both (said in the logout confirm). Conversations are read and answered in
 * Conversas (the existing chat window); this card links there instead of rebuilding it.
 * One line per org: there is no "add another connection" here, only "Criar linha" while the org has none.
 */
import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { MessageCircle } from "lucide-react";
import { ConfirmProvider, ConnectionPairingPanel, CreateConnectionDialog } from "@noctusai/lib/components";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { juliaLinhaHooks } from "@/hooks/useJuliaLinhaWhatsapp";
import { JULIA_ROTEAMENTO_KEY, type LinhaRoteamento, type Roteamento } from "@/hooks/useJuliaRoteamento";

const LOGOUT_TEXT =
  "Este número atende os leads com a Julia e envia os avisos para a equipe. Ao desconectar, os dois param até você ler um novo QR.";

function CriarLinha() {
  const qc = useQueryClient();
  const mutations = juliaLinhaHooks.useConnectionMutations();
  const [aberto, setAberto] = useState(false);
  return (
    <>
      <Button size="sm" onClick={() => setAberto(true)} data-testid="whatsapp-criar-linha">
        Criar linha
      </Button>
      <CreateConnectionDialog
        open={aberto}
        onClose={() => setAberto(false)}
        mutations={mutations}
        onCreated={(l) =>
          // The routing read is where this page learns the line: write it in (the server settles the rest).
          qc.setQueryData<Roteamento>(JULIA_ROTEAMENTO_KEY, (old) =>
            old && !old.linhas.some((x) => x.connection_id === l.id)
              ? {
                  ...old,
                  linhas: [
                    ...old.linhas,
                    { connection_id: l.id, label: l.label, alimenta: false, alimenta_desde: null, destino_handoff_user_id: null },
                  ],
                }
              : old,
          )
        }
      />
    </>
  );
}

export function WhatsAppJuliaCard({ linha, isAdmin }: { linha: LinhaRoteamento | undefined; isAdmin: boolean }) {
  return (
    <Card id="whatsapp" data-testid="whatsapp-julia-card">
      <CardHeader>
        <CardTitle className="text-base">WhatsApp da Julia</CardTitle>
        <CardDescription>
          O número de WhatsApp da sua empresa. Leia o QR em Aparelhos conectados para ligá-lo. Esse mesmo número também envia os avisos para a equipe.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <ConfirmProvider>
          <ConnectionPairingPanel
            connectionId={linha?.connection_id}
            hooks={juliaLinhaHooks}
            canManage={isAdmin}
            onLogoutConfirmText={LOGOUT_TEXT}
            emptyAction={isAdmin ? <CriarLinha /> : <p className="text-xs">Peça a um owner ou admin da organização para criar a linha.</p>}
          />
        </ConfirmProvider>
        {!isAdmin && !!linha && (
          <p className="text-xs text-muted-foreground">Somente owner ou admin da organização pode parear ou desconectar o número.</p>
        )}
        {linha && (
          <a
            href="/julia/conversas"
            className="inline-flex items-center gap-1 text-sm text-primary underline"
            data-testid="whatsapp-ver-conversas"
          >
            <MessageCircle className="h-4 w-4" /> Ver e responder conversas
          </a>
        )}
      </CardContent>
    </Card>
  );
}

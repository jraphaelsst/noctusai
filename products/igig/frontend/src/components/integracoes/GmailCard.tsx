/**
 * Integrações → Gmail (wave-2 contract, Slice B): the mailbox whose REPLIES to
 * sent orçamentos are detected (watch + Pub/Sub push).
 *
 * "Conectar" fetches the Google consent URL and navigates there; Google comes
 * back to `/integracoes?gmail=ok|erro&motivo=` (handled by the page).
 * `configuracao_gcp_ok=false` means the PLATFORM's Pub/Sub env is missing:
 * the mailbox may be connected, but replies cannot be detected — said
 * loudly, never implied to work.
 */
import { useState } from "react";
import { Button } from "@noctusai/lib/design-system";
import type { BadgeVariant } from "@noctusai/lib/design-system";
import { AlertTriangle, Link2Off, MailCheck } from "lucide-react";
import { toast } from "sonner";

import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { useGmail, useGmailMutations, type GmailStatus } from "@/hooks/useEmailIntegracao";
import { describeError } from "@/lib/errors";
import { dataBR } from "@/lib/format";
import { IntegracaoCard } from "./IntegracaoCard";

function badgeDe(g: GmailStatus): { texto: string; variante: BadgeVariant } {
  if (g.ultimo_erro) return { texto: "reconectar", variante: "destructive" };
  if (!g.conectado) return { texto: "não conectado", variante: "muted" };
  if (!g.watch_ativo) return { texto: "conectado · sem monitoramento", variante: "outline" };
  return { texto: "conectado", variante: "default" };
}

export function GmailCard() {
  const { gmail, showSkeleton, isError, error } = useGmail();
  const { iniciarOAuth, desconectar } = useGmailMutations();
  const [confirmando, setConfirmando] = useState(false);

  function conectar() {
    iniciarOAuth.mutate(undefined, {
      // A full navigation, not window.open: Google redirects back here.
      onSuccess: ({ url }) => window.location.assign(url),
      onError: (e) => toast.error(describeError(e, "Não foi possível iniciar a conexão com o Google.")),
    });
  }

  return (
    <IntegracaoCard
      titulo="Gmail (respostas de orçamentos)"
      icone={<MailCheck className="h-4 w-4" />}
      badge={gmail ? badgeDe(gmail) : null}
      descricao="Conecte a caixa que envia os orçamentos: quando o cliente responde, o orçamento é marcado e o responsável é notificado."
      showSkeleton={showSkeleton}
      erro={isError ? describeError(error, "Não foi possível carregar o Gmail.") : null}
      testId="gmail-card"
    >
      {gmail ? (
        <div className="space-y-3 text-sm">
          {!gmail.configuracao_gcp_ok ? (
            <div
              className="flex items-start gap-2 rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-destructive"
              data-testid="gmail-gcp-pendente"
            >
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <p>
                Configuração GCP pendente na plataforma (Pub/Sub do Gmail, variáveis GMAIL_PUSH_*). A caixa pode ser
                conectada, mas as respostas ainda não serão detectadas.
              </p>
            </div>
          ) : null}

          {gmail.conectado ? (
            <dl className="grid gap-2 sm:grid-cols-3">
              <div className="min-w-0">
                <dt className="text-xs text-muted-foreground">Caixa</dt>
                <dd className="truncate text-foreground">{gmail.email}</dd>
              </div>
              <div>
                <dt className="text-xs text-muted-foreground">Monitoramento</dt>
                <dd className="text-foreground">{gmail.watch_ativo ? "ativo" : "inativo"}</dd>
              </div>
              <div>
                <dt className="text-xs text-muted-foreground">Expira em</dt>
                <dd className="text-foreground">{gmail.expira_em ? dataBR(gmail.expira_em) : "—"}</dd>
              </div>
            </dl>
          ) : null}

          {gmail.ultimo_erro ? (
            <p className="flex items-start gap-1 text-xs text-destructive">
              <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />
              {gmail.ultimo_erro}
            </p>
          ) : null}

          <div className="flex flex-wrap gap-2">
            <Button className="max-sm:h-10" disabled={iniciarOAuth.isPending} onClick={conectar} data-testid="gmail-conectar">
              {iniciarOAuth.isPending ? "Abrindo o Google…" : gmail.conectado ? "Reconectar" : "Conectar Gmail"}
            </Button>
            {gmail.conectado ? (
              <Button variant="ghost" className="text-destructive max-sm:h-10" onClick={() => setConfirmando(true)}>
                <Link2Off className="mr-1 h-4 w-4" /> Desconectar
              </Button>
            ) : null}
          </div>
        </div>
      ) : null}

      <ConfirmDialog
        open={confirmando}
        title="Desconectar Gmail"
        description={<p>Desconectar {gmail?.email}? As respostas aos orçamentos deixam de ser detectadas.</p>}
        confirmLabel={desconectar.isPending ? "Desconectando…" : "Desconectar"}
        busy={desconectar.isPending}
        onCancel={() => setConfirmando(false)}
        onConfirm={() =>
          desconectar.mutate(undefined, {
            onSuccess: () => {
              setConfirmando(false);
              toast.success("Gmail desconectado.");
            },
            onError: (e) => toast.error(describeError(e, "Não foi possível desconectar.")),
          })
        }
      />
    </IntegracaoCard>
  );
}

/**
 * OlxWebhookCard — operational health for the Grupo OLX lead webhook.
 *
 * Answers three questions, in the order an operator asks them:
 *   1. is anything stuck? (`unresolved` / `error` — a real enquiry nobody
 *      has been told about)
 *   2. are leads arriving at all?
 *   3. what URL do I give OLX at homologation?
 *
 * The stuck count leads because it is the only thing here that needs
 * someone to act. Everything else is reassurance.
 */
import { useMemo, useState } from "react";
import { AlertTriangle, CheckCircle2, Copy, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { Skeleton } from "@noctusai/lib/design-system";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useOlxBackfill, useOlxEvents, type OlxLeadEvent } from "@/hooks/useOlxLeads";

const RECEIVER_PATH = "/api/portals/olx/leads";

const STATUS_LABEL: Record<string, string> = {
  received: "Recebido",
  processed: "Processado",
  error: "Erro",
  unresolved: "Sem cliente",
  ignored: "Ignorado",
};

function statusVariant(status: string): "default" | "secondary" | "destructive" {
  if (status === "error" || status === "unresolved") return "destructive";
  if (status === "processed") return "default";
  return "secondary";
}

function formatWhen(value: string | null): string {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? "—" : parsed.toLocaleString("pt-BR");
}

export default function OlxWebhookCard() {
  const { events, counts, stuck, loading, isEmpty, isError, error, refetch } =
    useOlxEvents(50);
  const backfill = useOlxBackfill();
  const [copied, setCopied] = useState(false);

  const receiverUrl = useMemo(
    () => `${window.location.origin}${RECEIVER_PATH}`,
    [],
  );

  const copyUrl = async () => {
    try {
      await navigator.clipboard.writeText(receiverUrl);
      setCopied(true);
      toast.success("URL copiada — envie ao Grupo OLX na homologação.");
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.error("Não foi possível copiar. Selecione e copie manualmente.");
    }
  };

  const runBackfill = async () => {
    try {
      const result = await backfill.mutateAsync();
      toast.success(
        `Backfill concluído: ${result.ingested} novo(s), ` +
          `${result.skipped_existing} já existia(m).`,
      );
    } catch {
      toast.error("O backfill falhou. Verifique os logs do servidor.");
    }
  };

  return (
    <div
      className="rounded-lg border border-border p-4 space-y-4"
      data-testid="olx-webhook-card"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold">Grupo OLX (ZAP / VivaReal / ImovelWeb)</h3>
          <p className="text-xs text-muted-foreground">
            Leads dos portais chegam por webhook. Um mesmo endereço atende todos
            os portais do grupo.
          </p>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => refetch()}
          data-testid="olx-refresh"
          aria-label="Atualizar"
        >
          <RefreshCw className="h-4 w-4" />
        </Button>
      </div>

      {/* Homologation URL — the thing an operator actually needs to hand over. */}
      <div className="space-y-1.5">
        <span className="text-xs font-medium text-muted-foreground">
          URL do receptor (informe ao Grupo OLX)
        </span>
        <div className="flex items-center gap-2">
          <code
            className="flex-1 truncate rounded-md bg-muted px-2 py-1.5 text-xs"
            data-testid="olx-receiver-url"
          >
            {receiverUrl}
          </code>
          <Button variant="outline" size="sm" onClick={copyUrl} data-testid="olx-copy-url">
            <Copy className="mr-1 h-3.5 w-3.5" />
            {copied ? "Copiado" : "Copiar"}
          </Button>
        </div>
      </div>

      {loading ? (
        <div className="space-y-2" data-testid="olx-events-loading">
          <Skeleton className="h-4 w-40" />
          <Skeleton className="h-16 w-full" />
        </div>
      ) : isError ? (
        <div
          className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm"
          data-testid="olx-events-error"
        >
          <AlertTriangle className="mt-0.5 h-4 w-4 text-destructive" />
          <div>
            <p className="font-medium">Não foi possível carregar as entregas.</p>
            <p className="text-xs text-muted-foreground">
              {(error as Error | null)?.message ?? "Tente novamente."}
            </p>
          </div>
        </div>
      ) : isEmpty ? (
        <div
          className="rounded-md border border-dashed border-border p-3 text-sm text-muted-foreground"
          data-testid="olx-events-empty"
        >
          Nenhuma entrega recebida ainda. Isso é esperado antes da homologação —
          o Grupo OLX só passa a enviar depois de validar a URL acima.
        </div>
      ) : (
        <div className="space-y-3" data-testid="olx-events-success">
          {stuck.length > 0 ? (
            <div
              className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm"
              data-testid="olx-stuck-banner"
            >
              <AlertTriangle className="mt-0.5 h-4 w-4 text-destructive" />
              <div>
                <p className="font-medium">
                  {stuck.length} lead(s) aguardando atenção
                </p>
                <p className="text-xs text-muted-foreground">
                  &quot;Sem cliente&quot; significa que o lead chegou mas não foi
                  possível identificar de qual cliente ele é — ele fica guardado
                  até alguém definir, nunca é atribuído por suposição.
                </p>
              </div>
            </div>
          ) : (
            <div
              className="flex items-center gap-2 text-sm text-muted-foreground"
              data-testid="olx-healthy"
            >
              <CheckCircle2 className="h-4 w-4 text-emerald-600" />
              Todas as entregas recentes foram processadas.
            </div>
          )}

          <div className="flex flex-wrap gap-1.5" data-testid="olx-status-counts">
            {Object.entries(counts).map(([status, count]) => (
              <Badge key={status} variant={statusVariant(status)}>
                {STATUS_LABEL[status] ?? status}: {count}
              </Badge>
            ))}
          </div>

          <ul className="space-y-1.5" data-testid="olx-events-list">
            {events.slice(0, 8).map((event: OlxLeadEvent) => (
              <li
                key={event.id}
                className="flex items-center justify-between gap-2 text-xs"
              >
                <span className="truncate font-mono">{event.id}</span>
                <span className="shrink-0 text-muted-foreground">
                  {event.client_listing_id ?? "—"}
                </span>
                <span className="shrink-0 text-muted-foreground">
                  {formatWhen(event.received_at)}
                </span>
                <Badge variant={statusVariant(event.status)}>
                  {STATUS_LABEL[event.status] ?? event.status}
                </Badge>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="flex items-center justify-between border-t border-dashed border-border pt-3">
        <p className="text-xs text-muted-foreground">
          Reprocessa leads já recebidos que ainda não viraram registros.
        </p>
        <Button
          variant="outline"
          size="sm"
          onClick={runBackfill}
          disabled={backfill.isPending}
          data-testid="olx-backfill"
        >
          {backfill.isPending ? "Processando…" : "Reprocessar"}
        </Button>
      </div>
    </div>
  );
}

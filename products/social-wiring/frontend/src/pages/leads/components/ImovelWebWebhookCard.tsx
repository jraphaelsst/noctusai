/**
 * ImovelWebWebhookCard — operational health for the ImovelWeb / OpenNavent
 * lead pipe.
 *
 * Answers, in the order an operator asks:
 *   1. is anything stuck? (`unresolved` / `error` — a real enquiry nobody
 *      has been told about)
 *   2. is the callback registered, and is it subscribed to anything?
 *   3. is the registered URL still ours?
 *   4. are leads arriving by the fast path, or are we pulling them?
 *
 * (2) and (3) are the job the OLX card does not have, and they matter more
 * than they look. The registration is INTEGRATOR-WIDE — one bad write
 * redirects every agency's leads at once — and both of its failure modes
 * are silent: a wrong URL means the vendor believes it delivered, and an
 * empty subscription list means it never sends anything at all. Neither
 * produces an error anywhere, so this card is the only place they surface.
 *
 * (4) is the early-warning signal. The vendor allows 1.5 seconds to answer;
 * miss it and the leads still arrive, just pulled by reconciliation
 * instead. A rising reconcile share is what that looks like from outside.
 */
import { useMemo, useState } from "react";
import { AlertTriangle, CheckCircle2, Copy, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { Skeleton } from "@noctusai/lib/design-system";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  useImovelWebBackfill,
  useImovelWebCallbackConfig,
  useImovelWebEvents,
  useImovelWebReconcile,
  useRegisterImovelWebCallback,
  type ImovelWebLeadEvent,
} from "@/hooks/useImovelWebLeads";

const RECEIVER_PATH = "/api/portals/imovelweb/leads";

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

export default function ImovelWebWebhookCard() {
  const {
    events,
    counts,
    stuck,
    bySource,
    reconcileShare,
    loading,
    isEmpty,
    isError,
    error,
    refetch,
  } = useImovelWebEvents(50);
  const callback = useImovelWebCallbackConfig();
  const register = useRegisterImovelWebCallback();
  const backfill = useImovelWebBackfill();
  const reconcile = useImovelWebReconcile();
  const [copied, setCopied] = useState(false);

  const receiverUrl = useMemo(
    () => `${window.location.origin}${RECEIVER_PATH}`,
    [],
  );

  const registeredUrl = callback.config?.url ?? null;
  // Only a MISMATCH is a problem. "Not registered yet" is a different
  // state, and colouring it red would make first-time setup look broken.
  const urlMismatch =
    !!registeredUrl && registeredUrl.replace(/\/$/, "") !== receiverUrl;

  const copyUrl = async () => {
    try {
      await navigator.clipboard.writeText(receiverUrl);
      setCopied(true);
      toast.success("URL copiada.");
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.error("Não foi possível copiar. Selecione e copie manualmente.");
    }
  };

  const runRegister = async () => {
    // The blast radius is named in the prompt, not buried in a tooltip:
    // this configuration has no agency code, so it moves everyone's leads.
    const confirmed = window.confirm(
      "Registrar o receptor no ImovelWeb?\n\n" +
        "Esta configuração é ÚNICA para toda a integração — não existe " +
        "código de imobiliária nesta chamada. Ela afeta TODAS as " +
        "imobiliárias autorizadas ao mesmo tempo.",
    );
    if (!confirmed) return;
    try {
      const result = await register.mutateAsync({});
      if (result.drift?.length) {
        toast.warning(
          `Registrado, mas o portal gravou algo diferente: ${result.drift[0]}`,
        );
      } else {
        toast.success("Receptor registrado e confirmado na leitura de volta.");
      }
    } catch {
      toast.error("Não foi possível registrar. Verifique as credenciais.");
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

  const runReconcile = async () => {
    try {
      const result = await reconcile.mutateAsync();
      toast.success(
        result.recovered > 0
          ? `${result.recovered} lead(s) recuperado(s) do portal.`
          : "Nenhum lead pendente — o webhook está entregando tudo.",
      );
    } catch {
      toast.error("A reconciliação falhou. Verifique as credenciais.");
    }
  };

  return (
    <div
      className="rounded-lg border border-border p-4 space-y-4"
      data-testid="imovelweb-webhook-card"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold">ImovelWeb / Wimoveis (OpenNavent)</h3>
          <p className="text-xs text-muted-foreground">
            Integração direta com o portal — diferente do Grupo OLX, e é ela
            que identifica de qual portal veio cada lead.
          </p>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => refetch()}
          data-testid="imovelweb-refresh"
          aria-label="Atualizar"
        >
          <RefreshCw className="h-4 w-4" />
        </Button>
      </div>

      {/* ── 1. Stuck first: the only thing that needs someone to act. ── */}
      {stuck.length > 0 && (
        <div
          className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm"
          data-testid="imovelweb-stuck-banner"
        >
          <AlertTriangle className="mt-0.5 h-4 w-4 text-destructive" />
          <div>
            <p className="font-medium">{stuck.length} lead(s) aguardando atenção</p>
            <p className="text-xs text-muted-foreground">
              &quot;Sem cliente&quot; significa que o lead chegou mas não foi
              possível identificar de qual imobiliária ele é — ele fica guardado
              até alguém definir, nunca é atribuído por suposição.
            </p>
          </div>
        </div>
      )}

      {/* ── 2. The registration. Both failures here are silent. ── */}
      <div className="space-y-2 rounded-md border border-dashed border-border p-3">
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs font-medium text-muted-foreground">
            Registro do callback (afeta todas as imobiliárias)
          </span>
          <Button
            variant="outline"
            size="sm"
            onClick={runRegister}
            disabled={register.isPending}
            data-testid="imovelweb-register"
          >
            {register.isPending ? "Registrando…" : "Registrar / Atualizar"}
          </Button>
        </div>

        {callback.loading ? (
          // The testid goes on the wrapper, not on `Skeleton` — the
          // design-system component does not forward arbitrary props, and
          // a testid that silently vanishes makes the test assert nothing.
          <div data-testid="imovelweb-callback-loading">
            <Skeleton className="h-12 w-full" />
          </div>
        ) : callback.isError ? (
          <p
            className="text-xs text-muted-foreground"
            data-testid="imovelweb-callback-error"
          >
            Não foi possível consultar o portal. Isso não significa que o
            registro está errado — apenas que não conseguimos lê-lo agora.
          </p>
        ) : callback.isUnregistered ? (
          <p
            className="text-xs text-muted-foreground"
            data-testid="imovelweb-callback-unregistered"
          >
            Nenhum receptor registrado ainda. Enquanto isso, o portal não envia
            nada.
          </p>
        ) : (
          <div className="space-y-1.5 text-xs" data-testid="imovelweb-callback-config">
            {callback.deliversNothing ? (
              <div
                className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/5 p-2"
                data-testid="imovelweb-no-subscriptions"
              >
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 text-destructive" />
                <span>
                  <strong>Nenhum evento assinado — nada será entregue.</strong>{" "}
                  O portal aceita esta configuração e simplesmente não envia
                  nada, sem gerar erro em lugar nenhum.
                </span>
              </div>
            ) : (
              <div className="flex flex-wrap gap-1.5" data-testid="imovelweb-subscriptions">
                {callback.subscriptions.map((eventName) => (
                  <Badge key={eventName} variant="secondary">
                    {eventName}
                  </Badge>
                ))}
              </div>
            )}

            {urlMismatch && (
              <div
                className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/5 p-2"
                data-testid="imovelweb-url-mismatch"
              >
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 text-destructive" />
                <span>
                  <strong>URL registrada diferente da nossa.</strong> Os leads
                  estão indo para <code>{registeredUrl}</code>.
                </span>
              </div>
            )}

            <p className="text-muted-foreground">
              Idioma do corpo: <code>{callback.config?.lenguajeCallbackBody ?? "—"}</code>
              {" · "}
              Cabeçalho: <code>{callback.config?.authorizationHeaderKey ?? "—"}</code>
            </p>
          </div>
        )}

        <div className="flex items-center gap-2">
          <code
            className="flex-1 truncate rounded-md bg-muted px-2 py-1.5 text-xs"
            data-testid="imovelweb-receiver-url"
          >
            {receiverUrl}
          </code>
          <Button
            variant="outline"
            size="sm"
            onClick={copyUrl}
            data-testid="imovelweb-copy-url"
          >
            <Copy className="mr-1 h-3.5 w-3.5" />
            {copied ? "Copiado" : "Copiar"}
          </Button>
        </div>
      </div>

      {/* ── 3. Deliveries. ── */}
      {loading ? (
        <div className="space-y-2" data-testid="imovelweb-events-loading">
          <Skeleton className="h-4 w-40" />
          <Skeleton className="h-16 w-full" />
        </div>
      ) : isError ? (
        <div
          className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm"
          data-testid="imovelweb-events-error"
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
          data-testid="imovelweb-events-empty"
        >
          Nenhuma entrega recebida ainda. Confirme acima que o receptor está
          registrado e com eventos assinados.
        </div>
      ) : (
        <div className="space-y-3" data-testid="imovelweb-events-success">
          {stuck.length === 0 && (
            <div
              className="flex items-center gap-2 text-sm text-muted-foreground"
              data-testid="imovelweb-healthy"
            >
              <CheckCircle2 className="h-4 w-4 text-emerald-600" />
              Todas as entregas recentes foram processadas.
            </div>
          )}

          <div className="flex flex-wrap gap-1.5" data-testid="imovelweb-status-counts">
            {Object.entries(counts).map(([status, count]) => (
              <Badge key={status} variant={statusVariant(status)}>
                {STATUS_LABEL[status] ?? status}: {count}
              </Badge>
            ))}
          </div>

          {/* The early-warning signal — see the module header. */}
          {reconcileShare !== null && (
            <p
              className="text-xs text-muted-foreground"
              data-testid="imovelweb-source-split"
            >
              Entregas: {bySource.callback} por webhook, {bySource.reconcile} por
              reconciliação
              {reconcileShare > 0.2 && (
                <strong className="text-destructive">
                  {" "}
                  — muitas recuperadas; o receptor pode estar lento demais para o
                  limite de 1,5s do portal.
                </strong>
              )}
            </p>
          )}

          <ul className="space-y-1.5" data-testid="imovelweb-events-list">
            {events.slice(0, 8).map((event: ImovelWebLeadEvent) => (
              <li
                key={event.id}
                className="flex items-center justify-between gap-2 text-xs"
              >
                <span className="truncate font-mono">{event.id}</span>
                <span className="shrink-0 text-muted-foreground">
                  {event.lead_origin ?? "—"}
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

      <div className="flex items-center justify-between gap-2 border-t border-dashed border-border pt-3">
        <p className="text-xs text-muted-foreground">
          Reconciliar busca no portal os leads que o webhook não entregou.
        </p>
        <div className="flex shrink-0 gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={runReconcile}
            disabled={reconcile.isPending}
            data-testid="imovelweb-reconcile"
          >
            {reconcile.isPending ? "Buscando…" : "Reconciliar"}
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={runBackfill}
            disabled={backfill.isPending}
            data-testid="imovelweb-backfill"
          >
            {backfill.isPending ? "Processando…" : "Reprocessar"}
          </Button>
        </div>
      </div>
    </div>
  );
}

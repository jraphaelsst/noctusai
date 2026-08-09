/**
 * LeadgenWebhookCard — Meta Lead-Ads webhook subscription management.
 *
 * Lead delivery needs TWO separate subscriptions, and this card exists
 * because either one alone delivers leads to nobody, silently:
 *
 *   1. App-level  — the operator ticks `leadgen` on the Page object in the
 *      Meta App Dashboard. No code can do this; `verify_token_configured`
 *      only reports whether OUR side of that click's GET handshake
 *      (`META_WEBHOOK_VERIFY_TOKEN`) is ready.
 *   2. Page-level — `POST /{page_id}/subscribed_apps` per Page. Automated
 *      by the backend; this card drives it.
 *
 * `last_received_at === null` in the delivery-health block is the single
 * most diagnostic signal in the whole feature: it means Meta has NEVER
 * called our webhook, i.e. the App-Dashboard half isn't configured yet.
 */
import { useState } from "react";

/** Sentinel for "no client" in the <select>. A DOM select cannot hold `null`,
 *  and "" is indistinguishable from "nothing chosen yet". */
const UNATTRIBUTED = "__none__";
import { Check, Copy, Info, Loader2, ShieldAlert, Webhook } from "lucide-react";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  useLeadgenEvents,
  useLeadgenSubscriptions,
  useSubscribeLeadgenPages,
  useUnsubscribeLeadgenPage,
  type LeadgenPageSubscription,
  type LeadgenSubscribeResult,
  useSetPageMarca,
} from "@/hooks/useMetaLeadgen";
import { useMarcas } from "@/hooks/useMarcas";
import { AdsError, AdsLoading } from "./adsShared";

const STATUS_LABEL: Record<string, string> = {
  received: "Recebidos",
  processed: "Processados",
  error: "Erros",
  unresolved: "Não resolvidos",
  ignored: "Ignorados",
};

function formatDateTime(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return `${d.toLocaleDateString("pt-BR")} ${d.toLocaleTimeString("pt-BR", {
    hour: "2-digit",
    minute: "2-digit",
  })}`;
}

/** Inline copy-to-clipboard — checked `noctus.dev.find_reusable_component`
 *  first (best match scored 0.44, "shelfware"/"emerging" with zero-to-few
 *  consumers, none clipboard-shaped); every existing copy affordance in the
 *  codebase (AdminApiKeys, AdminWebhooks) is this same inline
 *  `navigator.clipboard.writeText` + icon-button shape, so this mirrors
 *  established convention rather than inventing a new one. */
function CopyButton({ value }: { value: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <Button
      type="button"
      variant="outline"
      size="sm"
      onClick={() => {
        navigator.clipboard.writeText(value);
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      }}
      data-testid="leadgen-copy-callback-url"
    >
      {copied ? (
        <Check className="mr-1.5 h-3.5 w-3.5" />
      ) : (
        <Copy className="mr-1.5 h-3.5 w-3.5" />
      )}
      {copied ? "Copiado" : "Copiar"}
    </Button>
  );
}

/** One Page's subscribe/unsubscribe row — owns its own mutation + inline
 *  error state so ONE Page's failure never blocks or gets confused with
 *  another Page's or the bulk action's outcome. */
function PageRow({ page }: { page: LeadgenPageSubscription }) {
  const subscribe = useSubscribeLeadgenPages();
  const unsubscribe = useUnsubscribeLeadgenPage();
  const setClient = useSetPageMarca();
  const { data: marcas = [] } = useMarcas();
  const [rowError, setRowError] = useState<string | null>(null);
  const busy = subscribe.isPending || unsubscribe.isPending;

  const onSubscribe = () => {
    setRowError(null);
    subscribe.mutate([page.page_id], {
      onSuccess: (res) => {
        const r = res.results[0];
        if (r && !r.ok) setRowError(r.error ?? "Falha ao inscrever a Página.");
      },
      onError: (e) => setRowError((e as Error).message),
    });
  };
  const onUnsubscribe = () => {
    setRowError(null);
    unsubscribe.mutate(page.page_id, {
      onSuccess: (r) => {
        if (!r.ok) setRowError(r.error ?? "Falha ao desinscrever a Página.");
      },
      onError: (e) => setRowError((e as Error).message),
    });
  };

  return (
    <div
      className="rounded-lg border px-4 py-3"
      data-testid={`leadgen-page-row-${page.page_id}`}
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <span className="truncate font-medium">
            {page.page_name || page.page_id}
          </span>
          <Badge
            variant="outline"
            className={
              page.subscribed
                ? "border-emerald-500/30 bg-emerald-500/15 text-emerald-600"
                : "border-muted-foreground/30 text-muted-foreground"
            }
          >
            {page.subscribed ? "Inscrita" : "Não inscrita"}
          </Badge>
        </div>
        <Button
          variant={page.subscribed ? "outline" : "default"}
          size="sm"
          disabled={busy}
          onClick={page.subscribed ? onUnsubscribe : onSubscribe}
        >
          {busy && <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />}
          {page.subscribed ? "Desinscrever" : "Inscrever"}
        </Button>
      </div>
      {/* Client attribution — the key that decides WHICH client's recipients
          get alerted for this Page's leads (migration 045). Unattributed is a
          legitimate state, not an error: those leads reach the org-wide tier
          rather than nobody. It is stated plainly so the operator can see that
          per-client routing is not yet in effect for this Page. */}
      <div className="mt-2 flex flex-wrap items-center gap-2 border-t pt-2">
        <span className="text-xs text-muted-foreground">Cliente:</span>
        <select
          className="h-8 rounded-md border bg-background px-2 text-xs"
          aria-label={`Cliente da página ${page.page_name || page.page_id}`}
          value={page.marca_id ?? UNATTRIBUTED}
          disabled={setClient.isPending}
          onChange={(e) => {
            setRowError(null);
            setClient.mutate(
              {
                pageId: page.page_id,
                marcaId: e.target.value === UNATTRIBUTED ? null : e.target.value,
              },
              { onError: (err) => setRowError((err as Error).message) },
            );
          }}
        >
          <option value={UNATTRIBUTED}>Sem cliente (alertas gerais)</option>
          {marcas.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
        {setClient.isPending && (
          <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />
        )}
        {/* A Page whose forms disagree is real — a form that synced after the
            assignment carries NULL and still routes to the org tier. Showing
            only the majority would hide exactly that. */}
        {typeof page.forms_total === "number" && page.forms_total > 0 &&
          page.forms_attributed !== page.forms_total && (
            <span className="text-xs text-amber-600">
              {page.forms_attributed}/{page.forms_total} formulários atribuídos —
              os demais usam os alertas gerais
            </span>
          )}
      </div>
      {rowError && (
        <p className="mt-1.5 text-xs text-destructive">{rowError}</p>
      )}
    </div>
  );
}

/** Bulk-subscribe result: NEVER collapsed to a blanket success/error. Always
 *  states the N-of-M count, and lists every named per-Page failure. */
function BulkResultsSummary({
  results,
  pages,
}: {
  results: LeadgenSubscribeResult[];
  pages: LeadgenPageSubscription[];
}) {
  const failed = results.filter((r) => !r.ok);
  const okCount = results.length - failed.length;
  const nameFor = (pageId: string) =>
    pages.find((p) => p.page_id === pageId)?.page_name || pageId;

  return (
    <div
      className="rounded-md border bg-muted/30 p-3 text-sm"
      data-testid="leadgen-bulk-results"
    >
      <p className={failed.length === 0 ? "text-emerald-600" : "font-medium"}>
        {okCount} de {results.length} página(s) inscrita(s)
        {failed.length === 0 ? " com sucesso." : "."}
      </p>
      {failed.length > 0 && (
        <ul className="mt-1.5 space-y-1 text-xs text-muted-foreground">
          {failed.map((r) => (
            <li key={r.page_id}>
              <span className="font-medium text-foreground">
                {nameFor(r.page_id)}:
              </span>{" "}
              {r.error ?? "falha desconhecida"}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** Delivery health — the counts + the diagnostic `last_received_at`. Its own
 *  loading/error handling is intentionally small: this is a secondary panel
 *  and must never block the subscription controls above it. */
function DeliveryHealth() {
  const eventsQ = useLeadgenEvents(20);

  if (eventsQ.isPending || eventsQ.isFetching) {
    return (
      <p className="text-sm text-muted-foreground" data-testid="leadgen-health-loading">
        Carregando saúde da entrega…
      </p>
    );
  }
  if (eventsQ.isError) {
    return (
      <p className="text-sm text-destructive" data-testid="leadgen-health-error">
        Não foi possível carregar o histórico de entregas do webhook.
      </p>
    );
  }
  const d = eventsQ.data;
  if (!d) return null;
  const statuses = Object.entries(d.counts);
  const total = statuses.reduce((acc, [, n]) => acc + n, 0);

  return (
    <div className="space-y-2" data-testid="leadgen-delivery-health">
      <p className="text-sm font-medium">Saúde da entrega</p>
      {d.last_received_at === null ? (
        <p className="text-sm text-amber-600" data-testid="leadgen-never-received">
          A Meta nunca chamou este webhook — normalmente significa que a
          inscrição do App (Painel da Meta) ainda não foi configurada.
          Confira o handshake usando a URL de callback abaixo.
        </p>
      ) : (
        <p className="text-sm text-muted-foreground">
          Último evento recebido: {formatDateTime(d.last_received_at)}
        </p>
      )}
      {/* Leads landing correctly with nobody configured to hear about it is
          a silent failure: the list fills up, nothing errors, and the absence
          of a WhatsApp message is indistinguishable from a quiet day. It
          happened in production on 2026-08-04 (two real leads, zero alerts),
          so it is stated here rather than left to be noticed. */}
      {d.notification_recipients_active === 0 && (
        <p className="text-sm text-amber-600" data-testid="leadgen-no-recipients">
          ⚠️ Nenhum destinatário de notificação ativo — os leads estão sendo
          salvos, mas <strong>ninguém está sendo avisado</strong>. Cadastre um
          destinatário em Configuração → Configurações.
        </p>
      )}
      {total > 0 ? (
        <div className="flex flex-wrap gap-2">
          {statuses.map(([status, n]) => (
            <Badge key={status} variant="secondary" className="font-mono">
              {(STATUS_LABEL[status] ?? status)}: {n}
            </Badge>
          ))}
        </div>
      ) : (
        <p className="text-xs text-muted-foreground">
          Nenhum evento registrado ainda.
        </p>
      )}
    </div>
  );
}

export default function LeadgenWebhookCard() {
  const subsQ = useLeadgenSubscriptions();
  const bulkSubscribe = useSubscribeLeadgenPages();
  const [bulkResults, setBulkResults] = useState<LeadgenSubscribeResult[] | null>(
    null,
  );

  if (subsQ.isPending || subsQ.isFetching) {
    return <AdsLoading label="Carregando inscrições do webhook…" />;
  }
  if (subsQ.isError) {
    return (
      <AdsError
        message="Não foi possível carregar as inscrições do webhook de leads."
        onRetry={() => subsQ.refetch()}
      />
    );
  }

  const s = subsQ.data;
  if (!s) return null; // defensive only — queryFn never resolves undefined.

  const onBulkSubscribe = () => {
    setBulkResults(null);
    bulkSubscribe.mutate(null, {
      onSuccess: (res) => setBulkResults(res.results),
    });
  };

  return (
    <Card data-testid="leadgen-webhook-card">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Webhook className="h-4 w-4 text-muted-foreground" />
          Webhook de leads (Meta)
        </CardTitle>
        <CardDescription>
          Duas inscrições são necessárias para os leads chegarem
          automaticamente: a do App (feita no Painel da Meta) e a de cada
          Página (feita aqui). As duas juntas entregam os leads — nenhuma
          delas sozinha entrega qualquer coisa, e a falta é silenciosa.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        {s.gated && (
          <div
            className="flex items-start gap-3 rounded-lg border border-amber-500/30 bg-amber-500/5 p-4 text-sm"
            data-testid="leadgen-gated-banner"
          >
            <Info className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
            <div>
              <div className="font-medium">Requer permissão adicional</div>
              <p className="text-muted-foreground">{s.reason}</p>
            </div>
          </div>
        )}

        {!s.verify_token_configured && (
          <div
            className="flex items-start gap-3 rounded-lg border border-dashed p-4 text-sm"
            data-testid="leadgen-not-configured-banner"
          >
            <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" />
            <div>
              <div className="font-medium">
                Verificação do webhook não configurada
              </div>
              <p className="text-muted-foreground">
                O handshake com a Meta não pode ser concluído até a variável{" "}
                <code className="font-mono">META_WEBHOOK_VERIFY_TOKEN</code>{" "}
                ser configurada no backend. A inscrição das Páginas abaixo
                continua funcionando normalmente — só a verificação inicial
                no Painel da Meta fica bloqueada até essa variável ser
                definida.
              </p>
            </div>
          </div>
        )}

        <div className="space-y-1.5">
          <p className="text-sm font-medium">URL de callback</p>
          <div className="flex flex-wrap items-center gap-2">
            <code className="min-w-0 flex-1 truncate rounded bg-muted px-3 py-1.5 text-xs">
              {s.callback_url || "—"}
            </code>
            <CopyButton value={s.callback_url} />
          </div>
          <p className="text-xs text-muted-foreground">
            Cole esta URL no campo "URL de retorno de chamada" ao configurar
            o Webhook de leads no Painel da Meta — necessária mesmo antes da
            verificação estar pronta.
          </p>
        </div>

        <DeliveryHealth />

        <div className="space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm font-medium">Páginas ({s.pages.length})</p>
            {s.pages.length > 0 && (
              <Button
                variant="outline"
                size="sm"
                disabled={bulkSubscribe.isPending}
                onClick={onBulkSubscribe}
                data-testid="leadgen-subscribe-all-btn"
              >
                {bulkSubscribe.isPending && (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                )}
                Assinar todas as páginas
              </Button>
            )}
          </div>
          {bulkSubscribe.isError && (
            <p className="text-xs text-destructive">
              {(bulkSubscribe.error as Error)?.message ??
                "Falha ao inscrever as páginas."}
            </p>
          )}
          {bulkResults && (
            <BulkResultsSummary results={bulkResults} pages={s.pages} />
          )}
          {s.pages.length === 0 ? (
            <p
              className="py-6 text-center text-sm text-muted-foreground"
              data-testid="leadgen-pages-empty"
            >
              Nenhuma Página do Facebook conectada.
            </p>
          ) : (
            <div className="space-y-2">
              {s.pages.map((p) => (
                <PageRow key={p.page_id} page={p} />
              ))}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

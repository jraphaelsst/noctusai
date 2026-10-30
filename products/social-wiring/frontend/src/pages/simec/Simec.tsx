/**
 * SIMEC — Inteligência de marketing (Instagram).
 *
 * Contract: products/social-wiring/projects/marketing-intelligence/specs/simec-api-contract.md
 * Route `/simec`, status_pagina `simec` (migration 284, seeded `desenvolvimento`).
 *
 * Two tabs over the same profile selection:
 *   Leitura       — profile selector, latest/previous readouts, "Gerar leitura".
 *   Configuração  — org + profile override layers (owner/admin edit, others read).
 *
 * Every empty state from the contract is explicit: no Instagram connected
 * (today's reality — links to where the connection is made), reconnect
 * needed, no readout yet, no content in the period, demo data.
 */
import { useState } from "react";
import { Link } from "react-router-dom";
import { BarChart3, Instagram, Loader2, RefreshCw, ShieldAlert } from "lucide-react";
import { ErrorState, FormError, Select, Skeleton, useIsOrgAdmin } from "@noctusai/lib/design-system";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useStartProviderOAuth } from "@/hooks/useIntegrationAccounts";
import {
  useComputeSimecReadout,
  useSimecAccounts,
  useSimecConfig,
  useSimecLatestReadout,
  useSimecReadout,
  useSimecReadouts,
} from "@/hooks/useSimec";
import {
  accountLabel,
  isDemo,
  needsReconnect,
  simecErrorMessage,
  type SimecAccount,
} from "@/lib/simec";
import { useActiveAccountId, useActiveAccountStore } from "@/state/useActiveAccount";

import { SimecConfigEditor } from "./SimecConfigEditor";
import { DemoBanner, SimecReadoutView } from "./SimecReadoutView";

/** Where an Instagram connection is created (MarcaModal › Contas). */
export const INSTAGRAM_CONNECT_HREF = "/marcas";
/** The org's Instagram page (Meta dashboard, Instagram network). */
export const INSTAGRAM_PAGE_HREF = "/meta";

const PROVIDER = "instagram";

function NoInstagramConnected() {
  return (
    <Card>
      <CardContent className="flex flex-col items-center gap-3 p-8 text-center" data-testid="simec-no-instagram">
        <Instagram className="h-7 w-7 text-muted-foreground" />
        <div className="text-base font-medium">Conecte o Instagram desta conta para usar o SIMEC</div>
        <p className="max-w-xl text-sm text-muted-foreground">
          O SIMEC lê as métricas diárias das publicações do Instagram conectado. Conecte o perfil em
          Marcas (aba Contas → “Conectar Instagram”); depois da primeira sincronização, gere a leitura aqui.
          A configuração do SIMEC já pode ser ajustada na aba Configuração.
        </p>
        <div className="flex flex-wrap justify-center gap-2">
          <Button asChild size="sm">
            <Link to={INSTAGRAM_CONNECT_HREF} data-testid="simec-connect-link">
              Conectar Instagram
            </Link>
          </Button>
          <Button asChild size="sm" variant="outline">
            <Link to={INSTAGRAM_PAGE_HREF} data-testid="simec-instagram-page-link">
              Abrir página do Instagram
            </Link>
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function ReconnectBanner({ account }: { account: SimecAccount }) {
  const oauth = useStartProviderOAuth(PROVIDER);
  return (
    <div
      role="alert"
      data-testid="simec-reconnect"
      className="flex flex-wrap items-center gap-3 rounded-md border border-warning/40 bg-warning/10 p-3 text-sm"
    >
      <ShieldAlert className="h-4 w-4 shrink-0 text-warning-foreground" />
      <p className="flex-1">
        {account.insights_scope_granted
          ? "A conexão deste perfil precisa ser renovada para continuar sincronizando as métricas."
          : "Este perfil foi conectado sem a permissão de métricas do Instagram. Reconecte para liberar os dados do SIMEC."}
      </p>
      <Button
        size="sm"
        disabled={oauth.isPending}
        onClick={() => oauth.mutate({ marcaId: account.marca_id ?? undefined })}
        data-testid="simec-reconnect-button"
      >
        {oauth.isPending && <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />}
        Reconectar Instagram
      </Button>
    </div>
  );
}

function ReadoutSection({ account }: { account: SimecAccount }) {
  const accountId = account.account_id;
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const configQ = useSimecConfig(accountId);
  const reviews = Object.entries(configQ.data?.config.cadence?.reviews ?? {});
  const [cadence, setCadence] = useState<string>("mensal");
  const effectiveCadence = reviews.some(([k]) => k === cadence) ? cadence : (reviews[0]?.[0] ?? cadence);

  const latestQ = useSimecLatestReadout(accountId);
  const listQ = useSimecReadouts(accountId);
  const pickedQ = useSimecReadout(selectedId);
  const compute = useComputeSimecReadout(accountId);

  const active = selectedId ? pickedQ : latestQ;
  const readout = selectedId ? pickedQ.data : latestQ.data?.readout;
  const history = listQ.data?.items ?? [];

  const generate = () =>
    compute.mutate({ cadence: effectiveCadence }, { onSuccess: () => setSelectedId(null) });

  const controls = (
    <div className="flex flex-wrap items-end gap-3">
      <label className="flex flex-col gap-1 text-xs">
        Período da leitura
        <Select
          value={effectiveCadence}
          onChange={(e) => setCadence(e.target.value)}
          aria-label="Período da leitura"
          className="w-56"
          data-testid="simec-cadence"
          disabled={reviews.length === 0}
        >
          {reviews.length === 0 ? (
            <option value={effectiveCadence}>{effectiveCadence}</option>
          ) : (
            reviews.map(([k, r]) => (
              <option key={k} value={k}>
                {r.label} ({r.every_days} dias)
              </option>
            ))
          )}
        </Select>
      </label>
      <Button size="sm" onClick={generate} disabled={compute.isPending} data-testid="simec-generate">
        {compute.isPending ? <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" /> : <BarChart3 className="mr-2 h-3.5 w-3.5" />}
        Gerar leitura
      </Button>
      {history.length > 0 && (
        <label className="flex flex-col gap-1 text-xs">
          Leituras anteriores
          <Select
            value={selectedId ?? ""}
            onChange={(e) => setSelectedId(e.target.value || null)}
            aria-label="Leituras anteriores"
            className="w-72"
            data-testid="simec-history"
          >
            <option value="">Mais recente</option>
            {history.map((h) => (
              <option key={h.id} value={h.id}>
                {h.period_start} a {h.period_end} · {h.config_version}
              </option>
            ))}
          </Select>
        </label>
      )}
      {active.isRefreshing && <RefreshCw className="h-4 w-4 animate-spin text-muted-foreground" aria-label="Atualizando" />}
    </div>
  );

  let body: React.ReactNode;
  if (active.showSkeleton) {
    body = (
      <div className="space-y-2" data-testid="simec-readout-skeleton">
        <Skeleton className="h-6 w-1/2" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  } else if (active.error && !readout) {
    body = <ErrorState message={simecErrorMessage(active.error, selectedId ? "leitura" : "conta")} />;
  } else if (!readout) {
    body = (
      <Card>
        <CardContent className="flex flex-col items-center gap-2 p-8 text-center text-sm" data-testid="simec-no-readout">
          <div className="font-medium">Nenhuma leitura ainda</div>
          <p className="text-muted-foreground">
            Gere a primeira leitura deste perfil: o SIMEC calcula os indicadores das publicações do período
            e os compara com o histórico do próprio perfil.
          </p>
          <Button size="sm" onClick={generate} disabled={compute.isPending} data-testid="simec-generate-empty">
            Gerar leitura
          </Button>
        </CardContent>
      </Card>
    );
  } else {
    body = <SimecReadoutView readout={readout} />;
  }

  return (
    <div className="space-y-4">
      {controls}
      <FormError message={compute.isError ? simecErrorMessage(compute.error, "conta") : null} />
      {body}
    </div>
  );
}

export default function Simec() {
  const isAdmin = useIsOrgAdmin();
  const accountsQ = useSimecAccounts();
  const storedId = useActiveAccountId(PROVIDER);
  const setActiveAccount = useActiveAccountStore((s) => s.setActiveAccount);

  const data = accountsQ.data;
  const accounts = data?.accounts ?? [];
  const account = accounts.find((a) => a.account_id === storedId) ?? accounts[0] ?? null;

  let leitura: React.ReactNode;
  if (accountsQ.showSkeleton) {
    leitura = (
      <div className="space-y-2" data-testid="simec-accounts-skeleton">
        <Skeleton className="h-9 w-72" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  } else if (accountsQ.error && !data) {
    leitura = <ErrorState message={simecErrorMessage(accountsQ.error, "conta")} />;
  } else if (!account) {
    leitura = <NoInstagramConnected />;
  } else {
    leitura = (
      <div className="space-y-4">
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-xs">
            Perfil
            <Select
              value={account.account_id}
              onChange={(e) => setActiveAccount(PROVIDER, e.target.value)}
              aria-label="Perfil"
              className="w-72"
              data-testid="simec-profile"
            >
              {accounts.map((a) => (
                <option key={a.account_id} value={a.account_id}>
                  {accountLabel(a)}
                </option>
              ))}
            </Select>
          </label>
          <span className="text-xs text-muted-foreground">
            {account.last_synced_at
              ? `Última sincronização: ${new Date(account.last_synced_at).toLocaleString("pt-BR", { timeZone: "America/Sao_Paulo" })}`
              : "Ainda não sincronizado"}
          </span>
        </div>
        {needsReconnect(account) && <ReconnectBanner account={account} />}
        <ReadoutSection key={account.account_id} account={account} />
      </div>
    );
  }

  return (
    <div className="space-y-4 p-6" data-testid="simec-page">
      <div className="flex flex-wrap items-center gap-2">
        <div>
          <h1 className="text-2xl font-semibold">SIMEC</h1>
          <p className="text-sm text-muted-foreground">
            Inteligência de marketing do Instagram: indicadores por janela, comparados com o histórico do
            próprio perfil. Métrica que a plataforma não fornece aparece como “não disponível”, nunca estimada.
          </p>
        </div>
        {accountsQ.isRefreshing && <RefreshCw className="ml-auto h-4 w-4 animate-spin text-muted-foreground" aria-label="Atualizando" />}
      </div>

      {isDemo(data?.metrics_source) && <DemoBanner />}

      <Tabs defaultValue="leitura">
        <TabsList>
          <TabsTrigger value="leitura">Leitura</TabsTrigger>
          <TabsTrigger value="config" data-testid="simec-tab-config">
            Configuração
          </TabsTrigger>
        </TabsList>
        <TabsContent value="leitura" className="pt-4">
          {leitura}
        </TabsContent>
        <TabsContent value="config" className="pt-4">
          <SimecConfigEditor
            accountId={account?.account_id ?? null}
            accountName={account ? accountLabel(account) : null}
            canEdit={isAdmin}
          />
        </TabsContent>
      </Tabs>
    </div>
  );
}

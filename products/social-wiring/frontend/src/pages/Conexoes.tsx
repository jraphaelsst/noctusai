/**
 * Conexoes — unified connections page.
 *
 * Sections:
 *   1. WhatsApp  — reuses WhatsAppConnections from Conexao.tsx (WAHA sessions)
 *   2. Per-provider — one section per integration provider (YouTube, Meta, n8n…)
 *      pulled from useIntegrationProviders. Each provider section uses
 *      ProviderSection from Integrations.tsx.
 *
 * YouTube on-mount adopt-legacy: fires once so a pre-existing single-account
 * YouTube credential automatically becomes a default integration account.
 *
 * Handles ?account_created=<id> query param from the OAuth callback: shows a
 * success toast + clears the param.
 *
 * All four states per section: loading / empty / error / success.
 */
import { useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { Link2, Loader2, Plug, Smartphone } from "lucide-react";

import { Separator } from "@/components/ui/separator";
import { Button } from "@/components/ui/button";

import { WhatsAppConnections } from "@/pages/Conexao";
import { ProviderSection } from "@/pages/Integrations";
import {
  useIntegrationProviders,
  useIntegrationAccounts,
  useAdoptLegacy,
  useStartYouTubeOAuth,
} from "@/hooks/useIntegrationAccounts";

// ─── YouTube section (custom — OAuth button + adopt-legacy on mount) ──────────

function YouTubeSection() {
  const { data: accounts = [], isLoading: accountsLoading } = useIntegrationAccounts("youtube");
  const adopt = useAdoptLegacy("youtube");
  const oauthStart = useStartYouTubeOAuth();

  // Adopt-legacy once on mount: idempotent — promotes legacy single-account
  // cred to a proper default integration account if one exists.
  useEffect(() => {
    adopt.mutate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function handleConnect() {
    oauthStart.mutate(undefined, {
      onError: (e: any) =>
        toast.error("Falha ao iniciar conexao com o YouTube", {
          description: e?.message ?? "Tente novamente",
        }),
    });
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-muted-foreground uppercase tracking-wide">
          YouTube
        </h3>
        <Button
          size="sm"
          variant="outline"
          onClick={handleConnect}
          disabled={oauthStart.isPending}
        >
          {oauthStart.isPending ? (
            <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
          ) : (
            <Link2 className="mr-1.5 h-3.5 w-3.5" />
          )}
          Conectar canal do YouTube
        </Button>
      </div>

      {accountsLoading ? (
        <div className="flex items-center gap-2 py-4 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Carregando contas YouTube...
        </div>
      ) : accounts.length === 0 ? (
        <div className="rounded-md border border-dashed bg-muted/20 py-6 text-center text-sm text-muted-foreground">
          Nenhuma conta YouTube conectada. Use o botao acima para autorizar um canal.
        </div>
      ) : (
        <div className="space-y-2">
          {accounts.map((acc) => (
            <div
              key={acc.id}
              className="flex items-center justify-between gap-4 rounded-lg border bg-card p-3"
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 text-sm font-medium">
                  {(acc.metadata?.channel_title as string) ?? acc.account_label}
                  {acc.is_default && (
                    <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-medium text-primary">
                      Padrao
                    </span>
                  )}
                </div>
                {acc.metadata?.channel_id && (
                  <p className="truncate text-xs text-muted-foreground font-mono">
                    {acc.metadata.channel_id as string}
                  </p>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Other providers section ─────────────────────────────────────────────────

function OtherProvidersSection() {
  const { data: providers = [], isLoading, isError } = useIntegrationProviders();

  // Filter out YouTube — it has a dedicated section above
  const otherProviders = providers.filter((p) => p.id !== "youtube");

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 py-4 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        Carregando provedores...
      </div>
    );
  }

  if (isError) {
    return (
      <p className="py-4 text-sm text-destructive">
        Erro ao carregar provedores. Tente recarregar a pagina.
      </p>
    );
  }

  if (otherProviders.length === 0) {
    return null;
  }

  return (
    <div className="space-y-4">
      {otherProviders.map((p) => (
        <ProviderSection key={p.id} providerConfig={p} />
      ))}
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function Conexoes() {
  const [searchParams, setSearchParams] = useSearchParams();

  // Handle OAuth callback: ?account_created=<id> → success toast + clear param
  useEffect(() => {
    const accountId = searchParams.get("account_created");
    if (accountId) {
      toast.success("Canal conectado com sucesso!");
      const next = new URLSearchParams(searchParams);
      next.delete("account_created");
      setSearchParams(next, { replace: true });
    }
  }, [searchParams, setSearchParams]);

  return (
    <div className="space-y-8">
      {/* Page header */}
      <div className="flex items-center gap-3">
        <Plug className="h-6 w-6 text-primary" />
        <div>
          <h1 className="text-2xl font-bold text-foreground">Conexoes</h1>
          <p className="text-sm text-muted-foreground">
            Gerencie todas as suas conexoes: WhatsApp (WAHA), YouTube e outros provedores.
          </p>
        </div>
      </div>

      {/* WhatsApp section */}
      <section className="space-y-4">
        <div className="flex items-center gap-2">
          <Smartphone className="h-5 w-5 text-muted-foreground" />
          <h2 className="text-lg font-semibold">WhatsApp</h2>
        </div>
        <WhatsAppConnections />
      </section>

      <Separator />

      {/* YouTube section */}
      <section className="space-y-4">
        <YouTubeSection />
      </section>

      {/* Other providers section (Meta, n8n, Google Drive, Gmail…) */}
      <OtherProvidersSection />
    </div>
  );
}

/**
 * OAuthStatusPage — Google Calendar OAuth status + reconnect.
 *
 * Shows connection state + token expiry; "Reconnect" button initiates the OAuth
 * redirect to backend `/oauth/google/init`.
 */
import { useOAuthStatus, redirectToOAuthInit } from "@/hooks/useOAuthStatus";
import { Link2, Loader2, CheckCircle2, AlertCircle, RefreshCw } from "lucide-react";

function formatExpiry(expires_at?: string | null): { label: string; isExpired: boolean } {
  if (!expires_at) return { label: "—", isExpired: false };
  try {
    const d = new Date(expires_at);
    const now = Date.now();
    const isExpired = d.getTime() < now;
    return {
      label: d.toLocaleString("pt-BR"),
      isExpired,
    };
  } catch {
    return { label: expires_at, isExpired: false };
  }
}

export default function OAuthStatusPage() {
  const { data, isLoading, error, refetch, isFetching } = useOAuthStatus();

  const status = data;
  const connected = !!status?.connected;
  const expiry = formatExpiry(status?.expires_at);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <Link2 className="h-6 w-6 text-primary" />
          <div>
            <h1 className="text-2xl font-bold text-foreground">Google Calendar</h1>
            <p className="text-sm text-muted-foreground">
              Status da conexão OAuth e renovação de credenciais.
            </p>
          </div>
        </div>
        <button
          className="inline-flex items-center gap-2 rounded-md border border-border bg-background px-3 py-2.5 text-sm font-medium text-foreground hover:bg-muted/50 transition-colors disabled:opacity-50"
          onClick={() => refetch()}
          disabled={isFetching}
        >
          {isFetching ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <RefreshCw className="h-4 w-4" />
          )}
          Atualizar
        </button>
      </div>

      {/* Body */}
      {isLoading ? (
        <div className="flex flex-col items-center justify-center py-20 gap-3">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
          <p className="text-sm text-muted-foreground">Verificando status...</p>
        </div>
      ) : error ? (
        <div className="rounded-lg border border-destructive/40 bg-destructive/10 p-4 text-sm text-destructive">
          Erro ao verificar status OAuth.
        </div>
      ) : (
        <div className="rounded-lg border border-border bg-card p-6 space-y-6">
          {/* Status row */}
          <div className="flex items-start gap-4">
            {connected ? (
              <CheckCircle2 className="h-6 w-6 text-green-600 dark:text-green-400 shrink-0 mt-0.5" />
            ) : (
              <AlertCircle className="h-6 w-6 text-yellow-600 dark:text-yellow-400 shrink-0 mt-0.5" />
            )}
            <div className="flex-1 space-y-1">
              <h2 className="text-lg font-semibold text-foreground">
                {connected ? "Conectado" : "Não conectado"}
              </h2>
              <p className="text-sm text-muted-foreground">
                {connected
                  ? "O Media Scheduling pode criar e atualizar eventos no Google Calendar."
                  : "Conecte uma conta Google para que o agendador possa publicar eventos no calendário."}
              </p>
              {status?.account_email && (
                <p className="text-sm text-foreground">
                  <span className="text-muted-foreground">Conta: </span>
                  <span className="font-medium">{status.account_email}</span>
                </p>
              )}
            </div>
          </div>

          {/* Detail grid */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 border-t border-border pt-4">
            <div>
              <dt className="text-xs uppercase tracking-wide text-muted-foreground">
                Expira em
              </dt>
              <dd
                className={`text-sm font-medium ${
                  expiry.isExpired ? "text-destructive" : "text-foreground"
                }`}
              >
                {expiry.label}
                {expiry.isExpired && (
                  <span className="ml-2 inline-flex rounded-full bg-red-100 px-2 py-0.5 text-xs font-medium text-red-800 dark:bg-red-900/30 dark:text-red-400">
                    Expirado
                  </span>
                )}
              </dd>
            </div>
            {status?.last_error && (
              <div>
                <dt className="text-xs uppercase tracking-wide text-muted-foreground">
                  Último erro
                </dt>
                <dd className="text-sm text-destructive">{status.last_error}</dd>
              </div>
            )}
          </div>

          {/* Action */}
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-end border-t border-border pt-4">
            <p className="text-xs text-muted-foreground sm:mr-auto">
              Reconectar redireciona para a tela de consentimento do Google.
            </p>
            <button
              className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
              onClick={redirectToOAuthInit}
            >
              <Link2 className="h-4 w-4" />
              {connected ? "Reconectar" : "Conectar Google Calendar"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

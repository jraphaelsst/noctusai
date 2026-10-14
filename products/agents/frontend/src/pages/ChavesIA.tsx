/**
 * Chaves de IA — `/chaves-ia` (org owner/admin; writes are admin-gated
 * server-side by `api_keys_router`).
 *
 * The org's LLM provider keys (`openai_api_key`, `anthropic_api_key`) that a
 * `runtime='llm'` agent (Julia / `lead-imob`) resolves per turn. Consumes the
 * canonical seed `ApiKeysPanel` organ — status, set/replace, Testar, remove —
 * over `/api/settings/api-keys`; nothing is re-implemented here.
 */
import { KeyRound, ShieldAlert } from "lucide-react";
import { ApiKeysPanel } from "@noctusai/lib/components";
import { orgApiKeysHooks } from "@/hooks/useOrgApiKeys";
import { useIsAdmin } from "@/hooks/useIsAdmin";

export default function ChavesIA() {
  const isAdmin = useIsAdmin();

  return (
    <div className="space-y-4" data-testid="chaves-ia-page">
      <div className="flex items-center gap-3">
        <KeyRound className="h-6 w-6 text-primary" />
        <div>
          <h1 className="text-2xl font-bold text-foreground">Chaves de IA</h1>
          <p className="text-sm text-muted-foreground">
            Chaves do provedor de IA desta organização, usadas pelos agentes (ex.: Julia nos canais). O valor é
            enviado uma única vez e nunca é exibido de volta.
          </p>
        </div>
      </div>

      {isAdmin ? (
        <ApiKeysPanel hooks={orgApiKeysHooks} title="Provedores de IA" />
      ) : (
        <div
          className="flex items-center gap-2 rounded-lg border border-border bg-card p-6 text-sm text-muted-foreground"
          role="alert"
          data-testid="chaves-ia-forbidden"
        >
          <ShieldAlert className="h-5 w-5 text-destructive" />
          Apenas administradores da organização gerenciam as chaves de IA.
        </div>
      )}
    </div>
  );
}

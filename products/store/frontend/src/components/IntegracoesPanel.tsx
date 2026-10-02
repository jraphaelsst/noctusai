/**
 * "Integrações" — payment credentials stored via the DB (contract §6 / A10).
 *
 * Consumes the canonical seed organ `<ApiKeysPanel/>` + `createApiKeysHooks`
 * against the seed router mounted at `/api/settings/api-keys*` (asaas_api_key,
 * asaas_webhook_token, asaas_environment). Values are write-only: the panel only
 * ever shows the masked `hint` and the `source` tier. Rendered inside `/admin`,
 * which already shows "Sem acesso" for a non-admin, so the panel never mounts for one.
 */
import { useState } from "react";
import { toast } from "sonner";
import { Copy } from "lucide-react";
import { ApiKeysPanel } from "@noctusai/lib/components";
import { Button, Card } from "@noctusai/lib/design-system";
import { getApiKeysHooks } from "@/lib/api";

export const WEBHOOK_PATH = "/api/webhooks/asaas";

export function WebhookUrl() {
  const [url] = useState(() => `${window.location.origin}${WEBHOOK_PATH}`);
  async function copy() {
    try {
      await navigator.clipboard.writeText(url);
      toast.success("URL copiada.");
    } catch {
      toast.error("Não foi possível copiar. Selecione e copie manualmente.");
    }
  }
  return (
    <div className="space-y-1">
      <p className="text-sm font-medium">URL do webhook (cole no Asaas)</p>
      <div className="flex items-center gap-2">
        <code data-testid="webhook-url" className="flex-1 break-all rounded bg-muted px-2 py-1.5 text-xs">{url}</code>
        <Button variant="outline" size="sm" onClick={copy} aria-label="Copiar URL do webhook">
          <Copy className="mr-1 h-3.5 w-3.5" /> Copiar
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">
        No Asaas, use o mesmo token cadastrado acima em "Token do webhook". Os valores nunca são exibidos aqui, só os 4 últimos caracteres.
      </p>
    </div>
  );
}

export function IntegracoesPanel() {
  return (
    <Card className="space-y-4" data-testid="integracoes">
      <ApiKeysPanel hooks={getApiKeysHooks()} title="Integrações · Asaas" />
      <WebhookUrl />
    </Card>
  );
}

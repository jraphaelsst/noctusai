/**
 * Org LLM provider keys — `/api/settings/api-keys` (openai_api_key /
 * anthropic_api_key, admin-gated server-side). The seed `createApiKeysHooks`
 * factory + `ApiKeysPanel` organ do all the work; this file only binds the
 * factory to this product's `api` client and exposes the status query so the
 * Canais tab can hint "chave do provedor configurada?".
 */
import { createApiKeysHooks, type ApiKeysStatus } from "@noctusai/lib/components";
import { api } from "@/lib/api";

export const orgApiKeysHooks = createApiKeysHooks(api);

/** Which key a studio provider needs. */
export const PROVIDER_KEY: Record<string, string> = {
  anthropic: "anthropic_api_key",
  openai: "openai_api_key",
};

export function isProviderKeyConfigured(status: ApiKeysStatus | undefined, provider: string): boolean | undefined {
  if (!status) return undefined;
  const wanted = PROVIDER_KEY[provider];
  return status.items.find((k) => k.key === wanted)?.configured;
}

/**
 * WhatsApp connection hooks for Orbity — the SEED contract
 * (`/api/whatsapp/connections*`) consumed through `createWhatsAppConnectionsHooks`.
 *
 * `useWhatsAppConnectionState` derives the single signal the Automação page
 * needs: is this org's WhatsApp really connected (paired)?
 */
import { createWhatsAppConnectionsHooks } from "@noctusai/lib/components";
import { api } from "@/lib/api";

export const waHooks = createWhatsAppConnectionsHooks(api);

export type WhatsAppConnectionState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "disconnected" }
  | { kind: "connected"; label: string; number: string | null; session: string };

export function useWhatsAppConnectionState(): WhatsAppConnectionState {
  const conns = waHooks.useConnections();
  const lines = conns.data ?? [];
  const first = lines[0] ?? null;
  const status = waHooks.useConnectionStatus(first?.id ?? null, !!first);

  if (conns.showSkeleton) return { kind: "loading" };
  if (conns.error && !conns.data) return { kind: "error", message: conns.error.message };
  if (!first) return { kind: "disconnected" };
  if (!status.data) {
    if (status.error) return { kind: "error", message: status.error.message };
    return { kind: "loading" };
  }
  if (!status.data.paired) return { kind: "disconnected" };
  const meId = status.data.me_id;
  return {
    kind: "connected",
    label: first.label,
    number: meId ? meId.replace(/@.*$/, "") : (status.data.me_name ?? null),
    session: status.data.session || first.session_name,
  };
}

/**
 * Multi-session WhatsApp (WAHA) connection hooks.
 *
 * Wraps the product `/api/whatsapp/connections` router (per-user "lines"):
 * list/create/update/delete + per-line live ops (status / QR / start /
 * restart / logout / webhook). One line = one WAHA server URL + session +
 * API key; the API key is write-only (encrypted at rest, never returned).
 *
 * Built on @tanstack/react-query (v5) directly — same engine the seed
 * single-session hooks use, here for the multi-line surface. queryFns never
 * return undefined (B3 TanStack contract).
 */
import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";

// ─── Types (mirror app/schemas/whatsapp_connection.py) ──────────────────────
export interface WhatsAppConnectionLine {
  id: string;
  label: string;
  /** Derived by the backend; read-only in the UI. */
  base_url: string;
  /** Derived by the backend; read-only in the UI. */
  session_name: string;
  /** Derived public webhook URL returned by the backend on create/update. */
  webhook_url: string | null;
  created_at: string;
  updated_at: string;
}

export interface WhatsAppConnectionStatus {
  connection_id: string;
  status: string | null;
  paired: boolean;
  me_id: string | null;
  me_name: string | null;
  session: string;
  error: string | null;
}

export interface WhatsAppConnectionQr {
  connection_id: string;
  scannable: boolean;
  status: string | null;
  png_base64: string | null;
}

/**
 * Create payload — backend derives session_name, base_url, and webhook_url.
 * Only label + api_key are user-supplied.
 */
export interface CreateConnectionBody {
  label: string;
  api_key: string;
}

/**
 * Update payload — only the user-editable fields: label and optionally a new
 * api_key (write-only; omit to leave unchanged).
 * base_url, session_name, and webhook_url are backend-derived; not sent.
 */
export interface UpdateConnectionBody {
  label?: string;
  api_key?: string;
}

export interface WebhookResult {
  connection_id: string;
  ok: boolean;
  url: string;
  events: string[];
  status: string | null;
}

const BASE = "/api/whatsapp/connections";
const KEY = ["whatsapp", "connections"] as const;

// ─── Listing ────────────────────────────────────────────────────────────────
export function useWhatsAppConnections() {
  return useQuery<WhatsAppConnectionLine[]>({
    queryKey: KEY,
    queryFn: () => api.get<WhatsAppConnectionLine[]>(BASE),
  });
}

export function useWhatsAppConnectionMutations() {
  const qc = useQueryClient();
  const invalidate = () => qc.invalidateQueries({ queryKey: KEY });

  const create = useMutation<WhatsAppConnectionLine, unknown, CreateConnectionBody>({
    mutationFn: (body) => api.post<WhatsAppConnectionLine>(BASE, body),
    onSuccess: invalidate,
  });

  const update = useMutation<
    WhatsAppConnectionLine,
    unknown,
    { id: string; body: UpdateConnectionBody }
  >({
    mutationFn: ({ id, body }) =>
      api.patch<WhatsAppConnectionLine>(`${BASE}/${id}`, body),
    onSuccess: invalidate,
  });

  const remove = useMutation<unknown, unknown, string>({
    mutationFn: (id) => api.delete(`${BASE}/${id}`),
    onSuccess: invalidate,
  });

  return { create, update, remove };
}

// ─── Per-line live state ─────────────────────────────────────────────────────
/**
 * Live session status for one line. Polls while not paired so the UI reflects
 * the QR→pairing→WORKING transition; backs off once paired.
 */
export function useWhatsAppConnectionStatus(
  connectionId: string | null,
  enabled = true,
  options?: { pollMs?: number },
) {
  return useQuery<WhatsAppConnectionStatus>({
    queryKey: [...KEY, connectionId, "status"],
    queryFn: () =>
      api.get<WhatsAppConnectionStatus>(`${BASE}/${connectionId}/status`),
    enabled: enabled && !!connectionId,
    refetchInterval: (query) => {
      const data = query.state.data as WhatsAppConnectionStatus | undefined;
      if (data?.paired) return false;
      return options?.pollMs ?? 5000;
    },
  });
}

/**
 * Live QR for one line. Only fetched while the caller asks (unpaired); polls
 * so a rotated QR refreshes, stops once a scan completes (scannable false).
 */
export function useWhatsAppConnectionQr(
  connectionId: string | null,
  enabled: boolean,
  options?: { pollMs?: number },
) {
  return useQuery<WhatsAppConnectionQr>({
    queryKey: [...KEY, connectionId, "qr"],
    queryFn: () =>
      api.get<WhatsAppConnectionQr>(`${BASE}/${connectionId}/qr`),
    enabled: enabled && !!connectionId,
    refetchInterval: (query) => {
      const data = query.state.data as WhatsAppConnectionQr | undefined;
      if (data && !data.scannable) return false;
      return options?.pollMs ?? 8000;
    },
  });
}

export function useWhatsAppConnectionActions() {
  const qc = useQueryClient();
  const invalidate = (id: string) => {
    qc.invalidateQueries({ queryKey: [...KEY, id, "status"] });
    qc.invalidateQueries({ queryKey: [...KEY, id, "qr"] });
  };

  const start = useMutation<WhatsAppConnectionStatus, unknown, string>({
    mutationFn: (id) =>
      api.post<WhatsAppConnectionStatus>(`${BASE}/${id}/start`),
    onSuccess: (_d, id) => invalidate(id),
  });

  const restart = useMutation<WhatsAppConnectionStatus, unknown, string>({
    mutationFn: (id) =>
      api.post<WhatsAppConnectionStatus>(`${BASE}/${id}/restart`),
    onSuccess: (_d, id) => invalidate(id),
  });

  const logout = useMutation<WhatsAppConnectionStatus, unknown, string>({
    mutationFn: (id) =>
      api.post<WhatsAppConnectionStatus>(`${BASE}/${id}/logout`),
    onSuccess: (_d, id) => invalidate(id),
  });

  const configureWebhook = useMutation<
    WebhookResult,
    unknown,
    { id: string; url: string }
  >({
    mutationFn: ({ id, url }) =>
      api.post<WebhookResult>(`${BASE}/${id}/webhook`, { url }),
    onSuccess: (_d, { id }) => invalidate(id),
  });

  return { start, restart, logout, configureWebhook };
}

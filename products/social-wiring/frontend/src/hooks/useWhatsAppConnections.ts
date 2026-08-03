/**
 * Multi-session WhatsApp (WAHA) connection hooks.
 *
 * Wraps the product `/api/whatsapp/connections` router (per-user "lines"):
 * list/create/update/delete + per-line live ops (status / QR / start /
 * restart / logout / webhook). One line = one WAHA server URL + session +
 * API key; the API key is write-only on every path EXCEPT the explicit,
 * owner-scoped reveal (`useRevealApiKey` → GET /{id}/api-key), used only by the
 * eye toggle in the connection modal.
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
  /**
   * Whether the IA auto-reply is enabled for this connection.
   * Defaults to false. Toggled via PUT /api/whatsapp/connections/{id}/auto-reply.
   */
  auto_reply_enabled: boolean;
  /**
   * Allowlist of E.164 numbers permitted to trigger auto-reply / workflows.
   * Empty array = ALL numbers are allowed.
   */
  authorized_numbers: string[];
  /**
   * Chats whose inbound messages are relayed. Each entry carries the WAHA
   * chat_id (JID) plus a human-readable label.
   * Empty array = ALL chats are listened.
   */
  bound_chats: { chat_id: string; label: string }[];
}

/**
 * Chat summary returned by GET /api/whatsapp/connections/{id}/chats.
 * `contact` is the display name; `chat_id` is the WAHA JID used as the key.
 */
export interface ChatSummary {
  chat_id: string;
  contact: string;
  last_message: string;
  last_message_at: string | null;
  last_direction: string;
  unread: number;
  contact_id: string | null;
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
 * Only label + api_key are user-supplied. `client_id` is optional; when
 * supplied the new connection is immediately owned by that cliente.
 */
export interface CreateConnectionBody {
  label: string;
  api_key: string;
  /** Assign to a cliente on creation. */
  client_id?: string | null;
}

/**
 * Update payload — user-editable fields.
 * - label: human-readable name
 * - api_key: write-only rotation (omit to leave unchanged)
 * - authorized_numbers: E.164 allowlist — [] means "all numbers"
 * - bound_chats: listened chat list — [] means "all chats"
 * base_url, session_name, and webhook_url are backend-derived; not sent.
 */
export interface UpdateConnectionBody {
  label?: string;
  api_key?: string;
  authorized_numbers?: string[];
  bound_chats?: { chat_id: string; label: string }[];
}

export interface WebhookResult {
  connection_id: string;
  ok: boolean;
  url: string;
  events: string[];
  status: string | null;
}

/** Decrypted API key for one line — returned ONLY by the reveal endpoint. */
export interface ApiKeyReveal {
  connection_id: string;
  api_key: string;
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

/**
 * Reveal the decrypted API key for one line on demand (eye toggle in the
 * modal). Modelled as a mutation so the plaintext secret is NEVER persisted in
 * the react-query cache — it lives only in the caller's local state while shown.
 */
export function useRevealApiKey() {
  return useMutation<ApiKeyReveal, unknown, string>({
    mutationFn: (id) => api.get<ApiKeyReveal>(`${BASE}/${id}/api-key`),
  });
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
      // 🔴 Only a session that is actually PAIRED has nothing left to scan.
      //
      // This previously returned false on ANY `!scannable` response — but
      // STOPPED / STARTING / FAILED are precisely the transient states you
      // must poll THROUGH to reach SCAN_QR_CODE. The result was that a single
      // non-scannable reply killed the poll permanently: on 2026-08-03 the
      // live server logged /auth/qr hit exactly twice in 35 minutes while
      // /status was hit every 5s, and the panel sat on a frozen
      // "Aguardando QR (STOPPED)" forever.
      //
      // WORKING is the only terminal state here. Everything else keeps polling.
      if (data?.status === "WORKING") return false;
      return options?.pollMs ?? 3000;
    },
  });
}

/**
 * Recover a stuck session — the escalation ladder (`start` → `restart` →
 * `logout` + `start`).
 *
 * Why this exists rather than just calling `restart`: a session that still
 * holds credentials WhatsApp has invalidated will retry those dead credentials
 * on restart, hang in STARTING, and get force-stopped by WAHA's watchdog ~5
 * minutes later — proven twice in the production logs on 2026-08-03. Only
 * clearing the credentials produces a QR. The ladder converges regardless of
 * which rung is individually correct for the current state.
 */
export function useRecoverConnection() {
  const qc = useQueryClient();
  return useMutation<WhatsAppConnectionStatus, unknown, string>({
    mutationFn: (connectionId: string) =>
      api.post<WhatsAppConnectionStatus>(`${BASE}/${connectionId}/recover`, {}),
    onSuccess: (_data, connectionId) => {
      qc.invalidateQueries({ queryKey: [...KEY, connectionId, "status"] });
      qc.invalidateQueries({ queryKey: [...KEY, connectionId, "qr"] });
    },
  });
}

/**
 * Chats available for a given connection line. Used to populate the bound-chats
 * picker. Enabled only when a connectionId is provided; never fetches eagerly.
 * Each ChatSummary: `contact` = display label, `chat_id` = WAHA JID key.
 */
export function useConnectionChats(connectionId: string | null) {
  return useQuery<ChatSummary[]>({
    queryKey: [...KEY, connectionId, "chats"],
    queryFn: () =>
      api.get<ChatSummary[]>(`${BASE}/${connectionId}/chats`),
    enabled: !!connectionId,
    staleTime: 30_000,
  });
}

/**
 * Toggle the IA auto-reply flag for one connection.
 * Uses PUT /api/whatsapp/connections/{id}/auto-reply with { enabled: boolean }.
 * Invalidates the connections list so the card reflects the new value.
 */
export function useToggleAutoReply() {
  const qc = useQueryClient();
  return useMutation<WhatsAppConnectionLine, unknown, { id: string; enabled: boolean }>({
    mutationFn: ({ id, enabled }) =>
      api.put<WhatsAppConnectionLine>(`${BASE}/${id}/auto-reply`, { enabled }),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}

// ─── Client-scoped connections ───────────────────────────────────────────────
/**
 * List WhatsApp connections owned by a specific cliente.
 * Maps to GET /api/whatsapp/connections?client_id=<id>.
 * Used by the ClienteModal Chat tab + Contas tab to resolve WA connections.
 */
export function useClientWhatsAppConnections(clientId: string | null) {
  return useQuery<WhatsAppConnectionLine[]>({
    queryKey: [...KEY, "client", clientId],
    queryFn: () =>
      api.get<WhatsAppConnectionLine[]>(`${BASE}?client_id=${encodeURIComponent(clientId!)}`),
    enabled: !!clientId,
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

/**
 * WhatsApp connection-admin + intake-monitor hooks for NoctusAI products.
 *
 * Two seed hook factories, same injection pattern as `createLLMHooks`
 * (the product passes its own authenticated `createApiClient()`):
 *
 * - `createWhatsAppConnectionsHooks` wraps the MULTI-connection
 *   `/api/whatsapp/connections/*` router (per-user "lines": one row =
 *   one WAHA server URL + session + API key) — any WhatsApp-chatbot
 *   product gets the whole multi-line pairing UX (list, create, update,
 *   delete, live status, QR scan, start/restart/logout, the
 *   start→restart→logout+start recovery ladder, and webhook wiring).
 *   Lifted 2026-09-17 from `products/social-wiring`
 *   (`hooks/useWhatsAppConnections.ts` +
 *   `backend/app/routers/whatsapp_connections_router.py`) as a PURE
 *   ADDITION — social-wiring keeps its own local copy for now.
 *   Reworked from the single-session `createWhatsAppConnectionHooks`
 *   (removed 2026-09-17): confirmed zero product imports of that name or
 *   of its backend, `whatsapp_admin_router.py` (grepped repo-wide before
 *   the rename — only the barrel re-export and an archived reference
 *   remained).
 * - `createWhatsAppIntakeHooks` wraps the intake/flow-monitor router
 *   (`/api/whatsapp/intake/conversations*`) — a read-only live window
 *   into WhatsApp conversation state + recent message history, plus the
 *   "cancel stuck flow" action. UNCHANGED — live consumer:
 *   `products/social-wiring/frontend/src/hooks/useWhatsAppIntake.ts`.
 *
 * Presentation (pt-BR labels, cards, polling cadence overrides) stays in
 * the product; this module is locale-agnostic. The multi-connection
 * factory has a sibling presentational organ family at
 * `./components/whatsapp-connections` (`WhatsAppConnectionsPage`,
 * `CreateConnectionDialog`, `ConnectionDetailDialog`).
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { ApiClient } from './api';

// ---------------------------------------------------------------------------
// Multi-connection types — mirror the backend DTOs
// (app/schemas/whatsapp_connection.py). Deliberately excludes the
// social-wiring-specific chatbot-intake extension fields
// (auto_reply_enabled / authorized_numbers / bound_chats / marca_id) — those
// are per-product routing config for SW's own chatbot feature, not part of
// generic WAHA connection-line management. A product that needs them can
// extend `WhatsAppConnectionLine` locally.
// ---------------------------------------------------------------------------

export interface WhatsAppConnectionLine {
  id: string;
  label: string;
  /** Derived server-side (the shared WAHA server URL); read-only. */
  base_url: string;
  /** Derived server-side (the WAHA session name this line drives); read-only. */
  session_name: string;
  /** Auto-minted public inbound webhook URL; read-only. */
  webhook_url: string | null;
  created_at: string;
  updated_at: string;
}

/**
 * Create payload — the backend derives `base_url` / `session_name` /
 * `webhook_url` server-side. Only `label` + `api_key` are user-supplied.
 */
export interface CreateWhatsAppConnectionBody {
  label: string;
  api_key: string;
}

/**
 * Update payload — all fields optional (omit to leave unchanged).
 * `api_key` is write-only rotation: re-supply only to rotate the stored key.
 */
export interface UpdateWhatsAppConnectionBody {
  label?: string;
  api_key?: string;
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

/** Converged state after the start→restart→logout+start recovery ladder. */
export interface WhatsAppConnectionRecoverResult {
  connection_id: string;
  status: string | null;
  paired: boolean;
  /** Which rung the ladder converged at: already_working / start / restart / logout_start. */
  stage: string;
}

export interface ConfigureWhatsAppConnectionWebhookBody {
  url: string;
  events?: string[];
}

export interface WhatsAppConnectionWebhookResult {
  connection_id: string;
  ok: boolean;
  url: string;
  events: string[];
  status: string | null;
}

// ---------------------------------------------------------------------------
// Intake-monitor types — mirror the backend DTOs (intake_monitor_router.py:
// IntakeConversationDTO / IntakeMessageDTO / IntakeConversationDetailDTO /
// IntakeCancelResult)
// ---------------------------------------------------------------------------

export interface IntakeConversation {
  session_id: string;
  state: string;
  product_code: string | null;
  drive_url: string | null;
  video_filename: string | null;
  video_format: string | null;
  candidate_count: number;
  active_uploads: number;
}

export interface IntakeMessage {
  direction: string;
  body: string;
  created_at: string | null;
  provider_message_id: string | null;
}

export interface IntakeConversationDetail {
  conversation: IntakeConversation;
  messages: IntakeMessage[];
}

export interface IntakeCancelResult {
  session_id: string;
  cleared: boolean;
}

// ---------------------------------------------------------------------------
// Multi-connection hook factory — takes an api client, returns bound hooks
// ---------------------------------------------------------------------------

export interface CreateWhatsAppConnectionsHooksOptions {
  /** Default `/api/whatsapp/connections`. */
  basePath?: string;
}

const DEFAULT_CONNECTIONS_BASE_PATH = '/api/whatsapp/connections';

export function createWhatsAppConnectionsHooks(
  api: ApiClient,
  options: CreateWhatsAppConnectionsHooksOptions = {},
) {
  const basePath = options.basePath ?? DEFAULT_CONNECTIONS_BASE_PATH;
  const KEY = ['whatsapp', 'connections', basePath] as const;

  /**
   * The list of connection lines. 🔴 TWO loading signals, never a bare
   * `isLoading`/`isFetching`: `showSkeleton` only on the first load,
   * `isRefreshing` for a quiet refetch over data already on screen (a
   * create/update/delete invalidates this query).
   */
  function useConnections() {
    const query = useQuery({
      queryKey: KEY,
      queryFn: () => api.get<WhatsAppConnectionLine[]>(basePath),
    });
    return {
      ...query,
      showSkeleton: query.isPending && !query.data,
      isRefreshing: query.isFetching && !!query.data,
    };
  }

  function useConnectionMutations() {
    const qc = useQueryClient();
    const invalidate = () => qc.invalidateQueries({ queryKey: KEY });

    const create = useMutation<
      WhatsAppConnectionLine,
      unknown,
      CreateWhatsAppConnectionBody
    >({
      mutationFn: (body) => api.post<WhatsAppConnectionLine>(basePath, body),
      onSuccess: invalidate,
    });

    const update = useMutation<
      WhatsAppConnectionLine,
      unknown,
      { id: string; body: UpdateWhatsAppConnectionBody }
    >({
      mutationFn: ({ id, body }) =>
        api.patch<WhatsAppConnectionLine>(
          `${basePath}/${encodeURIComponent(id)}`,
          body,
        ),
      onSuccess: invalidate,
    });

    const remove = useMutation<unknown, unknown, string>({
      mutationFn: (id) =>
        api.delete(`${basePath}/${encodeURIComponent(id)}`),
      onSuccess: invalidate,
    });

    return { create, update, remove };
  }

  /**
   * Live session status for one line. Polls while not paired so the UI
   * reflects the QR→pairing→WORKING transition without a manual refresh;
   * backs off once paired (status is then stable).
   */
  function useConnectionStatus(
    connectionId: string | null,
    enabled = true,
    options?: { pollMs?: number },
  ) {
    return useQuery<WhatsAppConnectionStatus>({
      queryKey: [...KEY, connectionId, 'status'],
      queryFn: () =>
        api.get<WhatsAppConnectionStatus>(
          `${basePath}/${encodeURIComponent(connectionId ?? '')}/status`,
        ),
      enabled: enabled && !!connectionId,
      refetchInterval: (query) => {
        const data = query.state.data as WhatsAppConnectionStatus | undefined;
        if (data?.paired) return false;
        return options?.pollMs ?? 5000;
      },
    });
  }

  /**
   * QR image (base64 PNG) for one line. Only fetched while `enabled`; polls
   * so a rotated QR refreshes. Only WORKING (paired) stops the poll — every
   * other status (STOPPED / STARTING / FAILED) is a transient the caller
   * must poll THROUGH to reach SCAN_QR_CODE.
   */
  function useConnectionQr(
    connectionId: string | null,
    enabled: boolean,
    options?: { pollMs?: number },
  ) {
    return useQuery<WhatsAppConnectionQr>({
      queryKey: [...KEY, connectionId, 'qr'],
      queryFn: () =>
        api.get<WhatsAppConnectionQr>(
          `${basePath}/${encodeURIComponent(connectionId ?? '')}/qr`,
        ),
      enabled: enabled && !!connectionId,
      refetchInterval: (query) => {
        const data = query.state.data as WhatsAppConnectionQr | undefined;
        if (data?.status === 'WORKING') return false;
        return options?.pollMs ?? 3000;
      },
    });
  }

  function useConnectionActions() {
    const qc = useQueryClient();
    const invalidate = (id: string) => {
      qc.invalidateQueries({ queryKey: [...KEY, id, 'status'] });
      qc.invalidateQueries({ queryKey: [...KEY, id, 'qr'] });
    };

    const start = useMutation<WhatsAppConnectionStatus, unknown, string>({
      mutationFn: (id) =>
        api.post<WhatsAppConnectionStatus>(
          `${basePath}/${encodeURIComponent(id)}/start`,
        ),
      onSuccess: (_d, id) => invalidate(id),
    });

    const restart = useMutation<WhatsAppConnectionStatus, unknown, string>({
      mutationFn: (id) =>
        api.post<WhatsAppConnectionStatus>(
          `${basePath}/${encodeURIComponent(id)}/restart`,
        ),
      onSuccess: (_d, id) => invalidate(id),
    });

    const logout = useMutation<WhatsAppConnectionStatus, unknown, string>({
      mutationFn: (id) =>
        api.post<WhatsAppConnectionStatus>(
          `${basePath}/${encodeURIComponent(id)}/logout`,
        ),
      onSuccess: (_d, id) => invalidate(id),
    });

    return { start, restart, logout };
  }

  /**
   * The start→restart→logout+start recovery ladder. Primary reconnect
   * action: a session holding stored-but-dead credentials answers
   * `restart` by retrying those dead credentials and hangs in STARTING
   * until WAHA's watchdog force-stops it; only `logout` clears the stored
   * credentials so NOWEB can re-enter SCAN_QR_CODE. `start`/`restart`/
   * `logout` remain individually callable via `useConnectionActions`.
   */
  function useRecoverConnection() {
    const qc = useQueryClient();
    return useMutation<WhatsAppConnectionRecoverResult, unknown, string>({
      mutationFn: (id) =>
        api.post<WhatsAppConnectionRecoverResult>(
          `${basePath}/${encodeURIComponent(id)}/recover`,
          {},
        ),
      onSuccess: (_data, id) => {
        qc.invalidateQueries({ queryKey: [...KEY, id, 'status'] });
        qc.invalidateQueries({ queryKey: [...KEY, id, 'qr'] });
      },
    });
  }

  function useConfigureConnectionWebhook() {
    const qc = useQueryClient();
    return useMutation<
      WhatsAppConnectionWebhookResult,
      unknown,
      { id: string; body: ConfigureWhatsAppConnectionWebhookBody }
    >({
      mutationFn: ({ id, body }) =>
        api.post<WhatsAppConnectionWebhookResult>(
          `${basePath}/${encodeURIComponent(id)}/webhook`,
          body,
        ),
      // Invalidates the whole list — a re-registered webhook can change
      // `webhook_url` on the line, which only the list/get shape carries.
      onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
    });
  }

  return {
    useConnections,
    useConnectionMutations,
    useConnectionStatus,
    useConnectionQr,
    useConnectionActions,
    useRecoverConnection,
    useConfigureConnectionWebhook,
  };
}

export type WhatsAppConnectionsHooks = ReturnType<
  typeof createWhatsAppConnectionsHooks
>;

// ---------------------------------------------------------------------------
// Intake-monitor hook factory — takes an api client, returns bound hooks
// ---------------------------------------------------------------------------

export function createWhatsAppIntakeHooks(api: ApiClient) {
  const KEY = ['whatsapp', 'intake'] as const;

  /**
   * Live conversation list. Polls so the monitor stays current without a
   * manual refresh; the backend already orders non-idle states first.
   */
  function useIntakeConversations(options?: { pollMs?: number }) {
    return useQuery<IntakeConversation[]>({
      queryKey: [...KEY, 'conversations'],
      queryFn: () => api.get('/api/whatsapp/intake/conversations'),
      refetchInterval: options?.pollMs ?? 5000,
    });
  }

  /**
   * One conversation's live state + recent message history. Only enabled
   * when a session is selected; polls so an in-flight flow stays current.
   */
  function useIntakeConversation(
    sessionId: string | null,
    options?: { pollMs?: number },
  ) {
    return useQuery<IntakeConversationDetail>({
      queryKey: [...KEY, 'conversation', sessionId],
      queryFn: () =>
        api.get(
          `/api/whatsapp/intake/conversations/${encodeURIComponent(
            sessionId ?? '',
          )}`,
        ),
      enabled: !!sessionId,
      refetchInterval: options?.pollMs ?? 5000,
    });
  }

  function useCancelConversation() {
    const qc = useQueryClient();
    return useMutation<IntakeCancelResult, unknown, string>({
      mutationFn: (sessionId) =>
        api.post(
          `/api/whatsapp/intake/conversations/${encodeURIComponent(
            sessionId,
          )}/cancel`,
        ),
      onSuccess: () => {
        qc.invalidateQueries({ queryKey: KEY });
      },
    });
  }

  return {
    useIntakeConversations,
    useIntakeConversation,
    useCancelConversation,
  };
}
